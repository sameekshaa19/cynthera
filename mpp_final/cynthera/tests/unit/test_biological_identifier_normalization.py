"""Unit tests for BiologicalIdentifierResolver and NormalizationAudit.

Tests dynamic canonical resolution, classification, provenance preservation,
and generic normalization/matching audits without hardcoding drug/disease expectations.
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.protein import Protein
from backend.core.domain.gene import Gene
from backend.core.domain.pathway import Pathway
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierType,
    CanonicalBiologicalIdentifier,
)
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)
from backend.reasoning.normalization.normalization_audit import (
    audit_identifiers,
    build_package_normalization_audit,
    calculate_matching_audit,
)
from backend.reasoning.mechanistic.evidence_graph import (
    build_validated_gene_scores,
    pathway_gene_symbols,
)


def _make_sample_protein(accession: str = "P12345", symbol: str = "GENE1", name: str = "Test Protein") -> Protein:
    return Protein(
        uniprot_accession=accession,
        gene_symbol=symbol,
        name=name,
        organism="Homo sapiens",
        is_reviewed=True,
    )


def _make_sample_gene(symbol: str = "GENE2", ncbi_id: int = 1234, protein_ids: list[str] | None = None) -> Gene:
    return Gene(
        hgnc_symbol=symbol,
        ncbi_gene_id=ncbi_id,
        name=f"{symbol} test gene",
        protein_ids=protein_ids or ["Q98765"],
    )


def test_uniprot_and_symbol_resolve_to_same_identity():
    """Protein record creates bidirectional mapping so both symbol and accession resolve to same canonical entity."""
    prot = _make_sample_protein(accession="P99999", symbol="ALPHA1")
    resolver = BiologicalIdentifierResolver(proteins=[prot])

    res_symbol = resolver.resolve("ALPHA1", "test_source")
    res_uniprot = resolver.resolve("P99999", "test_source")

    assert res_symbol.canonical_symbol == "ALPHA1"
    assert res_uniprot.canonical_symbol == "ALPHA1"
    assert res_symbol.canonical_identifier == "P99999"
    assert res_uniprot.canonical_identifier == "P99999"
    assert res_symbol.identifier_type == BiologicalIdentifierType.GENE_SYMBOL
    assert res_uniprot.identifier_type == BiologicalIdentifierType.UNIPROT


def test_gene_entity_provides_dynamic_mapping():
    """Gene records dynamically map protein_ids to hgnc_symbol."""
    gene = _make_sample_gene(symbol="BETA2", protein_ids=["Q55555"])
    resolver = BiologicalIdentifierResolver(genes=[gene])

    res_acc = resolver.resolve("Q55555", "test_source")
    assert res_acc.canonical_symbol == "BETA2"
    assert res_acc.canonical_identifier == "Q55555"


def test_unresolved_uniprot_is_not_fabricated():
    """Unmapped UniProt accession is classified as UNIPROT with canonical_symbol=None."""
    resolver = BiologicalIdentifierResolver(proteins=[], genes=[])

    res = resolver.resolve("O00000", "test_source")
    assert res.identifier_type == BiologicalIdentifierType.UNIPROT
    assert res.canonical_symbol is None
    assert res.canonical_identifier == "O00000"
    assert res.original_identifier == "O00000"


def test_unmapped_gene_symbol_preserves_symbol():
    """Unmapped valid gene symbol retains itself as canonical_symbol and canonical_identifier."""
    resolver = BiologicalIdentifierResolver(proteins=[], genes=[])

    res = resolver.resolve("GAMMA3", "test_source")
    assert res.identifier_type == BiologicalIdentifierType.GENE_SYMBOL
    assert res.canonical_symbol == "GAMMA3"
    assert res.canonical_identifier == "GAMMA3"


def test_isoform_suffix_cleaning():
    """Isoform suffix like -1 or -2 is stripped during UniProt normalization."""
    prot = _make_sample_protein(accession="P11111", symbol="DELTA4")
    resolver = BiologicalIdentifierResolver(proteins=[prot])

    res = resolver.resolve("P11111-2", "test_source")
    assert res.canonical_symbol == "DELTA4"
    assert res.canonical_identifier == "P11111"


def test_provenance_and_score_retention():
    """Original identifier, source, and confidence are strictly preserved."""
    prot = _make_sample_protein(accession="P22222", symbol="EPSILON5")
    resolver = BiologicalIdentifierResolver(proteins=[prot])

    res = resolver.resolve("P22222-1", source="Open Targets", confidence=0.88)
    assert res.original_identifier == "P22222-1"
    assert res.source == "Open Targets"
    assert res.confidence == 0.88
    assert "P22222-1" in res.source_identifiers


def test_normalization_audit_metrics():
    """Normalization audit dynamically tracks total, classified, resolved, and canonical counts."""
    prot = _make_sample_protein(accession="P33333", symbol="ZETA6")
    resolver = BiologicalIdentifierResolver(proteins=[prot])

    raw_list = [
        ("ZETA6", "source_a"),
        ("P33333", "source_b"),
        ("Q00001", "source_c"),  # unmapped UniProt
        ("ETA7", "source_d"),    # unmapped symbol
    ]

    audit = audit_identifiers(raw_list, resolver)
    assert audit.total_identifiers == 4
    assert audit.gene_symbols == 2
    assert audit.uniprot_accessions == 2
    assert audit.other_identifiers == 0
    assert audit.resolved == 3  # ZETA6, P33333, ETA7
    assert audit.unresolved == 1  # Q00001
    assert audit.resolution_rate == 0.75


def test_package_canonical_matching_audit():
    """calculate_matching_audit detects newly discoverable matches between pathway and disease genes."""
    prot = _make_sample_protein(accession="P44444", symbol="THETA8")
    gene = _make_sample_gene(symbol="IOTA9", protein_ids=["P55555"])

    # Package where disease genes has UniProt 'P44444' and pathway has gene symbol 'THETA8'
    # Raw matching: 'P44444' vs 'P44444' would only match if exact strings match.
    # In this case: disease gene has 'P44444' (0.75), pathway participants has 'P44444'.
    # Also disease gene has 'IOTA9' (0.9), pathway has participant 'P55555'.
    from backend.core.value_objects.identifier import ResolvedIdentifierSet
    drug = Drug(name="TestDrug", identifiers=ResolvedIdentifierSet(entity_name="TestDrug", entity_type="drug"))
    disease = Disease(name="TestDisease", identifiers=ResolvedIdentifierSet(entity_name="TestDisease", entity_type="disease"))

    pathway = Pathway(
        reactome_id="R-HSA-1001",
        name="Test Pathway",
        participant_uniprot_ids=["P44444", "P55555"],
    )

    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        proteins=[prot],
        genes=[gene],
        pathways=[pathway],
        validated_disease_genes={
            "P44444": 0.75,  # UniProt key
            "IOTA9": 0.90,   # Symbol key
        },
    )

    resolver = BiologicalIdentifierResolver(proteins=package.proteins, genes=package.genes)
    scores = build_validated_gene_scores(package, resolver=resolver)

    assert "THETA8" in scores
    assert "IOTA9" in scores
    assert scores["THETA8"] == 0.75
    assert scores["IOTA9"] == 0.90

    pw_symbols = pathway_gene_symbols(pathway, resolver)
    assert "THETA8" in pw_symbols
    assert "IOTA9" in pw_symbols

    matching = calculate_matching_audit(package, resolver)
    assert matching["canonical_matches"] >= 2
