"""Phase 4D — Five Live Benchmark Cases Verification Script.

Executes MasterOrchestrator across:
1. Furosemide -> Edema
2. Propranolol -> Infantile Hemangioma
3. Dapagliflozin -> Heart Failure
4. Thalidomide -> Multiple Myeloma
5. Aspirin -> Colorectal Cancer

Prints full audit breakdown for Phase 4D Therapeutic Alignment.
"""
from __future__ import annotations

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

async def verify_5_cases():
    print("=" * 80)
    print("CYNTHERA PHASE 4D — THERAPEUTIC ALIGNMENT FIVE BENCHMARK CASES")
    print("=" * 80)

    orch = MasterOrchestrator()

    for drug, disease in TEST_CASES:
        print(f"\n================================================================================")
        print(f"CASE: {drug} -> {disease}")
        print(f"================================================================================")

        hyp, pkg, res = await orch.evaluate(drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=True)

        ta_report = res.audit_report.therapeutic_alignment
        if not ta_report:
            print("  [ERROR] No therapeutic alignment report found in ScientificAuditReport!")
            continue

        print(f"Overall Alignment:         {ta_report.get('overall_alignment')}")
        print(f"Total Independent Groups:  {ta_report.get('total_independent_groups')}")
        print(f"Supporting Groups Count:   {ta_report.get('supporting_groups_count')}")
        print(f"Opposing Groups Count:     {ta_report.get('opposing_groups_count')}")
        print(f"DrugMechDB Validated:      {ta_report.get('drugmechdb_validated')}")
        print(f"Overall Explanation:       {ta_report.get('explanation')}")

        print(f"\n--- Target-Level Alignments ---")
        for t in ta_report.get("target_alignments", []):
            tid = t.get("target_id")
            tname = t.get("target_name") or "—"
            is_prim = "PRIMARY" if t.get("is_primary") else "SECONDARY"
            d_act = t.get("drug_action")
            des_act = t.get("desired_target_action")
            al = t.get("alignment")
            supp = t.get("supporting_groups", [])
            opp = t.get("opposing_groups", [])
            egroups = t.get("evidence_groups", [])
            expl = t.get("explanation")

            print(f"\n  Target: {tid} ({tname}) [{is_prim}]")
            print(f"    - Drug Action (ChEMBL):           {d_act}")
            print(f"    - Desired Target Action:          {des_act}")
            print(f"    - Target Alignment Verdict:       {al}")
            print(f"    - Supporting Groups ({len(supp)}):       {supp[:5]}")
            print(f"    - Opposing Groups ({len(opp)}):         {opp[:5]}")
            print(f"    - Total Independent Groups:       {len(egroups)}")
            print(f"    - Explanation:                    {expl}")

            if egroups:
                print(f"    - Sample Evidence Group:          {egroups[0].get('group_id')} -> {egroups[0].get('summary')}")

        # Confirm scores unchanged
        print(f"\n--- Scoring Invariance Verification ---")
        print(f"  Support Score (SS):      {res.support_assessment.score:.3f} ({res.support_assessment.level})")
        print(f"  Mechanistic Score (MS):  {res.mechanistic_assessment.score:.3f} ({res.mechanistic_assessment.level})")
        print(f"  Risk Score (RS):         {res.risk_assessment.score:.3f} ({res.risk_assessment.level})")
        print(f"  Recommendation Status:   {res.recommendation_status.value}")

    print("\n" + "=" * 80)
    print("PHASE 4D FIVE-CASE VERIFICATION COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(verify_5_cases())
