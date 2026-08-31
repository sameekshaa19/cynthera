"""Unit tests for Phase 4C: Therapeutic Direction Evidence.

Tests coverage:
1. Open Targets DoE parsing & raw semantics preservation (LoF/GoF, protect/risk)
2. DATTs therapeutic action extraction (Inhibition, Activation, Targeting, Unknown)
3. Entity mapping & canonical gating (EXACT, RESOLVED, UNRESOLVED)
4. Literature directional claim canonicalization & generic placeholder rejection
5. Source independence & collinearity grouping (shared PMID/DOI/NCT)
6. DrugMechDB mechanistic path validation
7. Connector failure modes & graceful degradation
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.claim import Claim
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    OpenTargetsDoEEvidence,
    DATTsEvidence,
    DrugMechDBEvidence,
    TherapeuticDirectionEvidence,
    normalize_therapeutic_action,
    compute_independence_group,
)
from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
from backend.engineering.retrieval.connectors.datts import DATTsConnector
from backend.infrastructure.knowledge.drugmechdb_client import DrugMechDBClient
from backend.reasoning.directional.directional_evidence_builder import DirectionalEvidenceBuilder
from backend.reasoning.directional.canonical_entity_gate import is_canonically_grounded, validate_directional_claim
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver


# ─────────────────────────────────────────────────────────────────────────────
# 1. Open Targets DoE Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_opentargets_doe_raw_semantics_preservation():
    """Verify Open Targets DoE records preserve LoF/GoF and protect/risk without lossy conversion."""
    ev = OpenTargetsDoEEvidence(
        target_id="ENSG00000074803",
        disease_id="MONDO_0009693",
        direction_on_target="LoF",
        direction_on_trait="protect",
        datasource_id="clinical_precedence",
        datatype_id="clinical",
        score=0.95,
        literature=["31737482"],
        study_id="NCT03036124",
    )
    assert ev.direction_on_target == "LoF"
    assert ev.direction_on_trait == "protect"
    assert ev.datasource_id == "clinical_precedence"
    assert ev.score == 0.95
    assert "31737482" in ev.literature


def test_opentargets_doe_missing_directions():
    """Verify Open Targets DoE gracefully handles missing or unknown direction fields."""
    ev = OpenTargetsDoEEvidence(
        target_id="ENSG00000163631",
        disease_id="EFO_0009373",
        direction_on_target=None,
        direction_on_trait=None,
    )
    assert ev.direction_on_target is None
    assert ev.direction_on_trait is None


@pytest.mark.asyncio
async def test_opentargets_connector_fetch_doe_mock():
    """Test OpenTargetsConnector.fetch_direction_of_effect parsing."""
    mock_response = {
        "data": {
            "target": {
                "id": "ENSG00000074803",
                "evidences": {
                    "count": 1,
                    "rows": [
                        {
                            "id": "ev_001",
                            "datasourceId": "eva",
                            "datatypeId": "genetic_association",
                            "directionOnTarget": "GoF",
                            "directionOnTrait": "risk",
                            "score": 0.88,
                            "literature": ["12345678"],
                            "studyId": "GCST001234",
                        }
                    ]
                }
            }
        }
    }
    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        records = await connector.fetch_direction_of_effect("ENSG00000074803", "MONDO_0005575")
        assert len(records) == 1
        assert records[0].direction_on_target == "GoF"
        assert records[0].direction_on_trait == "risk"
        assert records[0].datasource_id == "eva"


# ─────────────────────────────────────────────────────────────────────────────
# 2. DATTs Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_datts_therapeutic_action_normalization():
    """Verify normalization of raw DATTs relationship strings to typed TherapeuticAction."""
    assert normalize_therapeutic_action("Inhibition") == TherapeuticAction.INHIBITION
    assert normalize_therapeutic_action("Inhibitor") == TherapeuticAction.INHIBITION
    assert normalize_therapeutic_action("Antagonist") == TherapeuticAction.INHIBITION
    assert normalize_therapeutic_action("Activation") == TherapeuticAction.ACTIVATION
    assert normalize_therapeutic_action("Agonist") == TherapeuticAction.ACTIVATION
    assert normalize_therapeutic_action("Targeting") == TherapeuticAction.TARGETING
    assert normalize_therapeutic_action("Unknown") == TherapeuticAction.UNKNOWN
    assert normalize_therapeutic_action(None) == TherapeuticAction.UNKNOWN


@pytest.mark.asyncio
async def test_datts_connector_fetch_therapeutic_actions_mock():
    """Test DATTsConnector matching disease and extracting structured DATTsEvidence."""
    mock_response = {
        "data": {
            "proteinList": [
                {
                    "id": 1,
                    "proteinId": "hsa:6557",
                    "geneSymbol": "SLC12A1",
                    "uniprotId": "Q13621",
                    "relationships": [
                        {
                            "id": 101,
                            "relType": "Inhibition",
                            "source": "Pharmacology Textbook",
                            "literature": "Med Media 2014",
                            "disease": {
                                "id": 50,
                                "nameEn": "Edema",
                            }
                        },
                        {
                            "id": 102,
                            "relType": "Inhibition",
                            "source": "Textbook",
                            "literature": "Med Media 2014",
                            "disease": {
                                "id": 51,
                                "nameEn": "Hypertension",
                            }
                        }
                    ]
                }
            ]
        }
    }
    connector = DATTsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        records = await connector.fetch_therapeutic_actions("SLC12A1", "Q13621", "Edema")
        assert len(records) == 1
        assert records[0].gene_symbol == "SLC12A1"
        assert records[0].disease_name == "Edema"
        assert records[0].required_action == TherapeuticAction.INHIBITION
        assert records[0].literature == "Med Media 2014"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Entity Normalization & Canonical Gating Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_entity_gate_validates_grounded_entities():
    """Verify is_canonically_grounded accepts real proteins and rejects placeholders."""
    resolver = BiologicalIdentifierResolver()
    # Add real proteins
    resolver.resolve("SLC12A1", source="test")
    resolver.resolve("Q13621", source="test")

    assert is_canonically_grounded("SLC12A1", resolver) is True
    assert is_canonically_grounded("Q13621", resolver) is True

    # Generic placeholders must be rejected
    assert is_canonically_grounded("compound", resolver) is False
    assert is_canonically_grounded("molecular target", resolver) is False
    assert is_canonically_grounded("the drug", resolver) is False
    assert is_canonically_grounded("protein", resolver) is False
    assert is_canonically_grounded("gene", resolver) is False


def test_directional_claim_validation():
    """Verify validate_directional_claim rejects ungrounded claims."""
    resolver = BiologicalIdentifierResolver()
    prov = ProvenanceReference(source_name="Lit", source_version="v1", record_id="1")
    erw = ERW.from_base(1.0)

    grounded_claim = Claim(
        subject="SLC12A1",
        predicate=PredicateType.INHIBITS,
        object="Edema",
        confidence=0.9,
        erw=erw,
        provenance=prov,
    )
    ungrounded_claim = Claim(
        subject="compound",
        predicate=PredicateType.INHIBITS,
        object="molecular target",
        confidence=0.9,
        erw=erw,
        provenance=prov,
    )

    assert validate_directional_claim(grounded_claim, resolver) is not None
    assert validate_directional_claim(ungrounded_claim, resolver) is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Source Independence & Collinearity Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_shared_underlying_publication_collinearity_grouping():
    """Verify evidence from different sources sharing a DOI/PMID receive the same independence_group."""
    # Open Targets record citing NEJM DAPA-HF trial (PMID 31737482)
    group_ot = compute_independence_group(
        EvidenceFamily.CLINICAL_TRIAL,
        references=["pubmed/31737482", "NCT03036124"],
        source="OpenTargets",
    )

    # DATTs record citing the same PMID
    group_datts = compute_independence_group(
        EvidenceFamily.CLINICAL_TRIAL,
        references=["PMID: 31737482"],
        source="DATTs",
    )

    assert group_ot == group_datts
    assert group_ot == "CLINICAL_TRIAL:pmid:31737482"


def test_independent_evidence_families_distinct_groups():
    """Verify independent evidence families produce distinct independence groups."""
    group_genetic = compute_independence_group(
        EvidenceFamily.GENETIC,
        references=["doi:10.1038/s41588-020-0001"],
        source="GWAS",
    )
    group_clinical = compute_independence_group(
        EvidenceFamily.CLINICAL_TRIAL,
        references=["doi:10.1056/NEJMoa1911303"],
        source="NEJM",
    )
    assert group_genetic != group_clinical


# ─────────────────────────────────────────────────────────────────────────────
# 5. DrugMechDB Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_drugmechdb_lookup_mechanism():
    """Test DrugMechDBClient retrieves curated path when available."""
    client = DrugMechDBClient()
    mock_paths = [
        {
            "graph": {
                "_id": "DB00695_MESH_D004487_1",
                "drug": "furosemide",
                "drugbank": "DB00695",
                "disease": "Edema",
                "disease_mesh": "MESH:D004487",
            },
            "nodes": [{"id": "DB00695"}, {"id": "UniProt:Q13621"}, {"id": "MESH:D004487"}],
            "links": [
                {"source": "DB00695", "target": "UniProt:Q13621", "key": "decreases activity of"},
                {"source": "UniProt:Q13621", "target": "MESH:D004487", "key": "causes"},
            ]
        }
    ]
    with patch.object(client, "load_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_paths
        ev = await client.lookup_mechanism("Furosemide", "Edema", "Q13621")
        assert ev.is_curated_path_available is True
        assert ev.drugbank_id == "DB00695"
        assert "decreases activity of" in ev.path_summary


@pytest.mark.asyncio
async def test_drugmechdb_missing_path():
    """Test DrugMechDBClient gracefully returns is_curated_path_available=False for uncurated indications."""
    client = DrugMechDBClient()
    with patch.object(client, "load_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = []
        ev = await client.lookup_mechanism("Aspirin", "Colorectal Cancer", "P35354")
        assert ev.is_curated_path_available is False
        assert ev.path_summary == "NONE"


# ─────────────────────────────────────────────────────────────────────────────
# 6. DirectionalEvidenceBuilder Multi-Source Normalization Test
# ─────────────────────────────────────────────────────────────────────────────

def test_directional_evidence_builder_normalization():
    """Test DirectionalEvidenceBuilder normalizes all sources into unified TherapeuticDirectionEvidence."""
    hyp_id = uuid.uuid4()
    drug = Drug(name="Dapagliflozin", identifiers={"chembl": "CHEMBL2048455"})
    disease = Disease(name="Heart Failure", identifiers={"mondo": "MONDO_0005252"})
    erw = ERW.from_base(1.0)
    prov = ProvenanceReference(source_name="Test", source_version="v1", record_id="rec1")

    target = Target(
        drug_chembl_id="CHEMBL2048455",
        protein_uniprot="P31639",
        affinity_nm=1.0,
        affinity_type="IC50",
        mechanism="INHIBITOR",
        erw=erw,
        provenance=prov,
    )
    protein = Protein(
        uniprot_accession="P31639",
        gene_symbol="SLC5A2",
        name="Sodium/glucose cotransporter 2",
    )
    doe_ev = OpenTargetsDoEEvidence(
        target_id="ENSG00000140675",
        disease_id="MONDO_0005252",
        direction_on_target="LoF",
        direction_on_trait="protect",
        datasource_id="clinical_precedence",
        literature=["31737482"],
    )
    datts_ev = DATTsEvidence(
        gene_symbol="SLC5A2",
        disease_name="Heart Failure",
        rel_type="Inhibition",
        required_action=TherapeuticAction.INHIBITION,
        literature="NEJM 2019 DAPA-HF",
    )
    dm_ev = DrugMechDBEvidence(
        drug_name="Dapagliflozin",
        disease_name="Heart Failure",
        is_curated_path_available=False,
    )

    pkg = RetrievalPackage(
        hypothesis_id=hyp_id,
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        opentargets_doe_evidence=[doe_ev],
        datts_evidence=[datts_ev],
        drugmechdb_evidence=[dm_ev],
    )

    builder = DirectionalEvidenceBuilder()
    evidence_records = builder.build_all(pkg)

    assert len(evidence_records) >= 3

    # Check ChEMBL record
    chembl_rec = next(r for r in evidence_records if r.source == "ChEMBL")
    assert chembl_rec.target_direction == "NEGATIVE"
    assert chembl_rec.evidence_family == EvidenceFamily.BIOCHEMICAL

    # Check Open Targets record
    ot_rec = next(r for r in evidence_records if r.source == "OpenTargets")
    assert ot_rec.target_direction == "LoF"
    assert ot_rec.trait_direction == "protect"
    assert ot_rec.evidence_family == EvidenceFamily.CLINICAL_TRIAL

    # Check DATTs record
    datts_rec = next(r for r in evidence_records if r.source == "DATTs")
    assert datts_rec.required_action == "INHIBITION"
    assert datts_rec.evidence_family == EvidenceFamily.CURATED_REFERENCE
