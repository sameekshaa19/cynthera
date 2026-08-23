"""Unit tests for ReactomeConnector."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from backend.engineering.retrieval.connectors.reactome import ReactomeConnector


@pytest.mark.asyncio
async def test_reactome_headers_override():
    """Verify custom User-Agent is set in _build_headers."""
    connector = ReactomeConnector()
    headers = connector._build_headers()
    assert "User-Agent" in headers
    assert "CYNTHERA-Research" in headers["User-Agent"]


@pytest.mark.asyncio
async def test_reactome_fetch_success():
    """Verify fetch returns pathways list."""
    mock_payload = [
        {"stId": "R-HSA-418457", "displayName": "cGMP effects"},
    ]
    with patch.object(ReactomeConnector, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_payload
        async with ReactomeConnector() as conn:
            res = await conn.fetch("O76074")
            assert "pathways" in res
            assert len(res["pathways"]) == 1
            assert res["pathways"][0]["stId"] == "R-HSA-418457"
            mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_reactome_fetch_participants_extracts_uniprot_ids():
    """Verify fetch_participants extracts UniProt accessions from refEntities."""
    mock_payload = [
        {
            "peDbId": 1234,
            "refEntities": [
                {
                    "schemaClass": "ReferenceGeneProduct",
                    "identifier": "Q13976",
                },
                {
                    "schemaClass": "ReferenceIsoform",
                    "identifier": "Q13237-1",
                },
                {
                    "schemaClass": "ReferenceDNASequence",
                    "identifier": "NON_PROTEIN",
                },
            ],
        }
    ]
    with patch.object(ReactomeConnector, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_payload
        async with ReactomeConnector() as conn:
            res = await conn.fetch_participants("R-HSA-418457")
            assert "uniprot_ids" in res
            assert res["uniprot_ids"] == ["Q13976", "Q13237"]
