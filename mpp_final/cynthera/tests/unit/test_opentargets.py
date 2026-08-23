"""Unit tests for OpenTargetsConnector."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector


@pytest.mark.asyncio
async def test_opentargets_resolve_mondo_id():
    mock_search_resp = {
        "data": {
            "search": {
                "hits": [
                    {"id": "MONDO_0009693", "name": "plasma cell myeloma", "entity": "disease"},
                    {"id": "MONDO_0005235", "name": "smoldering plasma cell myeloma", "entity": "disease"},
                ]
            }
        }
    }

    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_search_resp

        mondo_id = await connector.resolve_mondo_id("Multiple Myeloma")
        assert mondo_id == "MONDO_0009693"


@pytest.mark.asyncio
async def test_opentargets_fetch_associations():
    mock_assoc_resp = {
        "data": {
            "disease": {
                "id": "MONDO_0009693",
                "name": "plasma cell myeloma",
                "associatedTargets": {
                    "count": 500,
                    "rows": [
                        {
                            "target": {
                                "id": "ENSG00000113851",
                                "approvedSymbol": "CRBN",
                                "proteinIds": [
                                    {"id": "Q96SW2", "source": "uniprot_swissprot"}
                                ],
                            },
                            "score": 0.684564,
                        },
                        {
                            "target": {
                                "id": "ENSG00000048462",
                                "approvedSymbol": "TNFRSF17",
                                "proteinIds": [],
                            },
                            "score": 0.680125,
                        },
                    ],
                },
            }
        }
    }

    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_assoc_resp

        gene_scores = await connector.fetch_associations("MONDO_0009693", page_size=10)
        assert gene_scores.get("CRBN") == 0.684564
        assert gene_scores.get("Q96SW2") == 0.684564
        assert gene_scores.get("TNFRSF17") == 0.680125
