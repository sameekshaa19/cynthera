import asyncio
import httpx

async def test_datts():
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Check https://datts.nibb.ac.jp
        try:
            r = await client.get("https://datts.nibb.ac.jp/")
            print("DATTs homepage status:", r.status_code)
            print("DATTs preview:", r.text[:300])
        except Exception as e:
            print("Error reaching DATTs homepage:", e)

        # Search for API endpoints or search endpoints on DATTs
        try:
            r2 = await client.get("https://datts.nibb.ac.jp/search?q=edema")
            print("DATTs search status:", r2.status_code)
        except Exception as e:
            print("Error searching DATTs:", e)

asyncio.run(test_datts())
