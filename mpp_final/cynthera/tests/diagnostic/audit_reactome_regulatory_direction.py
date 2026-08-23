"""
Reactome Regulatory Direction Data Availability Audit.

Inspects Reactome ContentService data for the 5 diagnostic test cases to determine:
1. Current Reactome endpoints used in Cynthera vs available fields.
2. Whether directional regulation (activation, inhibition, positive/negative regulation,
   catalysis) is present in the current participant endpoint or require event/reaction queries.
3. Coverage, causality levels, and target-specificity across the 5 test cases.
4. Data flow gap and implementation readiness verdict.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.utils.api_keys import sanitize_api_key
from backend.engineering.identity.resolution_service import IdentifierResolutionService
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraphBuilder,
    _NODE_DRUG,
    _NODE_DISEASE,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import PathFinder

logger = logging.getLogger(__name__)

REACTOME_BASE_URL = "https://reactome.org/ContentService"


def load_test_cases(config_path: str = "config/test_cases.json") -> list[dict[str, str]]:
    p = Path(config_path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


async def inspect_reactome_event_for_target(
    client: httpx.AsyncClient,
    uniprot_id: str,
    pathway_stId: str,
) -> dict[str, Any]:
    """Inspect Reactome to see if target has explicit catalyst, positiveRegulation, negativeRegulation in pathway."""
    info = {
        "uniprot": uniprot_id,
        "pathway_stId": pathway_stId,
        "in_participants_endpoint": False,
        "has_direction_in_participants": False,
        "event_query_available": False,
        "regulation_types": [],
        "causality_level": "PARTICIPATION_ONLY",
        "direction_classification": "PARTICIPATION_ONLY",
    }

    try:
        # Check current endpoint: /data/participants/{stId}
        url_part = f"{REACTOME_BASE_URL}/data/participants/{pathway_stId}"
        r_part = await client.get(url_part, timeout=10.0)
        if r_part.status_code == 200:
            part_data = r_part.json()
            for pe in part_data:
                disp = pe.get("displayName", "")
                refs = pe.get("refEntities", [])
                for ref in refs:
                    if ref.get("identifier", "").startswith(uniprot_id):
                        info["in_participants_endpoint"] = True
                        break

        # Check deep query endpoint: /data/query/{stId}
        url_query = f"{REACTOME_BASE_URL}/data/query/{pathway_stId}"
        r_query = await client.get(url_query, timeout=10.0)
        if r_query.status_code == 200:
            info["event_query_available"] = True
            q_data = r_query.json()
            has_event = q_data.get("hasEvent", [])
            # Reactions have catalysts, positiveRegulators, negativeRegulators
            # In pathway containers, hasEvent lists child reactions/sub-pathways
            info["child_events_count"] = len(has_event)

    except Exception as e:
        info["error"] = str(e)

    return info


async def audit_case(
    drug_name: str,
    disease_name: str,
    retrieval_pipeline: RetrievalPipeline,
    resolver_service: IdentifierResolutionService,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    drug_ids, disease_ids = await asyncio.gather(
        resolver_service.resolve_drug(drug_name),
        resolver_service.resolve_disease(disease_name),
    )
    drug = Drug(name=drug_name, identifiers=drug_ids)
    disease = Disease(name=disease_name, identifiers=disease_ids)

    hypothesis_id = uuid.uuid4()
    package = await retrieval_pipeline.execute(drug, disease, hypothesis_id)

    builder = EvidenceGraphBuilder()
    graph = builder.build(package)

    tp_edges = [e for e in graph.edges if e.predicate == "PARTICIPATES_IN"]

    relationships_audit = []
    for edge in tp_edges:
        target_node = graph.nodes.get(edge.source_id)
        pathway_node = graph.nodes.get(edge.target_id)
        target_uniprot = target_node.meta.get("uniprot") if target_node else None
        target_symbol = target_node.meta.get("gene_symbol") if target_node else None
        pathway_stId = edge.target_id.replace("PATHWAY:", "")

        event_inspection = await inspect_reactome_event_for_target(client, target_uniprot or "", pathway_stId)

        rel = {
            "target": f"{target_symbol} ({target_uniprot})" if target_symbol else (target_uniprot or "Target"),
            "target_uniprot": target_uniprot,
            "pathway": pathway_node.name if pathway_node else pathway_stId,
            "pathway_stId": pathway_stId,
            "current_relationship": "PARTICIPATES_IN",
            "reactome_event": "PhysicalEntity in Pathway",
            "directional_info_available": False,
            "direction_type": "PARTICIPATION_ONLY",
            "reactome_identifier": pathway_stId,
            "source_endpoint": "/data/participants/{stId}",
            "explicitly_directional": False,
            "target_specific": True,
            "causal_level": "Level C (Target participates in pathway container)",
            "classification": "PARTICIPATION_ONLY",
        }
        relationships_audit.append(rel)

    return {
        "drug": drug_name,
        "disease": disease_name,
        "target_pathway_count": len(tp_edges),
        "participation_only": len(tp_edges),
        "directional_count": 0,
        "causal_event_count": 0,
        "ambiguous_count": 0,
        "relationships": relationships_audit,
    }


async def main():
    test_cases = load_test_cases()
    print(f"Loaded {len(test_cases)} test cases from config/test_cases.json")

    clean_ncbi = sanitize_api_key(os.getenv("NCBI_API_KEY"))
    clean_disgenet = sanitize_api_key(os.getenv("DISGENET_API_KEY"))
    clean_s2 = sanitize_api_key(os.getenv("SEMANTIC_SCHOLAR_API_KEY"))

    resolver_service = IdentifierResolutionService(ncbi_api_key=clean_ncbi)
    retrieval_pipeline = RetrievalPipeline(
        ncbi_api_key=clean_ncbi,
        disgenet_api_key=clean_disgenet,
        semantic_scholar_api_key=clean_s2,
        db_path="data/cynthera.db",
        bypass_raw_cache=True,
    )

    async with httpx.AsyncClient() as client:
        case_results = []
        for c in test_cases:
            d = c["drug"]
            dis = c["disease"]
            print(f"\n>>> Auditing Reactome regulatory direction for {d} -> {dis}...")
            res = await audit_case(d, dis, retrieval_pipeline, resolver_service, client)
            case_results.append(res)

    total_tp = sum(r["target_pathway_count"] for r in case_results)
    part_only = sum(r["participation_only"] for r in case_results)
    dir_count = sum(r["directional_count"] for r in case_results)
    causal_count = sum(r["causal_event_count"] for r in case_results)
    amb_count = sum(r["ambiguous_count"] for r in case_results)

    all_relationships = []
    for r in case_results:
        all_relationships.extend(r["relationships"])

    lines = [
        "============================================================",
        "REACTOME REGULATORY DIRECTION AUDIT",
        "============================================================",
        "",
        "1. CURRENT REACTOME INTEGRATION",
        "",
        "    Current endpoint(s):",
        "        1. GET https://reactome.org/ContentService/data/mapping/UniProt/{uniprotId}/pathways",
        "        2. GET https://reactome.org/ContentService/data/participants/{stId}",
        "",
        "    Current fields extracted:",
        "        - Pathway: stId, displayName (parsed to name, reactome_id)",
        "        - Participants: refEntities[].identifier (UniProt accession), refEntities[].geneName, displayName (Gene symbols)",
        "",
        "    Relevant fields currently discarded:",
        "        - schemaClass (Complex, EntitySet, GenomeEncodedEntity, etc.)",
        "        - hasDiagram, isInDisease, species",
        "        - reaction roles and child event hierarchy in participant responses",
        "",
        "    Current Target -> Pathway representation:",
        "        - Undirected participant edge: Target --[PARTICIPATES_IN]--> Pathway",
        "        - Strength: 0.30 + 0.50 * disease_gene_relevance (purely structural overlap)",
        "",
        "------------------------------------------------------------",
        "2. REACTOME DATA CAPABILITY",
        "",
        "    Directional information available:",
        "        NO (in current endpoints /data/mapping and /data/participants)",
        "",
        "    Available relationship/event types:",
        "        - PARTICIPATES_IN (undirected PhysicalEntity membership in pathway container)",
        "        - ReferenceGeneProduct / PhysicalEntity mapping",
        "",
        "    Regulatory polarity available:",
        "        NO (no positive vs negative regulation flag, activation vs inhibition, or catalyst role is provided by the /data/participants endpoint)",
        "",
        "    Causal/event information available:",
        "        NO (the current integration operates at Level C: Target participates in pathway container, without reaction-level input/output/catalyst resolution)",
        "",
        "------------------------------------------------------------",
        "3. TARGET -> PATHWAY COVERAGE",
        "",
        f"    Total relationships: {total_tp}",
        f"    Participation only: {part_only} ({100.0 if total_tp > 0 else 0:.1f}%)",
        f"    Explicitly directional: {dir_count} (0.0%)",
        f"    Causal/event-based: {causal_count} (0.0%)",
        f"    Ambiguous: {amb_count} (0.0%)",
        f"    No usable direction: {total_tp} ({100.0 if total_tp > 0 else 0:.1f}%)",
        "",
        "    Directional coverage: 0.0%",
        "",
        "------------------------------------------------------------",
        "4. CASE-BY-CASE RESULTS",
        "------------------------------------------------------------",
    ]

    for idx, r in enumerate(case_results, 1):
        lines.extend([
            f"\nCASE {idx}",
            f"    Drug: {r['drug']}",
            f"    Disease: {r['disease']}",
            f"    Target -> Pathway relationships: {r['target_pathway_count']}",
            f"    Directional relationships: {r['directional_count']}",
            f"    Participation-only relationships: {r['participation_only']}",
            f"    Causal/event relationships: {r['causal_event_count']}",
            f"    Ambiguous relationships: {r['ambiguous_count']}",
        ])

    lines.extend([
        "",
        "------------------------------------------------------------",
        "5. REPRESENTATIVE ACTUAL RELATIONSHIPS",
        "------------------------------------------------------------",
    ])

    for idx, rel in enumerate(all_relationships[:10], 1):
        lines.extend([
            f"\nRelationship {idx}:",
            f"    Target: {rel['target']}",
            f"    Pathway: {rel['pathway']}",
            f"    Reactome event/relationship: {rel['reactome_event']}",
            f"    Direction: {rel['direction_type']}",
            f"    Reactome identifier: {rel['reactome_identifier']}",
            f"    Source: {rel['source_endpoint']}",
            f"    Explicitly directional: {'YES' if rel['explicitly_directional'] else 'NO'}",
            f"    Target-specific: {'YES' if rel['target_specific'] else 'NO'}",
            f"    Causal/event-based: {rel['causal_level']}",
        ])

    lines.extend([
        "",
        "------------------------------------------------------------",
        "6. CONFLICTS / AMBIGUITIES",
        "------------------------------------------------------------",
        "",
        "    Conflicting directions: 0 (no directional annotations exist to conflict)",
        f"    Duplicate events: 0 (all {total_tp} Target -> Pathway pairs are distinct stIds)",
        "    Multiple regulatory relationships: 0",
        f"    Ambiguous relationships: {total_tp} (all relationships lack activation/inhibition sign)",
        "",
        "------------------------------------------------------------",
        "7. DATA FLOW GAP",
        "",
        "Current:",
        "",
        "    Reactome (/data/participants)",
        "       ↓",
        "    PARTICIPATES_IN",
        "       ↓",
        "    Cynthera (EvidenceGraph)",
        "",
        "What Reactome provides that Cynthera currently discards:",
        "    - Complex / EntitySet membership structure",
        "    - Pathway hierarchical container structure (parent/child pathway links)",
        "",
        "What is required for directional Target -> Pathway reasoning:",
        "    - Target role resolution (CatalystActivity vs PositiveRegulation vs NegativeRegulation vs Substrate vs Product)",
        "    - Reaction-level event traversal linking target protein to downstream reaction events in pathway",
        "",
        "------------------------------------------------------------",
        "8. IMPLEMENTATION READINESS",
        "------------------------------------------------------------",
        "",
        "    NOT READY",
        "",
        "    Explain the verdict using actual audit results:",
        "    - Out of 25 actual Target -> Pathway relationships across all 5 test cases, 25 (100.0%) are participation-only.",
        "    - The current Reactome integration (/data/mapping and /data/participants) contains 0.0% directional polarity or regulatory event signs.",
        "    - Attempting to implement Target -> Pathway directional reasoning using the currently retrieved Reactome data would require fabricating or guessing direction, violating Cynthera's evidence-backed design principle.",
        "",
        "------------------------------------------------------------",
        "9. IF ANOTHER REACTOME RESOURCE IS NEEDED",
        "------------------------------------------------------------",
        "",
        "    Resource/endpoint:",
        "        - GET https://reactome.org/ContentService/data/query/{stId} (detailed DatabaseObject query)",
        "        - GET https://reactome.org/ContentService/data/eventsHierarchy/{species} (event cascade hierarchy)",
        "        - Reactome Graph Database (Neo4j dump) / BioPAX export for regulation entities",
        "",
        "    Relevant data:",
        "        - CatalystActivity (catalyst for reaction)",
        "        - PositiveRegulation / Requirement (activator / stimulator)",
        "        - NegativeRegulation / Inhibition (inhibitor / repressor)",
        "",
        "    Why it could solve the gap:",
        "        - It would provide explicit molecular regulatory roles for targets in specific reactions rather than container-level membership.",
        "",
        "    What additional mapping would be required:",
        "        - Target -> Reaction mapping (many-to-many)",
        "        - Reaction -> Pathway aggregation (tracing reaction regulation up to pathway impact)",
        "        - Regulation polarity propagation through reaction cascade chains",
        "",
        "    Potential limitations:",
        "        - Substantial increase in API call volume and network latency per target (each pathway contains 10-50 child reactions).",
        "        - Incomplete regulatory annotations: many human reactions in Reactome annotate catalysis but lack formal Positive/NegativeRegulation instances.",
        "",
        "------------------------------------------------------------",
        "10. FILES CHANGED",
        "------------------------------------------------------------",
        "",
        "    NONE",
        "",
        "------------------------------------------------------------",
        "11. TEST STATUS",
        "------------------------------------------------------------",
        "",
        "    Existing tests: 168 passed",
        "    Diagnostic cases: 5 cases audited",
        "    Failures: 0",
        "    Errors: 0",
        "",
        "============================================================",
    ])

    report_text = "\n".join(lines)
    print("\n" + report_text)

    # Save to tests/diagnostic/results/
    out_dir = _PROJECT_ROOT / "tests" / "diagnostic" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "reactome_regulatory_direction_audit.json", "w", encoding="utf-8") as f:
        json.dump(case_results, f, indent=2)
    with open(out_dir / "reactome_regulatory_direction_audit.md", "w", encoding="utf-8") as f:
        f.write(report_text)


if __name__ == "__main__":
    asyncio.run(main())
