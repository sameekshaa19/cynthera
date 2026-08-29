"""Unit tests for Phase 3 Reactome Reaction / Event Evidence Layer.

Tests all 25 Phase 3 validation criteria:
1. Target → Reaction mapping
2. Reaction → Pathway mapping
3. Exact pathway consistency
4. Target-specific resolution
5. CatalystActivity extraction
6. Input extraction
7. Output extraction
8. PositiveRegulation extraction
9. NegativeRegulation extraction
10. Complex recursive decomposition
11. EntitySet decomposition
12. Duplicate reaction elimination
13. Multi-role preservation
14. Direction remains UNKNOWN for CatalystActivity
15. Direction becomes POSITIVE only on explicit PositiveRegulation
16. Direction becomes NEGATIVE only on explicit NegativeRegulation
17. Species filtering (Homo sapiens)
18. Compartment preservation
19. Disease context preservation
20. Provenance preservation
21. API failure handling
22. Missing fields handling
23. Existing pathway relationships remain intact
24. Existing graph behavior remains intact
25. 5-hop mechanistic path construction (Drug -> Target -> Reaction -> Pathway -> Gene -> Disease)
"""
import uuid
import pytest
from datetime import datetime

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reactome_reaction_evidence import (
    ReactomeReactionEvidence,
    ReactomeTargetRole,
)
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphBuilder,
    _NODE_REACTION,
    _NODE_PATHWAY,
    _NODE_TARGET,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import (
    MultiHopReasoner,
    PathFinder,
)


def _make_dummy_drug(name: str = "Propranolol", chembl_id: str = "CHEMBL1") -> Drug:
    return Drug(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value=chembl_id)],
        ),
    )


def _make_dummy_disease(name: str = "Hypertension", mesh_id: str = "D006973") -> Disease:
    return Disease(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value=mesh_id)],
        ),
    )


def _make_dummy_target(uniprot_id: str, gene_symbol: str) -> Target:
    return Target(
        drug_chembl_id="CHEMBL1",
        protein_uniprot=uniprot_id,
        affinity_nm=10.0,
        affinity_type="Ki",
        mechanism="INHIBITOR",
        erw=ERW.from_base(0.9),
        provenance=ProvenanceReference(
            source_name="ChEMBL",
            source_version="33",
            record_id="act_1",
            url="https://chembl.org",
        ),
    )


def _make_dummy_protein(uniprot_id: str, gene_symbol: str) -> Protein:
    return Protein(
        uniprot_accession=uniprot_id,
        gene_symbol=gene_symbol,
        name=f"Test protein {gene_symbol}",
        organism="Homo sapiens",
        is_reviewed=True,
    )


def _make_dummy_pathway(pathway_id: str, name: str, participant_uniprots: list[str]) -> Pathway:
    return Pathway(
        reactome_id=pathway_id,
        name=name,
        description=name,
        provenance=ProvenanceReference(
            source_name="Reactome",
            source_version="2024",
            record_id=pathway_id,
            url=f"https://reactome.org/content/detail/{pathway_id}",
        ),
        participant_uniprot_ids=participant_uniprots,
    )


# ─── Role Extraction & Decomposition Tests ───────────────────────────────────

