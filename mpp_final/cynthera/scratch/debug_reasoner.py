import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import PathFinder, PathScorer

async def debug_reasoner():
    orch = MasterOrchestrator()
    hypothesis, pkg, result = await orch.evaluate("Furosemide", "Edema", policy=RetrievalPolicy.STANDARD)
    builder = EvidenceGraphBuilder()
    graph = builder.build(pkg)

    drug_id = f"DRUG:{pkg.drug.name}"
    disease_id = f"DISEASE:{pkg.disease.name}"

    print(f"Drug ID in graph: {drug_id in graph.nodes} ({drug_id})")
    print(f"Disease ID in graph: {disease_id in graph.nodes} ({disease_id})")

    print("\n--- OUT EDGES FROM DRUG ---")
    for e in graph.out_edges(drug_id):
        print(f"  {e.source_id} -> {e.target_id} (pred={e.predicate}, strength={e.evidence_strength})")
        for e2 in graph.out_edges(e.target_id):
            print(f"    {e2.source_id} -> {e2.target_id} (pred={e2.predicate}, strength={e2.evidence_strength})")
            for e3 in graph.out_edges(e2.target_id):
                print(f"      {e3.source_id} -> {e3.target_id} (pred={e3.predicate}, strength={e3.evidence_strength})")
                for e4 in graph.out_edges(e3.target_id):
                    print(f"        {e4.source_id} -> {e4.target_id} (pred={e4.predicate}, strength={e4.evidence_strength})")
                    for e5 in graph.out_edges(e4.target_id):
                        print(f"          {e5.source_id} -> {e5.target_id} (pred={e5.predicate}, strength={e5.evidence_strength})")

    finder = PathFinder()
    paths = finder.find(graph, drug_id, disease_id)
    print(f"\nRaw paths found by PathFinder: {len(paths)}")
    scorer = PathScorer()
    for p in paths:
        score = scorer.score(p)
        print(f"  - Path ({len(p.hops)-1} hops): {p.description}")
        print(f"    Score: {score} | Hops statuses: {[h.status for h in p.hops]}")

asyncio.run(debug_reasoner())
