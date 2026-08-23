"""Unit tests for ScientificContextBuilder — dimensional prior-knowledge context."""
from __future__ import annotations

import uuid

import pytest

from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.evidence import Evidence
from backend.core.domain.reasoning_result import MechanisticAssessment, SupportAssessment
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.reasoning.context.scientific_context_builder import (
    CLINICAL_HUMAN,
    MATURITY_ESTABLISHED,
    MATURITY_GROWING,
    MATURITY_SPECULATIVE,
    MECHANISTIC_MODERATE,
    MECHANISTIC_STRONG,
    MECHANISTIC_WEAK,
    REGULATORY_APPROVED,
    REGULATORY_INVESTIGATIONAL,
    REGULATORY_NONE,
    REPURPOSING_EMERGING,
    REPURPOSING_ESTABLISHED,
    REPURPOSING_NOVEL,
    ScientificContextBuilder,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _prov(source: str) -> ProvenanceReference:
    return ProvenanceReference(
        source_name=source,
        source_version="v1.0",
        record_id=f"raw_{source}_001",
        url=f"https://{source}.example.com",
    )


def make_evidence(etype: EvidenceType) -> Evidence:
    return Evidence(
        hypothesis_id=uuid.uuid4(),
        title=f"Evidence {etype.value}",
        abstract="Abstract about a drug-disease association.",
        evidence_type=etype,
        erw=ERW(value=0.6),
        source="pubmed",
        provenance=_prov("pubmed"),
    )


def build_package(
    approval_signal: ApprovalSignal | None = None,
    clinical_trials: list[ClinicalTrial] | None = None,
    evidence_records: list[Evidence] | None = None,
    sources_failed: list[str] | None = None,
    drug_name: str = "Aspirin",
    disease_name: str = "Lung Cancer",
) -> RetrievalPackage:
    drug = Drug(name=drug_name, identifiers={"chembl_id": "CHEMBL_TEST"})
    disease = Disease(name=disease_name, identifiers={"mesh_id": "D000000"})
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        approval_signal=approval_signal,
        clinical_trials=clinical_trials or [],
        evidence_records=evidence_records or [],
        sources_failed=sources_failed or [],
    )


def make_support(score: float = 0.0) -> SupportAssessment:
    return SupportAssessment(score=score, level="LOW", evidence_count=0)


def make_mech(score: float) -> MechanisticAssessment:
    level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")
    return MechanisticAssessment(score=score, level=level, pathway_count=0)


def make_prior_ctx(**kwargs) -> PriorKnowledgeContext:
    defaults = dict(
        evaluation_pathway="NOVEL_HYPOTHESIS",
        is_approved_indication=False,
        approval_type="NOVEL_HYPOTHESIS",
        approval_confidence=0.0,
        matched_indication_term="",
        has_established_precedent=False,
        evidence_boost=0.0,
        confidence_adjustment=0.0,
        narrative="",
        top_entries=[],
        approved_indications_count=0,
    )
    defaults.update(kwargs)
    return PriorKnowledgeContext(**defaults)


def _build(
    prior_ctx,
    package,
    mech_score: float = 0.0,
    mechanistic_paths=None,
    support_score: float = 0.0,
):
    return ScientificContextBuilder.build(
        prior_ctx=prior_ctx,
        support=make_support(support_score),
        mechanistic=make_mech(mech_score),
        mechanistic_paths=mechanistic_paths or [],
        package=package,
    )


# ─────────────────────────────────────────────
# Regulatory
# ─────────────────────────────────────────────

class TestRegulatory:
    def test_approved_from_live_signal(self):
        sig = ApprovalSignal.from_chembl_indication_match(
            max_phase=4, matched_term="Lung Cancer", match_confidence=0.95, approved_count=3
        )
        ctx = _build(make_prior_ctx(), build_package(approval_signal=sig))
        assert ctx.regulatory.status == REGULATORY_APPROVED
        assert ctx.regulatory.confidence == 0.95
        assert ctx.is_approved is True

    def test_investigational_from_phase2(self):
        sig = ApprovalSignal.from_chembl_indication_match(
            max_phase=2, matched_term="Lung Cancer", match_confidence=0.8, approved_count=0
        )
        ctx = _build(make_prior_ctx(), build_package(approval_signal=sig))
        assert ctx.regulatory.status == REGULATORY_INVESTIGATIONAL
        assert ctx.is_approved is False

    def test_none_when_no_signal(self):
        ctx = _build(make_prior_ctx(), build_package())
        assert ctx.regulatory.status == REGULATORY_NONE

    def test_none_with_chembl_failure(self):
        ctx = _build(
            make_prior_ctx(), build_package(sources_failed=["chembl"])
        )
        assert ctx.regulatory.status == REGULATORY_NONE
        assert any("unavailable" in e for e in ctx.regulatory.evidence)


# ─────────────────────────────────────────────
# Repurposing
# ─────────────────────────────────────────────

class TestRepurposing:
    def test_established_requires_approved_elsewhere_and_pair_literature(self):
        pkg = build_package(evidence_records=[make_evidence(EvidenceType.META_ANALYSIS)])
        prior = make_prior_ctx(approved_indications_count=3)
        ctx = _build(prior, pkg)
        assert ctx.repurposing.status == REPURPOSING_ESTABLISHED
        assert ctx.repurposing.confidence == 0.8

    def test_emerging_pair_literature_only(self):
        pkg = build_package(evidence_records=[make_evidence(EvidenceType.META_ANALYSIS)])
        prior = make_prior_ctx(approved_indications_count=0)
        ctx = _build(prior, pkg)
        assert ctx.repurposing.status == REPURPOSING_EMERGING

    def test_novel(self):
        ctx = _build(make_prior_ctx(), build_package())
        assert ctx.repurposing.status == REPURPOSING_NOVEL


