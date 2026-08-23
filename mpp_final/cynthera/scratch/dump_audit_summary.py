import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("scratch/deep_reactome_complete_audit_metrics.json", "r", encoding="utf-8") as f:
    d = json.load(f)

print(f"Total relationships: {d['total_relationships']}")
for i, r in enumerate(d["records"], 1):
    print(f"\n[{i}] Case: {r['case']}")
    print(f"    Target: {r['target']} -> Pathway: {r['pathway_name']} ({r['pathway_stId']})")
    print(f"    Status: {r['target_mapping_status']} | Mapping: {r['mapping_type']} | Specificity: {r['specificity']}")
    print(f"    Matching Reactions Count: {r['matching_rxn_count']}")
    for m in r["matching_reactions"][:2]:
        print(f"      - {m['stId']} ({m['schemaClass']}) [{m['method']}]: {m['displayName']}")
        for ro in m["roles"]:
            print(f"          Role: {ro['role']} | Polarity: {ro['polarity']} | Field: {ro['raw_field']} | Obj: {ro.get('object_name')[:60]}")
    print(f"    Explicit Role: {r['has_explicit_role']} | Explicit Polarity: {r['has_explicit_polarity']} | Conflict: {r['conflict_status']}")
