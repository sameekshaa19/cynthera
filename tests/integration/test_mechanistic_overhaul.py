"""Comprehensive Integration & Regression Test Suite for Mechanistic Discovery Engine Overhaul.

Verifies:
1. Dapagliflozin → Heart Failure regression test (prevents 89.5% HIGH inflation with 0 literature claims).
2. Candidate Mechanism Discovery & Ranking (Candidate 1, 2, etc. with hop-by-hop links).
3. Evidence URL Resolution via SourceURLBuilder (PubMed, DOI, Europe PMC, ChEMBL, UniProt, Reactome, Open Targets).
4. Evidence status distinction (SOURCE_UNAVAILABLE, INSUFFICIENT_EVIDENCE, MECHANISTICALLY_UNSUPPORTED, MECHANISTICALLY_PLAUSIBLE).
5. 4-Question Acceptance Criteria.
"""
import pytest
import uuid
from datetime import datetime

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.evidence import Evidence
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.evidence_type import EvidenceType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.core.value_objects.source_url_builder import SourceURLBuilder, EvidenceLink


@pytest.fixture
def dapagliflozin_package():
    """Build synthetic Dapagliflozin → Heart Failure RetrievalPackage fixture matching actual retrieval shape."""
    hyp_id = uuid.uuid4()
    drug = Drug(name="Dapagliflozin", identifiers={"chembl": "CHEMBL1201267"})
    disease = Disease(name="Heart Failure", identifiers={"mesh": "D006333"})

    targets = [
        Target(
            drug_chembl_id="CHEMBL1201267",
            protein_uniprot="P31639",  # SLC5A2
            affinity_nm=6.0,
            affinity_type="IC50",
            mechanism="INHIBITOR",
            erw=ERW(value=0.95),
            provenance=ProvenanceReference(source_name="ChEMBL", source_version="v33", record_id="CHEMBL1201267"),
        )
    ]

    proteins = [
        Protein(
            uniprot_accession="P31639",
            gene_symbol="SLC5A2",
            name="Sodium/glucose cotransporter 2",
            organism="Homo sapiens",
            is_reviewed=True,
            provenance=ProvenanceReference(source_name="UniProt", source_version="2024_01", record_id="P31639"),
        )
    ]

    pathways = [
        Pathway(
            reactome_id="R-HSA-163200",
            name="Transport of glucose and other sugars, bile salts and organic acids, metal ions and amine compounds",
            participant_uniprot_ids=["P31639"],
            provenance=ProvenanceReference(source_name="Reactome", source_version="v85", record_id="R-HSA-163200"),
        )
    ]

    val_genes = {"SLC5A2": 0.82}

    ev_records = [
        Evidence(
            evidence_type=EvidenceType.OBSERVATIONAL,
            erw=ERW(value=0.70),
            citation_key="PMID:31545428",
            title="Dapagliflozin in Patients with Heart Failure and Reduced Ejection Fraction.",
            abstract="Dapagliflozin reduced the risk of worsening heart failure or death from cardiovascular causes.",
            provenance=ProvenanceReference(source_name="PubMed", source_version="2024", record_id="PMID:31545428"),
        )
    ]

    return RetrievalPackage(
        hypothesis_id=hyp_id,
        drug=drug,
        disease=disease,
        targets=targets,
        proteins=proteins,
        genes=[],
        pathways=pathways,
        evidence_records=ev_records,
        clinical_trials=[],
        retrieval_confidence="HIGH",
        sources_queried=["chembl", "uniprot", "reactome", "pubmed", "opentargets"],
        sources_failed=[],
        validated_disease_genes=val_genes,
    )


@pytest.mark.asyncio
async def test_dapagliflozin_hf_regression(dapagliflozin_package):
    """Test 1: Dapagliflozin → Heart Failure regression test.

    Verifies score is non-inflated (not 89.5% HIGH without pathways/claims),
    candidate mechanisms are discovered, and hop evidence URLs resolve.
    """
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(dapagliflozin_package)

    assert len(paths) >= 1, "At least 1 path should be traced for Dapagliflozin → SLC5A2"
    ms_score = reasoner.compute_mechanistic_score(paths)

    # Core Regression Assertion: MS must be conservative and reflect single-path evidence strength, NOT 89.5%
    assert ms_score < 0.85, f"MS score ({ms_score}) should not be artificially inflated to >85%!"

    # Discover candidate mechanisms
    candidates = reasoner.discover_candidate_mechanisms(dapagliflozin_package, paths)
    assert len(candidates) >= 1, "Candidate mechanisms should be discovered"

    cand1 = candidates[0]
    assert "SLC5A2" in cand1.name or "Mechanism 1" in cand1.name
    # Discovery records a structural candidate; it is not a validated causal
    # mechanism until the literature-to-hop validation stage runs.
    assert cand1.discovery_status == "CANDIDATE_STRUCTURAL"
    assert cand1.support_level == "WEAK_SPECULATIVE"

    # Verify Hop evidence links
    has_links = any(len(h.links) > 0 for h in cand1.hops)
    assert has_links, "Hop evidence links must be attached to graph edges!"