# ─────────────────────────────────────────────
# Mechanistic
# ─────────────────────────────────────────────

class TestMechanistic:
    @pytest.mark.parametrize("score,expected", [
        (0.80, MECHANISTIC_STRONG),
        (0.50, MECHANISTIC_MODERATE),
        (0.20, MECHANISTIC_WEAK),
    ])
    def test_mapping(self, score, expected):
        ctx = _build(make_prior_ctx(), build_package(), mech_score=score)
        assert ctx.mechanistic.status == expected
        assert ctx.mechanistic.confidence == score

    def test_path_evidence_surfaced(self):
        from backend.reasoning.mechanistic.multi_hop_reasoner import MechanisticPath
        path = MechanisticPath(
            hop_count=2,
            confidence=0.6,
            path_type="2-HOP",
            description="Aspirin inhibits PTGS1 → activates prostaglandin pathway → Lung Cancer",
        )
        ctx = _build(make_prior_ctx(), build_package(), mech_score=0.5, mechanistic_paths=[path])
        assert any("prostaglandin" in e for e in ctx.mechanistic.evidence)


# ─────────────────────────────────────────────
# Clinical
# ─────────────────────────────────────────────

class TestClinical:
    def test_human_evidence_from_trials(self):
        trial = ClinicalTrial(
            nct_id="NCT00000001",
            title="Trial",
            phase="Phase II",
            status=TrialOutcomeStatus.ACTIVE,
            provenance=_prov("ClinicalTrials.gov"),
        )
        ctx = _build(make_prior_ctx(), build_package(clinical_trials=[trial]))
        assert ctx.clinical.status == CLINICAL_HUMAN
        assert ctx.clinical.confidence == 0.8
        assert any("NCT00000001" in e for e in ctx.clinical.evidence)

    def test_human_evidence_from_literature(self):
        pkg = build_package(evidence_records=[make_evidence(EvidenceType.RCT)])
        ctx = _build(make_prior_ctx(), pkg)
        assert ctx.clinical.status == CLINICAL_HUMAN

    def test_ct_failed_caps_confidence(self):
        pkg = build_package(
            evidence_records=[make_evidence(EvidenceType.RCT)],
            sources_failed=["clinicaltrials"],
        )
        ctx = _build(make_prior_ctx(), pkg)
        assert ctx.clinical.confidence <= 0.2
        assert any("unavailable" in e for e in ctx.clinical.evidence)


# ─────────────────────────────────────────────
# Knowledge Maturity
# ─────────────────────────────────────────────

class TestMaturity:
    def test_growing_from_related_cache(self):
        prior = make_prior_ctx(top_entries=[
            {"drug": "aspirin", "disease": "colorectal cancer",
             "similarity": 0.6, "established": False, "evidence_level": "MEDIUM"},
        ])
        ctx = _build(prior, build_package())
        assert ctx.knowledge_maturity.status == MATURITY_GROWING
        assert ctx.knowledge_maturity.confidence == 0.6
        assert len(ctx.related_pairs) == 1
        assert ctx.related_pairs[0]["disease"] == "colorectal cancer"

    def test_established_exact_cache(self):
        prior = make_prior_ctx(top_entries=[
            {"drug": "aspirin", "disease": "lung cancer",
             "similarity": 1.0, "established": True, "evidence_level": "HIGH"},
        ])
        ctx = _build(prior, build_package(drug_name="Aspirin", disease_name="Lung Cancer"))
        assert ctx.knowledge_maturity.status == MATURITY_ESTABLISHED

    def test_speculative_empty(self):
        ctx = _build(make_prior_ctx(top_entries=[]), build_package())
        assert ctx.knowledge_maturity.status == MATURITY_SPECULATIVE


# ─────────────────────────────────────────────
# Orthogonality — dimensions are independent
# ─────────────────────────────────────────────

class TestOrthogonality:
    def test_multiple_dimensions_set_independently(self):
        trial = ClinicalTrial(
            nct_id="NCT00000002", title="T", phase="Phase I",
            status=TrialOutcomeStatus.ACTIVE, provenance=_prov("ClinicalTrials.gov"),
        )
        prior = make_prior_ctx(top_entries=[
            {"drug": "aspirin", "disease": "colorectal cancer",
             "similarity": 0.5, "established": False, "evidence_level": "LOW"},
        ])
        ctx = _build(prior, build_package(clinical_trials=[trial]), mech_score=0.5)
        assert ctx.regulatory.status == REGULATORY_NONE
        assert ctx.mechanistic.status == MECHANISTIC_MODERATE
        assert ctx.clinical.status == CLINICAL_HUMAN
        assert ctx.knowledge_maturity.status == MATURITY_GROWING
        assert ctx.is_approved is False

    def test_to_dict_serializable(self):
        ctx = _build(make_prior_ctx(), build_package())
        d = ctx.to_dict()
        assert set(d) == {"regulatory", "repurposing", "mechanistic",
                          "clinical", "knowledge_maturity", "related_pairs"}
        for dim in ("regulatory", "repurposing", "mechanistic", "clinical", "knowledge_maturity"):
            assert "status" in d[dim]
            assert "confidence" in d[dim]
            assert "evidence" in d[dim]
