"""
Parallel Complete Reactome Capability Audit Script
"""
import asyncio
import json
import sys
from collections import defaultdict
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REACTOME_BASE = "https://reactome.org/ContentService"

CASES = [
    {
        "case": "Propranolol -> Infantile Hemangioma",
        "drug": "Propranolol",
        "disease": "Infantile Hemangioma",
        "relationships": [
            {"target_symbol": "ADRB1", "uniprot": "P08588", "pathway_stId": "R-HSA-390696", "pathway_name": "Adrenoceptors"},
            {"target_symbol": "ADRB1", "uniprot": "P08588", "pathway_stId": "R-HSA-418555", "pathway_name": "G alpha (s) signalling events"}
        ]
    },
    {
        "case": "Dapagliflozin -> Heart Failure",
        "drug": "Dapagliflozin",
        "disease": "Heart Failure",
        "relationships": [
            {"target_symbol": "SLC5A2", "uniprot": "P31639", "pathway_stId": "R-HSA-5658208", "pathway_name": "Defective SLC5A2 causes renal glucosuria (GLYS1)"},
            {"target_symbol": "SLC5A2", "uniprot": "P31639", "pathway_stId": "R-HSA-189200", "pathway_name": "Cellular hexose transport"},
            {"target_symbol": "SLC5A1", "uniprot": "P13866", "pathway_stId": "R-HSA-5656364", "pathway_name": "Defective SLC5A1 causes congenital glucose/galactose malabsorption (GGM)"},
            {"target_symbol": "SLC5A1", "uniprot": "P13866", "pathway_stId": "R-HSA-8981373", "pathway_name": "Intestinal hexose absorption"},
            {"target_symbol": "SLC5A1", "uniprot": "P13866", "pathway_stId": "R-HSA-189200", "pathway_name": "Cellular hexose transport"}
        ]
    },
    {
        "case": "Thalidomide -> Multiple Myeloma",
        "drug": "Thalidomide",
        "disease": "Multiple Myeloma",
        "relationships": [
            {"target_symbol": "TNF", "uniprot": "P01375", "pathway_stId": "R-HSA-5668541", "pathway_name": "TNFR2 non-canonical NF-kB pathway"},
            {"target_symbol": "TNF", "uniprot": "P01375", "pathway_stId": "R-HSA-5626978", "pathway_name": "TNFR1-mediated ceramide production"},
            {"target_symbol": "TNF", "uniprot": "P01375", "pathway_stId": "R-HSA-9942503", "pathway_name": "Differentiation of naive CD4+ T cells to T helper 1 cells (Th1 cells)"},
            {"target_symbol": "TNF", "uniprot": "P01375", "pathway_stId": "R-HSA-5357786", "pathway_name": "TNFR1-induced proapoptotic signaling"},
            {"target_symbol": "TNF", "uniprot": "P01375", "pathway_stId": "R-HSA-5357956", "pathway_name": "TNFR1-induced NF-kappa-B signaling pathway"},
            {"target_symbol": "TNF", "uniprot": "P01375", "pathway_stId": "R-HSA-6783783", "pathway_name": "Interleukin-10 signaling"}
        ]
    },
    {
        "case": "Aspirin -> Colorectal Cancer",
        "drug": "Aspirin",
        "disease": "Colorectal Cancer",
        "relationships": [
            {"target_symbol": "PTGS2", "uniprot": "P35354", "pathway_stId": "R-HSA-9027604", "pathway_name": "Biosynthesis of electrophilic omega-3 PUFA oxo-derivatives"},
            {"target_symbol": "PTGS2", "uniprot": "P35354", "pathway_stId": "R-HSA-9025094", "pathway_name": "Biosynthesis of DPAn-3 SPMs"},
            {"target_symbol": "PTGS2", "uniprot": "P35354", "pathway_stId": "R-HSA-2142770", "pathway_name": "Synthesis of 15-eicosatetraenoic acid derivatives"},
            {"target_symbol": "PTGS2", "uniprot": "P35354", "pathway_stId": "R-HSA-9018679", "pathway_name": "Biosynthesis of EPA-derived SPMs"},
            {"target_symbol": "PTGS2", "uniprot": "P35354", "pathway_stId": "R-HSA-2162123", "pathway_name": "Synthesis of Prostaglandins (PG) and Thromboxanes (TX)"},
            {"target_symbol": "PTGS2", "uniprot": "P35354", "pathway_stId": "R-HSA-9018677", "pathway_name": "Biosynthesis of DHA-derived SPMs"}
        ]
    },
    {
        "case": "Minoxidil -> Hair Loss",
        "drug": "Minoxidil",
        "disease": "Hair Loss",
        "relationships": [
            {"target_symbol": "KCNJ11", "uniprot": "Q14654", "pathway_stId": "R-HSA-5678420", "pathway_name": "Defective ABCC9 causes CMD10, ATFB12 and Cantu syndrome"},
            {"target_symbol": "KCNJ11", "uniprot": "Q14654", "pathway_stId": "R-HSA-5683177", "pathway_name": "Defective ABCC8 can cause hypo- and hyper-glycemias"},
            {"target_symbol": "KCNJ11", "uniprot": "Q14654", "pathway_stId": "R-HSA-1296025", "pathway_name": "ATP sensitive Potassium channels"},
            {"target_symbol": "KCNJ11", "uniprot": "Q14654", "pathway_stId": "R-HSA-5578775", "pathway_name": "Ion homeostasis"},
            {"target_symbol": "KCNJ11", "uniprot": "Q14654", "pathway_stId": "R-HSA-422356", "pathway_name": "Regulation of insulin secretion"},
            {"target_symbol": "KCNJ11", "uniprot": "Q14654", "pathway_stId": "R-HSA-382556", "pathway_name": "ABC-family protein mediated transport"}
        ]
    }
]

