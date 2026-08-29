import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.reactome import ReactomeConnector

async def test_probe_rxn():
    async with ReactomeConnector() as conn:
        stId = "R-HSA-379044"
        det = await conn.fetch_reaction_details(stId)
        part = await conn.fetch_participating_entities(stId)
        print("--- DETAILS ---")
        print("catalystActivity:", json.dumps(det.get("catalystActivity"), indent=2))
        print("input:", json.dumps(det.get("input"), indent=2))
        print("output:", json.dumps(det.get("output"), indent=2))
        print("--- PARTICIPANTS ---")
        print(json.dumps([{"dbId": p.get("dbId"), "displayName": p.get("displayName"), "schemaClass": p.get("schemaClass"), "refEntities": p.get("refEntities")} for p in part], indent=2))
        roles = ReactomeConnector.extract_target_roles(det, part, "P08588", "ADRB1")
        print("Extracted roles:", roles)

asyncio.run(test_probe_rxn())
