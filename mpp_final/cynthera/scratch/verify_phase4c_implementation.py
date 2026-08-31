"""Live Verification Script for Phase 4C Implementation across the 5 Test Cases.

Runs the full pipeline with live/cached connectors and prints concise, structured
verification results for:
1. Furosemide -> Edema
2. Propranolol -> Infantile Hemangioma
3. Dapagliflozin -> Heart Failure
4. Thalidomide -> Multiple Myeloma
5. Aspirin -> Colorectal Cancer
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

TEST_CASES = [
    ("Furosemide", "Edema"),
    ("Propranolol", "Infantile Hemangioma"),
    ("Dapagliflozin", "Heart Failure"),
    ("Thalidomide", "Multiple Myeloma"),
    ("Aspirin", "Colorectal Cancer"),
]

async def verify_case(drug_name: str, disease_name: str):
    print("=" * 80)
    print(f"CASE VERIFICATION: {drug_name} -> {disease_name}")
    print("=" * 80)

    orch = MasterOrchestrator()
    hyp, pkg, res = await orch.evaluate(drug_name, disease_name, policy=RetrievalPolicy.STANDARD, bypass_cache=False)

    print(f"Sources Queried: {pkg.sources_queried}")
    print(f"Sources Failed: {pkg.sources_failed}")
    print(f"Retrieval Confidence: {pkg.retrieval_confidence}")
    print(f"Total Targets: {len(pkg.targets)} | Total Proteins: {len(pkg.proteins)}")
    print(f"Open Targets DoE Records: {len(pkg.opentargets_doe_evidence)}")
    print(f"DATTs Records: {len(pkg.datts_evidence)}")
    print(f"DrugMechDB Records: {len(pkg.drugmechdb_evidence)}")
    print(f"Normalized Therapeutic Direction Evidence Records: {len(pkg.therapeutic_direction_evidence)}")

    # Index by target symbol/uniprot
    protein_map = {p.uniprot_accession: p for p in pkg.proteins}

    for t in pkg.targets:
        prot = protein_map.get(t.protein_uniprot)
        sym = prot.gene_symbol if prot else "UNKNOWN"
        name = prot.name if prot else f"Protein {t.protein_uniprot}"

        # Match OT DoE
        ot_matches = [
            d for d in pkg.opentargets_doe_evidence
            if d.target_id.upper() in (sym.upper(), t.protein_uniprot.upper()) or getattr(d, "datasource_id", "")
        ]
        ot_dir_target = next((d.direction_on_target for d in pkg.opentargets_doe_evidence if d.direction_on_target), "UNKNOWN")
        ot_dir_trait = next((d.direction_on_trait for d in pkg.opentargets_doe_evidence if d.direction_on_trait), "UNKNOWN")
        ot_datasources = list(set(d.datasource_id for d in pkg.opentargets_doe_evidence if d.datasource_id))

        # Match DATTs
        datts_matches = [
            d for d in pkg.datts_evidence
            if (d.gene_symbol and d.gene_symbol.upper() == sym.upper()) or (d.uniprot_id and d.uniprot_id.upper() == t.protein_uniprot.upper())
        ]
        datts_action = datts_matches[0].required_action.value if datts_matches else "NONE"
        datts_citation = datts_matches[0].literature if datts_matches else "NONE"
        datts_prot_id = datts_matches[0].datts_protein_id if datts_matches else "NONE"

        # Match DrugMechDB
        dm_matches = [
            dm for dm in pkg.drugmechdb_evidence
            if dm.is_curated_path_available
        ]
        dm_available = "YES" if dm_matches else "NO"
        dm_summary = dm_matches[0].path_summary[:80] if dm_matches else "NONE"

        # Match normalized TherapeuticDirectionEvidence
        norm_records = [
            e for e in pkg.therapeutic_direction_evidence
            if e.target_canonical_id.upper() in (sym.upper(), t.protein_uniprot.upper())
        ]
        mapping_status = norm_records[0].mapping_status if norm_records else "RESOLVED"
        indep_groups = list(set(e.independence_group for e in norm_records if e.independence_group))

        print(f"\n  Target: {sym} ({t.protein_uniprot}) — {name}")
        print(f"    - ChEMBL Action:            {t.mechanism}")
        print(f"    - Open Targets DoE:         Target={ot_dir_target} | Trait={ot_dir_trait} | Sources={ot_datasources} (Rows: {len(pkg.opentargets_doe_evidence)})")
        print(f"    - DATTs Action:             {datts_action} (Target ID: {datts_prot_id} | Citation: {datts_citation})")
        print(f"    - DrugMechDB Available:     {dm_available} (Path: {dm_summary})")
        print(f"    - Entity Mapping Status:    {mapping_status}")
        print(f"    - Independence Groups:      {indep_groups}")

async def run_all():
    print("=" * 80)
    print("STARTING LIVE 5-CASE VERIFICATION FOR PHASE 4C")
    print("=" * 80)
    for drug, disease in TEST_CASES:
        try:
            await verify_case(drug, disease)
        except Exception as e:
            print(f"Error verifying {drug} -> {disease}: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(run_all())
