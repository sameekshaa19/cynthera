import json

with open("scratch/phase4c_directional_audit_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

for case in results:
    drug = case["drug"]
    disease = case["disease"]
    print(f"\n==================== {drug} -> {disease} ====================")
    for t in case["targets"]:
        print(f"Target: {t['gene_symbol']} | UniProt: {t['uniprot_id']} | Name: {t['target_name']}")
        print(f"  ChEMBL Action: {t['chembl_action']} -> Polarity: {t['chembl_polarity']}")
        print(f"  OT: Ensembl={t['ot_ensembl_id']} (Status: {t['ot_mapping_status']}) | DoE count={t['ot_doe_directional_count']} | Target={t['ot_doe_dir_target']} | Trait={t['ot_doe_dir_trait']}")
        print(f"  DATTs: Action={t['datts_action']} | Status={t['datts_mapping_status']} | RelType={t['datts_rel_type']} | Ref={t['datts_ref']}")
        print(f"  Literature: Grounded={t['lit_claims_grounded']} / Total={t['lit_claims_total']}")
        print(f"  Reactome: Reactions={t['reactome_rxns_count']} | Roles={t['reactome_roles']} | Regulatory={t['reactome_explicit_regulatory']}")
        print(f"  DrugMechDB: Available={t['drugmech_available']} | Target={t['drugmech_target_id']} (Status: {t['drugmech_map_status']})")
        print(f"  Convergence: {t['convergence']} | Coverage: {t['directional_coverage_score']}")
