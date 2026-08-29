"""Unit tests for Phase 1 (Relationship Representation) and Phase 2 (Identifier Normalization).

Validates all 10 required architectural properties:
1. Equivalent identifiers resolve to the same canonical entity.
2. Unresolved identifiers remain unresolved rather than fabricated.
3. Original identifiers and source provenance are preserved.
4. Duplicate raw identifiers resolving to one biological entity do not create duplicate canonical entities.
5. Disease genes and pathway participants use the same resolver.
6. PARTICIPATES_IN remains PARTICIPATES_IN.
7. PARTICIPATES_IN does not automatically receive ACTIVATES or INHIBITS direction.
8. A relationship can represent direction = UNKNOWN.
9. Canonical matching can reveal matches that raw string matching misses.
10. All properties remain generic without hardcoded entities.
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import MagicMock

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.protein import Protein
from backend.core.domain.gene import Gene
from backend.core.domain.pathway import Pathway
from backend.core.domain.target import Target
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.identifier import ResolvedIdentifierSet
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierType,
    BiologicalIdentifierMapping,
    CanonicalBiologicalIdentifier,
    BiologicalDirection,
    BiologicalRelationshipType,
)
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)
from backend.reasoning.normalization.normalization_audit import (
    calculate_matching_audit,
    build_package_normalization_audit,
)
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraphBuilder,
    build_validated_gene_scores,
    pathway_gene_symbols,
    GraphEdge,
    GraphNode,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import PathFinder


def test_1_equivalent_identifiers_resolve_to_same_canonical_entity():
    """Property 1: Equivalent identifiers (e.g. symbol vs UniProt) resolve to the same canonical symbol & ID."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="GENE_ALPHA",
        uniprot_accession="P99001",
        source="OpenTargets",
        score=0.9,
        original_identifiers=("GENE_ALPHA", "P99001"),
    )
    resolver = BiologicalIdentifierResolver(mappings=[mapping])

    res_symbol = resolver.resolve("GENE_ALPHA", "test_source")
    res_uniprot = resolver.resolve("P99001", "test_source")

    assert res_symbol.canonical_symbol == "GENE_ALPHA"
    assert res_uniprot.canonical_symbol == "GENE_ALPHA"
    assert res_symbol.canonical_identifier == "P99001"
    assert res_uniprot.canonical_identifier == "P99001"
    assert res_symbol.canonical_id == res_uniprot.canonical_id


def test_2_unresolved_identifiers_remain_unresolved():
    """Property 2: Unresolved identifiers are explicit (canonical_symbol=None), never fabricated."""
    resolver = BiologicalIdentifierResolver()

    res = resolver.resolve("UNKNOWN_ENTITY_XYZ", "test_source")
    assert res.canonical_symbol is None
    assert res.original_identifier == "UNKNOWN_ENTITY_XYZ"
    assert res.original_id == "UNKNOWN_ENTITY_XYZ"


def test_3_original_identifiers_and_provenance_preserved():
    """Property 3: Original identifier string and originating source are preserved exactly."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="GENE_BETA",
        uniprot_accession="P99002",
        source="Reactome",
        score=0.75,
        original_identifiers=("GENE_BETA", "P99002"),
    )
    resolver = BiologicalIdentifierResolver(mappings=[mapping])

    res = resolver.resolve("P99002", "Reactome")
    assert res.original_identifier == "P99002"
    assert res.source == "Reactome"
    assert res.canonical_symbol == "GENE_BETA"


def test_4_duplicate_identifiers_fold_without_duplicate_nodes():
    """Property 4: Multiple raw keys resolving to the same entity fold to max score without duplicate nodes."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="GENE_GAMMA",
        uniprot_accession="P99003",
        source="OpenTargets",
        score=0.85,
        original_identifiers=("GENE_GAMMA", "P99003"),
    )
    drug = Drug(name="DrugA", identifiers=ResolvedIdentifierSet(entity_name="DrugA", entity_type="drug"))
    disease = Disease(name="DiseaseA", identifiers=ResolvedIdentifierSet(entity_name="DiseaseA", entity_type="disease"))

    # Both gene symbol and UniProt accession are in validated_disease_genes
    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        identifier_mappings=[mapping],
        validated_disease_genes={"GENE_GAMMA": 0.40, "P99003": 0.85},
    )

    resolver = BiologicalIdentifierResolver(mappings=package.identifier_mappings)
    scores = build_validated_gene_scores(package, resolver=resolver)

    assert len(scores) == 1
    assert "GENE_GAMMA" in scores
    assert scores["GENE_GAMMA"] == 0.85  # Max score preserved


