"""ChEMBLConnector — queries ChEMBL API for drug bioactivities and targets.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://www.ebi.ac.uk/chembl/api/data/
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLConnector(BaseConnector):
    """Connector for the ChEMBL bioactivity and target database.

    Fetches:
    - Drug bioactivity records (IC50, Ki, Kd)
    - Drug-target interaction mechanisms
    - Drug approval and indication data
    """

    source_name = "chembl"
    base_url = CHEMBL_BASE
    timeout_seconds = 30.0

    async def fetch(self, chembl_id: str, limit: int = 100) -> dict[str, Any]:
        """Fetch bioactivity records for a ChEMBL compound.

        Args:
            chembl_id: ChEMBL compound identifier (e.g., 'CHEMBL941').
            limit: Maximum number of records to retrieve (default 100).

        Returns:
            Raw JSON payload from ChEMBL /activity endpoint.
        """
        url = f"{self.base_url}/activity.json"
        params = {
            "molecule_chembl_id": chembl_id,
            "limit": limit,
            "format": "json",
        }
        logger.info("chembl_fetch", extra={"chembl_id": chembl_id, "limit": limit})
        return await self._get(url, params=params)

    async def fetch_molecule(self, chembl_id: str) -> dict[str, Any]:
        """Fetch molecule details for a ChEMBL compound.

        Args:
            chembl_id: ChEMBL compound identifier.

        Returns:
            Raw JSON molecule record from ChEMBL.
        """
        url = f"{self.base_url}/molecule/{chembl_id}.json"
        return await self._get(url)

    async def fetch_targets(self, chembl_id: str) -> dict[str, Any]:
        """Fetch drug-target interaction data for a ChEMBL compound.

        Args:
            chembl_id: ChEMBL compound identifier.

        Returns:
            Raw JSON payload from ChEMBL /mechanism endpoint.
        """
        url = f"{self.base_url}/mechanism.json"
        params = {"molecule_chembl_id": chembl_id, "format": "json"}
        return await self._get(url, params=params)

    async def search_molecule(self, drug_name: str) -> dict[str, Any]:
        """Search for a molecule by name to resolve ChEMBL ID.

        Args:
            drug_name: Drug common name to search.

        Returns:
            Raw JSON search results from ChEMBL.
        """
        url = f"{self.base_url}/molecule/search.json"
        params = {"q": drug_name, "format": "json"}
        return await self._get(url, params=params)
