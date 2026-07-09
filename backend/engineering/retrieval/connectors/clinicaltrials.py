"""ClinicalTrialsConnector — queries ClinicalTrials.gov API for trial records.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://clinicaltrials.gov/api/v2/
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

CLINICALTRIALS_BASE = "https://clinicaltrials.gov/api/v2"


class ClinicalTrialsConnector(BaseConnector):
    """Connector for ClinicalTrials.gov API v2.

    Fetches:
    - Trial records for a drug-disease pair
    - Trial phase, status, and outcome data
    """

    source_name = "clinicaltrials"
    base_url = CLINICALTRIALS_BASE
    timeout_seconds = 30.0

    async def fetch(
        self,
        drug_name: str,
        disease_name: str,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Fetch clinical trial records for a drug-disease pair.

        Args:
            drug_name: Drug name to search for.
            disease_name: Disease/condition name to search for.
            max_results: Maximum number of trials to retrieve.

        Returns:
            Raw JSON payload from ClinicalTrials.gov.
        """
        url = f"{self.base_url}/studies"
        params: dict[str, Any] = {
            "query.intr": drug_name,
            "query.cond": disease_name,
            "pageSize": max_results,
            "format": "json",
        }
        logger.info(
            "clinicaltrials_fetch",
            extra={"drug": drug_name, "disease": disease_name},
        )
        return await self._get(url, params=params)
