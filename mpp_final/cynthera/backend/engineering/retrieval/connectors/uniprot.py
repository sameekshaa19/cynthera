"""UniProtConnector — queries UniProt REST API for protein target details.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://rest.uniprot.org/
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

UNIPROT_BASE = "https://rest.uniprot.org/uniprotkb"


class UniProtConnector(BaseConnector):
    """Connector for the UniProt protein knowledgebase.

    Fetches:
    - Protein function, organism, and gene name data
    - Protein-pathway associations
    - Disease-gene associations via UniProt disease links
    """

    source_name = "uniprot"
    base_url = UNIPROT_BASE
    timeout_seconds = 30.0

    async def fetch(self, uniprot_accession: str) -> dict[str, Any]:
        """Fetch full protein record for a UniProt accession.

        Args:
            uniprot_accession: UniProt accession (e.g., 'O76074').

        Returns:
            Raw JSON protein record from UniProt.
        """
        url = f"{self.base_url}/{uniprot_accession}"
        params = {"format": "json"}
        logger.info("uniprot_fetch", extra={"accession": uniprot_accession})
        return await self._get(url, params=params)

    async def search(self, gene_name: str, organism: str = "homo+sapiens") -> dict[str, Any]:
        """Search UniProt for proteins by gene name and organism.

        Args:
            gene_name: HGNC gene symbol to search (e.g., 'PDE5A').
            organism: Organism filter (default 'homo+sapiens').

        Returns:
            Raw JSON search results from UniProt.
        """
        url = f"{self.base_url}/search"
        params = {
            "query": f"gene:{gene_name} AND organism_id:9606",
            "format": "json",
            "size": 5,
        }
        return await self._get(url, params=params)
