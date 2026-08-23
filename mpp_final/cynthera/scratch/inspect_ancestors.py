import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("scratch/deep_reactome_raw_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for u, t_info in data["target_data"].items():
    sym = t_info["symbol"]
    print(f"\n=======================================================")
    print(f"TARGET: {sym} ({u})")
    print(f"=======================================================")
    print("Reactions mapped by Reactome:")
    for rxn in t_info["reactions"]:
        rst = rxn["stId"]
        anc = data["rxn_ancestors"].get(rst, [])
        anc_pws = set()
        for path in anc:
            if isinstance(path, list):
                for node in path:
                    sc = node.get("schemaClass", "")
                    if "Pathway" in sc:
                        anc_pws.add(f"{node.get('stId')} ({node.get('displayName')})")
        print(f"  Rxn {rst}: {rxn.get('displayName')}")
        print(f"    SchemaClass: {rxn.get('schemaClass')}")
        print(f"    Ancestor Pathways ({len(anc_pws)}): {list(anc_pws)}")

    print("\nExisting Cynthera Pathways for this target:")
    for pw in t_info["pathways"]:
        print(f"  PW {pw.get('stId')}: {pw.get('displayName')}")
