import asyncio
import httpx
import json

async def introspect_ot_evidence():
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query {
      __type(name: "Evidence") {
        fields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
    }
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json={"query": query})
        if r.status_code == 200:
            fields = [f["name"] for f in r.json()["data"]["__type"]["fields"]]
            print("Evidence fields count:", len(fields))
            print("Evidence fields:", sorted(fields))

asyncio.run(introspect_ot_evidence())
