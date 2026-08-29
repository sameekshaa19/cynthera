import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.reactome import ReactomeConnector

async def test_probe():
    async with ReactomeConnector() as conn:
        rxns = await conn.fetch_reactions("P35354")
        print(f"P35354 reactions: {len(rxns)}")
        if rxns:
            r0 = rxns[0]
            stId = r0.get("stId")
            print(f"Reaction 0: {stId} - {r0.get('displayName')}")
            det = await conn.fetch_reaction_details(stId)
            part = await conn.fetch_participating_entities(stId)
            roles = ReactomeConnector.extract_target_roles(det, part, "P35354", "PTGS2")
            print(f"Extracted roles for PTGS2: {roles}")

        rxns_adrb1 = await conn.fetch_reactions("P08588")
        print(f"P08588 reactions: {len(rxns_adrb1)}")
        if rxns_adrb1:
            for r in rxns_adrb1[:3]:
                stId = r.get("stId")
                det = await conn.fetch_reaction_details(stId)
                part = await conn.fetch_participating_entities(stId)
                roles = ReactomeConnector.extract_target_roles(det, part, "P08588", "ADRB1")
                print(f"Reaction {stId} ({r.get('displayName')}) roles: {roles}")

asyncio.run(test_probe())
