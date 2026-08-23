"""
Phase 1: RetrievalPackage Diagnostic Audit

Inspects the exact biological data boundary (RetrievalPackage) produced by
IdentifierResolutionService + RetrievalPipeline BEFORE any reasoning is performed.

Runs 3 diagnostic cases with bypass_cache=True:
1. Sildenafil -> Pulmonary Arterial Hypertension
2. Metformin -> Type 2 Diabetes
3. Paracetamol -> Melanoma
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, asdict
from typing import Any
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.utils.api_keys import sanitize_api_key
from backend.engineering.identity.resolution_service import IdentifierResolutionService
from backend.engineering.retrieval.pipeline import RetrievalPipeline

RESULTS_DIR = Path("tests/diagnostic/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

UNIPROT_REGEX = re.compile(
    r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}|[A-Z0-9]{6,10})(-[0-9]+)?$"
)
HGNC_SYMBOL_REGEX = re.compile(r"^[A-Z][A-Z0-9_-]{1,15}$")


@dataclass(frozen=True)
class AuditCase:
    id: str
    drug: str
    disease: str
    category: str
    rationale: str


AUDIT_CASES = [
    AuditCase(
        id="CASE_1",
        drug="Sildenafil",
        disease="Pulmonary Arterial Hypertension",
        category="STRONG_POSITIVE",
        rationale="Expected strong biological relationship (PDE5 / cGMP / vasodilation)",
    ),
    AuditCase(
        id="CASE_2",
        drug="Metformin",
        disease="Type 2 Diabetes",
        category="KNOWN_RELATIONSHIP_ZERO_PATHS",
        rationale="Known established relationship that currently gets 0 mechanistic paths",
    ),
    AuditCase(
        id="CASE_3",
        drug="Paracetamol",
        disease="Melanoma",
        category="NEGATIVE_CONTROL",
        rationale="Negative / control relationship without strong primary mechanistic link",
    ),
]


def classify_identifier(key: str) -> str:
    """Classify whether a key is UniProt accession, HGNC Gene Symbol, or Unknown."""
    k = key.strip()
    if UNIPROT_REGEX.match(k):
        # Additional heuristic: if it looks like a gene symbol e.g. "INS", distinguish
        # UniProt accessions usually have digits e.g. P01308, O76074, Q96SW2
        has_digit = any(c.isdigit() for c in k)
        if has_digit and len(k) >= 6:
            return "UNIPROT"
    if HGNC_SYMBOL_REGEX.match(k):
        return "GENE_SYMBOL"
    if UNIPROT_REGEX.match(k):
        return "UNIPROT"
    return "UNKNOWN"


def audit_package(case: AuditCase, package: RetrievalPackage) -> dict[str, Any]:
    """Perform exhaustive audit on RetrievalPackage without running reasoning."""
    protein_map = {p.uniprot_accession: p for p in package.proteins}
    target_uniprots = [t.protein_uniprot for t in package.targets]
    resolved_proteins = [u for u in target_uniprots if u in protein_map]

    # Target -> UniProt mapping details
    target_mapping_details = []
    for t in package.targets:
        is_mapped = t.protein_uniprot in protein_map
        prot = protein_map.get(t.protein_uniprot)
        status_icon = "[OK]" if is_mapped else "[MISSING]"
        target_mapping_details.append({
            "target_uniprot": t.protein_uniprot,
            "gene_symbol": prot.gene_symbol if prot else "N/A",
            "protein_name": prot.name if prot else "N/A",
            "mechanism": t.mechanism,
            "affinity_nm": t.affinity_nm,
            "affinity_type": t.affinity_type,
            "status": status_icon,
            "is_mapped": is_mapped,
        })

    # Proteins breakdown
    reviewed_count = sum(1 for p in package.proteins if p.is_reviewed)
    unreviewed_count = sum(1 for p in package.proteins if not p.is_reviewed)
    human_count = sum(1 for p in package.proteins if "homo sapiens" in (p.organism or "").lower())
    non_human_count = sum(1 for p in package.proteins if p.organism and "homo sapiens" not in p.organism.lower())
    unknown_organism_count = sum(1 for p in package.proteins if not p.organism)

    # Genes breakdown
    gene_symbols = [g.symbol for g in package.genes]
    protein_gene_symbols = [p.gene_symbol for p in package.proteins if p.gene_symbol]
    all_gene_symbols = sorted(list(set(gene_symbols + protein_gene_symbols)))

    # Pathways breakdown
    pathways_with_participants = [p for p in package.pathways if p.participant_uniprot_ids]
    pathways_empty = [p for p in package.pathways if not p.participant_uniprot_ids]
    pathway_participant_counts = {
        f"{p.reactome_id} ({p.name})": len(p.participant_uniprot_ids)
        for p in package.pathways[:20]  # top 20
    }

    # Disease Genes breakdown
    disease_gene_keys = list(package.validated_disease_genes.keys())
    key_classifications = {"GENE_SYMBOL": 0, "UNIPROT": 0, "UNKNOWN": 0}
    classified_keys = []
    for k in disease_gene_keys:
        cls = classify_identifier(k)
        key_classifications[cls] = key_classifications.get(cls, 0) + 1
        classified_keys.append({"key": k, "type": cls, "score": package.validated_disease_genes[k]})

    scores = list(package.validated_disease_genes.values())
    score_min = min(scores) if scores else None
    score_max = max(scores) if scores else None
    score_mean = (sum(scores) / len(scores)) if scores else None

    # Evidence breakdown
    evidence_by_type: dict[str, int] = {}
    evidence_by_source: dict[str, int] = {}
    for ev in package.evidence_records:
        etype = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type)
        evidence_by_type[etype] = evidence_by_type.get(etype, 0) + 1
        src = "unknown"
        if ev.provenance:
            src = (getattr(ev.provenance, "source_name", None) or getattr(ev.provenance, "source", "UNKNOWN")).lower()
        evidence_by_source[src] = evidence_by_source.get(src, 0) + 1

    # Integrity Checks
    targets_without_proteins = [t.protein_uniprot for t in package.targets if t.protein_uniprot not in protein_map]
    target_uniprot_set = set(target_uniprots)
    proteins_without_targets = [p.uniprot_accession for p in package.proteins if p.uniprot_accession not in target_uniprot_set]
    pathways_without_participants = [p.reactome_id for p in pathways_empty]

    # Suspicious partial retrieval check
    # Check if target count > len(proteins) or if targets > 5 but only 5 looked up
    suspicious_truncation = False
    truncation_notes = []
    if len(package.targets) > len(package.proteins):
        suspicious_truncation = True
        truncation_notes.append(
            f"Targets retrieved ({len(package.targets)}) > Proteins resolved ({len(package.proteins)}). Potential [:5] slice or unmapped accessions."
        )
    if key_classifications["UNIPROT"] > 0:
        truncation_notes.append(
            f"validated_disease_genes contains {key_classifications['UNIPROT']} UniProt accessions. Downstream symbol matching may fail."
        )

    # Determine overall audit status
    integrity_failures = []
    integrity_warnings = []

    if case.category == "STRONG_POSITIVE" and len(package.targets) == 0:
        integrity_failures.append("Zero targets retrieved for strong positive case")
    if case.category == "STRONG_POSITIVE" and len(package.pathways) == 0:
        integrity_failures.append("Zero pathways retrieved for strong positive case")
    if case.category == "KNOWN_RELATIONSHIP_ZERO_PATHS" and (len(package.targets) == 0 or len(package.pathways) == 0):
        integrity_failures.append(f"Zero targets ({len(package.targets)}) or pathways ({len(package.pathways)}) retrieved for known relationship")

    if targets_without_proteins:
        integrity_warnings.append(f"{len(targets_without_proteins)} targets lack resolved Protein entities: {targets_without_proteins}")
    if key_classifications["UNIPROT"] > 0:
        integrity_warnings.append(f"{key_classifications['UNIPROT']} UniProt keys in validated_disease_genes")
    if suspicious_truncation:
        integrity_warnings.extend(truncation_notes)

    final_status = "FAIL" if integrity_failures else ("WARNING" if integrity_warnings else "PASS")

    return {
        "case_id": case.id,
        "drug_input": case.drug,
        "disease_input": case.disease,
        "category": case.category,
        "rationale": case.rationale,
        "identity": {
            "drug_name": package.drug.name,
            "drug_chembl_id": package.drug.chembl_id,
            "disease_name": package.disease.name,
            "disease_mesh_id": package.disease.mesh_id,
            "disease_mondo_id": package.disease.mondo_id,
        },
        "targets": {
            "total_retrieved": len(package.targets),
            "proteins_resolved": len(resolved_proteins),
            "protein_resolution_rate_pct": round(len(resolved_proteins) / len(package.targets) * 100, 1) if package.targets else 0.0,
            "mapping_details": target_mapping_details,
        },
        "proteins": {
            "total": len(package.proteins),
            "reviewed": reviewed_count,
            "unreviewed": unreviewed_count,
            "human": human_count,
            "non_human": non_human_count,
            "unknown_organism": unknown_organism_count,
            "accessions": [p.uniprot_accession for p in package.proteins],
        },
        "genes": {
            "total": len(all_gene_symbols),
            "symbols": all_gene_symbols,
        },
        "pathways": {
            "total": len(package.pathways),
            "with_participants": len(pathways_with_participants),
            "empty_participants": len(pathways_empty),
            "sample_participant_counts": pathway_participant_counts,
        },
        "disease_genes": {
            "total": len(disease_gene_keys),
            "classification_counts": key_classifications,
            "score_distribution": {
                "min": round(score_min, 4) if score_min is not None else None,
                "max": round(score_max, 4) if score_max is not None else None,
                "mean": round(score_mean, 4) if score_mean is not None else None,
            },
            "sample_keys": classified_keys[:25],
        },
        "evidence": {
            "total": len(package.evidence_records),
            "literature_with_abstracts": len(package.literature_evidence),
            "by_type": evidence_by_type,
            "by_source": evidence_by_source,
        },
        "clinical_trials": {
            "total": len(package.clinical_trials),
            "retrieval_status": package.clinical_trial_retrieval_status,
        },
        "sources": {
            "queried": package.sources_queried,
            "failed": package.sources_failed,
        },
        "integrity_checks": {
            "targets_without_proteins": targets_without_proteins,
            "proteins_without_targets": proteins_without_targets,
            "pathways_without_participants_count": len(pathways_without_participants),
            "uniprot_keys_in_disease_genes_count": key_classifications["UNIPROT"],
            "suspicious_partial_retrieval": suspicious_truncation,
            "notes": truncation_notes,
        },
        "final": {
            "retrieval_confidence": package.retrieval_confidence,
            "status": final_status,
            "integrity_failures": integrity_failures,
            "integrity_warnings": integrity_warnings,
        },
    }


def print_audit_report(report: dict[str, Any]) -> None:
    """Print beautifully structured terminal report."""
    ident = report["identity"]
    targets = report["targets"]
    prots = report["proteins"]
    genes = report["genes"]
    paths = report["pathways"]
    dgenes = report["disease_genes"]
    ev = report["evidence"]
    trials = report["clinical_trials"]
    sources = report["sources"]
    integrity = report["integrity_checks"]
    final = report["final"]

    print("\n" + "=" * 78)
    print(f"RETRIEVAL PACKAGE AUDIT: {report['case_id']} | {report['drug_input']} -> {report['disease_input']}")
    print(f"Category : {report['category']} ({report['rationale']})")
    print("=" * 78)

    print("\n1. IDENTITY")
    print(f"  Drug    : {ident['drug_name']} (ChEMBL ID: {ident['drug_chembl_id'] or 'None'})")
    print(f"  Disease : {ident['disease_name']} (MeSH ID: {ident['disease_mesh_id'] or 'None'}, MONDO ID: {ident['disease_mondo_id'] or 'None'})")

    print("\n2. TARGETS")
    print(f"  Retrieved               : {targets['total_retrieved']}")
    print(f"  Proteins Resolved       : {targets['proteins_resolved']}")
    print(f"  Protein Resolution Rate : {targets['protein_resolution_rate_pct']}%")
    print("  Targets mapping list:")
    for m in targets["mapping_details"]:
        print(f"    {m['status']:9} {m['target_uniprot']:10} | {m['gene_symbol']:8} | {m['mechanism']:14} | {m['affinity_nm']} nM ({m['affinity_type']}) | {m['protein_name']}")

    print("\n3. PROTEINS")
    print(f"  Total                   : {prots['total']}")
    print(f"  Reviewed (Swiss-Prot)   : {prots['reviewed']}")
    print(f"  Unreviewed (TrEMBL)     : {prots['unreviewed']}")
    print(f"  Human (Homo sapiens)    : {prots['human']}")
    print(f"  Non-Human               : {prots['non_human']}")
    print(f"  Unknown Organism        : {prots['unknown_organism']}")
    print(f"  Accessions              : {', '.join(prots['accessions'])}")

    print("\n4. GENES")
    print(f"  Total Symbols           : {genes['total']}")
    print(f"  Symbols List            : {', '.join(genes['symbols']) if genes['symbols'] else 'None'}")

    print("\n5. PATHWAYS")
    print(f"  Total Pathways          : {paths['total']}")
    print(f"  With Participants       : {paths['with_participants']}")
    print(f"  Empty Participant Lists : {paths['empty_participants']}")
    if paths["sample_participant_counts"]:
        print("  Sample Participant Counts:")
        for pname, count in list(paths["sample_participant_counts"].items())[:8]:
            print(f"    • {pname} -> {count} participant(s)")

    print("\n6. DISEASE GENES (validated_disease_genes)")
    print(f"  Total Entries           : {dgenes['total']}")
    print(f"  Gene Symbols Count      : {dgenes['classification_counts']['GENE_SYMBOL']}")
    print(f"  UniProt Accessions Count: {dgenes['classification_counts']['UNIPROT']}")
    print(f"  Unknown Format Count    : {dgenes['classification_counts']['UNKNOWN']}")
    print(f"  Score Distribution      : min={dgenes['score_distribution']['min']}, max={dgenes['score_distribution']['max']}, mean={dgenes['score_distribution']['mean']}")
    if dgenes["sample_keys"]:
        print("  Sample Key Classifications (first 10):")
        for k in dgenes["sample_keys"][:10]:
            print(f"    • {k['key']:12} -> {k['type']:12} (score: {k['score']:.4f})")

    print("\n7. EVIDENCE")
    print(f"  Total Evidence Records  : {ev['total']}")
    print(f"  Abstracts for Claim Ext : {ev['literature_with_abstracts']}")
    print("  By Type:")
    for etype, count in ev["by_type"].items():
        print(f"    • {etype:20}: {count}")
    print("  By Source:")
    for src, count in ev["by_source"].items():
        print(f"    • {src:20}: {count}")

    print("\n8. CLINICAL TRIALS")
    print(f"  Total Trials            : {trials['total']}")
    print(f"  Retrieval Status        : {trials['retrieval_status']}")

    print("\n9. SOURCES ACCESSED")
    print(f"  Queried                 : {', '.join(sources['queried']) if sources['queried'] else 'None'}")
    print(f"  Failed                  : {', '.join(sources['failed']) if sources['failed'] else 'None'}")

    print("\n10. INTEGRITY CHECKS")
    print(f"  Targets Without Proteins: {len(integrity['targets_without_proteins'])} ({integrity['targets_without_proteins']})")
    print(f"  Proteins Without Targets: {len(integrity['proteins_without_targets'])} ({integrity['proteins_without_targets']})")
    print(f"  Pathways Without Partic : {integrity['pathways_without_participants_count']}")
    print(f"  UniProt Disease Genes   : {integrity['uniprot_keys_in_disease_genes_count']}")
    print(f"  Suspicious Truncation   : {integrity['suspicious_partial_retrieval']}")
    for note in integrity["notes"]:
        print(f"    ⚠ NOTE: {note}")

    print("\nFINAL STATUS")
    print(f"  Retrieval Confidence   : {final['retrieval_confidence']}")
    print(f"  Audit Result           : [{final['status']}]")
    if final["integrity_failures"]:
        for fail in final["integrity_failures"]:
            print(f"    ✗ FAIL: {fail}")
    if final["integrity_warnings"]:
        for warn in final["integrity_warnings"]:
            print(f"    ⚠ WARN: {warn}")


async def run_audit():
    print("=" * 78)
    print("CYNTHERA PHASE 1: RETRIEVAL PACKAGE DIAGNOSTIC AUDIT")
    print("Bypassing all caches (forcing fresh live API retrieval)...")
    print("Reasoning Orchestrator is STOPPED — inspecting only RetrievalPackage boundary.")
    print("=" * 78)

    clean_ncbi = sanitize_api_key(os.getenv("NCBI_API_KEY"))
    clean_disgenet = sanitize_api_key(os.getenv("DISGENET_API_KEY"))
    clean_s2 = sanitize_api_key(os.getenv("SEMANTIC_SCHOLAR_API_KEY"))

    resolver = IdentifierResolutionService(ncbi_api_key=clean_ncbi)
    retrieval = RetrievalPipeline(
        ncbi_api_key=clean_ncbi,
        disgenet_api_key=clean_disgenet,
        semantic_scholar_api_key=clean_s2,
        db_path="data/cynthera.db",
        bypass_raw_cache=True,
    )

    all_reports: list[dict[str, Any]] = []

    for case in AUDIT_CASES:
        trace_id = uuid.uuid4()
        hypothesis_id = uuid.uuid4()

        print(f"\n[Retrieval] Querying APIs for {case.drug} -> {case.disease}...")
        try:
            drug_ids, disease_ids = await asyncio.gather(
                resolver.resolve_drug(case.drug, trace_id),
                resolver.resolve_disease(case.disease, trace_id),
            )
            drug = Drug(name=case.drug, identifiers=drug_ids)
            disease = Disease(name=case.disease, identifiers=disease_ids)

            package = await retrieval.execute(drug, disease, hypothesis_id)

            report = audit_package(case, package)
            all_reports.append(report)
            print_audit_report(report)

            # Save individual case package json
            case_path = RESULTS_DIR / f"audit_{case.id}_{case.drug}_{case.disease}.json".replace(" ", "_")
            case_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")

        except Exception as exc:
            print(f"ERROR auditing {case.drug} -> {case.disease}: {repr(exc)}")
            import traceback
            traceback.print_exc()
            all_reports.append({
                "case_id": case.id,
                "drug_input": case.drug,
                "disease_input": case.disease,
                "status": "ERROR",
                "error": repr(exc),
            })

    # Save summary report
    summary_path = RESULTS_DIR / "phase1_retrieval_package_audit.json"
    summary_path.write_text(json.dumps(all_reports, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 78)
    print("PHASE 1 AUDIT COMPLETE")
    print(f"Full JSON report saved to: {summary_path}")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(run_audit())
