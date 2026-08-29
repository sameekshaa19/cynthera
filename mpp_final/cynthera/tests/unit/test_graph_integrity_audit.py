"""Unit tests for GraphIntegrityAuditor.

Validates all 12 architectural observability properties:
1. Audit counts actual graph nodes rather than RetrievalPackage counts.
2. Audit counts actual graph edges.
3. Audit correctly groups relationship types.
4. PARTICIPATES_IN is reported with UNKNOWN direction.
5. Unresolved identifiers are reported.
6. Canonical matching is distinguished from raw matching.
7. Isolated nodes are detected.
8. Partial path depth is reported.
9. Complete path count is reported.
10. Root-cause classification is based on observed graph state.
11. The audit does not modify the EvidenceGraph.
12. Generic test fixtures without hardcoded real entities.
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.target import Target
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.identifier import ResolvedIdentifierSet
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierMapping,
    BiologicalDirection,
)
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraphBuilder,
    EvidenceGraph,
    GraphNode,
    GraphEdge,
    _NODE_DRUG,
    _NODE_TARGET,
    _NODE_PATHWAY,
    _NODE_GENE,
    _NODE_DISEASE,
)
from backend.reasoning.mechanistic.graph_integrity_audit import (
    GraphIntegrityAuditor,
    GraphGapDiagnosis,
)


@pytest.fixture
def sample_package() -> RetrievalPackage:
    drug = Drug(name="TestDrug", chembl_id="CHEMBL100", identifiers=ResolvedIdentifierSet(entity_name="TestDrug", entity_type="drug"))
    disease = Disease(name="TestDisease", identifiers=ResolvedIdentifierSet(entity_name="TestDisease", entity_type="disease"))
    protein = Protein(name="Protein A", uniprot_accession="P99100", gene_symbol="GENE_A", organism="Homo sapiens")
    prov = ProvenanceReference(source_name="ChEMBL", source_version="v33", record_id="r1", url="http://chembl.org")
    target = Target(
        drug_chembl_id="CHEMBL100",
        protein_uniprot="P99100",
        affinity_nm=5.0,
        affinity_type="IC50",
        mechanism="INHIBITOR",
        erw=ERW.from_base(1.0),
        provenance=prov,
    )
    pathway = Pathway(reactome_id="R-TEST-900", name="Cascade A", participant_uniprot_ids=["P99100", "P99200"])
    mapping1 = BiologicalIdentifierMapping(canonical_symbol="GENE_A", uniprot_accession="P99100", source="OpenTargets", score=0.8)
    mapping2 = BiologicalIdentifierMapping(canonical_symbol="GENE_B", uniprot_accession="P99200", source="Reactome", score=0.7)

    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        identifier_mappings=[mapping1, mapping2],
        validated_disease_genes={"GENE_A": 0.8, "GENE_B": 0.7},
    )


def test_1_and_2_audit_counts_actual_graph_nodes_and_edges(sample_package):
    """Property 1 & 2: Audit counts actual graph nodes and edges rather than assuming from package."""
    auditor = GraphIntegrityAuditor()
    report = auditor.audit(sample_package)

    assert report.total_graph_nodes > 0
    assert report.total_graph_edges > 0
    assert report.graph_nodes_by_type[_NODE_DRUG] == 1
    assert report.graph_nodes_by_type[_NODE_DISEASE] == 1
    assert report.graph_nodes_by_type[_NODE_TARGET] == 1
    assert report.graph_nodes_by_type[_NODE_PATHWAY] == 1


def test_3_and_4_groups_relationships_and_preserves_unknown_direction(sample_package):
    """Properties 3 & 4: Audit groups relationship types and reports PARTICIPATES_IN as UNKNOWN direction."""
    auditor = GraphIntegrityAuditor()
    report = auditor.audit(sample_package)

    participates_in_group = next(
        (eg for eg in report.edge_groups if eg.relationship_type == "PARTICIPATES_IN"),
        None,
    )
    assert participates_in_group is not None
    assert participates_in_group.direction == "UNKNOWN"
    assert participates_in_group.source_type == _NODE_TARGET
    assert participates_in_group.target_type == _NODE_PATHWAY


def test_5_and_6_reports_canonical_vs_raw_matching(sample_package):
    """Properties 5 & 6: Audit calculates raw vs canonical matching and tracks resolution rate."""
    auditor = GraphIntegrityAuditor()
    report = auditor.audit(sample_package)

    assert report.resolution_rate == 1.0
    assert report.unresolved == 0
    assert report.canonical_matching >= report.raw_matching


def test_7_detects_isolated_nodes():
    """Property 7: Isolated nodes (with in-degree or out-degree == 0) are detected."""
    graph = EvidenceGraph()
    graph.add_node(GraphNode(id="DRUG:D1", label=_NODE_DRUG, name="D1"))
    graph.add_node(GraphNode(id="DISEASE:Dis1", label=_NODE_DISEASE, name="Dis1"))
    graph.add_node(GraphNode(id="TARGET:T_ISOLATED", label=_NODE_TARGET, name="T_ISOLATED"))
    graph.add_node(GraphNode(id="PATHWAY:P_ISOLATED", label=_NODE_PATHWAY, name="P_ISOLATED"))

    # Connect only Drug -> Disease directly (leaving Target and Pathway isolated)
    graph.add_edge(GraphEdge(source_id="DRUG:D1", target_id="DISEASE:Dis1", predicate="ASSOCIATED_WITH", evidence_strength=0.5, source="Test"))

    drug = Drug(name="D1", identifiers=ResolvedIdentifierSet(entity_name="D1", entity_type="drug"))
    disease = Disease(name="Dis1", identifiers=ResolvedIdentifierSet(entity_name="Dis1", entity_type="disease"))
    pkg = RetrievalPackage(hypothesis_id=uuid.uuid4(), drug=drug, disease=disease)

    auditor = GraphIntegrityAuditor()
    report = auditor.audit(pkg, graph=graph)

    assert "T_ISOLATED" in report.isolated_nodes["Targets"]
    assert "P_ISOLATED" in report.isolated_nodes["Pathways"]


def test_8_and_9_reports_path_depths_and_complete_paths(sample_package):
    """Properties 8 & 9: Audit accurately counts partial path depths and complete paths."""
    auditor = GraphIntegrityAuditor()
    report = auditor.audit(sample_package)

    assert report.depth_1_paths >= 1
    assert report.complete_paths >= 1
    assert report.shortest_path_len >= 4  # Drug -> Target -> Gene -> Disease


def test_10_root_cause_diagnosis_on_observed_graph_state():
    """Property 10: Root-cause diagnosis is strictly data-driven based on observed graph state."""
    drug = Drug(name="EmptyDrug", identifiers=ResolvedIdentifierSet(entity_name="EmptyDrug", entity_type="drug"))
    disease = Disease(name="EmptyDisease", identifiers=ResolvedIdentifierSet(entity_name="EmptyDisease", entity_type="disease"))
    empty_pkg = RetrievalPackage(hypothesis_id=uuid.uuid4(), drug=drug, disease=disease)

    auditor = GraphIntegrityAuditor()
    report = auditor.audit(empty_pkg)

    assert report.diagnosis == GraphGapDiagnosis.RETRIEVAL_GAP
    assert "0 targets" in report.diagnosis_evidence


def test_11_audit_does_not_modify_evidence_graph(sample_package):
    """Property 11: GraphIntegrityAuditor is strictly read-only and does not mutate graph nodes or edges."""
    builder = EvidenceGraphBuilder()
    graph, _ = builder.build(sample_package)

    nodes_before = len(graph.nodes)
    edges_before = len(graph.edges)

    auditor = GraphIntegrityAuditor()
    report = auditor.audit(sample_package, graph=graph)

    assert len(graph.nodes) == nodes_before
    assert len(graph.edges) == edges_before