async def robust_get(client, sem, endpoint, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with sem:
                r = await client.get(endpoint)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 404:
                    return None
        except Exception:
            await asyncio.sleep(0.3 * (attempt + 1))
    return None

async def main():
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=20)
    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient(base_url=REACTOME_BASE, timeout=20.0, limits=limits) as client:
        targets = {}
        pathways = {}
        for c in CASES:
            for rel in c["relationships"]:
                targets[rel["uniprot"]] = rel["target_symbol"]
                pathways[rel["pathway_stId"]] = rel["pathway_name"]

        print(f"Auditing {len(targets)} Targets and {len(pathways)} Pathways across {len(CASES)} Cases...", flush=True)

        async def fetch_target_info(u, sym):
            rxns = await robust_get(client, sem, f"/data/mapping/UniProt/{u}/reactions") or []
            pws = await robust_get(client, sem, f"/data/mapping/UniProt/{u}/pathways") or []
            return u, sym, rxns, pws

        target_tasks = [fetch_target_info(u, sym) for u, sym in targets.items()]
        t_results = await asyncio.gather(*target_tasks)

        target_rxns = {}
        target_pws = {}
        all_rxn_stIds = set()
        dbId_to_stId = {}
        for u, sym, rxns, pws in t_results:
            target_rxns[u] = rxns
            target_pws[u] = pws
            for r in rxns:
                all_rxn_stIds.add(r["stId"])
                if "dbId" in r and "stId" in r:
                    dbId_to_stId[r["dbId"]] = r["stId"]

        async def fetch_pw_info(p_stId, p_name):
            p_data = await robust_get(client, sem, f"/data/query/enhanced/{p_stId}") or {}
            has_ev = p_data.get("hasEvent", [])
            return p_stId, {
                "displayName": p_data.get("displayName", p_name),
                "hasEvent": has_ev,
                "schemaClass": p_data.get("schemaClass", "Pathway")
            }

        pw_tasks = [fetch_pw_info(p_stId, p_name) for p_stId, p_name in pathways.items()]
        pw_results = await asyncio.gather(*pw_tasks)
        pathway_events = dict(pw_results)

        print(f"Discovered {len(all_rxn_stIds)} unique reactions. Fetching details concurrently...", flush=True)

        async def fetch_rxn_data(stId):
            det = await robust_get(client, sem, f"/data/query/enhanced/{stId}") or {}
            anc = await robust_get(client, sem, f"/data/event/{stId}/ancestors") or []
            part = await robust_get(client, sem, f"/data/participants/{stId}/participatingPhysicalEntities") or []
            return stId, det, anc, part

        rxn_tasks = [fetch_rxn_data(stId) for stId in all_rxn_stIds]
        rxn_results = await asyncio.gather(*rxn_tasks)

        rxn_details = {}
        rxn_ancestors = {}
        rxn_participants = {}
        for stId, det, anc, part in rxn_results:
            rxn_details[stId] = det
            rxn_ancestors[stId] = anc
            rxn_participants[stId] = part
            if isinstance(det, dict) and "dbId" in det:
                dbId_to_stId[det["dbId"]] = stId

        print("Fetched all data. Analyzing roles, polarities, and mappings...", flush=True)

        def find_target_in_entity(entity_obj, uniprot_id, symbol):
            if not entity_obj or not isinstance(entity_obj, dict):
                return False, None
            disp = entity_obj.get("displayName", "")
            for ref in entity_obj.get("refEntities", []):
                if isinstance(ref, dict) and ref.get("identifier") == uniprot_id:
                    return True, entity_obj.get("schemaClass", "Entity")
            ref_ent = entity_obj.get("referenceEntity")
            if isinstance(ref_ent, dict) and ref_ent.get("identifier") == uniprot_id:
                return True, entity_obj.get("schemaClass", "Entity")
            for cr in entity_obj.get("crossReference", []):
                if isinstance(cr, dict) and cr.get("identifier") == uniprot_id:
                    return True, entity_obj.get("schemaClass", "Entity")
            if symbol and (f" {symbol} " in f" {disp} " or f":{symbol}:" in disp or f":{symbol} " in disp or f"({symbol})" in disp or disp.startswith(f"{symbol} ") or disp.endswith(f" {symbol}") or disp == symbol or f"[{symbol}]" in disp or f"{symbol}-" in disp or f"-{symbol}" in disp):
                return True, entity_obj.get("schemaClass", "Entity")
            for comp in entity_obj.get("hasComponent", []):
                if isinstance(comp, dict):
                    found, sc = find_target_in_entity(comp, uniprot_id, symbol)
                    if found:
                        return True, f"Complex member (in {entity_obj.get('schemaClass', 'Complex')})"
            for mem in entity_obj.get("hasMember", []):
                if isinstance(mem, dict):
                    found, sc = find_target_in_entity(mem, uniprot_id, symbol)
                    if found:
                        return True, f"EntitySet member (in {entity_obj.get('schemaClass', 'EntitySet')})"
            return False, None

        def extract_roles(stId, uniprot, symbol):
            det = rxn_details.get(stId, {})
            parts = rxn_participants.get(stId, [])
            roles = []
            
            # Catalyst Activity
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

            # Positive Regulation
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

            # Negative Regulation
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

            # Requirement
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

            # Input
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

            # Output
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

            # Fallback to participants
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

        def get_all_ancestor_pathways(stId):
            anc_list = rxn_ancestors.get(stId, [])
            pathways = {}
            for path in anc_list:
                if isinstance(path, list):
                    for item in path:
                        if isinstance(item, dict):
                            sc = item.get("schemaClass", "")
                            if "Pathway" in sc:
                                pathways[item.get("stId")] = {
                                    "stId": item.get("stId"),
                                    "displayName": item.get("displayName"),
                                    "schemaClass": sc
                                }
            return pathways

        audit_records = []
        for c in CASES:
            for rel in c["relationships"]:
                u = rel["uniprot"]
                sym = rel["target_symbol"]
                pw_stId = rel["pathway_stId"]
                pw_name = rel["pathway_name"]
                drug = c["drug"]
                disease = c["disease"]

                t_rxns = target_rxns.get(u, [])
                has_target_rxns = len(t_rxns) > 0

                matching_rxns = []
                # 1. Ancestors check
                for rxn in t_rxns:
                    rst = rxn["stId"]
                    anc = get_all_ancestor_pathways(rst)
                    if pw_stId in anc:
                        matching_rxns.append({
                            "stId": rst,
                            "displayName": rxn.get("displayName"),
                            "schemaClass": rxn.get("schemaClass"),
                            "method": "ANCESTOR_TRAVERSAL",
                            "roles": extract_roles(rst, u, sym)
                        })

                # 2. hasEvent check
                pw_ev_list = pathway_events.get(pw_stId, {}).get("hasEvent", [])
                for ev in pw_ev_list:
                    if isinstance(ev, dict):
                        ev_stId = ev.get("stId")
                        ev_disp = ev.get("displayName")
                        ev_sc = ev.get("schemaClass")
                    elif isinstance(ev, int):
                        ev_stId = dbId_to_stId.get(ev)
                        ev_disp = str(ev)
                        ev_sc = "Reaction"
                    else:
                        continue

                    if ev_stId and any(rx['stId'] == ev_stId for rx in t_rxns):
                        if not any(m['stId'] == ev_stId for m in matching_rxns):
                            matching_rxns.append({
                                "stId": ev_stId,
                                "displayName": ev_disp,
                                "schemaClass": ev_sc,
                                "method": "HAS_EVENT_TRAVERSAL",
                                "roles": extract_roles(ev_stId, u, sym)
                            })

                all_roles = []
                for m in matching_rxns:
                    all_roles.extend(m["roles"])

                has_same_pathway = len(matching_rxns) > 0
                has_explicit_role = any(not r["role"].startswith("PhysicalEntity participant") for r in all_roles) if has_same_pathway else False
                has_explicit_polarity = any(r["polarity"] in ("POSITIVE", "NEGATIVE", "CATALYSIS", "REQUIREMENT") for r in all_roles) if has_same_pathway else False
                
                if has_same_pathway:
                    is_direct = any(m["method"] == "HAS_EVENT_TRAVERSAL" for m in matching_rxns)
                    mapping_type = "DIRECT_PATHWAY_MAPPING" if is_direct else "HIERARCHICAL_PATHWAY_MAPPING"
                elif has_target_rxns:
                    mapping_type = "INDIRECT_MAPPING"
                else:
                    mapping_type = "NO_MAPPING"

                target_mapping_status = "RESOLVED" if has_target_rxns else "NOT_RESOLVED"
                specificity = "TARGET_SPECIFIC" if has_same_pathway else ("PATHWAY_LEVEL_ONLY" if has_target_rxns else "AMBIGUOUS")

                unique_roles = set(r["role"] for r in all_roles)
                unique_pols = set(r["polarity"] for r in all_roles)
                if len(unique_roles) > 1 or len(unique_pols) > 1:
                    conflict_status = "MULTI_ROLE"
                elif len(unique_roles) == 1:
                    conflict_status = "CONSISTENT"
                else:
                    conflict_status = "UNKNOWN"

                audit_records.append({
                    "case": c["case"],
                    "drug": drug,
                    "disease": disease,
                    "target": f"{sym} ({u})",
                    "target_uniprot": u,
                    "target_symbol": sym,
                    "pathway_stId": pw_stId,
                    "pathway_name": pw_name,
                    "target_mapping_status": target_mapping_status,
                    "target_rxn_count": len(t_rxns),
                    "matching_rxn_count": len(matching_rxns),
                    "mapping_type": mapping_type,
                    "specificity": specificity,
                    "has_same_pathway": has_same_pathway,
                    "has_explicit_role": has_explicit_role,
                    "has_explicit_polarity": has_explicit_polarity,
                    "conflict_status": conflict_status,
                    "roles": all_roles,
                    "matching_reactions": matching_rxns
                })

        N = len(audit_records)
        target_rxn_resolved = sum(1 for r in audit_records if r["target_mapping_status"] == "RESOLVED")
        same_pw_resolved = sum(1 for r in audit_records if r["has_same_pathway"])
        role_resolved = sum(1 for r in audit_records if r["has_explicit_role"])
        polarity_resolved = sum(1 for r in audit_records if r["has_explicit_polarity"])
        target_specific_resolved = sum(1 for r in audit_records if r["specificity"] == "TARGET_SPECIFIC")
        
        catalyst_count = sum(1 for r in audit_records if any(x["role"] == "CatalystActivity" for x in r["roles"]))
        pos_reg_count = sum(1 for r in audit_records if any(x["role"] == "PositiveRegulation" for x in r["roles"]))
        neg_reg_count = sum(1 for r in audit_records if any(x["role"] == "NegativeRegulation" for x in r["roles"]))
        req_count = sum(1 for r in audit_records if any(x["role"] == "Requirement" for x in r["roles"]))
        input_count = sum(1 for r in audit_records if any(x["role"] == "Input" for x in r["roles"]))
        output_count = sum(1 for r in audit_records if any(x["role"] == "Output" for x in r["roles"]))

        print("\n" + "="*80, flush=True)
        print("FINAL MEASURED REACTOME CAPABILITY AUDIT METRICS", flush=True)
        print("="*80, flush=True)
        print(f"Total Target -> Pathway relationships: {N}", flush=True)
        print(f"Target -> Reaction mapping: {target_rxn_resolved} / {N} ({target_rxn_resolved/N*100:.1f}%)", flush=True)
        print(f"Reaction -> Existing Cynthera Pathway: {same_pw_resolved} / {N} ({same_pw_resolved/N*100:.1f}%)", flush=True)
        print(f"Target role resolved (under same pathway): {role_resolved} / {N} ({role_resolved/N*100:.1f}%)", flush=True)
        print(f"  CatalystActivity: {catalyst_count} / {N} ({catalyst_count/N*100:.1f}%)", flush=True)
        print(f"  Positive regulation: {pos_reg_count} / {N} ({pos_reg_count/N*100:.1f}%)", flush=True)
        print(f"  Negative regulation: {neg_reg_count} / {N} ({neg_reg_count/N*100:.1f}%)", flush=True)
        print(f"  Requirement: {req_count} / {N} ({req_count/N*100:.1f}%)", flush=True)
        print(f"  Input: {input_count} / {N} ({input_count/N*100:.1f}%)", flush=True)
        print(f"  Output: {output_count} / {N} ({output_count/N*100:.1f}%)", flush=True)
        print(f"Explicit regulatory polarity: {polarity_resolved} / {N} ({polarity_resolved/N*100:.1f}%)", flush=True)
        print(f"Target-specific resolution: {target_specific_resolved} / {N} ({target_specific_resolved/N*100:.1f}%)", flush=True)

        print("\nPer-Case Breakdown:", flush=True)
        case_map = defaultdict(list)
        for r in audit_records:
            case_map[r["case"]].append(r)

        for cname, recs in case_map.items():
            tot = len(recs)
            rxn_c = sum(1 for x in recs if x["target_mapping_status"] == "RESOLVED")
            same_c = sum(1 for x in recs if x["has_same_pathway"])
            role_c = sum(1 for x in recs if x["has_explicit_role"])
            pol_c = sum(1 for x in recs if x["has_explicit_polarity"])
            print(f"  Case: {cname}", flush=True)
            print(f"    Target -> Pathway: {tot}", flush=True)
            print(f"    Target -> Reaction: {rxn_c}", flush=True)
            print(f"    Reaction -> Existing Pathway: {same_c}", flush=True)
            print(f"    Explicit Role: {role_c}", flush=True)
            print(f"    Explicit Polarity: {pol_c}", flush=True)

        with open("scratch/deep_reactome_complete_audit_metrics.json", "w", encoding="utf-8") as f:
            json.dump({
                "total_relationships": N,
                "target_rxn_resolved": target_rxn_resolved,
                "same_pw_resolved": same_pw_resolved,
                "role_resolved": role_resolved,
                "polarity_resolved": polarity_resolved,
                "target_specific_resolved": target_specific_resolved,
                "catalyst_count": catalyst_count,
                "pos_reg_count": pos_reg_count,
                "neg_reg_count": neg_reg_count,
                "req_count": req_count,
                "input_count": input_count,
                "output_count": output_count,
                "records": audit_records
            }, f, indent=2, default=str)

        print("\nComplete audit metrics saved to scratch/deep_reactome_complete_audit_metrics.json", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
