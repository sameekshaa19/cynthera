"""Unit tests for EuropePMCConnector."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType
from backend.engineering.retrieval.connectors.europepmc import EuropePMCConnector


@pytest.mark.asyncio
async def test_europepmc_fetch_literature_success():
    mock_response = {
        "hitCount": 100,
        "resultList": {
            "result": [
                {
                    "id": "123456",
                    "source": "MED",
                    "pmid": "123456",
                    "doi": "10.1000/182",
                    "title": "Test Title on Thalidomide in Multiple Myeloma",
                    "pubYear": "2024",
                    "abstractText": "This is a test abstract with Greek letters α and β.",
                },
                {
                    "id": "PPR789",
                    "source": "PPR",
                    "doi": "10.1101/2024.01.01.123456",
                    "title": "Preprint on Thalidomide Mechanism",
                    "pubYear": "2024",
                    "abstractText": "Preprint abstract content.",
                },
            ]
        },
    }

    connector = EuropePMCConnector()
    with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        import uuid
        hyp_id = uuid.uuid4()
        records = await connector.fetch_literature("Thalidomide", "Multiple Myeloma", hyp_id, max_results=10)

        assert len(records) == 2
        # Record 0 precedence: DOI preferred
        assert records[0].citation_key == "doi:10.1000/182"
        assert records[0].evidence_type == EvidenceType.LITERATURE
        assert "Greek letters α and β" in records[0].abstract

        # Record 1 (preprint, no PMID): DOI used
        assert records[1].citation_key == "doi:10.1101/2024.01.01.123456"
        assert records[1].provenance.source_name == "europepmc"
