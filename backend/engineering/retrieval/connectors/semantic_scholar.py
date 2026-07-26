"""Semantic Scholar Connector — queries the Semantic Scholar Graph API.

Semantic Scholar provides AI-curated research context, citation velocity,
and influential citation detection. Free API with no key required.

API: https://api.semanticscholar.org/graph/v1
Reference: 03_RETRIEVAL_SPECIFICATION.md, Phase 2 literature scan expansion
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import httpx

from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_S2_BASE = "https://api.semanticscholar.org/graph/v1"
_DEFAULT_TIMEOUT = 20.0
_MAX_RESULTS = 12


class SemanticScholarConnector(BaseConnector):
    """Connector for the Semantic Scholar Graph API.

    Fetches literature evidence enriched with:
    - Influential citation count (highly cited, high-quality papers)
    - Fields of study (to validate relevance)
    - Open access PDF availability

    No API key required for basic use (100 req/5min limit).
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Semantic Scholar connector.

        Args:
            api_key: Optional Semantic Scholar API key for higher rate limits.
        """
        self._api_key = api_key
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["x-api-key"] = api_key

    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw data from the Semantic Scholar API.

        Satisfies the ``BaseConnector`` abstract contract. Delegates to the
        ``/paper/search`` endpoint using ``query`` and optional ``limit``
        kwargs.

        Args:
            **kwargs: Accepts ``query`` (str) and ``limit`` (int).

        Returns:
            Raw JSON payload as returned by the Semantic Scholar API.
        """
        params: dict[str, Any] = {
            "query": kwargs.get("query", ""),
            "fields": (
                "paperId,title,abstract,year,citationCount,"
                "influentialCitationCount,fieldsOfStudy,isOpenAccess,externalIds"
            ),
            "limit": min(int(kwargs.get("limit", _MAX_RESULTS)), 20),
        }
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT, headers=self._headers
        ) as client:
            resp = await client.get(f"{_S2_BASE}/paper/search", params=params)
            resp.raise_for_status()
            return resp.json()

    async def fetch_literature(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
        max_results: int = _MAX_RESULTS,
    ) -> list[Evidence]:
        """Fetch literature evidence from Semantic Scholar.

        Args:
            drug_name: Drug name to search.
            disease_name: Disease name to search.
            hypothesis_id: UUID of the owning hypothesis.
            max_results: Maximum number of results.

        Returns:
            List of Evidence records.
        """
        query = f"{drug_name} {disease_name}"

        params: dict[str, Any] = {
            "query": query,
            "fields": (
                "paperId,title,abstract,year,citationCount,"
                "influentialCitationCount,fieldsOfStudy,isOpenAccess,externalIds"
            ),
            "limit": min(max_results, 20),
        }

        try:
            async with httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT, headers=self._headers
            ) as client:
                resp = await client.get(
                    f"{_S2_BASE}/paper/search",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning(
                "semantic_scholar_timeout",
                extra={"drug": drug_name, "disease": disease_name},
            )
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "semantic_scholar_http_error",
                extra={"status": exc.response.status_code},
            )
            return []
        except Exception as exc:
            logger.warning("semantic_scholar_fetch_error", extra={"error": str(exc)})
            return []

        papers = data.get("data") or []
        evidence_records: list[Evidence] = []

        for paper in papers[:max_results]:
            ev = self._parse_paper(paper, drug_name, disease_name, hypothesis_id)
            if ev is not None:
                evidence_records.append(ev)

        logger.info(
            "semantic_scholar_fetch_complete",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "records_returned": len(evidence_records),
            },
        )
        return evidence_records

    def _parse_paper(
        self,
        paper: dict[str, Any],
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> Evidence | None:
        """Parse a Semantic Scholar paper into an Evidence object."""
        try:
            title = paper.get("title") or "Untitled"
            abstract = paper.get("abstract") or ""
            pub_year = paper.get("year") or 2000
            citation_count = paper.get("citationCount") or 0
            influential_count = paper.get("influentialCitationCount") or 0

            # Extract DOI if available
            external_ids = paper.get("externalIds") or {}
            doi = external_ids.get("DOI") or external_ids.get("doi") or ""

            # Compute ERW with influential citation boost
            erw_value = self._compute_erw(
                citation_count=citation_count,
                influential_count=influential_count,
                pub_year=pub_year,
            )

            provenance = ProvenanceReference(
                source_name="semantic_scholar",
                source_url=(
                    f"https://doi.org/{doi}"
                    if doi
                    else f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"
                ),
                retrieved_at=datetime.utcnow(),
                raw_id=paper.get("paperId") or "",
            )

            return Evidence(
                hypothesis_id=hypothesis_id,
                title=title[:500],
                abstract=abstract[:2000],
                evidence_type=EvidenceType.LITERATURE,
                erw=ERW(value=erw_value),
                source="semantic_scholar",
                doi=doi[:200] if doi else None,
                publication_year=pub_year,
                provenance=provenance,
            )

        except Exception as exc:
            logger.debug("semantic_scholar_parse_error", extra={"error": str(exc)})
            return None

    def _compute_erw(
        self,
        citation_count: int,
        influential_count: int,
        pub_year: int,
    ) -> float:
        """Compute ERW with influential citation boost.

        Influential citations (papers that heavily cited this work) signal
        high scientific impact and receive an additional boost.
        """
        import math

        citation_score = 1.0 - math.exp(-0.008 * citation_count)
        influential_boost = min(0.2, influential_count * 0.02)
        age = max(0, datetime.utcnow().year - pub_year)
        recency_score = math.exp(-0.04 * age)

        erw = 0.5 * citation_score + influential_boost + 0.3 * recency_score
        return round(min(1.0, max(0.05, erw)), 4)
