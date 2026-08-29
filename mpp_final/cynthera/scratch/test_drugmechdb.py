import asyncio
import httpx
import yaml
import json

async def test_sources():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test DrugMechDB raw github
        r = await client.get("https://raw.githubusercontent.com/SuLab/DrugMechDB/main/indication_paths.yaml")
        print("DrugMechDB status:", r.status_code)
        if r.status_code == 200:
            data = yaml.safe_load(r.text)
            print(f"DrugMechDB loaded: {len(data)} indication paths.")
            # Search for our 5 drugs: Furosemide, Propranolol, Dapagliflozin, Thalidomide, Aspirin
            drugs = ["furosemide", "propranolol", "dapagliflozin", "thalidomide", "aspirin"]
            for item in data:
                d_name = item.get("drug", "").lower()
                disease = item.get("disease", "").lower()
                for target_d in drugs:
                    if target_d in d_name:
                        print(f"  Match: Drug='{item.get('drug')}', Disease='{item.get('disease')}', ID='{item.get('graph', {}).get('id')}'")
        
asyncio.run(test_sources())
