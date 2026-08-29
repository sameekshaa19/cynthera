import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

async def inspect_furosemide_edema_contradiction():
    orch = MasterOrchestrator()
    hyp, pkg, res = await orch.evaluate("Furosemide", "Edema", policy=RetrievalPolicy.STANDARD, bypass_cache=True)
    
    print("=== FUROSEMIDE -> EDEMA CONTRADICTIONS AUDIT ===")
    print(f"Total Contradictions: {len(res.contradictions)}")
    
    for i, c in enumerate(res.contradictions):
        print(f"\n--- Contradiction {i+1} ---")
        print(f"Claim A ID: {c.claim_id_a}")
        print(f"Claim B ID: {c.claim_id_b}")
        print(f"Score: {c.contradiction_score}")
        print(f"Explanation: {c.explanation}")

    # Let's inspect extracted claims from literature
    from backend.reasoning.extraction.claim_extraction_agent import ClaimExtractionAgent
    extractor = ClaimExtractionAgent()
    print(f"\nTotal Literature Records in Package: {len(pkg.literature_evidence)}")
    for j, ev in enumerate(pkg.literature_evidence[:10]):
        print(f"\nLiterature Record {j+1}: Citation: {ev.citation_key} | Title: {ev.title}")
        ev_claims = await extractor.extract_claims(ev, "Furosemide", "Edema")
        print(f"  Extracted Claims ({len(ev_claims)}):")
        for cl in ev_claims:
            print(f"    - Subject: '{cl.subject}' | Predicate: '{cl.predicate.value}' | Object: '{cl.object}' (confidence={cl.confidence})")
            print(f"      Raw text snippet: {cl.raw_text}")

asyncio.run(inspect_furosemide_edema_contradiction())
