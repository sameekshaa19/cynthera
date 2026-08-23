"""PubMedConnector — queries NCBI Entrez API for literature abstracts.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedConnector(BaseConnector):
    """Connector for PubMed/NCBI Entrez literature database.

    Fetches:
    - PMIDs for drug-disease literature via esearch
    - Abstract text via efetch
    """

    source_name = "pubmed"
    base_url = PUBMED_BASE
    timeout_seconds = 30.0

    async def fetch(self, drug_name: str, disease_name: str, max_results: int = 50) -> dict[str, Any]:
        """Search PubMed for literature on a drug-disease pair and fetch abstracts.

        Args:
            drug_name: Drug name to include in search query.
            disease_name: Disease name to include in search query.
            max_results: Maximum number of PMIDs to retrieve (default 50).

        Returns:
            Dict with 'pmids' list and 'abstracts' dict (pmid -> abstract text).
        """
        pmids = await self._search_pmids(drug_name, disease_name, max_results)
        abstracts: dict[str, str] = {}
        if pmids:
            abstracts = await self._fetch_abstracts(pmids[:20])  # limit to 20 abstracts
        return {"pmids": pmids, "abstracts": abstracts}

    async def _search_pmids(
        self,
        drug_name: str,
        disease_name: str,
        max_results: int,
    ) -> list[str]:
        """Run esearch to get PMIDs for a drug-disease query.

        Args:
            drug_name: Drug name.
            disease_name: Disease name.
            max_results: Maximum PMIDs to return.

        Returns:
            List of PMID strings.
        """
        url = f"{self.base_url}/esearch.fcgi"
        query = f"{drug_name}[Title/Abstract] AND {disease_name}[Title/Abstract]"
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        result = await self._get(url, params=params)
        return result.get("esearchresult", {}).get("idlist", [])

    async def _fetch_abstracts(self, pmids: list[str]) -> dict[str, str]:
        """Fetch abstract text for a list of PMIDs using efetch.

        Returns plain-text abstracts split per PMID.
        NOTE: efetch returns text/plain, NOT JSON — must NOT use _get().

        Args:
            pmids: List of PMID strings.

        Returns:
            Dict mapping pmid -> abstract text snippet.
        """
        if not pmids:
            return {}
        if not self._client:
            return {}

        url = f"{self.base_url}/efetch.fcgi"
        params: dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "text",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            full_text = response.text

            # Split the bulk response by PMID numeric marker lines (e.g. "\n\n1. ")
            # and assign the entire block to each pmid in order
            abstracts: dict[str, str] = {}
            # Simple approach: divide text roughly equally or assign full block
            # A more robust approach splits on "PMID- XXXXX" lines:
            import re
            blocks = re.split(r'\n\n\d+\.\s+', full_text)
            blocks = [b.strip() for b in blocks if b.strip()]
            for i, pmid in enumerate(pmids):
                if i < len(blocks):
                    abstracts[pmid] = blocks[i][:2000]
                else:
                    abstracts[pmid] = full_text[:500]  # fallback
            return abstracts
        except Exception as exc:
            logger.warning("pubmed_efetch_failed", extra={"error": str(exc)})
            return {}