def test_5_disease_genes_and_pathway_participants_share_one_resolver():
    """Property 5: Disease genes and Reactome pathway participants use the same resolver instance."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="GENE_DELTA",
        uniprot_accession="P99004",
        source="OpenTargets",
        score=0.8,
        original_identifiers=("GENE_DELTA", "P99004"),
    )
    resolver = BiologicalIdentifierResolver(mappings=[mapping])

    pathway = Pathway(
        reactome_id="R-TEST-001",
        name="Test Pathway",
        participant_uniprot_ids=["P99004"],
    )

    pw_symbols = pathway_gene_symbols(pathway, resolver)
    assert pw_symbols == {"GENE_DELTA"}


def test_6_and_7_participates_in_remains_association_with_unknown_direction():
    """Properties 6 & 7: Target -> Pathway edge predicate is strictly PARTICIPATES_IN with direction = UNKNOWN."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="GENE_EPSILON",
        uniprot_accession="P99005",
        source="OpenTargets",
        score=0.8,
        original_identifiers=("GENE_EPSILON", "P99005"),
    )
    from backend.core.value_objects.erw import ERW
    from backend.core.value_objects.provenance import ProvenanceReference

    drug = Drug(name="DrugB", chembl_id="CHEMBL999", identifiers=ResolvedIdentifierSet(entity_name="DrugB", entity_type="drug"))
    disease = Disease(name="DiseaseB", identifiers=ResolvedIdentifierSet(entity_name="DiseaseB", entity_type="disease"))
    protein = Protein(name="Test Protein Epsilon", uniprot_accession="P99005", gene_symbol="GENE_EPSILON", organism="Homo sapiens")
    prov = ProvenanceReference(source_name="ChEMBL", source_version="v33", record_id="rec1", url="http://test")
    target = Target(
        drug_chembl_id="CHEMBL999",
        protein_uniprot="P99005",
        affinity_nm=10.0,
        affinity_type="IC50",
        mechanism="INHIBITOR",
        erw=ERW.from_base(1.0),
        provenance=prov,
    )
    pathway = Pathway(reactome_id="R-TEST-002", name="Test Cascade", participant_uniprot_ids=["P99005"])

    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        identifier_mappings=[mapping],
        validated_disease_genes={"GENE_EPSILON": 0.8},
    )

    builder = EvidenceGraphBuilder()
    graph, _ = builder.build(package)

    tp_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("PATHWAY:")]
    assert len(tp_edges) == 1
    edge = tp_edges[0]

    # Must be PARTICIPATES_IN
    assert edge.predicate == "PARTICIPATES_IN"
    assert edge.relationship_type == "PARTICIPATES_IN"
    # Direction MUST NOT be fabricated into ACTIVATES or INHIBITS
    assert edge.direction == "UNKNOWN"


def test_8_relationship_can_represent_explicit_direction_and_unknown():
    """Property 8: Drug->Target carries explicit direction while non-directional edges remain UNKNOWN."""
    edge_neg = GraphEdge(
        source_id="DRUG:Test",
        target_id="TARGET:P1",
        predicate="INHIBITOR",
        evidence_strength=0.9,
        source="ChEMBL",
        direction="NEGATIVE",
        relationship_type="INHIBITOR",
    )
    assert edge_neg.direction == "NEGATIVE"

    edge_unk = GraphEdge(
        source_id="TARGET:P1",
        target_id="PATHWAY:R1",
        predicate="PARTICIPATES_IN",
        evidence_strength=0.5,
        source="Reactome",
        direction="UNKNOWN",
        relationship_type="PARTICIPATES_IN",
    )
    assert edge_unk.direction == "UNKNOWN"


def test_9_canonical_matching_reveals_hidden_matches():
    """Property 9: Canonical matching resolves UniProt vs Symbol mismatches that raw comparison misses."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="GENE_ZETA",
        uniprot_accession="P99006",
        source="Reactome",
        original_identifiers=("GENE_ZETA", "P99006"),
    )
    drug = Drug(name="DrugC", identifiers=ResolvedIdentifierSet(entity_name="DrugC", entity_type="drug"))
    disease = Disease(name="DiseaseC", identifiers=ResolvedIdentifierSet(entity_name="DiseaseC", entity_type="disease"))
    pathway = Pathway(reactome_id="R-TEST-003", name="Pathway C", participant_uniprot_ids=["P99006"])

    # Disease gene stored as gene symbol ("GENE_ZETA"), pathway participant stored as UniProt ("P99006")
    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        pathways=[pathway],
        identifier_mappings=[mapping],
        validated_disease_genes={"GENE_ZETA": 0.85},
    )

    resolver = BiologicalIdentifierResolver(mappings=package.identifier_mappings)
    audit_res = calculate_matching_audit(package, resolver)

    assert audit_res["raw_match_count"] == 0  # "GENE_ZETA" != "P99006"
    assert audit_res["canonical_match_count"] == 1  # Both resolve to "GENE_ZETA"
    assert audit_res["new_matches_revealed"] == 1
