"""ReactomeConnector — queries Reactome ContentService for pathway data.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://reactome.org/ContentService/

Endpoint verification (live-tested 2026-08-04):
  GET /data/participants/{stId} returns:
    list[{ peDbId, displayName, schemaClass, refEntities: [
        { identifier: "Q13976-1", schemaClass: "ReferenceGeneProduct"|"ReferenceIsoform",
          displayName: "UniProt:Q13976-1 PRKG1", ... }
    ]}]
  UniProt accessions are in refEntities[*].identifier when schemaClass is
  "ReferenceGeneProduct" or "ReferenceIsoform".
  The endpoint requires a User-Agent header (403 without one).
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

REACTOME_BASE = "https://reactome.org/ContentService"

# Reactome's ContentService returns 403 without a User-Agent.
_USER_AGENT = "CYNTHERA-Research/1.0 (scientific drug repurposing tool)"

# Physical entity schema classes that map 1:1 to a UniProt protein record.
_PROTEIN_SCHEMA_CLASSES = frozenset({"ReferenceGeneProduct", "ReferenceIsoform"})


class ReactomeConnector(BaseConnector):
    """Connector for the Reactome pathway knowledgebase.

    Fetches:
    - Pathways containing a given UniProt protein (forward direction)
    - UniProt participants of a given pathway (reverse direction)
    - Pathway detail records
    """

    source_name = "reactome"
    base_url = REACTOME_BASE
    timeout_seconds = 30.0

    def _build_headers(self) -> dict[str, str]:
        """Build default headers override to include custom User-Agent required by Reactome."""
        headers = super()._build_headers()
        headers["User-Agent"] = _USER_AGENT
        return headers

    async def fetch(self, uniprot_accession: str) -> dict[str, Any]:
        """Fetch all pathways that contain a given UniProt protein.

        Args:
            uniprot_accession: UniProt accession (e.g., 'O76074').

        Returns:
            Dict with 'pathways': list of raw pathway summary dicts from Reactome.
        """
        clean_acc = (uniprot_accession or "").strip().upper()
        url = f"{self.base_url}/data/mapping/UniProt/{clean_acc}/pathways"
        params: dict[str, Any] = {"species": "Homo sapiens"}
        logger.info("reactome_fetch", extra={"uniprot": clean_acc})
        result = await self._get(url, params=params)
        return {"pathways": result if isinstance(result, list) else []}

    async def fetch_participants(self, reactome_stid: str) -> dict[str, Any]:
        """Fetch UniProt accessions of all protein participants in a pathway.

        Uses GET /data/participants/{stId} which returns PhysicalEntity objects
        each containing a refEntities list. UniProt accessions are extracted
        from refEntities where schemaClass is ReferenceGeneProduct or ReferenceIsoform.

        Live-verified endpoint shape (2026-08-04):
          [{ peDbId, displayName, schemaClass, refEntities: [
              { identifier: "Q13976-1", schemaClass: "ReferenceGeneProduct",
                displayName: "UniProt:Q13976-1 PRKG1" }
          ]}]

        Args:
            reactome_stid: Reactome stable identifier (e.g., 'R-HSA-418457').

        Returns:
            Dict with 'uniprot_ids': list[str] of UniProt accessions (deduplicated).
            Returns {'uniprot_ids': []} on any failure — caller must not treat [] as
            confirmation that the pathway has no participants; check logs.
        """
        clean_stid = (reactome_stid or "").strip()
        url = f"{self.base_url}/data/participants/{clean_stid}"
        try:
            result = await self._get(url)
            uniprot_ids: list[str] = []
            if isinstance(result, list):
                for physical_entity in result:
                    if isinstance(physical_entity, dict):
                        for ref in physical_entity.get("refEntities", []):
                            if isinstance(ref, dict) and ref.get("schemaClass") in _PROTEIN_SCHEMA_CLASSES:
                                identifier = ref.get("identifier", "")
                                # Strip isoform suffix (e.g. Q13976-1 → Q13976) for
                                # consistent matching against UniProt accessions in the system.
                                base_accession = identifier.split("-")[0] if identifier else ""
                                if base_accession and base_accession not in uniprot_ids:
                                    uniprot_ids.append(base_accession)
            logger.debug(
                "reactome_participants_fetched",
                extra={"reactome_stid": clean_stid, "uniprot_count": len(uniprot_ids)},
            )
            return {"uniprot_ids": uniprot_ids}
        except Exception as exc:
            logger.warning(
                "reactome_participants_fetch_failed",
                extra={"reactome_stid": clean_stid, "error": str(exc), "error_type": type(exc).__name__},
            )
            return {"uniprot_ids": []}

    async def fetch_pathway_details(self, reactome_id: str) -> dict[str, Any]:
        """Fetch detailed information for a specific Reactome pathway.

        Args:
            reactome_id: Reactome stable identifier (e.g., 'R-HSA-202127').

        Returns:
            Raw JSON pathway detail record.
        """
        clean_id = (reactome_id or "").strip()
        url = f"{self.base_url}/data/query/{clean_id}"
        return await self._get(url)

