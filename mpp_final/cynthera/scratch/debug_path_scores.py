import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import PathFinder, PathScorer, MultiHopReasoner

async def debug_scores():
    orch = MasterOrchestrator()
    hypothesis, pkg, result = await orch.evaluate("Furosemide", "Edema", policy=RetrievalPolicy.STANDARD)
    builder = EvidenceGraphBuilder()
    graph = builder.build(pkg)
    drug_id = f"DRUG:{pkg.drug.name}"
    disease_id = f"DISEASE:{pkg.disease.name}"

    finder = PathFinder()
    paths = finder.find(graph, drug_id, disease_id)
    print(f"Raw paths count: {len(paths)}")
    scorer = PathScorer()
    for idx, p in enumerate(paths):
        s = scorer.score(p)
        hops_info = [(h.label, h.name, h.evidence_strength, h.status) for h in p.hops]
        print(f"\nPath {idx} ({len(p.hops)-1} hops) -> Score: {s}")
        for h in hops_info:
            print(f"   {h}")

    reasoner = MultiHopReasoner()
    final_paths = reasoner.trace_paths(pkg)
    print(f"\nFinal paths from trace_paths: {len(final_paths)}")

asyncio.run(debug_scores())
