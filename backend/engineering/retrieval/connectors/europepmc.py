"""EuropePMCConnector — queries Europe PMC for scientific literature.

Europe PMC is a free, open bibliographic database indexing PubMed-indexed
articles (source=MED), PMC full-text, preprints (source=PPR), and other
biomedical literature. No authentication required.

API: https://www.ebi.ac.uk/europepmc/webservices/rest/search
Rate limit: 10 req/sec (IP-based, no key required, no auth headers).

Live-verified against Thalidomide/Multiple Myeloma and Sildenafil/PAH.
Key findings:
- resultType=core returns abstractText inline — no separate fetch per record
- abstract field name: 'abstractText' (confirmed)
- identifier fields: 'pmid' (string), 'doi' (no https://doi.org/ prefix), 'id'
- source field: 'MED'=PubMed-indexed, 'PPR'=preprint, 'PMC'=PMC-only
- Preprint records (source=PPR) have doi but NO pmid
- 65% overlap with PubMed top-20 for the same query — genuinely additive
- abstractText contains Greek/Unicode chars — httpx returns str correctly

Reference: Implementation plan Part 1 — Source A findings
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType, ERW_BASE_WEIGHTS
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_DEFAULT_MAX_RESULTS = 20


class EuropePMCConnector(BaseConnector):
    """Connector for the Europe PMC REST API.

    Fetches literature evidence inline (abstract included in core response).
    Evidence type: LITERATURE, ERW base weight 0.65 (same tier as
    OpenAlex and Semantic Scholar — literature citation quality).

    citation_key precedence: DOI > PMID > Europe PMC internal id
    This matches the precedence established for OpenAlex/S2.
    """

    source_name = "europepmc"
    base_url = _EPMC_BASE
    timeout_seconds = 25.0

    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw search results from Europe PMC.

        Satisfies BaseConnector abstract contract. Delegates to the
        /search endpoint using 'query' and optional 'page_size' kwargs.

        Args:
            **kwargs: Accepts 'query' (str) and 'page_size' (int).

        Returns:
            Raw JSON payload from Europe PMC.
        """
        params: dict[str, Any] = {
            "query": kwargs.get("query", ""),
            "format": "json",
            "resultType": "core",
            "pageSize": min(int(kwargs.get("page_size", _DEFAULT_MAX_RESULTS)), 50),
        }
        url = f"{self.base_url}/search"
        return await self._get(url, params=params)

    async def fetch_literature(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> list[Evidence]:
        """Fetch literature evidence for a drug-disease pair from Europe PMC.

        Args:
            drug_name: Drug name to search.
            disease_name: Disease name to search.
            hypothesis_id: UUID of the owning hypothesis (for provenance).
            max_results: Maximum number of records to return.

        Returns:
            List of Evidence records. Empty list on failure (graceful
            degradation — Europe PMC failure does not halt the pipeline).

        sources_failed vs sources_queried contract:
            - Exception raised → caller marks as failed
            - Empty list returned without exception → caller marks as queried
              with zero results (NOT failed)
        """
        from backend.core.exceptions import SourceUnavailableError

        query = f"{drug_name} AND {disease_name}"
        params: dict[str, Any] = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": min(max_results, 50),
        }
        url = f"{self.base_url}/search"

        try:
            data = await self._get(url, params=params)
        except SourceUnavailableError:
            logger.warning(
                "europepmc_unavailable",
                extra={"drug": drug_name, "disease": disease_name},
            )
            raise
        except Exception as exc:
            logger.warning(
                "europepmc_fetch_error",
                extra={"drug": drug_name, "disease": disease_name, "error": str(exc)},
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=3,
            ) from exc

        results = data.get("resultList", {}).get("result", [])
        evidence_records: list[Evidence] = []

        for record in results[:max_results]:
            ev = self._parse_record(record, drug_name, disease_name)
            if ev is not None:
                evidence_records.append(ev)

        logger.info(
            "europepmc_fetch_complete",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "hit_count": data.get("hitCount", 0),
                "records_returned": len(evidence_records),
            },
        )
        return evidence_records

    def _parse_record(
        self,
        record: dict[str, Any],
        drug_name: str,
        disease_name: str,
    ) -> Evidence | None:
        """Parse a single Europe PMC result record into an Evidence object.

        citation_key precedence (confirmed from live responses):
            1. DOI — present on most MED and PPR records (without https://doi.org/ prefix)
            2. PMID — present on MED (PubMed-indexed) records
            3. Europe PMC internal id — always present (== pmid for MED records)

        Source codes:
            MED = PubMed-indexed
            PMC = PMC-only (has PMC ID, may have PMID)
            PPR = preprint (has DOI, no PMID)
            PAT = patent (skip)
        """
        try:
            source = record.get("source", "")
            # Skip patents — not relevant as biomedical evidence
            if source == "PAT":
                return None

            title = record.get("title") or "Untitled"
            abstract = record.get("abstractText") or ""
            pmid = record.get("pmid") or ""
            doi = record.get("doi") or ""
            epmc_id = record.get("id") or ""
            pub_year_raw = record.get("pubYear") or "2000"

            # citation_key: DOI > PMID > EPMC internal id
            if doi:
                citation_key = f"doi:{doi}"
            elif pmid:
                citation_key = f"PMID:{pmid}"
            elif epmc_id:
                citation_key = f"epmc:{epmc_id}"
            else:
                return None  # no usable identifier — drop

            # Provenance record_id: prefer PMID, fallback to EPMC id
            record_id = pmid or epmc_id or citation_key
            url_str: str | None = None
            if pmid:
                url_str = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif doi:
                url_str = f"https://doi.org/{doi}"
            elif epmc_id:
                url_str = f"https://europepmc.org/article/{source}/{epmc_id}"

            provenance = ProvenanceReference(
                source_name="europepmc",
                source_version="2024",
                record_id=record_id,
                url=url_str,
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
            logger.debug("europepmc_parse_error", extra={"error": str(exc)})
            return None
