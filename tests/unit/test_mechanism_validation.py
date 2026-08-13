"""Regression tests for separation of graph discovery and validation."""
from __future__ import annotations

import uuid

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.claim import Claim
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.pathway import Pathway
from backend.core.domain.protein import Protein
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.predicate_type import PredicateType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator


def _package() -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name="Sildenafil", identifiers={"chembl": "CHEMBL192"}),
        disease=Disease(name="Pulmonary Arterial Hypertension", identifiers={"mesh": "D006976"}),
        proteins=[Protein(
            uniprot_accession="O76074", gene_symbol="PDE5A", name="cGMP-specific phosphodiesterase 5A",
            organism="Homo sapiens", is_reviewed=True,
            provenance=ProvenanceReference(source_name="UniProt", source_version="1", record_id="O76074"),
        )],
        pathways=[Pathway(
            reactome_id="R-HSA-1234", name="cGMP signalling", participant_uniprot_ids=["O76074"],
            provenance=ProvenanceReference(source_name="Reactome", source_version="1", record_id="R-HSA-1234"),
        )],
        validated_disease_genes={"PDE5A": 0.8},
    )


def _candidate() -> CandidateMechanism:
    return CandidateMechanism(
        name="PDE5A candidate", support_level="WEAK_SPECULATIVE", confidence_score=0.6,
        summary_chain=[],
        hops=[
            MechanismHop(from_node="Drug: Sildenafil", to_node="Target: PDE5A (O76074)", predicate="INHIBITOR", evidence_strength=.95, source_database="ChEMBL"),
            MechanismHop(from_node="Target: PDE5A (O76074)", to_node="Pathway: cGMP signalling (R-HSA-1234)", predicate="PARTICIPATES_IN", evidence_strength=.5, source_database="Reactome"),
            MechanismHop(from_node="Pathway: cGMP signalling (R-HSA-1234)", to_node="Disease: Pulmonary Arterial Hypertension", predicate="CONTRIBUTES_TO", evidence_strength=.8, source_database="Open Targets"),
        ],
    )


def _claim(subject: str, predicate: PredicateType, obj: str, source: str = "PubMed") -> Claim:
    return Claim(
        subject=subject, predicate=predicate, object=obj, confidence=.9, erw=ERW(value=.8),
        provenance=ProvenanceReference(source_name=source, source_version="1", record_id="PMID:12345678"),
    )


def test_reactome_membership_stays_structural_without_a_mapped_bridge():
    result = MechanismValidator().validate(_package(), [_candidate()], [])
    candidate = result[0]
    assert candidate.support_level == "WEAK_SPECULATIVE"
    assert candidate.confidence_score < .5
    assert candidate.hops[1].status == "STRUCTURAL_EVIDENCE"
    assert candidate.missing_critical_evidence


def test_claims_map_by_canonical_identifiers_and_attach_to_hops():
    claims = [
        _claim("Sildenafil", PredicateType.INHIBITS, "PDE5A"),
        _claim("PDE5A", PredicateType.ACTIVATES, "cGMP signalling", "Europe PMC"),
        _claim("cGMP signalling", PredicateType.PREVENTS, "Pulmonary Arterial Hypertension", "PubMed"),
    ]
    candidate = MechanismValidator().validate(_package(), [_candidate()], claims)[0]
    assert candidate.hops[1].status == "LITERATURE_SUPPORTED"
    assert candidate.hops[1].canonical_from_id == "UNIPROT:O76074"
    assert candidate.hops[1].canonical_to_id == "REACTOME:R-HSA-1234"
    assert candidate.literature_citations
    assert candidate.discovery_status == "VALIDATED"
