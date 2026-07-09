"""DisGeNETConnector — queries DisGeNET for gene-disease associations.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://www.disgenet.org/api/
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

DISGENET_BASE = "https://www.disgenet.org/api"


class DisGeNETConnector(BaseConnector):
    """Connector for the DisGeNET gene-disease association database.

    Fetches:
    - Gene-disease association scores
    - Disease genes for pathway overlap analysis
    """

    source_name = "disgenet"
    base_url = DISGENET_BASE
    timeout_seconds = 30.0

    async def fetch(self, disease_id: str, source: str = "ALL", limit: int = 100) -> dict[str, Any]:
        """Fetch gene-disease associations for a disease identifier.

        Args:
            disease_id: UMLS CUI or MeSH ID of the disease.
            source: Data source filter (default 'ALL').
            limit: Maximum number of associations to retrieve.

        Returns:
            Raw JSON array of gene-disease associations.
        """
        url = f"{self.base_url}/gda/disease/{disease_id}"
        params: dict[str, Any] = {"source": source, "limit": limit}
        logger.info("disgenet_fetch", extra={"disease_id": disease_id})
        return await self._get(url, params=params)

    def _build_headers(self) -> dict[str, str]:
        """Build headers including DisGeNET API key if provided."""
        headers = super()._build_headers()
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
