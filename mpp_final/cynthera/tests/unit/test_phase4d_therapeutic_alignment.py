"""Unit tests for Phase 4D — Therapeutic Alignment Engine.

Covers all 20 required test cases:
1. LoF + protect + inhibition -> SUPPORTS
2. LoF + protect + activation -> OPPOSES
3. LoF + risk + inhibition -> OPPOSES
4. LoF + risk + activation -> SUPPORTS
5. GoF + protect + activation -> SUPPORTS
6. GoF + protect + inhibition -> OPPOSES
7. GoF + risk + inhibition -> SUPPORTS
8. GoF + risk + activation -> OPPOSES
9. UNKNOWN drug action -> INSUFFICIENT
10. UNKNOWN disease direction -> INSUFFICIENT
11. Conflicting independent groups -> INSUFFICIENT
12. Duplicate records from same reference -> 1 independence group
13. Same PMID across OT and DATTs -> 1 independence group
14. Different PMIDs -> distinct independence groups
15. Reactome CATALYST -> no directional inference
16. Reactome POSITIVE_REGULATOR -> positive polarity only
17. Reactome NEGATIVE_REGULATOR -> negative polarity only
18. Secondary target does not overwhelm primary target
19. Canonical Ensembl + UniProt + HGNC target -> 1 target
20. Provenance survives alignment
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
    OpenTargetsDoEEvidence,
    DATTsEvidence,
    DrugMechDBEvidence,
)
from backend.reasoning.directional.therapeutic_alignment import (
    derive_desired_target_action,
    normalize_drug_action,
    compare_drug_action_to_target_direction,
    group_evidence_by_independence,
    TherapeuticAlignmentEngine,
)
from backend.reasoning.directional.reactome_polarity import reactome_role_to_polarity
from backend.core.enums.molecular_polarity import MolecularPolarity


# ── Tests 1–8: Direction-of-Effect & Comparator Rules ──────────────────────────

def test_1_lof_protect_inhibition():
    """LoF + protect translates to desired INHIBITION -> Drug INHIBITION yields SUPPORTS."""
    desired = derive_desired_target_action(target_direction="LoF", trait_direction="protect")
    assert desired == TherapeuticAction.INHIBITION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.INHIBITION, desired)
    assert alignment == TherapeuticAlignment.SUPPORTS


def test_2_lof_protect_activation():
    """LoF + protect translates to desired INHIBITION -> Drug ACTIVATION yields OPPOSES."""
    desired = derive_desired_target_action(target_direction="LoF", trait_direction="protect")
    assert desired == TherapeuticAction.INHIBITION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.ACTIVATION, desired)
    assert alignment == TherapeuticAlignment.OPPOSES


def test_3_lof_risk_inhibition():
    """LoF + risk translates to desired ACTIVATION -> Drug INHIBITION yields OPPOSES."""
    desired = derive_desired_target_action(target_direction="LoF", trait_direction="risk")
    assert desired == TherapeuticAction.ACTIVATION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.INHIBITION, desired)
    assert alignment == TherapeuticAlignment.OPPOSES


def test_4_lof_risk_activation():
    """LoF + risk translates to desired ACTIVATION -> Drug ACTIVATION yields SUPPORTS."""
    desired = derive_desired_target_action(target_direction="LoF", trait_direction="risk")
    assert desired == TherapeuticAction.ACTIVATION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.ACTIVATION, desired)
    assert alignment == TherapeuticAlignment.SUPPORTS


def test_5_gof_protect_activation():
    """GoF + protect translates to desired ACTIVATION -> Drug ACTIVATION yields SUPPORTS."""
    desired = derive_desired_target_action(target_direction="GoF", trait_direction="protect")
    assert desired == TherapeuticAction.ACTIVATION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.ACTIVATION, desired)
    assert alignment == TherapeuticAlignment.SUPPORTS


def test_6_gof_protect_inhibition():
    """GoF + protect translates to desired ACTIVATION -> Drug INHIBITION yields OPPOSES."""
    desired = derive_desired_target_action(target_direction="GoF", trait_direction="protect")
    assert desired == TherapeuticAction.ACTIVATION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.INHIBITION, desired)
    assert alignment == TherapeuticAlignment.OPPOSES


def test_7_gof_risk_inhibition():
    """GoF + risk translates to desired INHIBITION -> Drug INHIBITION yields SUPPORTS."""
    desired = derive_desired_target_action(target_direction="GoF", trait_direction="risk")
    assert desired == TherapeuticAction.INHIBITION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.INHIBITION, desired)
    assert alignment == TherapeuticAlignment.SUPPORTS


def test_8_gof_risk_activation():
    """GoF + risk translates to desired INHIBITION -> Drug ACTIVATION yields OPPOSES."""
    desired = derive_desired_target_action(target_direction="GoF", trait_direction="risk")
    assert desired == TherapeuticAction.INHIBITION
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.ACTIVATION, desired)
    assert alignment == TherapeuticAlignment.OPPOSES


# ── Tests 9–11: Unknown, Ambiguous, and Conflicting Signals ───────────────────

def test_9_unknown_drug_action():
    """Ambiguous drug mechanism (MODULATOR/None) yields INSUFFICIENT alignment."""
    action = normalize_drug_action("MODULATOR")
    assert action == TherapeuticAction.UNKNOWN
    desired = derive_desired_target_action(target_direction="LoF", trait_direction="protect")
    alignment = compare_drug_action_to_target_direction(action, desired)
    assert alignment == TherapeuticAlignment.INSUFFICIENT


def test_10_unknown_disease_direction():
    """Uncharacterized disease direction yields INSUFFICIENT alignment."""
    desired = derive_desired_target_action(target_direction="UNKNOWN", trait_direction="UNKNOWN")
    assert desired == TherapeuticAction.UNKNOWN
    alignment = compare_drug_action_to_target_direction(TherapeuticAction.INHIBITION, desired)
    assert alignment == TherapeuticAlignment.INSUFFICIENT


def test_11_conflicting_independent_groups():
    """Conflicting independent groups for the same target result in INSUFFICIENT."""
    engine = TherapeuticAlignmentEngine()

    ev1 = TherapeuticDirectionEvidence(
        target_canonical_id="TARGET1",
        disease_canonical_id="DISEASE1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect", # -> INHIBITION
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:pmid:11111111",
        underlying_reference="11111111",
    )
    ev2 = TherapeuticDirectionEvidence(
        target_canonical_id="TARGET1",
        disease_canonical_id="DISEASE1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="risk", # -> ACTIVATION
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:22222222",
        underlying_reference="22222222",
    )

    alignment = engine.align_target(
        target_id="TARGET1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[ev1, ev2],
    )

    assert alignment.alignment == TherapeuticAlignment.INSUFFICIENT
    assert len(alignment.supporting_groups) == 1
    assert len(alignment.opposing_groups) == 1
    assert "Contradictory directional evidence" in alignment.explanation


# ── Tests 12–14: Evidence Independence & Deduplication ────────────────────────

def test_12_duplicate_records_same_reference():
    """Multiple rows citing the same publication collapse into 1 independent group."""
    recs = [
        TherapeuticDirectionEvidence(
            target_canonical_id="SLC12A1",
            disease_canonical_id="Edema",
            source="OpenTargets",
            target_direction="LoF",
            trait_direction="protect",
            evidence_family=EvidenceFamily.CLINICAL_TRIAL,
            independence_group="CLINICAL_TRIAL:pmid:30068263",
            underlying_reference="pmid:30068263",
        )
        for _ in range(25) # 25 duplicate rows
    ]

    groups = group_evidence_by_independence(recs)
    assert len(groups) == 1
    assert groups[0].member_record_count == 25
    assert groups[0].desired_action == TherapeuticAction.INHIBITION


def test_13_same_pmid_across_sources():
    """Open Targets and DATTs records sharing the same PMID share 1 independence group."""
    rec_ot = TherapeuticDirectionEvidence(
        target_canonical_id="CRBN",
        disease_canonical_id="Myeloma",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:21860026",
        underlying_reference="pmid:21860026",
    )
    rec_datts = TherapeuticDirectionEvidence(
        target_canonical_id="CRBN",
        disease_canonical_id="Myeloma",
        source="DATTs",
        required_action="INHIBITION",
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:21860026",
        underlying_reference="pmid:21860026",
    )

    groups = group_evidence_by_independence([rec_ot, rec_datts])
    assert len(groups) == 1
    assert groups[0].member_record_count == 2
    assert "OpenTargets" in groups[0].sources
    assert "DATTs" in groups[0].sources


def test_14_different_pmids_distinct_groups():
    """Distinct publications form distinct independence groups."""
    rec1 = TherapeuticDirectionEvidence(
        target_canonical_id="PTGS2",
        disease_canonical_id="CRC",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:pmid:10000001",
        underlying_reference="pmid:10000001",
    )
    rec2 = TherapeuticDirectionEvidence(
        target_canonical_id="PTGS2",
        disease_canonical_id="CRC",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:pmid:10000002",
        underlying_reference="pmid:10000002",
    )

    groups = group_evidence_by_independence([rec1, rec2])
    assert len(groups) == 2


# ── Tests 15–17: Reactome Semantics Integrity ─────────────────────────────────

def test_15_reactome_catalyst_no_directional_inference():
    """Reactome CATALYST role yields UNKNOWN polarity and never infers therapeutic direction."""
    polarity = reactome_role_to_polarity("CATALYST")
    assert polarity == MolecularPolarity.UNKNOWN


def test_16_reactome_positive_regulator():
    """Reactome POSITIVE_REGULATOR yields POSITIVE molecular polarity only."""
    polarity = reactome_role_to_polarity("POSITIVE_REGULATOR")
    assert polarity == MolecularPolarity.POSITIVE


def test_17_reactome_negative_regulator():
    """Reactome NEGATIVE_REGULATOR yields NEGATIVE molecular polarity only."""
    polarity = reactome_role_to_polarity("NEGATIVE_REGULATOR")
    assert polarity == MolecularPolarity.NEGATIVE


# ── Tests 18–20: Multi-Target Protection, Canonical Target, and Provenance ────

def test_18_secondary_target_does_not_overwhelm_primary():
    """A secondary target with 100 records cannot overpower a primary target with 1 record."""
    drug = Drug(name="DrugA", identifiers={"chembl": "CHEMBL1"})
    disease = Disease(name="DiseaseB", identifiers={"mondo": "MONDO_1"})
    erw = ERW.from_base(1.0)
    prov = ProvenanceReference(source_name="ChEMBL", source_version="v33", record_id="r1")
    target_prim = Target(
        drug_chembl_id="CHEMBL1",
        protein_uniprot="P00001",
        affinity_nm=1.0,
        affinity_type="IC50",
        mechanism="INHIBITOR",
        erw=erw,
        provenance=prov,
    )
    prot_prim = Protein(uniprot_accession="P00001", gene_symbol="PRIM1", name="Primary Target 1")

    # Primary target has 1 supporting record
    ev_prim = TherapeuticDirectionEvidence(
        target_canonical_id="PRIM1",
        disease_canonical_id="DiseaseB",
        source="DATTs",
        required_action="INHIBITION",
        evidence_family=EvidenceFamily.CURATED_REFERENCE,
        independence_group="CURATED_REFERENCE:ref:1",
    )

    # Secondary target (not in drug targets) has 100 opposing records
    ev_sec = [
        TherapeuticDirectionEvidence(
            target_canonical_id="SEC2",
            disease_canonical_id="DiseaseB",
            source="OpenTargets",
            target_direction="LoF",
            trait_direction="risk", # desired ACTIVATION
            evidence_family=EvidenceFamily.GENETIC,
            independence_group=f"GENETIC:ref:{i}",
        )
        for i in range(100)
    ]

    pkg = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[target_prim],
        proteins=[prot_prim],
        therapeutic_direction_evidence=[ev_prim] + ev_sec,
    )

    engine = TherapeuticAlignmentEngine()
    report = engine.align_package(pkg)

    # Overall alignment is determined by primary target PRIM1 -> SUPPORTS
    assert report.overall_alignment == TherapeuticAlignment.SUPPORTS
    assert len(report.primary_target_alignments) == 1
    assert report.primary_target_alignments[0].alignment == TherapeuticAlignment.SUPPORTS
    assert len(report.secondary_target_alignments) == 1
    assert report.secondary_target_alignments[0].alignment == TherapeuticAlignment.INSUFFICIENT


def test_19_canonical_ensembl_uniprot_hgnc_unified():
    """All equivalent target identifiers collapse into 1 target evaluation."""
    engine = TherapeuticAlignmentEngine()

    ev_ens = TherapeuticDirectionEvidence(
        target_canonical_id="SLC12A1",
        disease_canonical_id="Edema",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        original_target_id="ENSG00000074803",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:ref:1",
    )
    ev_uni = TherapeuticDirectionEvidence(
        target_canonical_id="SLC12A1",
        disease_canonical_id="Edema",
        source="ChEMBL",
        original_target_id="Q13621",
        evidence_family=EvidenceFamily.BIOCHEMICAL,
        independence_group="BIOCHEMICAL:ref:2",
    )

    alignment = engine.align_target(
        target_id="SLC12A1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[ev_ens, ev_uni],
    )

    assert alignment.target_id == "SLC12A1"
    assert alignment.alignment == TherapeuticAlignment.SUPPORTS


def test_20_provenance_survives_alignment():
    """Evidence groups and alignments preserve underlying citations and sources."""
    ev = TherapeuticDirectionEvidence(
        target_canonical_id="CRBN",
        disease_canonical_id="Myeloma",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:21860026",
        underlying_reference="pmid:21860026",
        original_target_id="ENSG00000113851",
    )

    engine = TherapeuticAlignmentEngine()
    alignment = engine.align_target(
        target_id="CRBN",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[ev],
    )

    assert alignment.evidence_groups[0].references == ["pmid:21860026"]
    assert alignment.evidence_groups[0].sources == ["OpenTargets"]