@pytest.mark.asyncio
async def test_source_url_builder_no_fabrication():
    """Test 2: SourceURLBuilder link generation correctness without fabrication."""
    pm_links = SourceURLBuilder.build_links_for_citation_key("PMID:31545428")
    assert any(l.source_name == "PubMed" and "pubmed.ncbi.nlm.nih.gov/31545428" in l.url for l in pm_links)
    assert any(l.source_name == "Europe PMC" and "europepmc.org/article/MED/31545428" in l.url for l in pm_links)

    chembl_url = SourceURLBuilder.chembl_compound_url("CHEMBL1201267")
    assert chembl_url == "https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL1201267/"

    uniprot_url = SourceURLBuilder.uniprot_url("P31639")
    assert uniprot_url == "https://www.uniprot.org/uniprotkb/P31639/entry"

    reactome_url = SourceURLBuilder.reactome_url("R-HSA-163200")
    assert reactome_url == "https://reactome.org/content/detail/R-HSA-163200"


@pytest.mark.asyncio
async def test_api_failure_evidence_status():
    """Test 3: API failure yields SOURCE_UNAVAILABLE and INSUFFICIENT_DATA recommendation."""
    hyp_id = uuid.uuid4()
    drug = Drug(name="UnknownDrug", identifiers={"chembl": "CHEMBL_FAIL"})
    disease = Disease(name="TestDisease", identifiers={"mesh": "D000000"})

    package = RetrievalPackage(
        hypothesis_id=hyp_id,
        drug=drug,
        disease=disease,
        targets=[],
        proteins=[],
        pathways=[],
        evidence_records=[],
        sources_queried=[],
        sources_failed=["chembl", "uniprot"],
    )

    orchestrator = ReasoningOrchestrator()
    result = await orchestrator.reason(package)

    assert result.mechanistic_assessment.score == 0.0
    assert result.mechanistic_assessment.evidence_status == "SOURCE_UNAVAILABLE"
    assert result.recommendation_status.value == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_missing_disease_mechanism_source_is_not_a_biological_negative(dapagliflozin_package):
    """A failed pathway/association source must not become "unsupported"."""
    package = dapagliflozin_package.model_copy(update={
        "pathways": [],
        "validated_disease_genes": {},
        "sources_failed": ["reactome", "opentargets"],
    })
    result = await ReasoningOrchestrator().reason(package)
    assert result.mechanistic_assessment.score == 0.0
    assert result.mechanistic_assessment.evidence_status == "SOURCE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_four_acceptance_criteria(dapagliflozin_package):
    """Test 4: Verify the 4-question acceptance test programmatically.

    1. Is there a plausible mechanism? -> Yes (ms_score > 0)
    2. Why does it think that? -> Rationale & candidate mechanism chain
    3. What exact biological evidence supports every step? -> Hop predicates & sources
    4. Can I click the source and verify it myself? -> Verified EvidenceLinks present
    """
    orchestrator = ReasoningOrchestrator()
    result = await orchestrator.reason(dapagliflozin_package)

    # 1. Plausible mechanism
    assert result.mechanistic_assessment.score > 0.0

    # 2. Why does it think that?
    assert len(result.mechanistic_assessment.candidate_mechanisms) >= 1
    cand1 = result.mechanistic_assessment.candidate_mechanisms[0]
    assert "summary_chain" in cand1

    # 3. Biological evidence per step
    assert len(cand1["hops"]) >= 1
    for hop in cand1["hops"]:
        assert "from_node" in hop and "to_node" in hop and "predicate" in hop

    # 4. Clickable sources
    hop1_links = cand1["hops"][0].get("links", [])
    assert len(hop1_links) >= 1
    assert all(l["url"].startswith("http") for l in hop1_links)
