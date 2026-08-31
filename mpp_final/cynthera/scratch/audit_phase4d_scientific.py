"""Phase 4D Scientific Audit Diagnostic Script.

Executes:
1. Five Canonical Benchmark Cases Trace (Full Evidence Chain)
2. Counterfactual Direction Flip Tests
3. Conflict Resolution Diagnostic Tests
4. Independence & Dedup Collision Tests
5. UNKNOWN & Structural Leakage Tests
6. Multi-Target Primary vs Secondary Dominance Tests
7. Confidence Metric Boundary Behavior Tests
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
)
from backend.reasoning.directional.therapeutic_alignment import (
    derive_desired_target_action,
    normalize_drug_action,
    compare_drug_action_to_target_direction,
    group_evidence_by_independence,
    TherapeuticAlignmentEngine,
)
from backend.reasoning.directional.chembl_polarity import chembl_action_to_polarity
from backend.reasoning.directional.reactome_polarity import reactome_role_to_polarity

BENCHMARK_CASES = [
    ("Furosemide", "Edema"),
    ("Propranolol", "Infantile Hemangioma"),
    ("Dapagliflozin", "Heart Failure"),
    ("Thalidomide", "Multiple Myeloma"),
    ("Aspirin", "Colorectal Cancer"),
]


async def run_scientific_audit():
    print("=" * 80)
    print("CYNTHERA PHASE 4D SCIENTIFIC AUDIT — DIAGNOSTIC EXECUTION")
    print("=" * 80)

    engine = TherapeuticAlignmentEngine()
    orch = MasterOrchestrator()

    # ─────────────────────────────────────────────────────────────────────────────
    # PART A: FIVE CANONICAL BENCHMARK CASES DEEP TRACE
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART A: FIVE CANONICAL BENCHMARK CASES TRACE")
    print("=" * 80)

    for drug_name, disease_name in BENCHMARK_CASES:
        print(f"\n=======================================================")
        print(f"CASE: {drug_name} -> {disease_name}")
        print(f"=======================================================")

        hyp, pkg, res = await orch.evaluate(drug_name, disease_name, policy=RetrievalPolicy.STANDARD, bypass_cache=True)
        ta_report = res.audit_report.therapeutic_alignment

        print(f"Overall Alignment:         {ta_report.get('overall_alignment')}")
        print(f"Total Independent Groups:  {ta_report.get('total_independent_groups')}")
        print(f"Supporting Groups Count:   {ta_report.get('supporting_groups_count')}")
        print(f"Opposing Groups Count:     {ta_report.get('opposing_groups_count')}")
        print(f"DrugMechDB Validated:      {ta_report.get('drugmechdb_validated')}")
        print(f"Overall Explanation:       {ta_report.get('explanation')}")

        for t in ta_report.get("target_alignments", []):
            tid = t.get("target_id")
            tname = t.get("target_name") or "—"
            is_prim = "PRIMARY" if t.get("is_primary") else "SECONDARY"
            d_act = t.get("drug_action")
            des_act = t.get("desired_target_action")
            al = t.get("alignment")
            conf = t.get("confidence")
            supp = t.get("supporting_groups", [])
            opp = t.get("opposing_groups", [])
            egroups = t.get("evidence_groups", [])

            print(f"\n  Target: {tid} ({tname}) [{is_prim}]")
            print(f"    - Drug Action (ChEMBL):           {d_act}")
            print(f"    - Desired Target Action:          {des_act}")
            print(f"    - Target Alignment Verdict:       {al} (Confidence: {conf})")
            print(f"    - Supporting Groups ({len(supp)}):       {supp[:4]}")
            print(f"    - Opposing Groups ({len(opp)}):         {opp[:4]}")
            print(f"    - Total Groups for Target:        {len(egroups)}")
            print(f"    - Explanation:                    {t.get('explanation')}")

            # Print detailed member evidence provenance for primary target
            if is_prim == "PRIMARY" and egroups:
                print(f"    - Evidence Groups Detail:")
                for eg in egroups[:3]:
                    print(f"        * Group ID:    {eg.get('group_id')}")
                    print(f"          Sources:     {eg.get('sources')}")
                    print(f"          Desired:     {eg.get('desired_action')}")
                    print(f"          Grounding:   {eg.get('causal_grounding')}")
                    print(f"          References:  {eg.get('references')[:3]}")
                    print(f"          Member Rows: {eg.get('member_record_count')}")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART B: COUNTERFACTUAL / DIRECTION FLIP TESTS
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART B: COUNTERFACTUAL DIRECTION FLIP TESTS")
    print("=" * 80)

    # Base evidence: LoF + protect (desired INHIBITION)
    ev_base = TherapeuticDirectionEvidence(
        target_canonical_id="SLC12A1",
        disease_canonical_id="Edema",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:ref:gwas1",
        underlying_reference="gwas1",
    )

    # 1. Actual: Drug INHIBITION on desired INHIBITION -> SUPPORTS
    res_actual = engine.align_target("SLC12A1", TherapeuticAction.INHIBITION, [ev_base])
    print(f"1. Actual:         Drug INHIBITION on desired INHIBITION -> Alignment: {res_actual.alignment.value} (Expected: SUPPORTS)")

    # 2. Counterfactual: Drug ACTIVATION on desired INHIBITION -> OPPOSES
    res_flipped = engine.align_target("SLC12A1", TherapeuticAction.ACTIVATION, [ev_base])
    print(f"2. Counterfactual: Drug ACTIVATION on desired INHIBITION -> Alignment: {res_flipped.alignment.value} (Expected: OPPOSES)")

    # 3. Drug UNKNOWN on desired INHIBITION -> INSUFFICIENT
    res_unknown_drug = engine.align_target("SLC12A1", TherapeuticAction.UNKNOWN, [ev_base])
    print(f"3. Drug UNKNOWN:   Drug UNKNOWN    on desired INHIBITION -> Alignment: {res_unknown_drug.alignment.value} (Expected: INSUFFICIENT)")

    # 4. Disease direction flipped: LoF + risk (desired ACTIVATION)
    ev_flipped_disease = TherapeuticDirectionEvidence(
        target_canonical_id="SLC12A1",
        disease_canonical_id="Edema",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="risk",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:ref:gwas2",
        underlying_reference="gwas2",
    )
    res_flipped_dis = engine.align_target("SLC12A1", TherapeuticAction.INHIBITION, [ev_flipped_disease])
    print(f"4. Disease Flipped: Drug INHIBITION on desired ACTIVATION -> Alignment: {res_flipped_dis.alignment.value} (Expected: OPPOSES)")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART C: CONFLICT RESOLUTION DIAGNOSTIC TESTS
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART C: CONFLICT RESOLUTION DIAGNOSTIC TESTS")
    print("=" * 80)

    # 1. Equal Tier Conflict: 1 Direct INHIBITION group vs 1 Direct ACTIVATION group
    ev_inh = TherapeuticDirectionEvidence(
        target_canonical_id="CONF_TGT",
        disease_canonical_id="DIS1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect", # desired INHIBITION
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:111",
        underlying_reference="pmid:111",
    )
    ev_act = TherapeuticDirectionEvidence(
        target_canonical_id="CONF_TGT",
        disease_canonical_id="DIS1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="risk", # desired ACTIVATION
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:222",
        underlying_reference="pmid:222",
    )

    res_conf_equal = engine.align_target("CONF_TGT", TherapeuticAction.INHIBITION, [ev_inh, ev_act])
    print(f"1. Equal Tier (1 vs 1): Alignment = {res_conf_equal.alignment.value}, Supporting = {len(res_conf_equal.supporting_groups)}, Opposing = {len(res_conf_equal.opposing_groups)}")
    print(f"   Explanation: {res_conf_equal.explanation}")

    # 2. Unequal Row Count but Equal Independent Groups: 50 rows in Group 1 vs 1 row in Group 2
    ev_inh_50 = [
        TherapeuticDirectionEvidence(
            target_canonical_id="CONF_TGT",
            disease_canonical_id="DIS1",
            source="OpenTargets",
            target_direction="LoF",
            trait_direction="protect",
            evidence_family=EvidenceFamily.CLINICAL_TRIAL,
            independence_group="CLINICAL_TRIAL:pmid:111", # same group
            underlying_reference="pmid:111",
        )
        for _ in range(50)
    ]
    res_conf_unequal_rows = engine.align_target("CONF_TGT", TherapeuticAction.INHIBITION, ev_inh_50 + [ev_act])
    print(f"2. Unequal Rows (50 rows in Group A vs 1 row in Group B): Alignment = {res_conf_unequal_rows.alignment.value}, Supporting = {len(res_conf_unequal_rows.supporting_groups)}, Opposing = {len(res_conf_unequal_rows.opposing_groups)}")
    print(f"   Explanation: {res_conf_unequal_rows.explanation}")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART D: INDEPENDENCE & DEDUPLICATION COLLISION TESTS
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART D: INDEPENDENCE & DEDUPLICATION COLLISION TESTS")
    print("=" * 80)

    # 1. Multi-source sharing PMID 12345678
    ev_ot_p = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="DIS1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:12345678",
        underlying_reference="pmid:12345678",
    )
    ev_datts_p = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="DIS1",
        source="DATTs",
        required_action="INHIBITION",
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:12345678",
        underlying_reference="pmid:12345678",
    )
    ev_lit_p = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="DIS1",
        source="Literature",
        target_direction="INHIBITED",
        trait_direction="IMPROVED",
        evidence_family=EvidenceFamily.CLINICAL_TRIAL,
        independence_group="CLINICAL_TRIAL:pmid:12345678",
        underlying_reference="pmid:12345678",
    )

    g_shared = group_evidence_by_independence([ev_ot_p, ev_datts_p, ev_lit_p])
    print(f"1. Same PMID across 3 databases (OpenTargets, DATTs, Literature):")
    print(f"   Input Records: 3 -> Output Independent Groups: {len(g_shared)} (Sources Merged: {g_shared[0].sources})")

    # 2. Unlinked / Missing Citations
    ev_unlinked1 = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="DIS1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:opentargets:unlinked",
    )
    ev_unlinked2 = TherapeuticDirectionEvidence(
        target_canonical_id="TGT1",
        disease_canonical_id="DIS1",
        source="OpenTargets",
        target_direction="LoF",
        trait_direction="protect",
        evidence_family=EvidenceFamily.GENETIC,
        independence_group="GENETIC:opentargets:unlinked",
    )
    g_unlinked = group_evidence_by_independence([ev_unlinked1, ev_unlinked2])
    print(f"2. Unlinked records with no PMID:")
    print(f"   Input Records: 2 -> Output Groups: {len(g_unlinked)} (Group ID: {g_unlinked[0].group_id})")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART E: UNKNOWN & STRUCTURAL LEAKAGE TESTS
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART E: UNKNOWN & STRUCTURAL LEAKAGE TESTS")
    print("=" * 80)

    # 1. Reactome CATALYST
    cat_pol = reactome_role_to_polarity("CATALYST")
    print(f"1. Reactome CATALYST polarity: {cat_pol.value} (Expected: UNKNOWN)")

    # 2. DATTs TARGETING
    des_tgt = derive_desired_target_action(required_action="TARGETING")
    res_tgt = compare_drug_action_to_target_direction(TherapeuticAction.INHIBITION, des_tgt)
    print(f"2. DATTs TARGETING desired action: {des_tgt.value} -> Alignment: {res_tgt.value} (Expected: INSUFFICIENT)")

    # 3. ChEMBL MODULATOR
    chembl_mod = normalize_drug_action("MODULATOR")
    res_mod = compare_drug_action_to_target_direction(chembl_mod, TherapeuticAction.INHIBITION)
    print(f"3. ChEMBL MODULATOR drug action: {chembl_mod.value} -> Alignment: {res_mod.value} (Expected: INSUFFICIENT)")

    # ─────────────────────────────────────────────────────────────────────────────
    # PART F: CONFIDENCE FORMULA BOUNDARY ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART F: CONFIDENCE FORMULA BOUNDARY ANALYSIS")
    print("=" * 80)

    scenarios = [
        ("5 supporting, 0 opposing", 5, 0),
        ("1 supporting, 0 opposing", 1, 0),
        ("50 supporting, 0 opposing", 50, 0),
        ("5 supporting, 5 opposing", 5, 5),
        ("0 supporting, 0 opposing", 0, 0),
    ]

    for name, s, o in scenarios:
        tot = s + o
        c = round(s / tot, 2) if tot > 0 else 0.0
        print(f"Scenario '{name}': Total Directional = {tot} -> Computed Confidence = {c}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC SCRIPT COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_scientific_audit())
