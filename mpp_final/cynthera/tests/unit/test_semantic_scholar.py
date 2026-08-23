"""Unit tests for SemanticScholarConnector.

Tests:
- API key loading from parameter and environment variable
- Header formatting (x-api-key header set, no Authorization header)
- Rate limiting mechanism (verifying rate limit throttling < 1 req/sec)
- Fetching and parsing papers into Evidence objects
- Error handling and graceful fallback
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from backend.engineering.retrieval.connectors.semantic_scholar import (
    SemanticScholarConnector,
    _S2_BASE,
)
from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType


@pytest.fixture
def mock_s2_response() -> dict:
    """Mock JSON response payload from Semantic Scholar Graph API."""
    return {
        "total": 2,
        "offset": 0,
        "data": [
            {
                "paperId": "s2_paper_101",
                "title": "Sildenafil in Pulmonary Arterial Hypertension: A Review",
                "abstract": "Sildenafil exhibits potent PDE5 inhibition for treatment of PAH.",
                "year": 2022,
                "citationCount": 45,
                "influentialCitationCount": 12,
                "fieldsOfStudy": ["Medicine", "Pharmacology"],
                "isOpenAccess": True,
                "externalIds": {"DOI": "10.1016/j.jacc.2022.01.001"},
            },
            {
                "paperId": "s2_paper_102",
                "title": "Targeting PDE5 in Vascular Disease",
                "abstract": "Explores therapeutic mechanism of action of sildenafil.",
                "year": 2020,
                "citationCount": 15,
                "influentialCitationCount": 2,
                "fieldsOfStudy": ["Cardiology"],
                "isOpenAccess": False,
                "externalIds": {},
            },
        ],
    }


def test_init_with_explicit_api_key():
    """Test initializing connector with explicit API key."""
    connector = SemanticScholarConnector(api_key="test_s2_key_123")
    assert connector._api_key == "test_s2_key_123"


def test_init_with_env_api_key(monkeypatch):
    """Test initializing connector with SEMANTIC_SCHOLAR_API_KEY environment variable."""
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env_s2_key_999")
    connector = SemanticScholarConnector()
    assert connector._api_key == "env_s2_key_999"


def test_build_headers_with_api_key():
    """Test header formatting includes x-api-key and omits Authorization header."""
    connector = SemanticScholarConnector(api_key="my_secret_s2_key")
    headers = connector._build_headers()
    assert headers.get("x-api-key") == "my_secret_s2_key"
    assert "Authorization" not in headers
    assert headers.get("Accept") == "application/json"


def test_build_headers_without_api_key(monkeypatch):
    """Test header formatting without API key."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    connector = SemanticScholarConnector()
    headers = connector._build_headers()
    assert "x-api-key" not in headers
    assert "Authorization" not in headers
    assert headers.get("Accept") == "application/json"


@pytest.mark.asyncio
async def test_rate_limiter_delay():
    """Verify that rate limiter throttles rapid consecutive requests."""
    connector = SemanticScholarConnector(api_key="test_key")
    
    # Reset timestamp for deterministic test run
    SemanticScholarConnector._last_request_time = 0.0

    t0 = time.monotonic()
    await connector._rate_limit()
    t1 = time.monotonic()
    await connector._rate_limit()
    t2 = time.monotonic()

    # The second call must wait at least ~1.0 second due to the 1 req/sec rate limit interval
    elapsed_between_calls = t2 - t1
    assert elapsed_between_calls >= 0.9, f"Expected delay >= 0.9s, got {elapsed_between_calls:.3f}s"


@pytest.mark.asyncio
async def test_fetch_literature_success(mock_s2_response):
    """Test fetch_literature returns correctly parsed Evidence list."""
    hypothesis_id = uuid.uuid4()
    connector = SemanticScholarConnector(api_key="test_key")

    with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_s2_response
        records = await connector.fetch_literature("Sildenafil", "PAH", hypothesis_id)

    assert len(records) == 2
    rec1 = records[0]
    assert rec1.citation_key == "doi:10.1016/j.jacc.2022.01.001"
    assert rec1.title == "Sildenafil in Pulmonary Arterial Hypertension: A Review"
    assert rec1.evidence_type == EvidenceType.LITERATURE
    assert rec1.provenance.source_name == "semantic_scholar"
    assert "s2_paper_101" in rec1.provenance.url

    rec2 = records[1]
    assert rec2.citation_key == "s2:s2_paper_102"
    assert rec2.title == "Targeting PDE5 in Vascular Disease"


@pytest.mark.asyncio
async def test_fetch_literature_handles_error():
    """Test fetch_literature raises SourceUnavailableError on failure."""
    from backend.core.exceptions import SourceUnavailableError

    hypothesis_id = uuid.uuid4()
    connector = SemanticScholarConnector(api_key="test_key")

    with patch.object(connector, "_get", side_effect=Exception("API limit exceeded")):
        with pytest.raises(SourceUnavailableError):
            await connector.fetch_literature("Sildenafil", "PAH", hypothesis_id)
