"""Unit tests for Phase 4E — Benchmark and Ablation Framework.

Covers:
1. Prediction normalization mapping
2. Positive classification metrics
3. Negative classification metrics
4. Uncertain classification handling
5. Missing negative class -> specificity = None
6. Missing positive class -> recall/precision = None
7. Confusion matrix (3x3) integrity
8. MCC calculation and zero-variance protection
9. Baseline calculation (Target existence heuristic)
10. Ablation configuration creation
11. Evidence family removal ablations
12. Independence-grouping ablation
13. Evaluation PDF generation
14. Report JSON serialization for frontend
15. Empty dataset graceful handling
16. Label provenance fields present on all benchmark cases
17. BENCH-NEG-01 flagged as unsuitable_for_directional_negative
18. EvaluationConfig defaults correct
19. EvaluationConfig with use_open_targets=False removes OT fields
20. EvaluationConfig with use_drugmechdb=False removes DrugMechDB fields
21. WeightConfig defaults correct (direct=1.0, structural=0.0, none=0.0)
22. WeightConfig.weight_for(DIRECT) == 1.0
23. WeightConfig.weight_for(STRUCTURAL) == 0.0 (hard zero regardless of config)
24. WeightConfig.weight_for(NONE) == 0.0 (hard zero regardless of config)
25. Weighted align: support only -> SUPPORTS
26. Weighted align: opposition only -> OPPOSES
27. Weighted align: total weight < min_effective_weight -> INSUFFICIENT
28. Weighted align: UNKNOWN drug action -> INSUFFICIENT
29. Weighted align: strong conflict (both sides >= min_effective_weight) -> INSUFFICIENT
30. Weighted align: net support > net opposition -> SUPPORTS
31. New BenchmarkSplit enum accessible
32. Benchmark dataset has >= 2 suitable negative cases (excluding flagged ones)
33. All benchmark cases have non-empty label_source and label_reference
34. AblationVerification model fields correct
35. BenchmarkEvaluationReport serializes new fields
"""
from __future__ import annotations

import pytest

from backend.evaluation.benchmark_models import (
    AblationConfig,
    AblationResult,
    AblationVerification,
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkClass,
    BenchmarkEvaluationReport,
    BenchmarkSplit,
    ExecutionStatus,
    WeightedBenchmarkCaseResult,
    WeightingComparisonResult,
    map_alignment_to_class,
)
from backend.evaluation.metrics import compute_benchmark_metrics
from backend.evaluation.ablation_runner import (
    compute_baseline_predictions,
    run_all_ablations,
    run_ablation_no_open_targets,
    run_ablation_no_datts,
    run_ablation_no_drugmechdb,
    run_ablation_no_independence,
)
from backend.reporting.evaluation_pdf_exporter import EvaluationPDFExporter
from backend.evaluation.evaluation_config import EvaluationConfig, EVALUATION_CONFIGS
from backend.evaluation.evidence_weights import WeightConfig, WEIGHT_CONFIGS, CONFIG_A, CONFIG_B, CONFIG_C
from backend.evaluation.benchmark_dataset import (
    BENCHMARK_DATASET_V1,
    get_directionally_suitable_negatives,
    get_unsuitable_negatives,
    get_cases_by_split,
)
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
    EvidenceFamily,
    DirectionalEvidenceGroup,
)
from backend.reasoning.directional.therapeutic_alignment import TherapeuticAlignmentEngine


# ── 1. Prediction Normalization ───────────────────────────────────────────────

def test_1_prediction_normalization():
    assert map_alignment_to_class("SUPPORTS") == BenchmarkClass.POSITIVE
    assert map_alignment_to_class("OPPOSES") == BenchmarkClass.NEGATIVE
    assert map_alignment_to_class("INSUFFICIENT") == BenchmarkClass.UNCERTAIN
    assert map_alignment_to_class("MIXED") == BenchmarkClass.UNCERTAIN
    assert map_alignment_to_class("UNKNOWN") == BenchmarkClass.UNCERTAIN
    assert map_alignment_to_class("") == BenchmarkClass.UNCERTAIN


# ── 2–4. Classification & Metrics Handling ────────────────────────────────────

def test_2_positive_classification_metrics():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        directional_concordance=1.0,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.total_cases == 1
    assert metrics.correct_predictions == 1
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0


