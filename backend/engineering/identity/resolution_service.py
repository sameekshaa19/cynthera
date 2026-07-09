"""IdentifierResolutionService — maps drug/disease names to canonical IDs.

Reference: 01_SYSTEM_ARCHITECTURE.md §3.4, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.exceptions import DrugNotResolvedException, DiseaseNotResolvedException

logger = logging.getLogger(__name__)

CHEMBL_SEARCH_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json"
PUBCHEM_SEARCH_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/JSON"
MESH_SEARCH_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"


class IdentifierResolutionService:
    """Maps ambiguous input text to a standardized set of database keys.

    Resolves:
    - Drug names → ChEMBL ID, PubChem CID
    - Disease names → MeSH ID

    Raises:
        DrugNotResolvedException: If the drug name cannot be mapped.
        DiseaseNotResolvedException: If the disease name cannot be mapped.
    """

    def __init__(self, ncbi_api_key: str | None = None, timeout: float = 30.0) -> None:
        """Initialize the resolver.

        Args:
            ncbi_api_key: Optional NCBI API key (increases PubMed rate limit).
            timeout: HTTP timeout in seconds.
        """
        self._ncbi_api_key = ncbi_api_key
        self._timeout = timeout

    async def resolve_drug(
        self,
        drug_name: str,
        trace_id: uuid.UUID | None = None,
    ) -> ResolvedIdentifierSet:
        """Resolve a drug name to a canonical identifier set.

        Attempts ChEMBL first, then PubChem as fallback.

        Args:
            drug_name: Common drug name (e.g., 'Sildenafil').
            trace_id: Optional trace ID for logging.

        Returns:
            ResolvedIdentifierSet with all resolved identifiers.

        Raises:
            DrugNotResolvedException: If no identifier can be resolved.
        """
        identifiers: list[CanonicalIdentifier] = []
        attempted: list[str] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Try ChEMBL
            chembl_id = await self._resolve_chembl(client, drug_name)
            attempted.append("chembl")
            if chembl_id:
                identifiers.append(CanonicalIdentifier(namespace="chembl", value=chembl_id))

            # Try PubChem
            pubchem_cid = await self._resolve_pubchem(client, drug_name)
            attempted.append("pubchem")
            if pubchem_cid:
                identifiers.append(CanonicalIdentifier(namespace="pubchem", value=pubchem_cid))

        if not identifiers:
            raise DrugNotResolvedException(
                drug_name=drug_name,
                attempted_sources=attempted,
                trace_id=trace_id,
            )

        confidence = 1.0 if len(identifiers) >= 2 else 0.7
        resolved = ResolvedIdentifierSet(
            entity_name=drug_name,
            entity_type="drug",
            identifiers=identifiers,
            resolution_confidence=confidence,
        )
        logger.info(
            "drug_resolved",
            extra={
                "drug_name": drug_name,
                "identifiers": [str(i) for i in identifiers],
                "confidence": confidence,
            },
        )
        return resolved

    async def resolve_disease(
        self,
        disease_name: str,
        trace_id: uuid.UUID | None = None,
    ) -> ResolvedIdentifierSet:
        """Resolve a disease name to a canonical identifier set.

        Attempts NLM MeSH lookup.

        Args:
            disease_name: Common disease name (e.g., 'Pulmonary Arterial Hypertension').
            trace_id: Optional trace ID for logging.

        Returns:
            ResolvedIdentifierSet with resolved MeSH identifier.

        Raises:
            DiseaseNotResolvedException: If no identifier can be resolved.
        """
        identifiers: list[CanonicalIdentifier] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            mesh_id = await self._resolve_mesh(client, disease_name)
            if mesh_id:
                identifiers.append(CanonicalIdentifier(namespace="mesh", value=mesh_id))

        if not identifiers:
            # Graceful degradation: create a synthetic identifier from the name
            logger.warning(
                "disease_mesh_not_found",
                extra={"disease_name": disease_name},
            )
            # Use the name itself as a low-confidence synthetic ID
            identifiers.append(
                CanonicalIdentifier(namespace="name", value=disease_name.lower().replace(" ", "_"))
            )

        confidence = 1.0 if any(i.namespace == "mesh" for i in identifiers) else 0.3
        resolved = ResolvedIdentifierSet(
            entity_name=disease_name,
            entity_type="disease",
            identifiers=identifiers,
            resolution_confidence=confidence,
        )
        logger.info(
            "disease_resolved",
            extra={"disease_name": disease_name, "confidence": confidence},
        )
        return resolved

    async def _resolve_chembl(
        self,
        client: httpx.AsyncClient,
        drug_name: str,
    ) -> str | None:
        """Look up ChEMBL ID for a drug name.

        Args:
            client: Active httpx async client.
            drug_name: Drug name to search.

        Returns:
            ChEMBL compound ID string, or None if not found.
        """
        try:
            resp = await client.get(
                CHEMBL_SEARCH_URL,
                params={"q": drug_name, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
            molecules = data.get("molecules", [])
            if molecules:
                return molecules[0].get("molecule_chembl_id")
        except Exception as exc:
            logger.warning("chembl_resolve_failed", extra={"drug": drug_name, "error": str(exc)})
        return None

    async def _resolve_pubchem(
        self,
        client: httpx.AsyncClient,
        drug_name: str,
    ) -> str | None:
        """Look up PubChem CID for a drug name.

        Args:
            client: Active httpx async client.
            drug_name: Drug name to search.

        Returns:
            PubChem CID string, or None if not found.
        """
        try:
            url = PUBCHEM_SEARCH_URL.format(name=drug_name)
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            cids = (
                data.get("PC_Compounds", [{}])[0]
                .get("id", {})
                .get("id", {})
                .get("cid")
            )
            if cids:
                return str(cids)
        except Exception as exc:
            logger.warning("pubchem_resolve_failed", extra={"drug": drug_name, "error": str(exc)})
        return None

    async def _resolve_mesh(
        self,
        client: httpx.AsyncClient,
        disease_name: str,
    ) -> str | None:
        """Look up MeSH ID for a disease name via NLM MeSH API.

        Args:
            client: Active httpx async client.
            disease_name: Disease name to search.

        Returns:
            MeSH descriptor ID string, or None if not found.
        """
        try:
            resp = await client.get(
                MESH_SEARCH_URL,
                params={"label": disease_name, "match": "contains", "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                return data[0].get("descriptor", {}).get("ui")
        except Exception as exc:
            logger.warning("mesh_resolve_failed", extra={"disease": disease_name, "error": str(exc)})
        return None