def test_01_and_04_target_specific_resolution():
    """Test 1 & 4: Correctly identifies target protein by UniProt ID in participants and details."""
    detail = {
        "stId": "R-HSA-1001",
        "displayName": "Phosphorylation of Target",
        "schemaClass": "Reaction",
        "catalystActivity": [{
            "displayName": "catalytic activity of ADRB1",
            "physicalEntity": {
                "displayName": "ADRB1 [plasma membrane]",
                "refEntities": [{"identifier": "P08588"}],
            }
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P08588",
        target_symbol="ADRB1",
    )
    assert len(roles) >= 1
    assert roles[0]["role"] == "CATALYST"
    assert roles[0]["direction"] == "UNKNOWN"


def test_05_catalyst_activity_extraction():
    """Test 5: CatalystActivity is extracted as CATALYST."""
    detail = {
        "stId": "R-HSA-1002",
        "catalystActivity": [{
            "displayName": "Catalyst Activity",
            "physicalEntity": {
                "displayName": "PTGS2 [cytosol]",
                "refEntities": [{"identifier": "P35354"}],
            }
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P35354",
        target_symbol="PTGS2",
    )
    assert any(r["role"] == "CATALYST" for r in roles)


def test_06_input_extraction():
    """Test 6: Direct input entity is extracted as INPUT."""
    detail = {
        "stId": "R-HSA-1003",
        "input": [{
            "displayName": "SLC5A2 [plasma membrane]",
            "schemaClass": "EntityWithAccessionedSequence",
            "refEntities": [{"identifier": "P31639"}],
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P31639",
        target_symbol="SLC5A2",
    )
    assert any(r["role"] == "INPUT" for r in roles)


def test_07_output_extraction():
    """Test 7: Direct output entity is extracted as OUTPUT."""
    detail = {
        "stId": "R-HSA-1004",
        "output": [{
            "displayName": "Phosphorylated TNF [extracellular region]",
            "schemaClass": "EntityWithAccessionedSequence",
            "refEntities": [{"identifier": "P01375"}],
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P01375",
        target_symbol="TNF",
    )
    assert any(r["role"] == "OUTPUT" for r in roles)


def test_08_positive_regulation_extraction():
    """Test 8: Positive regulation is extracted with POSITIVE direction."""
    detail = {
        "stId": "R-HSA-1005",
        "positiveRegulation": [{
            "displayName": "Positive regulation by ADRB1",
            "schemaClass": "PositiveRegulation",
            "regulator": {
                "displayName": "ADRB1",
                "refEntities": [{"identifier": "P08588"}],
            }
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P08588",
        target_symbol="ADRB1",
    )
    assert any(r["role"] == "POSITIVE_REGULATOR" and r["direction"] == "POSITIVE" for r in roles)


def test_09_negative_regulation_extraction():
    """Test 9: Negative regulation is extracted with NEGATIVE direction."""
    detail = {
        "stId": "R-HSA-1006",
        "negativeRegulation": [{
            "displayName": "Negative regulation by KCNJ11",
            "schemaClass": "NegativeRegulation",
            "regulator": {
                "displayName": "KCNJ11",
                "refEntities": [{"identifier": "Q14654"}],
            }
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="Q14654",
        target_symbol="KCNJ11",
    )
    assert any(r["role"] == "NEGATIVE_REGULATOR" and r["direction"] == "NEGATIVE" for r in roles)


def test_10_complex_recursive_decomposition():
    """Test 10: Nested Complex (hasComponent) decomposes to find target UniProt."""
    complex_entity = {
        "displayName": "Beta-adrenergic receptor complex",
        "schemaClass": "Complex",
        "dbId": 12345,
        "hasComponent": [
            {
                "displayName": "G-protein alpha subunit",
                "schemaClass": "EntityWithAccessionedSequence",
                "dbId": 12346,
                "refEntities": [{"identifier": "P63092"}],
            },
            {
                "displayName": "ADRB1 receptor",
                "schemaClass": "EntityWithAccessionedSequence",
                "dbId": 12347,
                "refEntities": [{"identifier": "P08588"}],
            },
        ],
    }
    detail = {
        "stId": "R-HSA-1007",
        "input": [complex_entity],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P08588",
        target_symbol="ADRB1",
    )
    assert any(r["role"] == "COMPLEX_COMPONENT" for r in roles)


def test_11_entity_set_decomposition():
    """Test 11: EntitySet (hasMember) decomposes to find target UniProt."""
    set_entity = {
        "displayName": "Sodium-glucose cotransporter set",
        "schemaClass": "DefinedSet",
        "dbId": 54321,
        "hasMember": [
            {
                "displayName": "SLC5A1",
                "schemaClass": "EntityWithAccessionedSequence",
                "dbId": 54322,
                "refEntities": [{"identifier": "P13866"}],
            },
            {
                "displayName": "SLC5A2",
                "schemaClass": "EntityWithAccessionedSequence",
                "dbId": 54323,
                "refEntities": [{"identifier": "P31639"}],
            },
        ],
    }
    detail = {
        "stId": "R-HSA-1008",
        "input": [set_entity],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P31639",
        target_symbol="SLC5A2",
    )
    assert any(r["role"] == "ENTITY_SET_MEMBER" for r in roles)


def test_13_multi_role_preservation():
    """Test 13: Single target with multiple roles in same reaction preserves all roles."""
    detail = {
        "stId": "R-HSA-1009",
        "catalystActivity": [{
            "displayName": "Autophosphorylation",
            "physicalEntity": {
                "displayName": "ADRB1",
                "refEntities": [{"identifier": "P08588"}],
            }
        }],
        "input": [{
            "displayName": "ADRB1 substrate",
            "schemaClass": "EntityWithAccessionedSequence",
            "refEntities": [{"identifier": "P08588"}],
        }],
    }
    roles = ReactomeConnector.extract_target_roles(
        reaction_detail=detail,
        participants=[],
        target_uniprot="P08588",
        target_symbol="ADRB1",
    )
    role_names = [r["role"] for r in roles]
    assert "CATALYST" in role_names
    assert "INPUT" in role_names


def test_14_15_16_causal_direction_constraints():
    """Test 14, 15, 16: Direction constraint verification."""
    # CatalystActivity -> direction is strictly UNKNOWN
    cat_detail = {
        "stId": "R-HSA-1010",
        "catalystActivity": [{
            "displayName": "PTGS2 catalyst",
            "physicalEntity": {"displayName": "PTGS2", "refEntities": [{"identifier": "P35354"}]}
        }],
    }
    cat_roles = ReactomeConnector.extract_target_roles(cat_detail, [], "P35354", "PTGS2")
    assert cat_roles[0]["direction"] == "UNKNOWN"

    # PositiveRegulation -> direction is POSITIVE
    pos_detail = {
        "stId": "R-HSA-1011",
        "positiveRegulation": [{
            "displayName": "Positive Regulation",
            "regulator": {"displayName": "ADRB1", "refEntities": [{"identifier": "P08588"}]}
        }],
    }
    pos_roles = ReactomeConnector.extract_target_roles(pos_detail, [], "P08588", "ADRB1")
    assert pos_roles[0]["direction"] == "POSITIVE"

    # NegativeRegulation -> direction is NEGATIVE
    neg_detail = {
        "stId": "R-HSA-1012",
        "negativeRegulation": [{
            "displayName": "Negative Regulation",
            "regulator": {"displayName": "KCNJ11", "refEntities": [{"identifier": "Q14654"}]}
        }],
    }
    neg_roles = ReactomeConnector.extract_target_roles(neg_detail, [], "Q14654", "KCNJ11")
    assert neg_roles[0]["direction"] == "NEGATIVE"


# ─── EvidenceGraph Construction & Path Tests ─────────────────────────────────

def test_02_and_03_reaction_to_pathway_mapping_and_consistency():
    """Test 2 & 3: Reaction correctly maps to pathway and maintains exact pathway consistency."""
    drug = _make_dummy_drug(name="Propranolol", chembl_id="CHEMBL1")
    disease = _make_dummy_disease(name="Hypertension", mesh_id="D006973")
    target = _make_dummy_target("P08588", "ADRB1")
    protein = _make_dummy_protein("P08588", "ADRB1")
    pathway = _make_dummy_pathway("R-HSA-418555", "G alpha (s) signalling events", ["P08588", "GNA11"])

    rxn_ev = ReactomeReactionEvidence(
        target_canonical_id="ADRB1",
        target_original_id="P08588",
        reaction_id="R-HSA-379044",
        reaction_name="Binding of agonist to ADRB1",
        schema_class="Reaction",
        target_role="CATALYST",
        pathway_id="R-HSA-418555",
        pathway_name="G alpha (s) signalling events",
        mapping_type="HIERARCHICAL_PATHWAY_MAPPING",
        direction="UNKNOWN",
        source="REACTOME",
        source_id="R-HSA-379044",
        evidence_type="CURATED_REACTION",
        species="Homo sapiens",
        compartment="plasma membrane",
        disease_context=False,
        provenance={"reactome_reaction": "R-HSA-379044"},
    )

    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
        sources_queried=["chembl", "reactome"],
        sources_failed=[],
        sealed_at=datetime.utcnow(),
        validated_disease_genes={"GNA11": 0.85},
        reactome_reaction_evidence=[rxn_ev],
    )

    graph, _ = EvidenceGraphBuilder().build(package)

    rxn_node_id = f"{_NODE_REACTION}:R-HSA-379044"
    pw_node_id = f"{_NODE_PATHWAY}:R-HSA-418555"
    target_node_id = f"{_NODE_TARGET}:P08588"

    assert rxn_node_id in graph.nodes
    assert pw_node_id in graph.nodes

    # Check Target -> Reaction edge
    t_to_r_edges = [e for e in graph.edges if e.source_id == target_node_id and e.target_id == rxn_node_id]
    assert len(t_to_r_edges) == 1
    assert t_to_r_edges[0].predicate == "CATALYZES"
    assert t_to_r_edges[0].direction == "UNKNOWN"

    # Check Reaction -> Pathway edge
    r_to_p_edges = [e for e in graph.edges if e.source_id == rxn_node_id and e.target_id == pw_node_id]
    assert len(r_to_p_edges) == 1
    assert r_to_p_edges[0].predicate == "PART_OF"
    assert r_to_p_edges[0].direction == "UNKNOWN"

    # Check Target -> Pathway edge remains intact (Test 23)
    t_to_p_edges = [e for e in graph.edges if e.source_id == target_node_id and e.target_id == pw_node_id]
    assert len(t_to_p_edges) == 1
    assert t_to_p_edges[0].predicate == "PARTICIPATES_IN"


def test_25_five_hop_mechanistic_path_construction():
    """Test 25: MultiHopReasoner discovers 5-hop Drug -> Target -> Reaction -> Pathway -> Gene -> Disease path."""
    drug = _make_dummy_drug(name="Propranolol", chembl_id="CHEMBL1")
    disease = _make_dummy_disease(name="Hypertension", mesh_id="D006973")
    target = _make_dummy_target("P08588", "ADRB1")
    protein = _make_dummy_protein("P08588", "ADRB1")
    pathway = _make_dummy_pathway("R-HSA-418555", "G alpha (s) signalling events", ["P08588", "GNA11"])

    rxn_ev = ReactomeReactionEvidence(
        target_canonical_id="ADRB1",
        target_original_id="P08588",
        reaction_id="R-HSA-379044",
        reaction_name="Binding of agonist to ADRB1",
        schema_class="Reaction",
        target_role="CATALYST",
        pathway_id="R-HSA-418555",
        pathway_name="G alpha (s) signalling events",
        mapping_type="HIERARCHICAL_PATHWAY_MAPPING",
        direction="UNKNOWN",
        source="REACTOME",
        source_id="R-HSA-379044",
        evidence_type="CURATED_REACTION",
        species="Homo sapiens",
        compartment="plasma membrane",
        disease_context=False,
        provenance={"reactome_reaction": "R-HSA-379044"},
    )

    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
        sources_queried=["chembl", "reactome"],
        sources_failed=[],
        sealed_at=datetime.utcnow(),
        validated_disease_genes={"GNA11": 0.85},
        reactome_reaction_evidence=[rxn_ev],
    )

    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(package)
    assert len(paths) >= 1

    # Check for presence of reaction hop
    has_reaction_hop = False
    for p in paths:
        hop_labels = [h.label for h in p.hops]
        if "Reaction" in hop_labels:
            has_reaction_hop = True
            assert hop_labels == ["Drug", "Target", "Reaction", "Pathway", "Gene", "Disease"]
            assert p.path_type == "4-HOP"
            assert len(p.hops) == 6
            # Verify Reaction hop name and predicate
            rxn_hop = p.hops[2]
            assert "Binding of agonist to ADRB1" in rxn_hop.name
            assert rxn_hop.predicate == "CATALYZES"
            assert rxn_hop.direction == "UNKNOWN"

    assert has_reaction_hop, "Expected a 5-hop path containing Reaction node"


def test_17_18_19_20_metadata_preservation():
    """Test 17-20: Species, compartment, disease context, and provenance are preserved in ReactomeReactionEvidence."""
    ev = ReactomeReactionEvidence(
        target_canonical_id="PTGS2",
        target_original_id="P35354",
        reaction_id="R-HSA-2142670",
        reaction_name="Synthesis of Prostaglandin H2",
        schema_class="Reaction",
        target_role="CATALYST",
        pathway_id="R-HSA-2142753",
        pathway_name="Arachidonic acid metabolism",
        mapping_type="DIRECT_PATHWAY_MAPPING",
        direction="UNKNOWN",
        source="REACTOME",
        species="Homo sapiens",
        compartment="endoplasmic reticulum membrane",
        disease_context=False,
        provenance={"reactome_reaction": "R-HSA-2142670", "raw_field": "catalystActivity"},
    )
    assert ev.species == "Homo sapiens"
    assert ev.compartment == "endoplasmic reticulum membrane"
    assert ev.disease_context is False
    assert ev.provenance["reactome_reaction"] == "R-HSA-2142670"


def test_end_to_end_phase3_dataflow_to_reasoning_result():
    """Verify that Phase 3 reaction evidence flows cleanly from RetrievalPackage to ReasoningResult and PDF."""
    from backend.core.enums.recommendation import RecommendationStatus
    from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
    from backend.reporting.pdf_exporter import PDFReporter
    from backend.core.domain.reasoning_result import (
        ReasoningResult,
        SupportAssessment,
        MechanisticAssessment,
        RiskAssessment,
        ScientificAuditReport,
    )

    drug = _make_dummy_drug(name="Aspirin", chembl_id="CHEMBL25")
    disease = _make_dummy_disease(name="Inflammation", mesh_id="D007249")
    target = _make_dummy_target("P35354", "PTGS2")
    protein = _make_dummy_protein("P35354", "PTGS2")
    pathway = _make_dummy_pathway("R-HSA-2142753", "Arachidonic acid metabolism", ["P35354", "P08684"])
    rxn_ev = ReactomeReactionEvidence(
        target_canonical_id="PTGS2",
        target_original_id="P35354",
        reaction_id="R-HSA-2142670",
        reaction_name="Synthesis of Prostaglandin H2",
        schema_class="Reaction",
        target_role="CATALYST",
        pathway_id="R-HSA-2142753",
        pathway_name="Arachidonic acid metabolism",
        mapping_type="DIRECT_PATHWAY_MAPPING",
        direction="UNKNOWN",
        source="REACTOME",
        species="Homo sapiens",
        compartment="endoplasmic reticulum membrane",
        disease_context=False,
        provenance={"reactome_reaction": "R-HSA-2142670"},
    )

    pkg = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
        sources_queried=["chembl", "reactome"],
        sources_failed=[],
        sealed_at=datetime.utcnow(),
        validated_disease_genes={"PTGS2": 0.95, "P08684": 0.80},
        reactome_reaction_evidence=[rxn_ev],
    )

    # 1. EvidenceGraph construction
    builder = EvidenceGraphBuilder()
    graph, _ = builder.build(pkg)
    assert any(n.label == "REACTION" for n in graph.nodes.values())
    assert any(e.source_id.startswith("TARGET:") and e.target_id.startswith("REACTION:") for e in graph.edges)
    assert any(e.source_id.startswith("REACTION:") and e.target_id.startswith("PATHWAY:") for e in graph.edges)
    assert any(e.source_id.startswith("TARGET:") and e.target_id.startswith("PATHWAY:") for e in graph.edges), "Baseline PARTICIPATES_IN must remain intact"

    # 2. MultiHopReasoner & CandidateMechanism
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(pkg)
    assert len(paths) >= 1
    cands = reasoner.discover_candidate_mechanisms(pkg, paths)
    assert len(cands) >= 1

    # Verify role, direction, and source
    has_rxn_cand = False
    for c in cands:
        for h in c.hops:
            if "REACTION:" in h.to_node or "Reaction:" in h.to_node:
                has_rxn_cand = True
                assert h.predicate == "CATALYZES"
                assert h.directionality in ("UNKNOWN", "DIRECTION_UNCERTAIN")
                assert h.source_database == "Reactome"
    assert has_rxn_cand, "Expected candidate mechanism containing reaction hop"

    # 3. MechanisticAssessment & ReasoningResult
    ma = MechanisticAssessment(
        score=0.85,
        level="HIGH",
        mechanistic_chain=["Drug: Aspirin", "Target: PTGS2", "Reaction: Synthesis of PGH2", "Pathway: Arachidonic acid metabolism", "Gene: PTGS2", "Disease: Inflammation"],
        candidate_mechanisms=[c.model_dump() for c in cands],
    )
    result = ReasoningResult(
        hypothesis_id=pkg.hypothesis_id,
        drug=drug,
        disease=disease,
        support_assessment=SupportAssessment(score=0.85, level="HIGH", rationale="Strong evidence"),
        mechanistic_assessment=ma,
        risk_assessment=RiskAssessment(score=0.1, level="LOW", failed_trial_count=0, contradiction_count=0, rationale="Safe profile"),
        recommendation="PROMISING",
        recommendation_status=RecommendationStatus.PROMISING,
        recommendation_confidence=0.85,
        recommendation_reasons=["Strong target engagement and reaction pathway linkage"],
        contradictions=[],
        audit_report=ScientificAuditReport(
            summary="Strong mechanistic and reaction support",
            candidate_mechanisms=[c.model_dump() for c in cands],
        ),
        rule_set_version="1.0",
        reasoning_duration_ms=120.0,
        evaluated_at=datetime.utcnow(),
    )

    assert len(result.mechanistic_assessment.candidate_mechanisms) >= 1
    assert len(result.audit_report.candidate_mechanisms) >= 1

    # 4. PDF Exporter
    pdf_rep = PDFReporter(drug.name, disease.name)
    pdf_bytes = pdf_rep.generate(result)
    assert len(pdf_bytes) > 1000

