import asyncio
import httpx
import yaml
import json

async def inspect_drugmechdb_structure():
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get("https://raw.githubusercontent.com/SuLab/DrugMechDB/main/indication_paths.yaml")
        if r.status_code == 200:
            data = yaml.safe_load(r.text)
            print(f"Total paths: {len(data)}")
            if len(data) > 0:
                print("Sample keys in first item:", list(data[0].keys()))
                print("First item sample:", json.dumps(data[0], indent=2)[:500])
                
            # Search across all items for our 5 drugs and diseases
            # 1. Furosemide -> Edema
            # 2. Propranolol -> Infantile Hemangioma
            # 3. Dapagliflozin -> Heart Failure
            # 4. Thalidomide -> Multiple Myeloma
            # 5. Aspirin -> Colorectal Cancer
            target_drugs = ["furosemide", "propranolol", "dapagliflozin", "thalidomide", "aspirin"]
            matches = []
            for item in data:
                # check all string fields in item
                item_str = json.dumps(item).lower()
                for d in target_drugs:
                    if d in item_str:
                        matches.append((d, item.get("graph", {}).get("drug"), item.get("graph", {}).get("disease"), item.get("graph", {}).get("id"), item))
            
            print(f"\nTotal matches for the 5 drugs: {len(matches)}")
            for d, drug_field, disease_field, gid, full_item in matches:
                print(f"Drug Query: {d} | Drug Name: {drug_field} | Disease: {disease_field} | ID: {gid}")

asyncio.run(inspect_drugmechdb_structure())
