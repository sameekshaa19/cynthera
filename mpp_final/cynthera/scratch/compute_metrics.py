import json

with open("scratch/phase4c_directional_audit_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

print("TOTAL CASES:", len(results))

all_targets = []
for case in results:
    drug = case["drug"]
    disease = case["disease"]
    mondo = case["mondo_id"]
    targets = case["targets"]
    print(f"\n=======================================================")
    print(f"CASE: {drug} -> {disease} (MONDO: {mondo}) | Targets: {len(targets)}")
    print(f"=======================================================")
    for t in targets:
        all_targets.append(t)
        print(f"Target: {t['gene_symbol']} / {t['uniprot_id']} ({t['target_name']})")
        print(f"  ChEMBL Action: {t['chembl_action']} (Polarity: {t['chembl_polarity']}, Grounding: {t['chembl_grounding']})")
        print(f"  OT Ensembl: {t['ot_ensembl_id']} (Status: {t['ot_mapping_status']})")
        print(f"  OT DoE Evidences: {t['ot_doe_count']} | Directional: {t['ot_doe_directional_count']} | Target: {t['ot_doe_dir_target']} | Trait: {t['ot_doe_dir_trait']} | Sources: {t['ot_doe_sources']}")
        print(f"  DATTs: Protein ID: {t['datts_protein_id']} | Total Records: {t['datts_found_count']} | Disease Matches: {t['datts_disease_matches']} | Action: {t['datts_action']} | Ref: {t['datts_ref']}")
        print(f"  Literature Claims: Total: {t['lit_claims_total']} | Canonically Grounded: {t['lit_claims_grounded']}")
        print(f"  Reactome Reactions: {t['reactome_rxns_count']} | Roles: {t['reactome_roles']} | Regulatory: {t['reactome_explicit_regulatory']} | Direction: {t['reactome_direction_summary']}")
        print(f"  DrugMechDB: Available: {t['drugmech_available']} | Target ID: {t['drugmech_target_id']} (Status: {t['drugmech_map_status']}) | Path: {t['drugmech_path_summary'][:100]}")
        print(f"  Convergence: {t['convergence']} (Directional Coverage: {t['directional_coverage_score']})")

print("\n" + "=" * 80)
print("COMPUTING CRITICAL COVERAGE METRICS (7 METRICS)")
print("=" * 80)

total_targets = len(all_targets)
explicit_chembl = sum(1 for t in all_targets if t["chembl_polarity"] != "UNKNOWN")
ot_doe_usable = sum(1 for t in all_targets if t["ot_doe_directional_count"] > 0)
datts_usable = sum(1 for t in all_targets if t["datts_action"] not in ["NONE", "UNKNOWN"])
lit_grounded = sum(1 for t in all_targets if t["lit_claims_grounded"] > 0)
drugmech_cases = sum(1 for c in results if any(t["drugmech_available"] for t in c["targets"]))
total_test_cases = len(results)

# Exact entity mapping rate
# Mappings attempted: For each target across OT, DATTs, DrugMechDB
ot_exact_res = sum(1 for t in all_targets if t["ot_mapping_status"] in ["EXACT", "RESOLVED"])
datts_exact_res = sum(1 for t in all_targets if t["datts_mapping_status"] in ["EXACT", "RESOLVED"])
dm_exact_res = sum(1 for t in all_targets if t["drugmech_map_status"] in ["EXACT", "RESOLVED"])
total_mappings_attempted = total_targets * 3
total_mappings_success = ot_exact_res + datts_exact_res + dm_exact_res

# Directional convergence rate
# target-disease pairs with convergent directional evidence / target-disease pairs with enough evidence to compare (>= 2 directional sources)
pairs_with_enough_ev = [t for t in all_targets if int(t["directional_coverage_score"].split("/")[0]) >= 2]
convergent_pairs = [t for t in pairs_with_enough_ev if t["convergence"] == "CONVERGENT"]

print(f"1. Drug-target polarity coverage: {explicit_chembl}/{total_targets} ({explicit_chembl/total_targets*100:.1f}%)")
print(f"2. Open Targets DoE coverage: {ot_doe_usable}/{total_targets} ({ot_doe_usable/total_targets*100:.1f}%)")
print(f"3. DATTs coverage: {datts_usable}/{total_targets} ({datts_usable/total_targets*100:.1f}%)")
print(f"4. Literature directional coverage: {lit_grounded}/{total_targets} ({lit_grounded/total_targets*100:.1f}%)")
print(f"5. DrugMechDB coverage: {drugmech_cases}/{total_test_cases} ({drugmech_cases/total_test_cases*100:.1f}%)")
print(f"6. Exact entity mapping rate: {total_mappings_success}/{total_mappings_attempted} ({total_mappings_success/total_mappings_attempted*100:.1f}%) [OT: {ot_exact_res}/{total_targets}, DATTs: {datts_exact_res}/{total_targets}, DM: {dm_exact_res}/{total_targets}]")
print(f"7. Directional convergence rate: {len(convergent_pairs)}/{len(pairs_with_enough_ev)} ({len(convergent_pairs)/len(pairs_with_enough_ev)*100:.1f}%)")
