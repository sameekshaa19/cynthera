"""Phase 3 Reactome Reaction / Event Evidence Layer Diagnostic Audit.

Audits the live retrieval, role extraction, graph enrichment, and mechanistic pathfinding
across the benchmark diagnostic drug-target cases.
"""
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.abspath("."))

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder, _NODE_REACTION
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner


BENCHMARK_CASES = [
    {
        "drug_name": "Propranolol",
        "chembl_id": "CHEMBL4",
        "disease_name": "Hypertension",
        "mesh_id": "D006973",
        "expected_target_symbols": ["ADRB1", "ADRB2"],
    },
    {
        "drug_name": "Dapagliflozin",
        "chembl_id": "CHEMBL2047164",
        "disease_name": "Diabetes Mellitus, Type 2",
        "mesh_id": "D003924",
        "expected_target_symbols": ["SLC5A2", "SLC5A1"],
    },
    {
        "drug_name": "Thalidomide",
        "chembl_id": "CHEMBL468",
        "disease_name": "Erythema Nodosum",
        "mesh_id": "D004893",
        "expected_target_symbols": ["TNF"],
    },
    {
        "drug_name": "Aspirin",
        "chembl_id": "CHEMBL25",
        "disease_name": "Inflammation",
        "mesh_id": "D007249",
        "expected_target_symbols": ["PTGS1", "PTGS2"],
    },
    {
        "drug_name": "Minoxidil",
        "chembl_id": "CHEMBL809",
        "disease_name": "Alopecia",
        "mesh_id": "D000505",
        "expected_target_symbols": ["KCNJ11"],
    },
]


def make_drug(name: str, chembl_id: str) -> Drug:
    return Drug(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value=chembl_id)],
        ),
    )


def make_disease(name: str, mesh_id: str) -> Disease:
    return Disease(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value=mesh_id)],
        ),
    )


async def run_diagnostic():
    print("=" * 80)
    print("CYNTHERA — PHASE 3 REACTOME REACTION EVIDENCE LAYER DIAGNOSTIC AUDIT")
    print("=" * 80)

    pipeline = RetrievalPipeline()
    builder = EvidenceGraphBuilder()
    reasoner = MultiHopReasoner()

    total_reactions_extracted = 0
    total_roles_extracted = 0
    roles_breakdown = {}
    directions_breakdown = {}
    audit_results = []

    for case in BENCHMARK_CASES:
        d_name = case["drug_name"]
        dis_name = case["disease_name"]
        print(f"\n[AUDITING CASE] {d_name} -> {dis_name}")

        drug = make_drug(d_name, case["chembl_id"])
        disease = make_disease(dis_name, case["mesh_id"])
        hypo_id = uuid.uuid4()

        package = await pipeline.execute(drug, disease, hypo_id)
        print(f"  Targets retrieved: {len(package.targets)}")
        print(f"  Pathways retrieved: {len(package.pathways)}")
        print(f"  Reaction evidence records: {len(package.reactome_reaction_evidence)}")

        graph = builder.build(package)
        rxn_nodes = [n for n in graph.nodes.values() if n.label == _NODE_REACTION]
        print(f"  Graph Nodes: {len(graph.nodes)} (Reaction nodes: {len(rxn_nodes)})")
        print(f"  Graph Edges: {len(graph.edges)}")

        paths = reasoner.trace_paths(package)
        paths_with_reaction = [
            p for p in paths if any(h.label == "Reaction" for h in p.hops)
        ]
        print(f"  Mechanistic paths discovered: {len(paths)} (Reaction-enriched: {len(paths_with_reaction)})")

        case_roles = {}
        for rev in package.reactome_reaction_evidence:
            total_reactions_extracted += 1
            total_roles_extracted += 1
            r = rev.target_role
            d = rev.direction
            roles_breakdown[r] = roles_breakdown.get(r, 0) + 1
            directions_breakdown[d] = directions_breakdown.get(d, 0) + 1
            case_roles[r] = case_roles.get(r, 0) + 1

        print(f"  Role distribution in case: {case_roles}")

        audit_results.append({
            "drug": d_name,
            "disease": dis_name,
            "targets_count": len(package.targets),
            "pathways_count": len(package.pathways),
            "reaction_evidence_count": len(package.reactome_reaction_evidence),
            "graph_reaction_nodes": len(rxn_nodes),
            "paths_count": len(paths),
            "paths_with_reaction_count": len(paths_with_reaction),
            "sample_reaction_hops": [
                p.description for p in paths_with_reaction[:2]
            ],
        })

    print("\n" + "=" * 80)
    print("PHASE 3 AUDIT SUMMARY METRICS")
    print("=" * 80)
    print(f"Total reaction evidence records: {total_reactions_extracted}")
    print(f"Roles distribution: {roles_breakdown}")
    print(f"Direction distribution: {directions_breakdown}")

    with open("scratch/phase3_reactome_diagnostic_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "total_reaction_evidence": total_reactions_extracted,
            "roles_breakdown": roles_breakdown,
            "directions_breakdown": directions_breakdown,
            "cases": audit_results,
        }, f, indent=2)

    print("\nAudit results dumped to scratch/phase3_reactome_diagnostic_results.json")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
