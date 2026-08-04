"""OpenAlex Connector — queries the OpenAlex API for scientific literature.

OpenAlex is a free, open bibliographic database with no API key required.
Returns Evidence records enriched with citation counts and venue information.

API: https://api.openalex.org/works
Reference: 03_RETRIEVAL_SPECIFICATION.md, Phase 2 literature scan expansion
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

import httpx

from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType, ERW_BASE_WEIGHTS
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"
_DEFAULT_TIMEOUT = 20.0
_MAX_RESULTS = 15


class OpenAlexConnector(BaseConnector):
    """Connector for the OpenAlex Open Science API.

    Fetches literature evidence for a drug-disease pair using full-text
    search. Evidence is enriched with citation count and open-access status.

    No API key required. Rate limit: 10 req/sec (polite pool with email).
    """

    def __init__(self, email: str | None = None) -> None:
        """Initialize the OpenAlex connector.

        Args:
            email: Optional contact email for the OpenAlex polite pool
                   (higher rate limits). Appended as ?mailto= parameter.
        """
        self._email = email or "research@cynthera.ai"
        self._base_params: dict[str, str] = {"mailto": self._email}

    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw data from the OpenAlex API.

        Satisfies the ``BaseConnector`` abstract contract. Delegates to the
        ``/works`` endpoint using ``query`` and optional ``limit`` kwargs.

        Args:
            **kwargs: Accepts ``query`` (str) and ``limit`` (int).

        Returns:
            Raw JSON payload as returned by the OpenAlex API.
        """
        params: dict[str, Any] = {
            **self._base_params,
            "search": kwargs.get("query", ""),
            "filter": "type:article",
            "sort": "cited_by_count:desc",
            "per-page": min(int(kwargs.get("limit", _MAX_RESULTS)), 25),
            "select": "id,doi,title,abstract_inverted_index,publication_year,cited_by_count,primary_location,open_access",
        }
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{_OPENALEX_BASE}/works", params=params)
            resp.raise_for_status()
            return resp.json()

    async def fetch_literature(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
        max_results: int = _MAX_RESULTS,
    ) -> list[Evidence]:
        """Fetch literature evidence from OpenAlex.

        Args:
            drug_name: Drug name to search for.
            disease_name: Disease name to search for.
            hypothesis_id: UUID of the owning hypothesis.
            max_results: Maximum number of results to return.

        Returns:
            List of Evidence records.
        """
        query = f"{drug_name} {disease_name} repurposing OR treatment OR mechanism"

        params: dict[str, Any] = {
            **self._base_params,
            "search": query,
            "filter": "type:article",
            "sort": "cited_by_count:desc",
            "per-page": min(max_results, 25),
            "select": "id,doi,title,abstract_inverted_index,publication_year,cited_by_count,primary_location,open_access",
        }

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{_OPENALEX_BASE}/works",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning(
                "openalex_timeout",
                extra={"drug": drug_name, "disease": disease_name},
            )
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "openalex_http_error",
                extra={"status": exc.response.status_code},
            )
            return []
        except Exception as exc:
            logger.warning("openalex_fetch_error", extra={"error": str(exc)})
            return []

        works = data.get("results", [])
        evidence_records: list[Evidence] = []

        for work in works[:max_results]:
            ev = self._parse_work(work, drug_name, disease_name, hypothesis_id)
            if ev is not None:
                evidence_records.append(ev)

        logger.info(
            "openalex_fetch_complete",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "records_returned": len(evidence_records),
            },
        )
        return evidence_records

    def _parse_work(
        self,
        work: dict[str, Any],
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> Evidence | None:
        """Parse a single OpenAlex work record into an Evidence object."""
        try:
            title = work.get("title") or "Untitled"
            doi = work.get("doi") or ""
            openalex_id = work.get("id") or ""
            pub_year = work.get("publication_year") or 2000
            cited_by = work.get("cited_by_count") or 0

            # Reconstruct abstract from inverted index
            abstract = self._reconstruct_abstract(
                work.get("abstract_inverted_index") or {}
            )

            # citation_key is required (min_length=1) — prefer DOI, fall back to OpenAlex ID
            if doi:
                citation_key = doi.replace("https://doi.org/", "doi:")
            elif openalex_id:
                citation_key = f"openalex:{openalex_id}"
            else:
                return None  # no usable identifier at all — drop the record

            provenance = ProvenanceReference(
                source_name="openalex",
                source_version="v1",
                record_id=openalex_id or citation_key,
                url=openalex_id or None,
                retrieved_at=datetime.utcnow(),
            )

            erw = ERW.from_base(base_weight=ERW_BASE_WEIGHTS["LITERATURE"])

            return Evidence(
                evidence_type=EvidenceType.LITERATURE,
                erw=erw,
                citation_key=citation_key,
                title=title[:500],
                abstract=abstract[:2000] if abstract else None,
                provenance=provenance,
            )

        except Exception as exc:
            logger.debug("openalex_parse_error", extra={"error": str(exc)})
            return None

    def _reconstruct_abstract(self, inverted_index: dict[str, list[int]]) -> str:
        """Reconstruct abstract text from OpenAlex inverted index format."""
        if not inverted_index:
            return ""
        try:
            word_positions: list[tuple[int, str]] = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            return " ".join(word for _, word in word_positions)
        except Exception:
            return ""

    def _compute_erw(self, cited_by: int, pub_year: int) -> float:
        """Compute Evidence Reliability Weight from citation count and year."""
        import math
        # Citation score: diminishing returns on citation count
        citation_score = 1.0 - math.exp(-0.01 * cited_by)
        # Recency score: publications within 10 years score higher
        age = max(0, datetime.utcnow().year - pub_year)
        recency_score = math.exp(-0.05 * age)
        # Combined: 60% citation, 40% recency
        erw = 0.6 * citation_score + 0.4 * recency_score
        return round(min(1.0, max(0.05, erw)), 4)
