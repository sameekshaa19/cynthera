import asyncio
import httpx
import re

async def inspect_datts_api():
    async with httpx.AsyncClient(timeout=20.0) as client:
        js_url = "https://datts.nibb.ac.jp/js/app.8b585c29.js"
        r_js = await client.get(js_url)
        print(f"Loaded app.js, length {len(r_js.text)}")
        endpoints = re.findall(r'https?://[^\s"\'<>]+', r_js.text)
        print("Endpoints in app.js:", endpoints[:10])
        # Find axios / fetch calls
        api_paths = re.findall(r'["\'](/[^"\']+)["\']', r_js.text)
        interesting = [p for p in api_paths if any(k in p for k in ["api", "data", "json", "search", "disease", "target", "download"])]
        print("Interesting paths:", set(interesting))

asyncio.run(inspect_datts_api())
