import asyncio
import httpx
import json

async def introspect_datts_graphql():
    query = """
    query {
      __type(name: "Query") {
        fields {
          name
          args {
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
      diseaseType: __type(name: "DiseaseType") {
        fields {
          name
        }
      }
      proteinType: __type(name: "ProteinType") {
        fields {
          name
        }
      }
      relationshipType: __type(name: "RelationshipType") {
        fields {
          name
        }
      }
    }
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post("https://datts.nibb.ac.jp/graphql", json={"query": query})
        print("DATTs GraphQL Schema Introspection:")
        print(json.dumps(r.json(), indent=2))

asyncio.run(introspect_datts_graphql())
