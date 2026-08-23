"""Unit tests for source-provided biological identifier mapping preservation.

Validates that Open Targets and Reactome connectors preserve row-level paired
mappings without static tables, hardcoded lookups, or fabricated values.
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, patch

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.identifier import ResolvedIdentifierSet
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierMapping,
    BiologicalIdentifierType,
)
from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)


@pytest.mark.asyncio
async def test_1_opentargets_paired_identifiers():
    """TEST 1 — Open Targets paired identifiers: preserves exactly ONE biological mapping with symbol and UniProt."""
    mock_resp = {
        "data": {
            "disease": {
                "id": "MONDO_TEST_001",
                "associatedTargets": {
                    "count": 1,
                    "rows": [
                        {
                            "target": {
                                "approvedSymbol": "TESTGENE_A",
                                "proteinIds": [
                                    {"id": "PTEST001", "source": "uniprot_swissprot"}
                                ],
                            },
                            "score": 0.8,
                        }
                    ],
                },
            }
        }
    }

    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        scores, mappings = await connector.fetch_association_mappings("MONDO_TEST_001")

        assert len(mappings) == 1
        m = mappings[0]
        assert m.canonical_symbol == "TESTGENE_A"
        assert m.uniprot_accession == "PTEST001"
        assert m.score == 0.8
        assert m.source == "OpenTargets"
        assert "TESTGENE_A" in m.original_identifiers
        assert "PTEST001" in m.original_identifiers


@pytest.mark.asyncio
async def test_2_multiple_uniprot_ids_in_one_association():
    """TEST 2 — Multiple UniProt IDs in one association: two mappings pointing to the same symbol with same score."""
    mock_resp = {
        "data": {
            "disease": {
                "id": "MONDO_TEST_002",
                "associatedTargets": {
                    "count": 1,
                    "rows": [
                        {
                            "target": {
                                "approvedSymbol": "TESTGENE_B",
                                "proteinIds": [
                                    {"id": "PTEST002", "source": "uniprot_swissprot"},
                                    {"id": "PTEST003", "source": "uniprot_swissprot"},
                                ],
                            },
                            "score": 0.7,
                        }
                    ],
                },
            }
        }
    }

    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        scores, mappings = await connector.fetch_association_mappings("MONDO_TEST_002")

        assert len(mappings) == 2
        assert all(m.canonical_symbol == "TESTGENE_B" for m in mappings)
        assert all(m.score == 0.7 for m in mappings)
        accessions = {m.uniprot_accession for m in mappings}
        assert accessions == {"PTEST002", "PTEST003"}


@pytest.mark.asyncio
async def test_3_missing_symbol():
    """TEST 3 — Missing symbol: no fabricated gene symbol, uniprot_accession preserved, canonical_symbol=None."""
    mock_resp = {
        "data": {
            "disease": {
                "id": "MONDO_TEST_003",
                "associatedTargets": {
                    "count": 1,
                    "rows": [
                        {
                            "target": {
                                "approvedSymbol": None,
                                "proteinIds": [
                                    {"id": "PTEST004", "source": "uniprot_swissprot"}
                                ],
                            },
                            "score": 0.6,
                        }
                    ],
                },
            }
        }
    }

    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        scores, mappings = await connector.fetch_association_mappings("MONDO_TEST_003")

        assert len(mappings) == 1
        m = mappings[0]
        assert m.canonical_symbol is None
        assert m.uniprot_accession == "PTEST004"
        assert m.score == 0.6


@pytest.mark.asyncio
async def test_4_missing_uniprot():
    """TEST 4 — Missing UniProt: symbol preserved, no fabricated UniProt accession."""
    mock_resp = {
        "data": {
            "disease": {
                "id": "MONDO_TEST_004",
                "associatedTargets": {
                    "count": 1,
                    "rows": [
                        {
                            "target": {
                                "approvedSymbol": "TESTGENE_C",
                                "proteinIds": [],
                            },
                            "score": 0.5,
                        }
                    ],
                },
            }
        }
    }

    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        scores, mappings = await connector.fetch_association_mappings("MONDO_TEST_004")

        assert len(mappings) == 1
        m = mappings[0]
        assert m.canonical_symbol == "TESTGENE_C"
        assert m.uniprot_accession is None
        assert m.score == 0.5


@pytest.mark.asyncio
async def test_5_reactome_paired_identifier():
    """TEST 5 — Reactome paired identifier: extracts PTEST005 ↔ TESTGENE_D."""
    mock_resp = [
        {
            "peDbId": 9901,
            "displayName": "UniProt:PTEST005-1 TESTGENE_D",
            "schemaClass": "PhysicalEntity",
            "refEntities": [
                {
                    "identifier": "PTEST005-1",
                    "schemaClass": "ReferenceGeneProduct",
                    "displayName": "UniProt:PTEST005-1 TESTGENE_D",
                    "geneName": ["TESTGENE_D"],
                }
            ],
        }
    ]

    connector = ReactomeConnector()
    with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await connector.fetch_participants("R-TEST-001")

        assert "PTEST005" in res["uniprot_ids"]
        assert len(res["mappings"]) == 1
        m = res["mappings"][0]
        assert m.uniprot_accession == "PTEST005"
        assert m.canonical_symbol == "TESTGENE_D"
        assert m.source == "Reactome"


@pytest.mark.asyncio
async def test_6_reactome_without_gene_symbol():
    """TEST 6 — Reactome without gene symbol: UniProt preserved, gene symbol remains unresolved."""
    mock_resp = [
        {
            "peDbId": 9902,
            "displayName": "UniProt:PTEST006",
            "schemaClass": "PhysicalEntity",
            "refEntities": [
                {
                    "identifier": "PTEST006",
                    "schemaClass": "ReferenceGeneProduct",
                    "displayName": "UniProt:PTEST006",
                }
            ],
        }
    ]

    connector = ReactomeConnector()
    with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await connector.fetch_participants("R-TEST-002")

        assert "PTEST006" in res["uniprot_ids"]
        assert len(res["mappings"]) == 1
        m = res["mappings"][0]
        assert m.uniprot_accession == "PTEST006"
        assert m.canonical_symbol is None


def test_7_resolver_consumes_source_mappings():
    """TEST 7 — Resolver consumes source mappings: TESTGENE_A ↔ PTEST001 resolve to same canonical biological identity."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="TESTGENE_A",
        uniprot_accession="PTEST001",
        source="OpenTargets",
        score=0.85,
        original_identifiers=("TESTGENE_A", "PTEST001"),
    )

    drug = Drug(name="TestDrug", identifiers=ResolvedIdentifierSet(entity_name="TestDrug", entity_type="drug"))
    disease = Disease(name="TestDisease", identifiers=ResolvedIdentifierSet(entity_name="TestDisease", entity_type="disease"))

    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        identifier_mappings=[mapping],
        validated_disease_genes={"PTEST001": 0.85},
    )

    resolver = BiologicalIdentifierResolver(
        proteins=package.proteins,
        genes=package.genes,
        mappings=package.identifier_mappings,
    )

    res_symbol = resolver.resolve("TESTGENE_A", "test_query")
    res_uniprot = resolver.resolve("PTEST001", "test_query")

    assert res_symbol.canonical_symbol == "TESTGENE_A"
    assert res_uniprot.canonical_symbol == "TESTGENE_A"
    assert res_symbol.canonical_identifier == "PTEST001"
    assert res_uniprot.canonical_identifier == "PTEST001"
