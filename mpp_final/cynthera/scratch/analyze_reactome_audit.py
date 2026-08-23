"""
Detailed Reactome Capability Audit Analyzer
Analyzes scratch/deep_reactome_raw_results.json and prints comprehensive empirical metrics for Audits 1-13.
"""
import json
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("scratch/deep_reactome_raw_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

target_data = data["target_data"]
rxn_details = data["rxn_details"]
rxn_ancestors = data["rxn_ancestors"]
rxn_participants = data["rxn_participants"]
cases = data["cases"]

print("Loaded audit data.")
targets = target_data.keys()
print(f"Targets analyzed: {list(targets)}")

# Helper to find if target is inside an entity (recursively or via refEntities)
def find_target_in_entity(entity_obj, uniprot_id, symbol):
    if not entity_obj or not isinstance(entity_obj, dict):
        return False, None
    disp = entity_obj.get("displayName", "")
    # check refEntities
    for ref in entity_obj.get("refEntities", []):
        if isinstance(ref, dict) and ref.get("identifier") == uniprot_id:
            return True, entity_obj.get("schemaClass", "Entity")
    # check referenceEntity
    ref_ent = entity_obj.get("referenceEntity")
    if isinstance(ref_ent, dict) and ref_ent.get("identifier") == uniprot_id:
        return True, entity_obj.get("schemaClass", "Entity")
    # check crossReferences
    for cr in entity_obj.get("crossReference", []):
        if isinstance(cr, dict) and cr.get("identifier") == uniprot_id:
            return True, entity_obj.get("schemaClass", "Entity")
    # check text match if gene symbol matches exact word
    if symbol and (f" {symbol} " in f" {disp} " or f":{symbol}:" in disp or f":{symbol} " in disp or f"({symbol})" in disp or disp.startswith(f"{symbol} ") or disp.endswith(f" {symbol}") or disp == symbol or f"[{symbol}]" in disp):
        return True, entity_obj.get("schemaClass", "Entity")
    # check hasComponent
    for comp in entity_obj.get("hasComponent", []):
        found, sc = find_target_in_entity(comp, uniprot_id, symbol)
        if found:
            return True, f"Complex member (in {entity_obj.get('schemaClass', 'Complex')})"
    # check hasMember
    for mem in entity_obj.get("hasMember", []):
        found, sc = find_target_in_entity(mem, uniprot_id, symbol)
        if found:
            return True, f"EntitySet member (in {entity_obj.get('schemaClass', 'EntitySet')})"
    return False, None

def get_target_roles_in_rxn(stId, uniprot, symbol):
    det = rxn_details.get(stId, {})
    parts = rxn_participants.get(stId, [])
    
    roles = []
    
    # 1. Catalyst Activity
    for cat in det.get("catalystActivity") or []:
        if not isinstance(cat, dict):
            continue
        cat_disp = cat.get("displayName", "")
        pe = cat.get("physicalEntity", {})
        found_pe, sc = find_target_in_entity(pe, uniprot, symbol)
        found_disp = (symbol and symbol in cat_disp)
        found_part = False
        for p in parts:
            p_found, p_sc = find_target_in_entity(p, uniprot, symbol)
            if p_found and (p.get("displayName", "") in cat_disp or (isinstance(pe, dict) and p.get("displayName", "") in pe.get("displayName", ""))):
                found_part = True
        if found_pe or found_disp or found_part:
            roles.append({
                "role": "CatalystActivity",
                "polarity": "CATALYSIS",
                "raw_field": "catalystActivity",
                "object_name": cat_disp,
                "schemaClass": cat.get("schemaClass", "CatalystActivity")
            })

    # 2. Positive Regulation
    for reg in det.get("positiveRegulation") or []:
        if not isinstance(reg, dict):
            continue
        reg_disp = reg.get("displayName", "")
        pe = reg.get("regulator", {})
        found_pe, sc = find_target_in_entity(pe, uniprot, symbol)
        found_disp = (symbol and symbol in reg_disp)
        if found_pe or found_disp:
            roles.append({
                "role": "PositiveRegulation",
                "polarity": "POSITIVE",
                "raw_field": "positiveRegulation",
                "object_name": reg_disp,
                "schemaClass": reg.get("schemaClass", "PositiveRegulation")
            })

    # 3. Negative Regulation
    for reg in det.get("negativeRegulation") or []:
        if not isinstance(reg, dict):
            continue
        reg_disp = reg.get("displayName", "")
        pe = reg.get("regulator", {})
        found_pe, sc = find_target_in_entity(pe, uniprot, symbol)
        found_disp = (symbol and symbol in reg_disp)
        if found_pe or found_disp:
            roles.append({
                "role": "NegativeRegulation",
                "polarity": "NEGATIVE",
                "raw_field": "negativeRegulation",
                "object_name": reg_disp,
                "schemaClass": reg.get("schemaClass", "NegativeRegulation")
            })

    # 4. Requirement
    for req in det.get("requirement") or []:
        if not isinstance(req, dict):
            continue
        req_disp = req.get("displayName", "")
        pe = req.get("regulator", {})
        found_pe, sc = find_target_in_entity(pe, uniprot, symbol)
        found_disp = (symbol and symbol in req_disp)
        if found_pe or found_disp:
            roles.append({
                "role": "Requirement",
                "polarity": "REQUIREMENT",
                "raw_field": "requirement",
                "object_name": req_disp,
                "schemaClass": req.get("schemaClass", "Requirement")
            })

    # 5. Input
    for inp in det.get("input") or []:
        if not isinstance(inp, dict):
            continue
        found_inp, sc = find_target_in_entity(inp, uniprot, symbol)
        disp = inp.get("displayName", "")
        found_disp = (symbol and symbol in disp)
        found_part = False
        for p in parts:
            p_found, p_sc = find_target_in_entity(p, uniprot, symbol)
            if p_found and p.get("displayName", "") in disp:
                found_part = True
        if found_inp or found_disp or found_part:
            roles.append({
                "role": "Input",
                "polarity": "NO_DIRECTION",
                "raw_field": "input",
                "object_name": disp,
                "schemaClass": inp.get("schemaClass", "Input")
            })

    # 6. Output
    for out in det.get("output") or []:
        if not isinstance(out, dict):
            continue
        found_out, sc = find_target_in_entity(out, uniprot, symbol)
        disp = out.get("displayName", "")
        found_disp = (symbol and symbol in disp)
        found_part = False
        for p in parts:
            p_found, p_sc = find_target_in_entity(p, uniprot, symbol)
            if p_found and p.get("displayName", "") in disp:
                found_part = True
        if found_out or found_disp or found_part:
            roles.append({
                "role": "Output",
                "polarity": "NO_DIRECTION",
                "raw_field": "output",
                "object_name": disp,
                "schemaClass": out.get("schemaClass", "Output")
            })

    # Fallback to participants if no role found
    if not roles:
        for p in parts:
            if not isinstance(p, dict):
                continue
            p_found, p_sc = find_target_in_entity(p, uniprot, symbol)
            if p_found:
                roles.append({
                    "role": f"PhysicalEntity participant ({p.get('schemaClass', 'Participant')})",
                    "polarity": "UNKNOWN",
                    "raw_field": "participants",
                    "object_name": p.get("displayName", ""),
                    "schemaClass": p.get("schemaClass", "PhysicalEntity")
                })

    return roles

def get_ancestor_pathways(stId):
    anc_list = rxn_ancestors.get(stId, [])
    pathways = {}
    for path in anc_list:
        if isinstance(path, list):
            for item in path:
                if isinstance(item, dict):
                    sc = item.get("schemaClass", "")
                    if sc in ("Pathway", "TopLevelPathway"):
                        pathways[item.get("stId")] = {
                            "stId": item.get("stId"),
                            "displayName": item.get("displayName"),
                            "schemaClass": sc
                        }
    return pathways

# Let's run analysis for all 25 Target -> Pathway relationships
print("\n" + "="*80)
print("AUDIT OF 25 CYNTHERA TARGET -> PATHWAY RELATIONSHIPS")
print("="*80)

total_relationships = 0
rel_with_rxn_mapping = 0
rel_with_explicit_role = 0
rel_with_explicit_polarity = 0
rel_with_same_pathway = 0
rel_target_specific = 0

role_counts = defaultdict(int)
polarity_counts = defaultdict(int)
case_stats = []

detailed_relationships_results = []

for case_obj in cases:
    case_name = case_obj["case"]
    drug = case_obj["drug"]
    disease = case_obj["disease"]
    rels = case_obj["relationships"]
    
    print(f"\n--- CASE: {case_name} ---")
    c_tp = len(rels)
    c_rxn_mapped = 0
    c_role_resolved = 0
    c_polarity_resolved = 0
    c_same_pathway = 0

    for rel in rels:
        total_relationships += 1
        u = rel["uniprot"]
        sym = rel["target_symbol"]
        pw_stId = rel["pathway_stId"]
        pw_name = rel["pathway_name"]
        
        target_rxns = target_data.get(u, {}).get("reactions", [])
        
        matching_rxns = []
        for rxn in target_rxns:
            rst = rxn["stId"]
            anc_pws = get_ancestor_pathways(rst)
            if pw_stId in anc_pws:
                roles = get_target_roles_in_rxn(rst, u, sym)
                matching_rxns.append({
                    "rxn_stId": rst,
                    "rxn_name": rxn.get("displayName"),
                    "schemaClass": rxn.get("schemaClass"),
                    "roles": roles,
                    "ancestors": anc_pws
                })
        
        has_rxn = len(target_rxns) > 0
        has_same_pw = len(matching_rxns) > 0
        
        all_target_roles = []
        for r in matching_rxns:
            all_target_roles.extend(r["roles"])
            
        has_role = any(not r["role"].startswith("PhysicalEntity participant") for r in all_target_roles)
        has_polarity = any(r["polarity"] in ("POSITIVE", "NEGATIVE", "CATALYSIS", "REQUIREMENT") for r in all_target_roles)
        
        if has_rxn:
            rel_with_rxn_mapping += 1
            c_rxn_mapped += 1
        if has_same_pw:
            rel_with_same_pathway += 1
            c_same_pathway += 1
            rel_target_specific += 1
        if has_role and has_same_pw:
            rel_with_explicit_role += 1
            c_role_resolved += 1
        if has_polarity and has_same_pw:
            rel_with_explicit_polarity += 1
            c_polarity_resolved += 1
            
        for r in all_target_roles:
            role_counts[r["role"]] += 1
            polarity_counts[r["polarity"]] += 1

        print(f"  Target: {sym} ({u}) -> Pathway: {pw_name} [{pw_stId}]")
        print(f"    Total target reactions discovered: {len(target_rxns)}")
        print(f"    Reactions mapping to SAME pathway: {len(matching_rxns)}")
        for m in matching_rxns[:3]:
            print(f"      - Rxn {m['rxn_stId']} ({m['schemaClass']}): {m['rxn_name']}")
            for role_info in m["roles"]:
                print(f"        Role: {role_info['role']} | Polarity: {role_info['polarity']} | Field: {role_info['raw_field']} ({role_info.get('object_name')[:60]})")
        if not matching_rxns:
            print(f"      NO reactions under this pathway for target!")

        detailed_relationships_results.append({
            "case": case_name,
            "target": f"{sym} ({u})",
            "target_uniprot": u,
            "target_symbol": sym,
            "pathway_stId": pw_stId,
            "pathway_name": pw_name,
            "target_rxn_count": len(target_rxns),
            "matching_rxn_count": len(matching_rxns),
            "has_rxn_mapping": has_rxn,
            "has_same_pathway": has_same_pw,
            "has_explicit_role": has_role and has_same_pw,
            "has_explicit_polarity": has_polarity and has_same_pw,
            "matching_reactions": matching_rxns
        })

    case_stats.append({
        "case": case_name,
        "drug": drug,
        "disease": disease,
        "target_pathway_count": c_tp,
        "reaction_mapped": c_rxn_mapped,
        "same_pathway_mapped": c_same_pathway,
        "role_resolved": c_role_resolved,
        "polarity_resolved": c_polarity_resolved
    })

print("\n" + "="*80)
print("AGGREGATE METRICS")
print("="*80)
print(f"Total Target -> Pathway relationships: {total_relationships}")
print(f"Target -> Reaction resolved (any reaction): {rel_with_rxn_mapping} / {total_relationships} ({rel_with_rxn_mapping/total_relationships*100:.1f}%)")
print(f"Reaction -> SAME Cynthera Pathway resolved: {rel_with_same_pathway} / {total_relationships} ({rel_with_same_pathway/total_relationships*100:.1f}%)")
print(f"Explicit Target Role resolved (under same pathway): {rel_with_explicit_role} / {total_relationships} ({rel_with_explicit_role/total_relationships*100:.1f}%)")
print(f"Explicit Regulatory Polarity (under same pathway): {rel_with_explicit_polarity} / {total_relationships} ({rel_with_explicit_polarity/total_relationships*100:.1f}%)")
print(f"Target-Specific Resolution: {rel_target_specific} / {total_relationships} ({rel_target_specific/total_relationships*100:.1f}%)")

print("\nRole Breakdown in Same-Pathway Reactions:")
for r_name, cnt in sorted(role_counts.items(), key=lambda x: -x[1]):
    print(f"  {r_name}: {cnt}")

print("\nPolarity Breakdown in Same-Pathway Reactions:")
for p_name, cnt in sorted(polarity_counts.items(), key=lambda x: -x[1]):
    print(f"  {p_name}: {cnt}")

print("\nCase by Case Summary:")
for cs in case_stats:
    print(f"  Case: {cs['case']}")
    print(f"    Target -> Pathway: {cs['target_pathway_count']}")
    print(f"    Target -> Reaction: {cs['reaction_mapped']}")
    print(f"    Same-Pathway Mappings: {cs['same_pathway_mapped']}")
    print(f"    Explicit Roles: {cs['role_resolved']}")
    print(f"    Explicit Polarity: {cs['polarity_resolved']}")

# Save detailed results for report generation
with open("scratch/deep_reactome_analyzed_results.json", "w", encoding="utf-8") as f:
    json.dump({
        "total_relationships": total_relationships,
        "rel_with_rxn_mapping": rel_with_rxn_mapping,
        "rel_with_same_pathway": rel_with_same_pathway,
        "rel_with_explicit_role": rel_with_explicit_role,
        "rel_with_explicit_polarity": rel_with_explicit_polarity,
        "rel_target_specific": rel_target_specific,
        "role_counts": dict(role_counts),
        "polarity_counts": dict(polarity_counts),
        "case_stats": case_stats,
        "detailed_relationships": detailed_relationships_results
    }, f, indent=2, default=str)
