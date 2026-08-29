import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.retrieval_policy import RetrievalPolicy

async def test_hypothesis():
    print("Testing Reactome Pathway Fetching in Pipeline...")
    async with ReactomeConnector() as conn:
        # Check ACE (P12821) pathways
        ace_pw_res = await conn.fetch("P12821")
        ace_pws = [p.get("stId") for p in ace_pw_res.get("pathways", [])]
        print(f"P12821 pathways returned from Reactome ({len(ace_pws)}): {ace_pws}")

        # Check participants of R-HSA-2022377
        part_res = await conn.fetch_participants("R-HSA-2022377")
        uids = part_res.get("uniprot_ids", [])
        print(f"R-HSA-2022377 participants fetched directly ({len(uids)}): {uids}")
        print(f"Is P12821 in R-HSA-2022377 participants? {'P12821' in uids}")

asyncio.run(test_hypothesis())
