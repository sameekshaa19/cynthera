"""OpenTargetsConnector — queries the Open Targets Platform GraphQL API.

Open Targets Platform is a gene-disease association database integrating
20+ data sources: genetics (GWAS, ClinVar), literature, pathway databases,
safety data, and clinical evidence. Free, no API key required.

API: https://api.platform.opentargets.org/api/v4/graphql (POST, GraphQL)
Rate limit: GraphQL complexity-based (tested query complexity = 6.0).
No X-RateLimit headers — CDN-backed, highly available.

CRITICAL — MONDO IDs (verified live):
    Open Targets has migrated to MONDO disease IDs. EFO IDs are deprecated:
    disease(efoId: "EFO_0001378") → {"disease": null}    # BROKEN
    disease(efoId: "MONDO_0009693") → correct MM data    # WORKS
    The field argument is still named 'efoId' in the schema, but the
    expected value is a MONDO ID.

Default sort order (confirmed live):
    associatedTargets rows are score-descending by default.
    Do NOT add orderByScore param — it scrambles results (verified).

Primary purpose in CYNTHERA:
    Populate RetrievalPackage.validated_disease_genes — a dict of
    {gene_symbol: ot_score, uniprot_accession: ot_score} used by
    MultiHopReasoner.trace_paths() for disease-relevance validation.
    Open Targets associations MUST NOT be routed into evidence_records
    or influence Support Score — they represent biological association
    strength, not literature claim quality.

Reference: Implementation plan Part 1 — Source B findings, Gap 1 correction
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.core.exceptions import SourceUnavailableError
from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_OT_GQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

# Number of top associations to fetch per disease query.
# The top 50 by score include all clinically relevant targets.
# More than 50 adds noise without improving MultiHopReasoner recall.
_DEFAULT_PAGE_SIZE = 50

# GraphQL query: resolve disease name → MONDO ID
_GQL_DISEASE_SEARCH = """
query SearchDisease($name: String!) {
  search(queryString: $name, entityNames: ["disease"], page: {index: 0, size: 5}) {
    hits {
      id
      name
      entity
    }
  }
}
"""

# GraphQL query: fetch top N target associations for a disease MONDO ID
# Returns score-descending by default (confirmed live) — no orderBy needed.
_GQL_ASSOCIATIONS = """
query Associations($mondoId: String!, $size: Int!) {
  disease(efoId: $mondoId) {
    id
    name
    associatedTargets(page: {index: 0, size: $size}) {
      count
      rows {
        target {
          id
          approvedSymbol
          approvedName
          proteinIds {
            id
            source
          }
        }
        score
        datatypeScores {
          id
          score
        }
      }
    }
  }
}
"""


class OpenTargetsConnector(BaseConnector):
    """Connector for the Open Targets Platform GraphQL API.

    Fetches gene-disease association data. Output populates
    RetrievalPackage.validated_disease_genes — NOT evidence_records.

    Two-step fetch:
    1. resolve_mondo_id(disease_name) — name → MONDO ID
    2. fetch_associations(mondo_id) — MONDO ID → scored gene set

    UniProt accessions are extracted from target.proteinIds[source=uniprot_swissprot]
    inline within the associations query, avoiding a separate per-target request.
    """

    source_name = "opentargets"
    base_url = _OT_GQL_URL
    timeout_seconds = 30.0

    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw associations from Open Targets.

        Satisfies BaseConnector abstract contract.

        Args:
            **kwargs: Accepts 'mondo_id' (str) and 'page_size' (int).

        Returns:
            Raw GraphQL response data dict.
        """
        mondo_id = kwargs.get("mondo_id", "")
        page_size = int(kwargs.get("page_size", _DEFAULT_PAGE_SIZE))
        return await self._post(
            self.base_url,
            {
                "query": _GQL_ASSOCIATIONS,
                "variables": {"mondoId": mondo_id, "size": page_size},
            },
        )

    async def resolve_mondo_id(self, disease_name: str) -> str | None:
        """Resolve a disease name to an Open Targets MONDO ID.

        Uses the OT search endpoint with candidate scoring to handle
        cases where the MONDO canonical name differs from common usage
        (e.g. "Multiple Myeloma" → "plasma cell myeloma" (MONDO_0009693)).

        Scoring: exact case-insensitive match > token Jaccard similarity > first result.
        Gracefully returns None if OT is unavailable — callers must handle this.

        Args:
            disease_name: Disease common name (e.g. "Multiple Myeloma").

        Returns:
            MONDO ID string (e.g. "MONDO_0009693"), or None on failure.
        """
        try:
            resp = await self._post(
                self.base_url,
                {"query": _GQL_DISEASE_SEARCH, "variables": {"name": disease_name}},
            )
        except (SourceUnavailableError, Exception) as exc:
            logger.warning(
                "opentargets_mondo_resolution_failed",
                extra={"disease": disease_name, "error": str(exc)},
            )
            return None

        hits = (resp.get("data") or {}).get("search", {}).get("hits", [])
        if not hits:
            logger.info(
                "opentargets_mondo_no_hits",
                extra={"disease": disease_name},
            )
            return None

        # Score candidates: prefer exact match, then token overlap
        query_tokens = set(disease_name.lower().split())
        best_hit = None
        best_score = -1.0

        for hit in hits[:5]:
            hit_name = (hit.get("name") or "").lower()
            hit_tokens = set(hit_name.split())

            # Exact match: highest priority
            if hit_name == disease_name.lower():
                best_hit = hit
                break

            # Jaccard similarity
            if query_tokens and hit_tokens:
                jaccard = len(query_tokens & hit_tokens) / len(query_tokens | hit_tokens)
            else:
                jaccard = 0.0

            if jaccard > best_score:
                best_score = jaccard
                best_hit = hit

        if not best_hit:
            best_hit = hits[0]

        mondo_id = best_hit.get("id")
        logger.info(
            "opentargets_mondo_resolved",
            extra={
                "disease": disease_name,
                "mondo_id": mondo_id,
                "mondo_name": best_hit.get("name"),
            },
        )
        return mondo_id

    async def fetch_associations(
        self, mondo_id: str, page_size: int = _DEFAULT_PAGE_SIZE
    ) -> dict[str, float]:
        """Fetch gene-disease associations for a MONDO ID.

        Returns a flat dict mapping both gene symbol and UniProt accession
        to the Open Targets association score. This dual-key approach lets
        MultiHopReasoner look up by whichever identifier it has available.

        Key structure:
            {
              "CRBN": 0.6846,       # gene symbol
              "Q96SW2": 0.6846,     # UniProt accession (Swiss-Prot reviewed)
              "TNFRSF17": 0.6801,
              ...
            }

        Args:
            mondo_id: MONDO disease ID (e.g. "MONDO_0009693").
            page_size: Max associations to fetch (default 50).

        Returns:
            Dict mapping gene symbols and UniProt accessions to scores.
            Returns empty dict on failure — callers must handle gracefully.
        """
        gene_scores, _ = await self.fetch_association_mappings(mondo_id, page_size=page_size)
        return gene_scores

    async def fetch_association_mappings(
        self,
        mondo_id: str,
        page_size: int = 50,
    ) -> tuple[dict[str, float], list[BiologicalIdentifierMapping]]:
        """Fetch target associations preserving row-level gene symbol ↔ UniProt mappings.

        Args:
            mondo_id: MONDO disease identifier (e.g., 'MONDO_0009693').
            page_size: Maximum associations to retrieve (default 50).

        Returns:
            Tuple of (gene_scores dict, list of BiologicalIdentifierMapping value objects).
        """
        try:
            resp = await self._post(
                self.base_url,
                {
                    "query": _GQL_ASSOCIATIONS,
                    "variables": {"mondoId": mondo_id, "size": page_size},
                },
            )
        except (SourceUnavailableError, Exception) as exc:
            logger.warning(
                "opentargets_associations_failed",
                extra={"mondo_id": mondo_id, "error": str(exc)},
            )
            return {}, []

        disease_data = (resp.get("data") or {}).get("disease")
        if not disease_data:
            logger.info(
                "opentargets_associations_null_disease",
                extra={"mondo_id": mondo_id},
            )
            return {}, []

        rows = disease_data.get("associatedTargets", {}).get("rows", [])
        total_count = disease_data.get("associatedTargets", {}).get("count", 0)

        gene_scores: dict[str, float] = {}
        mappings: list[BiologicalIdentifierMapping] = []

        for row in rows:
            target = row.get("target", {})
            score = row.get("score", 0.0)
            raw_symbol = target.get("approvedSymbol")
            gene_symbol = str(raw_symbol).strip().upper() if raw_symbol else None
            score_val = round(float(score), 6) if isinstance(score, (int, float)) and score > 0 else None

            # Extract UniProt accessions from proteinIds
            protein_ids: list[str] = []
            for protein_id in target.get("proteinIds", []):
                pid = protein_id.get("id") if isinstance(protein_id, dict) else str(protein_id)
                if pid:
                    clean_pid = str(pid).split("-")[0].strip().upper()
                    if clean_pid and clean_pid not in protein_ids:
                        protein_ids.append(clean_pid)

            # Preserve row-level paired mapping
            if gene_symbol and protein_ids:
                for pid in protein_ids:
                    mappings.append(
                        BiologicalIdentifierMapping(
                            canonical_symbol=gene_symbol,
                            uniprot_accession=pid,
                            source="OpenTargets",
                            score=score_val,
                            original_identifiers=(gene_symbol, pid),
                        )
                    )
            elif gene_symbol:
                mappings.append(
                    BiologicalIdentifierMapping(
                        canonical_symbol=gene_symbol,
                        uniprot_accession=None,
                        source="OpenTargets",
                        score=score_val,
                        original_identifiers=(gene_symbol,),
                    )
                )
            elif protein_ids:
                for pid in protein_ids:
                    mappings.append(
                        BiologicalIdentifierMapping(
                            canonical_symbol=None,
                            uniprot_accession=pid,
                            source="OpenTargets",
                            score=score_val,
                            original_identifiers=(pid,),
                        )
                    )

            # Populate gene_scores dictionary (backwards compatible)
            if score_val is not None:
                if gene_symbol:
                    gene_scores[gene_symbol] = score_val
                for pid in protein_ids:
                    gene_scores[pid] = score_val

        logger.info(
            "opentargets_associations_fetched",
            extra={
                "mondo_id": mondo_id,
                "total_db_count": total_count,
                "fetched": len(rows),
                "mappings_preserved": len(mappings),
                "indexed_keys": len(gene_scores),
            },
        )
        return gene_scores, mappings
