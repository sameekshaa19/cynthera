"""ReactomeConnector — queries Reactome ContentService for pathway data.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://reactome.org/ContentService/
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

REACTOME_BASE = "https://reactome.org/ContentService"


class ReactomeConnector(BaseConnector):
    """Connector for the Reactome pathway knowledgebase.

    Fetches:
    - Pathways containing a given UniProt protein
    - Pathway participant details
    - Pathway hierarchy for disease-pathway overlap
    """

    source_name = "reactome"
    base_url = REACTOME_BASE
    timeout_seconds = 30.0

    async def fetch(self, uniprot_accession: str) -> dict[str, Any]:
        """Fetch all pathways that contain a given UniProt protein.

        Args:
            uniprot_accession: UniProt accession (e.g., 'O76074').

        Returns:
            Raw JSON array of pathway summaries from Reactome.
        """
        url = f"{self.base_url}/data/mapping/UniProt/{uniprot_accession}/pathways"
        params: dict[str, Any] = {"species": "Homo sapiens"}
        logger.info("reactome_fetch", extra={"uniprot": uniprot_accession})
        result = await self._get(url, params=params)
        return {"pathways": result if isinstance(result, list) else []}

    async def fetch_pathway_details(self, reactome_id: str) -> dict[str, Any]:
        """Fetch detailed information for a specific Reactome pathway.

        Args:
            reactome_id: Reactome stable identifier (e.g., 'R-HSA-202127').

        Returns:
            Raw JSON pathway detail record.
        """
        url = f"{self.base_url}/data/query/{reactome_id}"
        return await self._get(url)
