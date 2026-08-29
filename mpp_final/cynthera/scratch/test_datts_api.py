import asyncio
import httpx
import json

async def test_datts_backend():
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        # Check filenames_to_download
        try:
            r = await client.get("https://datts.nibb.ac.jp/api/filenames_to_download/")
            print("filenames_to_download status:", r.status_code)
            print("filenames_to_download content:", r.text)
        except Exception as e:
            print("error filenames_to_download:", e)

        # Check GraphQL endpoint
        try:
            r_gql = await client.post("https://datts.nibb.ac.jp/graphql", json={"query": "{ __schema { types { name } } }"})
            print("GraphQL status:", r_gql.status_code)
            if r_gql.status_code == 200:
                print("GraphQL types:", [t["name"] for t in r_gql.json()["data"]["__schema"]["types"] if not t["name"].startswith("__")])
        except Exception as e:
            print("error graphql:", e)

asyncio.run(test_datts_backend())
