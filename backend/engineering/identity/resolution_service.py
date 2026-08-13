"""IdentifierResolutionService — maps drug/disease names to canonical IDs.

Reference: 01_SYSTEM_ARCHITECTURE.md §3.4, 03_RETRIEVAL_SPECIFICATION.md

Phase 4 addition: resolve_disease() now also resolves Open Targets MONDO IDs
concurrently with MeSH resolution. OT unavailability is gracefully degraded —
a missing MONDO ID delays Open Targets association fetch but does NOT raise
DiseaseNotResolvedException or block the pipeline.
"""
from __future__ import annotations

import asyncio
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
OPEN_TARGETS_GQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

_GQL_DISEASE_SEARCH = (
    'query SearchDisease($name: String!) {'
    '  search(queryString: $name, entityNames: ["disease"], page: {index: 0, size: 5}) {'
    '    hits { id name }'
    '  }'
    '}'
)


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
            # Try ChEMBL — with synonym retry on empty result (Bug P2 fix)
            chembl_id = await self._resolve_chembl(client, drug_name)
            attempted.append("chembl")
            if not chembl_id:
                # Retry with lowercase variant (ChEMBL text search is case-sensitive
                # for some compound names, e.g. "Thalidomide" may need to match
                # ChEMBL's preferred name casing)
                lower_name = drug_name.strip().lower()
                if lower_name != drug_name.strip():
                    chembl_id = await self._resolve_chembl(client, lower_name)
                    if chembl_id:
                        logger.info(
                            "chembl_resolved_via_lowercase_retry",
                            extra={"original": drug_name, "tried": lower_name},
                        )
                # Retry with hyphens/apostrophes stripped (e.g. "5-fluorouracil" → "5 fluorouracil")
                if not chembl_id:
                    simplified = drug_name.replace("-", " ").replace("'", "").strip()
                    if simplified.lower() != lower_name:
                        chembl_id = await self._resolve_chembl(client, simplified)
                        if chembl_id:
                            logger.info(
                                "chembl_resolved_via_simplified_retry",
                                extra={"original": drug_name, "tried": simplified},
                            )
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

        Attempts NLM MeSH lookup and Open Targets MONDO ID resolution
        concurrently. Both run in parallel to avoid serial latency.

        OT availability is NOT required: a missing MONDO ID is gracefully
        degraded (warning logged) but does NOT raise DiseaseNotResolvedException.
        The MONDO ID is stored as a 'mondo' namespace identifier so it is
        accessible via disease.mondo_id and used as the stable cache key
        for Open Targets association queries.

        Args:
            disease_name: Common disease name (e.g., 'Pulmonary Arterial Hypertension').
            trace_id: Optional trace ID for logging.

        Returns:
            ResolvedIdentifierSet with MeSH and MONDO identifiers where available.

        Raises:
            DiseaseNotResolvedException: If no identifier can be resolved.
        """
        identifiers: list[CanonicalIdentifier] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Run MeSH and MONDO resolution concurrently
            mesh_id, mondo_id = await asyncio.gather(
                self._resolve_mesh(client, disease_name),
                self._resolve_opentargets_mondo(client, disease_name),
                return_exceptions=False,
            )

        if mesh_id:
            identifiers.append(CanonicalIdentifier(namespace="mesh", value=mesh_id))

        if mondo_id:
            identifiers.append(CanonicalIdentifier(namespace="mondo", value=mondo_id))
            logger.info(
                "mondo_resolved",
                extra={"disease_name": disease_name, "mondo_id": mondo_id},
            )

        if not identifiers:
            # Graceful degradation: create a synthetic identifier from the name
            logger.warning(
                "disease_mesh_not_found",
                extra={"disease_name": disease_name},
            )
            identifiers.append(
                CanonicalIdentifier(namespace="name", value=disease_name.lower().replace(" ", "_"))
            )

        has_mesh = any(i.namespace == "mesh" for i in identifiers)
        has_mondo = any(i.namespace == "mondo" for i in identifiers)
        if has_mesh and has_mondo:
            confidence = 1.0
        elif has_mesh or has_mondo:
            confidence = 0.8
        else:
            confidence = 0.3

        resolved = ResolvedIdentifierSet(
            entity_name=disease_name,
            entity_type="disease",
            identifiers=identifiers,
            resolution_confidence=confidence,
        )
        logger.info(
            "disease_resolved",
            extra={
                "disease_name": disease_name,
                "confidence": confidence,
                "mesh_found": has_mesh,
                "mondo_found": has_mondo,
            },
        )
        return resolved

    async def _resolve_chembl(
        self,
        client: httpx.AsyncClient,
        drug_name: str,
    ) -> str | None:
        """Look up ChEMBL ID for a drug name using generic candidate scoring.

        Instead of naively picking molecules[0] (which can land on obscure, unnamed
        compounds returned first by ChEMBL text indexing), scores all returned
        candidates by:
        1. Exact preferred name match (case-insensitive)
        2. Presence of a preferred name (pref_name is not empty/null)
        3. Highest clinical development stage (max_phase)
        4. Parent compound status (molecule_chembl_id == parent_chembl_id)

        Args:
            client: Active httpx async client.
            drug_name: Drug name to search.

        Returns:
            ChEMBL compound ID string of the highest-scoring candidate, or None.
        """
        try:
            resp = await client.get(
                CHEMBL_SEARCH_URL,
                params={"q": drug_name, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
            molecules = data.get("molecules", [])
            if not molecules:
                return None

            clean_query = drug_name.strip().lower()

            def _score(m: dict[str, Any]) -> tuple[bool, bool, int, bool]:
                pref_name = (m.get("pref_name") or "").strip().lower()
                exact_match = pref_name == clean_query
                has_pref_name = bool(pref_name)
                max_phase = int(float(m.get("max_phase") or 0))
                is_parent = (
                    m.get("molecule_hierarchy", {}).get("parent_chembl_id")
                    == m.get("molecule_chembl_id")
                )
                return (exact_match, has_pref_name, max_phase, is_parent)

            best = max(molecules, key=_score)
            chosen_id = best.get("molecule_chembl_id")

            logger.info(
                "chembl_resolved",
                extra={
                    "drug_name": drug_name,
                    "chosen_id": chosen_id,
                    "chosen_pref_name": best.get("pref_name"),
                    "chosen_max_phase": best.get("max_phase"),
                    "candidates_considered": len(molecules),
                },
            )
            return chosen_id
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

        Normalizes possessive apostrophes (e.g. 'Alzheimer's Disease' -> 'Alzheimer Disease')
        which MeSH descriptors use.

        Args:
            client: Active httpx async client.
            disease_name: Disease name to search.

        Returns:
            MeSH descriptor ID string, or None if not found.
        """
        clean_name = disease_name.replace("'s", "").replace("’s", "").strip()
        queries = [disease_name]
        if clean_name != disease_name:
            queries.append(clean_name)

        for q in queries:
            try:
                resp = await client.get(
                    MESH_SEARCH_URL,
                    params={"label": q, "match": "contains", "limit": 1},
                )
                resp.raise_for_status()
                data = resp.json()
                if data:
                    resource = data[0].get("resource", "")
                    if resource:
                        return resource.rstrip("/").split("/")[-1]
            except Exception as exc:
                logger.warning("mesh_resolve_failed", extra={"disease": q, "error": str(exc)})
        return None

    async def _resolve_opentargets_mondo(
        self,
        client: httpx.AsyncClient,
        disease_name: str,
    ) -> str | None:
        """Resolve a disease name to an Open Targets MONDO ID.

        Runs concurrently with _resolve_mesh() inside resolve_disease().
        Any exception is caught and returns None — OT unavailability must
        not prevent disease resolution from succeeding.

        Scoring: exact case-insensitive match > Jaccard token similarity.
        Uses top 5 candidates (page size 5) to handle synonym mismatches
        (e.g. 'Multiple Myeloma' → 'plasma cell myeloma').

        Args:
            client: Active httpx async client.
            disease_name: Disease common name.

        Returns:
            MONDO ID string (e.g. 'MONDO_0009693'), or None on failure.
        """
        try:
            resp = await client.post(
                OPEN_TARGETS_GQL_URL,
                json={"query": _GQL_DISEASE_SEARCH, "variables": {"name": disease_name}},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "opentargets_mondo_resolve_failed",
                extra={"disease": disease_name, "error": str(exc)},
            )
            return None

        hits = (data.get("data") or {}).get("search", {}).get("hits", [])
        if not hits:
            logger.info(
                "opentargets_mondo_no_hits",
                extra={"disease": disease_name},
            )
            return None

        # Score candidates: exact match first, then Jaccard token similarity
        query_tokens = set(disease_name.lower().split())
        best_hit: dict | None = None
        best_score = -1.0

        for hit in hits:
            hit_name = (hit.get("name") or "").lower()
            if hit_name == disease_name.lower():
                best_hit = hit
                break
            hit_tokens = set(hit_name.split())
            if query_tokens and hit_tokens:
                jaccard = len(query_tokens & hit_tokens) / len(query_tokens | hit_tokens)
            else:
                jaccard = 0.0
            if jaccard > best_score:
                best_score = jaccard
                best_hit = hit

        if not best_hit:
            best_hit = hits[0]

        return best_hit.get("id")
