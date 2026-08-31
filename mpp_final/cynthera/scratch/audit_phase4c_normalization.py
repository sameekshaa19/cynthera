"""Phase 4C Evidence Normalization Audit Script — Pre-4D Readiness Check.

Audits the 5 canonical cases across all Phase 4C evidence streams, calculating:
- Raw evidence inventory (by source, target, disease, type)
- Target-disease relevance classification
- Canonical entity resolution and gating status
- Duplicate claim detection and unique claims
- Underlying reference deduplication (PMID, PMCID, DOI, NCT, study ID)
- Independence grouping & collinearity identification
- Directional semantics verification (ensuring no lossy conversions)
- Primary vs Secondary target distribution
- Complete Evidence Collapse / Reduction waterfall
- All 14 Pre-4D Metrics
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticDirectionEvidence,
)
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reasoning.directional.canonical_entity_gate import is_canonically_grounded
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder

TEST_CASES = [
    ("Furosemide", "Edema", "SLC12A1"),
    ("Propranolol", "Infantile Hemangioma", "ADRB1"),
    ("Dapagliflozin", "Heart Failure", "SLC5A2"),
    ("Thalidomide", "Multiple Myeloma", "CRBN"),
    ("Aspirin", "Colorectal Cancer", "PTGS2"),
]

# Canonical disease keywords for relevance checks
CASE_DISEASE_KEYWORDS = {
    "Edema": ["edema", "edematous", "fluid overload", "hypertension", "heart failure"],
    "Infantile Hemangioma": ["hemangioma", "infantile hemangioma", "vascular", "angioma"],
    "Heart Failure": ["heart failure", "cardiac failure", "chf", "hfref", "hfpef", "cardiomyopathy"],
    "Multiple Myeloma": ["multiple myeloma", "myeloma", "plasma cell", "kappalambda"],
    "Colorectal Cancer": ["colorectal", "colon cancer", "rectal cancer", "colorectal neoplasms", "adenoma"],
}

def extract_primary_ref(ref_str: str | None) -> str | None:
    if not ref_str:
        return None
    s = str(ref_str).strip().lower()
    pmid_m = re.search(r"pubmed/(\d+)|pmid:?\s*(\d+)", s)
    if pmid_m:
        return f"PMID:{pmid_m.group(1) or pmid_m.group(2)}"
    doi_m = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", s)
    if doi_m:
        return f"DOI:{doi_m.group(0)}"
    nct_m = re.search(r"nct\d{8}", s)
    if nct_m:
        return f"NCT:{nct_m.group(0).upper()}"
    return f"REF:{s[:40]}"

async def audit_case(drug_name: str, disease_name: str, expected_primary_target: str):
    orch = MasterOrchestrator()
    hyp, pkg, res = await orch.evaluate(drug_name, disease_name, policy=RetrievalPolicy.STANDARD, bypass_cache=False)

    # Build resolver from EvidenceGraphBuilder
    resolver = BiologicalIdentifierResolver()
    try:
        _, resolver = EvidenceGraphBuilder().build(pkg)
    except Exception:
        pass

    # Map UniProt -> Protein Object
    protein_map = {p.uniprot_accession.upper(): p for p in pkg.proteins if p.uniprot_accession}
    
    # 1. Inventory
    raw_chembl = len(pkg.targets)
    raw_ot_doe = len(pkg.opentargets_doe_evidence)
    raw_datts = len(pkg.datts_evidence)
    raw_dm = len([dm for dm in pkg.drugmechdb_evidence if dm.is_curated_path_available])
    raw_lit = len([ev for ev in pkg.evidence_records if ev.evidence_type.value in ("IN_VITRO", "CLINICAL", "LITERATURE", "REVIEW")])
    total_raw = len(pkg.therapeutic_direction_evidence)

    # Target classifications
    primary_sym = expected_primary_target.upper()
    target_counts = defaultdict(lambda: {"raw": 0, "relevant": 0, "canonical": 0, "unique_claims": set(), "unique_refs": set(), "indep_groups": set()})

    # Detailed audit collections
    relevant_records = []
    canonical_usable_records = []
    unique_claim_keys = set()
    unique_refs = set()
    independence_groups = set()
    pot_independent_groups = set()
    non_independent_groups = set()
    unknown_independence_groups = set()

    collinear_pairs = []
    ref_to_sources = defaultdict(set)
    ref_to_families = defaultdict(set)

    # Audit every normalized TherapeuticDirectionEvidence record
    for rec in pkg.therapeutic_direction_evidence:
        t_id = rec.target_canonical_id.upper()
        d_id = rec.disease_canonical_id.lower()
        src = rec.source

        # 2. Relevance Check
        # Check if target is in retrieved targets/proteins and disease matches
        is_primary = (t_id == primary_sym)
        keywords = CASE_DISEASE_KEYWORDS.get(disease_name, [disease_name.lower()])
        disease_relevant = any(kw in d_id or kw in disease_name.lower() for kw in keywords)

        # ChEMBL records are drug-target biochemical assays (target-specific, drug-specific)
        if src == "ChEMBL":
            rel_status = "RELEVANT"
        elif src == "OpenTargets":
            # OpenTargets DoE is already fetched against the disease MONDO/EFO
            rel_status = "RELEVANT" if disease_relevant else "DISEASE_ONLY"
        elif src == "DATTs":
            rel_status = "RELEVANT" if disease_relevant else "WRONG_DISEASE"
        elif src == "DrugMechDB":
            rel_status = "RELEVANT" if disease_relevant else "AMBIGUOUS"
        elif src == "Literature":
            rel_status = "RELEVANT" if disease_relevant else "AMBIGUOUS"
        else:
            rel_status = "RELEVANT"

        if not is_primary:
            tgt_category = "SECONDARY_TARGET"
        else:
            tgt_category = "PRIMARY_TARGET"

        target_counts[t_id]["raw"] += 1
        if rel_status == "RELEVANT":
            target_counts[t_id]["relevant"] += 1
            relevant_records.append(rec)

        # 3. Canonical Gating Check
        is_canonical = is_canonically_grounded(t_id, resolver) or (t_id in protein_map or any(p.gene_symbol == t_id for p in pkg.proteins))
        map_status = "EXACT" if is_canonical else rec.mapping_status

        if rel_status == "RELEVANT" and map_status in ("EXACT", "RESOLVED"):
            canonical_usable_records.append(rec)
            target_counts[t_id]["canonical"] += 1

            # 4. Canonical Claim Key for Deduplication
            # Key = (Target, Disease, DirectionOnTarget, DirectionOnTrait/RequiredAction, EvidenceFamily)
            claim_key = (
                t_id,
                disease_name.upper(),
                str(rec.target_direction),
                str(rec.trait_direction or rec.required_action),
                rec.evidence_family.value,
            )
            unique_claim_keys.add(claim_key)
            target_counts[t_id]["unique_claims"].add(claim_key)

            # 5. Underlying Reference Tracking
            raw_ref = rec.underlying_reference
            p_ref = extract_primary_ref(raw_ref)
            if p_ref:
                unique_refs.add(p_ref)
                ref_to_sources[p_ref].add(src)
                ref_to_families[p_ref].add(rec.evidence_family.value)
                target_counts[t_id]["unique_refs"].add(p_ref)

            # 6. Independence Grouping
            ind_grp = rec.independence_group
            if ind_grp:
                independence_groups.add(ind_grp)
                target_counts[t_id]["indep_groups"].add(ind_grp)

                # Classify Independence
                if "unlinked" in ind_grp:
                    unknown_independence_groups.add(ind_grp)
                else:
                    pot_independent_groups.add(ind_grp)

    # Detect Collinearity across sources
    for ref, sources in ref_to_sources.items():
        if len(sources) > 1:
            collinear_pairs.append({
                "reference": ref,
                "sources": list(sources),
                "families": list(ref_to_families[ref]),
            })

    # Source breakdown counts
    source_breakdown = {
        "ChEMBL": {"raw": raw_chembl, "usable": sum(1 for r in canonical_usable_records if r.source == "ChEMBL"), "excluded": raw_chembl - sum(1 for r in canonical_usable_records if r.source == "ChEMBL")},
        "OT_DoE": {"raw": raw_ot_doe, "usable": sum(1 for r in canonical_usable_records if r.source == "OpenTargets"), "excluded": raw_ot_doe - sum(1 for r in canonical_usable_records if r.source == "OpenTargets")},
        "DATTs": {"raw": raw_datts, "usable": sum(1 for r in canonical_usable_records if r.source == "DATTs"), "excluded": raw_datts - sum(1 for r in canonical_usable_records if r.source == "DATTs")},
        "Literature": {"raw": raw_lit, "usable": sum(1 for r in canonical_usable_records if r.source == "Literature"), "excluded": raw_lit - sum(1 for r in canonical_usable_records if r.source == "Literature")},
        "DrugMechDB": {"raw": raw_dm, "usable": sum(1 for r in canonical_usable_records if r.source == "DrugMechDB"), "excluded": raw_dm - sum(1 for r in canonical_usable_records if r.source == "DrugMechDB")},
    }

    # DrugMechDB validation status
    dm_avail = [dm for dm in pkg.drugmechdb_evidence if dm.is_curated_path_available]
    if dm_avail:
        dm_status = "VALIDATED"
    elif any(pkg.drugmechdb_evidence):
        dm_status = "MISSING"
    else:
        dm_status = "UNRESOLVED"

    # Semantics Check: verify LoF is not changed to INHIBITION
    ot_records_raw = [r for r in pkg.opentargets_doe_evidence if r.direction_on_target]
    ot_lof_count = sum(1 for r in ot_records_raw if r.direction_on_target == "LoF")
    ot_protect_count = sum(1 for r in ot_records_raw if r.direction_on_trait == "protect")
    norm_ot_lof = sum(1 for r in pkg.therapeutic_direction_evidence if r.source == "OpenTargets" and r.target_direction == "LoF")
    norm_ot_protect = sum(1 for r in pkg.therapeutic_direction_evidence if r.source == "OpenTargets" and r.trait_direction == "protect")
    semantics_preserved = (ot_lof_count == norm_ot_lof and ot_protect_count == norm_ot_protect)

    result_data = {
        "case": f"{drug_name} -> {disease_name}",
        "drug": drug_name,
        "disease": disease_name,
        "primary_target": primary_sym,
        "total_raw": total_raw,
        "relevant_count": len(relevant_records),
        "canonical_usable_count": len(canonical_usable_records),
        "duplicate_count": len(canonical_usable_records) - len(unique_claim_keys),
        "unique_claims_count": len(unique_claim_keys),
        "unique_refs_count": len(unique_refs),
        "independence_groups_count": len(independence_groups),
        "pot_independent_groups_count": len(pot_independent_groups),
        "unknown_independence_count": len(unknown_independence_groups),
        "source_breakdown": source_breakdown,
        "target_distribution": {t: dict(v, unique_claims=len(v["unique_claims"]), unique_refs=len(v["unique_refs"]), indep_groups=len(v["indep_groups"])) for t, v in target_counts.items()},
        "collinear_pairs": collinear_pairs,
        "drugmechdb_status": dm_status,
        "semantics_preserved": semantics_preserved,
        "ot_lof_count": ot_lof_count,
        "norm_ot_lof": norm_ot_lof,
    }
    return result_data

async def main():
    print("RUNNING PROGRAMMATIC AUDIT ACROSS ALL 5 CASES...")
    all_results = []
    for drug, disease, primary_tgt in TEST_CASES:
        res = await audit_case(drug, disease, primary_tgt)
        all_results.append(res)

    with open("scratch/phase4c_normalization_audit_report.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print("\nAUDIT SUMMARY PER CASE:")
    for r in all_results:
        print(f"\n=======================================================")
        print(f"CASE: {r['case']} (Primary Target: {r['primary_target']})")
        print(f"  Raw Records:                 {r['total_raw']}")
        print(f"  Relevant Records:            {r['relevant_count']}")
        print(f"  Canonically Usable:          {r['canonical_usable_count']}")
        print(f"  Unique Claims:               {r['unique_claims_count']} (Duplicates: {r['duplicate_count']})")
        print(f"  Unique References:           {r['unique_refs_count']}")
        print(f"  Independence Groups:         {r['independence_groups_count']}")
        print(f"  Potentially Independent:     {r['pot_independent_groups_count']}")
        print(f"  Unknown Independence:        {r['unknown_independence_count']}")
        print(f"  DrugMechDB Status:           {r['drugmechdb_status']}")
        print(f"  Semantics Preserved (LoF):   {r['semantics_preserved']} ({r['norm_ot_lof']} LoF preserved)")
        print(f"  Source Breakdown:            {r['source_breakdown']}")
        print(f"  Target Breakdown:            {r['target_distribution']}")
        print(f"  Collinear Shared Refs:       {len(r['collinear_pairs'])}")

asyncio.run(main())
