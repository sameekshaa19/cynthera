import asyncio
import json
import httpx

async def check_ot_graphql_doe():
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    
    # Query introspecting target or disease fields for directionOfEffect / genetic evidence
    query = """
    query IntrospectDOE {
      __type(name: "Target") {
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
        try:
            r = await client.post(url, json={"query": query})
            print("Target fields response status:", r.status_code)
            fields = [f["name"] for f in r.json()["data"]["__type"]["fields"]]
            print("Target fields matching 'direction' or 'effect':", [f for f in fields if "direct" in f.lower() or "effect" in f.lower() or "genetic" in f.lower()])
        except Exception as e:
            print("Error introspecting OT Target:", e)

        query2 = """
        query IntrospectTypes {
          __schema {
            types {
              name
            }
          }
        }
        """
        try:
            r2 = await client.post(url, json={"query": query2})
            types = [t["name"] for t in r2.json()["data"]["__schema"]["types"]]
            doe_types = [t for t in types if "direction" in t.lower() or "effect" in t.lower() or "doe" in t.lower()]
            print("Types matching 'direction' or 'effect':", doe_types)
        except Exception as e:
            print("Error introspecting schema types:", e)

asyncio.run(check_ot_graphql_doe())
