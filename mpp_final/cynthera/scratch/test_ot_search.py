import asyncio
import httpx
import json

async def test_ot_target_search():
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query SearchTarget($name: String!) {
      search(queryString: $name, entityNames: ["target"], page: {index: 0, size: 5}) {
        hits {
          id
          name
          entity
          score
        }
      }
    }
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        for term in ["SLC12A1", "Q13621", "ADRB1", "ADRB2", "SLC5A2", "CRBN", "PTGS1", "PTGS2"]:
            r = await client.post(url, json={"query": query, "variables": {"name": term}})
            print(f"Search for {term}:")
            hits = (r.json().get("data") or {}).get("search", {}).get("hits", [])
            for h in hits:
                print(f"  id: {h.get('id')} | name: {h.get('name')} | score: {h.get('score')}")

asyncio.run(test_ot_target_search())
