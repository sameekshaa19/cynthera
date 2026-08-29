import asyncio
import httpx
import json

async def test_ot_doe_query():
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    
    # Test query for SLC12A1 (Furosemide target) and Edema (or ADRB1/2, SGLT2/SLC5A2, CRBN, PTGS1/PTGS2/COX)
    query = """
    query TargetDOE($ensemblId: String!, $efoId: String!) {
      target(ensemblId: $ensemblId) {
        id
        approvedSymbol
        evidences(efoIds: [$efoId], size: 50) {
          count
          rows {
            datasourceId
            datatypeId
            disease {
              id
              name
            }
            score
            directionOnTrait
            variantEffect
            variantId
            variantRsId
            literature
          }
        }
      }
    }
    """
    # SLC12A1 is ENSG00000074803
    # PTGS2 (COX-2) is ENSG00000073756, PTGS1 (COX-1) is ENSG00000095303
    # SLC5A2 (SGLT2) is ENSG00000140675
    # ADRB1 is ENSG00000043591, ADRB2 is ENSG00000169252
    # CRBN is ENSG00000100878
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json={"query": query, "variables": {"ensemblId": "ENSG00000073756", "efoId": "MONDO_0005575"}}) # PTGS2 / Colorectal Cancer
        print("OT DoE PTGS2 -> Colorectal cancer response status:", r.status_code)
        print(json.dumps(r.json(), indent=2)[:1000])

asyncio.run(test_ot_doe_query())
