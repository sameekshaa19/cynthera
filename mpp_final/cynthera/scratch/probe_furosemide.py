import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline

async def probe_furosemide_reactome():
    uids = ["Q13621", "P02768", "P47745", "P29276"]
    print("Testing Reactome connector directly for Furosemide targets:")
    async with ReactomeConnector() as conn:
        for uid in uids:
            pw = await conn.fetch(uid)
            rxns = await conn.fetch_reactions(uid)
            print(f"Target {uid}: {len(pw)} pathways, {len(rxns)} reactions")
            for r in rxns[:3]:
                stId = r.get("stId")
                det = await conn.fetch_reaction_details(stId)
                part = await conn.fetch_participating_entities(stId)
                roles = ReactomeConnector.extract_target_roles(det, part, uid)
                print(f"   - Rxn {stId}: {r.get('displayName')} | Roles: {roles}")

    print("\nTesting Pipeline._fetch_reactome directly:")
    pipeline = RetrievalPipeline(bypass_raw_cache=True)
    res = await pipeline._fetch_reactome(uids, {"Q13621": "SLC12A1", "P02768": "ALB", "P47745": "ATP1A1", "P29276": "ADORA1"})
    print(f"Pathways: {len(res.get('pathways', []))}")
    print(f"Reaction evidence: {len(res.get('reaction_evidence', []))}")
    for rev in res.get("reaction_evidence", []):
        print(f"  - {rev.target_canonical_id} -> {rev.reaction_name} ({rev.reaction_id}) -> {rev.pathway_name} ({rev.pathway_id}) | Role: {rev.target_role}")

asyncio.run(probe_furosemide_reactome())