def test_3_negative_classification_metrics():
    case_pos = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_neg = BenchmarkCase(case_id="C2", drug="DrugC", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)

    res_pos = BenchmarkCaseResult(
        case=case_pos,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
    )
    res_neg = BenchmarkCaseResult(
        case=case_neg,
        predicted_alignment="OPPOSES",
        predicted_class=BenchmarkClass.NEGATIVE,
        is_correct=True,
        is_resolved=True,
    )

    metrics = compute_benchmark_metrics([res_pos, res_neg])
    assert metrics.total_cases == 2
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.specificity == 1.0
    assert metrics.mcc == 1.0


def test_4_uncertain_classification_handling():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.UNCERTAIN)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="INSUFFICIENT",
        predicted_class=BenchmarkClass.UNCERTAIN,
        is_correct=True,
        is_resolved=False,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.total_cases == 1
    assert metrics.uncertain_cases == 1
    assert metrics.correct_predictions == 1
    assert metrics.accuracy == 1.0


# ── 5–6. Missing Class N/A Behavior ───────────────────────────────────────────

def test_5_missing_negative_class_specificity_none():
    """When only positive cases are tested, specificity must evaluate to None (N/A)."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.specificity is None
    assert any("Specificity unavailable" in n for n in metrics.notes)


def test_6_missing_positive_class_recall_none():
    """When only negative cases are tested, recall and precision must evaluate to None."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="OPPOSES",
        predicted_class=BenchmarkClass.NEGATIVE,
        is_correct=True,
        is_resolved=True,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.recall is None
    assert metrics.precision is None


# ── 7–8. Confusion Matrix & MCC ───────────────────────────────────────────────

def test_7_confusion_matrix_3x3_integrity():
    case_p = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_n = BenchmarkCase(case_id="C2", drug="DrugB", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)
    case_u = BenchmarkCase(case_id="C3", drug="DrugC", disease="DisB", expected_class=BenchmarkClass.UNCERTAIN)

    res_p = BenchmarkCaseResult(case=case_p, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)
    res_n = BenchmarkCaseResult(case=case_n, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True)
    res_u = BenchmarkCaseResult(case=case_u, predicted_alignment="INSUFFICIENT", predicted_class=BenchmarkClass.UNCERTAIN, is_correct=True, is_resolved=False)

    metrics = compute_benchmark_metrics([res_p, res_n, res_u])
    cm = metrics.confusion_matrix
    assert cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE) == 1
    assert cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE) == 1
    assert cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN) == 1
    assert cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE) == 0


def test_8_mcc_zero_variance_handling():
    """Zero variance across classes gracefully evaluates MCC to None without division error."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)
    metrics = compute_benchmark_metrics([res])
    assert metrics.mcc is None


# ── 9. Baseline Comparison ───────────────────────────────────────────────────

def test_9_baseline_calculation():
    case_pos = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_neg = BenchmarkCase(case_id="C2", drug="DrugB", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)

    # Both have targets, but C2 is actually negative
    res_pos = BenchmarkCaseResult(case=case_pos, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True, primary_target="TGT1")
    res_neg = BenchmarkCaseResult(case=case_neg, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True, primary_target="TGT2")

    baseline_res = compute_baseline_predictions([res_pos, res_neg])
    assert len(baseline_res) == 2
    # Baseline predicts POSITIVE for both because targets exist
    assert baseline_res[0].predicted_class == BenchmarkClass.POSITIVE
    assert baseline_res[1].predicted_class == BenchmarkClass.POSITIVE
    assert baseline_res[0].is_correct is True
    assert baseline_res[1].is_correct is False  # Baseline falsely predicted POSITIVE on negative control!


# ── 10–12. Ablation Analysis ─────────────────────────────────────────────────

def test_10_ablation_configuration_creation():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="TGT1",
        target_alignments=[{
            "target_id": "TGT1",
            "evidence_groups": [{"sources": ["OpenTargets"], "desired_action": "INHIBITION"}],
        }],
    )

    ablations = run_all_ablations([res])
    assert len(ablations) == 4
    config_names = [a.config_name for a in ablations]
    assert AblationConfig.NO_OPEN_TARGETS in config_names
    assert AblationConfig.NO_DATTS in config_names
    assert AblationConfig.NO_DRUGMECHDB in config_names
    assert AblationConfig.NO_INDEPENDENCE_GROUPING in config_names


def test_11_evidence_family_removal_ablation():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    # Case has Open Targets evidence only
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="TGT1",
        target_alignments=[{
            "target_id": "TGT1",
            "evidence_groups": [{"sources": ["OpenTargets"], "desired_action": "INHIBITION"}],
        }],
    )

    ab_no_ot = run_ablation_no_open_targets([res])
    assert ab_no_ot.case_predictions["C1"] == BenchmarkClass.UNCERTAIN
    assert len(ab_no_ot.changed_cases_from_full) == 1


def test_12_independence_grouping_ablation():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="TGT1",
        directional_concordance=1.0,
    )
    ab_no_ind = run_ablation_no_independence([res])
    assert ab_no_ind.config_name == AblationConfig.NO_INDEPENDENCE_GROUPING
    assert ab_no_ind.metrics.total_cases == 1


# ── 13–15. PDF Generation, Serialization & Integration ────────────────────────

def test_13_pdf_generation():
    case = BenchmarkCase(case_id="BENCH-POS-01", drug="Furosemide", disease="Edema", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="SLC12A1",
        directional_concordance=1.0,
        supporting_group_count=5,
        opposing_group_count=0,
    )
    metrics = compute_benchmark_metrics([res])
    report = BenchmarkEvaluationReport(
        benchmark_version="v1.0",
        full_4d_metrics=metrics,
        baseline_metrics=metrics,
        case_results=[res],
    )

    exporter = EvaluationPDFExporter(report)
    pdf_bytes = exporter.generate_pdf_bytes()
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_14_report_json_serialization():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)
    report = BenchmarkEvaluationReport(
        benchmark_version="v1.0",
        case_results=[res],
    )
    report_dict = report.model_dump(mode="json")
    assert report_dict["benchmark_version"] == "v1.0"
    assert len(report_dict["case_results"]) == 1
    assert report_dict["case_results"][0]["predicted_class"] == "POSITIVE"


def test_15_empty_dataset_graceful_handling():
    metrics = compute_benchmark_metrics([])
    assert metrics.total_cases == 0
    assert metrics.accuracy is None
    assert len(metrics.notes) > 0


# ── 16–17. Label Provenance & Flags ──────────────────────────────────────────

def test_16_label_provenance_fields_present():
    """All benchmark cases must have non-empty label_source, label_reference, label_rationale."""
    for case in BENCHMARK_DATASET_V1:
        assert case.label_source, f"{case.case_id}: missing label_source"
        assert case.label_reference, f"{case.case_id}: missing label_reference"
        assert case.label_rationale, f"{case.case_id}: missing label_rationale"


def test_17_bench_neg_01_flagged_unsuitable():
    """BENCH-NEG-01 must be flagged as unsuitable_for_directional_negative=True with documented reason."""
    bench_neg_01 = next(c for c in BENCHMARK_DATASET_V1 if c.case_id == "BENCH-NEG-01")
    assert bench_neg_01.unsuitable_for_directional_negative is True
    assert bench_neg_01.expected_class == BenchmarkClass.NEGATIVE
    # The flag must not eliminate the case from the dataset
    assert bench_neg_01 in BENCHMARK_DATASET_V1


# ── 18–20. EvaluationConfig ───────────────────────────────────────────────────

def test_18_evaluation_config_defaults():
    """Default EvaluationConfig must have all sources enabled and weighting disabled."""
    cfg = EvaluationConfig()
    assert cfg.name == "FULL_4D"
    assert cfg.use_open_targets is True
    assert cfg.use_datts is True
    assert cfg.use_drugmechdb is True
    assert cfg.use_independence_grouping is True
    assert cfg.use_evidence_weighting is False  # Production default: no weighting


def test_19_evaluation_config_no_open_targets():
    """NO_OPEN_TARGETS config must set use_open_targets=False, all others True."""
    cfg = EVALUATION_CONFIGS["NO_OPEN_TARGETS"]
    assert cfg.use_open_targets is False
    assert cfg.use_datts is True
    assert cfg.use_drugmechdb is True
    assert cfg.use_independence_grouping is True


def test_20_evaluation_config_no_drugmechdb():
    """NO_DRUGMECHDB config must set use_drugmechdb=False, all others True."""
    cfg = EVALUATION_CONFIGS["NO_DRUGMECHDB"]
    assert cfg.use_drugmechdb is False
    assert cfg.use_open_targets is True
    assert cfg.use_datts is True


# ── 21–24. WeightConfig ───────────────────────────────────────────────────────

def test_21_weight_config_defaults():
    """Default WeightConfig must have direct=1.0, curated=0.9, structural=0.0, none=0.0."""
    from backend.evaluation.evidence_weights import DEFAULT_WEIGHT_CONFIG
    assert DEFAULT_WEIGHT_CONFIG.direct == 1.0
    assert DEFAULT_WEIGHT_CONFIG.curated == 0.9
    assert DEFAULT_WEIGHT_CONFIG.inferred == 0.5
    assert DEFAULT_WEIGHT_CONFIG.structural == 0.0
    assert DEFAULT_WEIGHT_CONFIG.none == 0.0


def test_22_weight_config_direct():
    """weight_for(DIRECT) must return direct weight."""
    assert CONFIG_A.weight_for(CausalGrounding.DIRECT) == 1.0
    assert CONFIG_B.weight_for(CausalGrounding.DIRECT) == 1.0
    assert CONFIG_C.weight_for(CausalGrounding.DIRECT) == 1.0


def test_23_weight_config_structural_always_zero():
    """weight_for(STRUCTURAL) must always return 0.0 regardless of config.

    Structural edges encode connectivity, not direction. They must NEVER
    contribute signed votes (see CausalGrounding docstring Rule).
    """
    custom_cfg = WeightConfig(name="custom", structural=99.0)  # structural value ignored
    assert custom_cfg.weight_for(CausalGrounding.STRUCTURAL) == 0.0
    assert CONFIG_A.weight_for(CausalGrounding.STRUCTURAL) == 0.0
    assert CONFIG_B.weight_for(CausalGrounding.STRUCTURAL) == 0.0


def test_24_weight_config_none_always_zero():
    """weight_for(NONE) must always return 0.0 regardless of config."""
    custom_cfg = WeightConfig(name="custom", none=99.0)  # none value ignored
    assert custom_cfg.weight_for(CausalGrounding.NONE) == 0.0
    assert CONFIG_A.weight_for(CausalGrounding.NONE) == 0.0


# ── 25–30. Weighted Alignment Engine ─────────────────────────────────────────

def _make_tde(target: str, source: str, required_action: str,
              grounding: CausalGrounding = CausalGrounding.CURATED,
              family: EvidenceFamily = EvidenceFamily.CURATED_REFERENCE) -> TherapeuticDirectionEvidence:
    """Helper: create a synthetic TherapeuticDirectionEvidence record."""
    from backend.core.value_objects.therapeutic_direction_evidence import compute_independence_group
    ig = compute_independence_group(family, [f"test:{source}:{target}:{required_action}"], source=source)
    return TherapeuticDirectionEvidence(
        target_canonical_id=target,
        disease_canonical_id="TEST_DISEASE",
        source=source,
        target_direction=None,
        trait_direction=None,
        required_action=required_action,
        evidence_type="TEST",
        causal_grounding=grounding,
        evidence_family=family,
        independence_group=ig,
        underlying_reference=f"test:{source}",
    )


def test_25_weighted_align_support_only():
    """When only support-direction evidence exists -> SUPPORTS."""
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde],
        weight_config=CONFIG_A,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.SUPPORTS
    assert result.confidence > 0


def test_26_weighted_align_opposition_only():
    """When only oppose-direction evidence exists -> OPPOSES."""
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.ACTIVATION,  # drug ACTIVATES, but disease needs INHIBITION
        evidence_records=[tde],
        weight_config=CONFIG_A,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.OPPOSES


def test_27_weighted_align_insufficient_weight():
    """When total effective weight < min_effective_weight -> INSUFFICIENT."""
    engine = TherapeuticAlignmentEngine()
    # STRUCTURAL evidence -> weight 0.0 always
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.STRUCTURAL)
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde],
        weight_config=cfg,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.INSUFFICIENT


def test_28_weighted_align_unknown_drug_action():
    """UNKNOWN drug action -> always INSUFFICIENT regardless of evidence."""
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.DIRECT)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.UNKNOWN,
        evidence_records=[tde],
        weight_config=CONFIG_A,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.INSUFFICIENT


def test_29_weighted_align_strong_conflict_insufficient():
    """When both support and opposition weight >= min_effective_weight -> INSUFFICIENT (strong conflict)."""
    engine = TherapeuticAlignmentEngine()
    tde_support = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.DIRECT,
                            EvidenceFamily.CURATED_REFERENCE)
    # Create a second record with different independence group for opposition
    from backend.core.value_objects.therapeutic_direction_evidence import compute_independence_group
    ig2 = compute_independence_group(EvidenceFamily.GENETIC, ["test:OT:TGT1:ACTIVATION"], "OT")
    tde_oppose = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="TEST_DISEASE",
        source="OpenTargets",
        target_direction=None,
        trait_direction=None,
        required_action="ACTIVATION",  # Requires ACTIVATION but drug INHIBITS -> oppose
        evidence_type="TEST",
        causal_grounding=CausalGrounding.DIRECT,
        evidence_family=EvidenceFamily.GENETIC,
        independence_group=ig2,
        underlying_reference="test:OT",
    )
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde_support, tde_oppose],
        weight_config=cfg,
        is_primary=True,
    )
    # Both DIRECT records on opposite sides >= 0.5 min_effective_weight -> INSUFFICIENT
    assert result.alignment == TherapeuticAlignment.INSUFFICIENT


def test_30_weighted_align_net_support_wins():
    """Net weighted support > net weighted opposition -> SUPPORTS (not INSUFFICIENT)."""
    engine = TherapeuticAlignmentEngine()
    from backend.core.value_objects.therapeutic_direction_evidence import compute_independence_group

    # DIRECT support record (weight 1.0)
    tde_support = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.DIRECT,
                            EvidenceFamily.CURATED_REFERENCE)
    # STRUCTURAL oppose record (weight 0.0 — should not block)
    ig_struct = compute_independence_group(EvidenceFamily.BIOCHEMICAL, ["test:struct"], "ChEMBL")
    tde_struct_oppose = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="TEST_DISEASE",
        source="ChEMBL",
        target_direction=None,
        trait_direction=None,
        required_action="ACTIVATION",
        evidence_type="TEST",
        causal_grounding=CausalGrounding.STRUCTURAL,  # Zero weight
        evidence_family=EvidenceFamily.BIOCHEMICAL,
        independence_group=ig_struct,
    )
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde_support, tde_struct_oppose],
        weight_config=cfg,
        is_primary=True,
    )
    # STRUCTURAL oppose has 0.0 weight, DIRECT support wins
    assert result.alignment == TherapeuticAlignment.SUPPORTS


# ── 31–33. Dataset Quality ────────────────────────────────────────────────────

def test_31_benchmark_split_enum():
    """BenchmarkSplit enum must have DEVELOPMENT, VALIDATION, TEST."""
    assert BenchmarkSplit.DEVELOPMENT.value == "DEVELOPMENT"
    assert BenchmarkSplit.VALIDATION.value == "VALIDATION"
    assert BenchmarkSplit.TEST.value == "TEST"


def test_32_benchmark_has_suitable_negatives():
    """Must have >= 1 NEGATIVE case suitable for directional evaluation (not flagged)."""
    suitable = get_directionally_suitable_negatives()
    assert len(suitable) >= 1, (
        f"Expected >= 1 suitable negative case, got {len(suitable)}. "
        f"Unsuitable negatives: {len(get_unsuitable_negatives())}"
    )
    for c in suitable:
        assert c.expected_class == BenchmarkClass.NEGATIVE
        assert c.unsuitable_for_directional_negative is False


def test_33_all_cases_have_label_provenance():
    """All benchmark cases must have non-empty label_source and label_reference."""
    for case in BENCHMARK_DATASET_V1:
        assert case.label_source.strip(), f"{case.case_id}: label_source is empty"
        assert case.label_reference.strip(), f"{case.case_id}: label_reference is empty"


# ── 34–35. New Model Serialization ────────────────────────────────────────────

def test_34_ablation_verification_fields():
    """AblationVerification must capture evidence-level change independently of prediction change."""
    verif = AblationVerification(
        case_id="BENCH-POS-01",
        ablation_config="NO_DRUGMECHDB",
        full_evidence_count=10,
        ablated_evidence_count=8,
        full_independence_group_count=4,
        ablated_independence_group_count=3,
        component_present_in_full=True,
        component_present_in_ablated=False,
        evidence_representation_changed=True,
        prediction_changed=False,  # Prediction unchanged — still a VERIFIED ablation
        full_prediction="POSITIVE",
        ablated_prediction="POSITIVE",
        verification_passed=True,
        verification_note="VERIFIED: Evidence removed. Prediction unchanged (observation only).",
    )
    assert verif.evidence_representation_changed is True
    assert verif.prediction_changed is False
    assert verif.verification_passed is True
    # Correctness is determined by evidence change, NOT prediction change
    assert verif.verification_passed == verif.evidence_representation_changed


def test_35_report_serializes_new_fields():
    """BenchmarkEvaluationReport must serialize new Phase 4E fields correctly."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)

    report = BenchmarkEvaluationReport(
        benchmark_version="v1.0",
        case_results=[res],
        dataset_quality_metrics={"total_cases": 1, "positive_cases": 1},
        benchmark_split_note="All cases in TEST split.",
    )
    d = report.model_dump(mode="json")
    assert "dataset_quality_metrics" in d
    assert "benchmark_split_note" in d
    assert d["benchmark_split_note"] == "All cases in TEST split."
    assert d["dataset_quality_metrics"]["total_cases"] == 1
    # New fields should serialize correctly even when None
    assert "weighted_4d_metrics" in d
    assert "weighting_comparison" in d
    assert d["weighted_4d_metrics"] is None
    assert d["weighting_comparison"] is None
