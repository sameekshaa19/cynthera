"""Run Normalization and Matching Audit across the test cases.

Calculates:
1. Normalization audit metrics (total, gene symbols, uniprot, resolved, unresolved, rate)
2. Matching audit (raw matches, canonical matches, additional matches revealed)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.utils.api_keys import sanitize_api_key
from backend.engineering.identity.resolution_service import IdentifierResolutionService
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)
from backend.reasoning.normalization.normalization_audit import (
    build_package_normalization_audit,
    calculate_matching_audit,
)


CASES = [
    ("Sildenafil", "Pulmonary Arterial Hypertension"),
    ("Metformin", "Type 2 Diabetes"),
    ("Paracetamol", "Melanoma"),
]


async def main():
    clean_ncbi = sanitize_api_key(os.getenv("NCBI_API_KEY"))
    clean_disgenet = sanitize_api_key(os.getenv("DISGENET_API_KEY"))
    clean_s2 = sanitize_api_key(os.getenv("SEMANTIC_SCHOLAR_API_KEY"))

    resolver_service = IdentifierResolutionService(ncbi_api_key=clean_ncbi)
    retrieval = RetrievalPipeline(
        ncbi_api_key=clean_ncbi,
        disgenet_api_key=clean_disgenet,
        semantic_scholar_api_key=clean_s2,
        db_path="data/cynthera.db",
        bypass_raw_cache=True,
    )

    print("=" * 78)
    print("BIOLOGICAL IDENTIFIER NORMALIZATION & MATCHING AUDIT")
    print("=" * 78)

    aggregate_audit = {
        "total_identifiers": 0,
        "gene_symbols": 0,
        "uniprot_accessions": 0,
        "other_identifiers": 0,
        "resolved": 0,
        "unresolved": 0,
        "raw_matches": 0,
        "canonical_matches": 0,
        "new_matches_revealed": 0,
    }

    for drug_name, disease_name in CASES:
        print(f"\n--- Evaluation: {drug_name} -> {disease_name} ---")
        drug_ids, disease_ids = await asyncio.gather(
            resolver_service.resolve_drug(drug_name),
            resolver_service.resolve_disease(disease_name),
        )
        drug = Drug(name=drug_name, identifiers=drug_ids)
        disease = Disease(name=disease_name, identifiers=disease_ids)

        import uuid
        package = await retrieval.execute(drug, disease, uuid.uuid4())

        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
        )

        norm_audit = build_package_normalization_audit(package)
        match_audit = calculate_matching_audit(package, resolver)

        print(f"Total Identifiers Audited: {norm_audit.total_identifiers}")
        print(f"  • Gene Symbols         : {norm_audit.gene_symbols}")
        print(f"  • UniProt Accessions   : {norm_audit.uniprot_accessions}")
        print(f"  • Other                : {norm_audit.other_identifiers}")
        print(f"  • Resolved             : {norm_audit.resolved} ({norm_audit.resolution_rate * 100:.1f}%)")
        print(f"  • Unresolved           : {norm_audit.unresolved}")
        print(f"  • Canonical Entities   : {norm_audit.canonical_entities}")
        print(f"  • Duplicate Raw IDs    : {norm_audit.duplicate_raw_identifiers}")

        print("Matching Audit:")
        print(f"  • Raw Matches (Pathways <-> Disease Genes)       : {match_audit['raw_matches']}")
        print(f"  • Canonical Matches (Pathways <-> Disease Genes) : {match_audit['canonical_matches']}")
        print(f"  • Additional Matches Revealed                    : {match_audit['new_matches_revealed']}")

        aggregate_audit["total_identifiers"] += norm_audit.total_identifiers
        aggregate_audit["gene_symbols"] += norm_audit.gene_symbols
        aggregate_audit["uniprot_accessions"] += norm_audit.uniprot_accessions
        aggregate_audit["other_identifiers"] += norm_audit.other_identifiers
        aggregate_audit["resolved"] += norm_audit.resolved
        aggregate_audit["unresolved"] += norm_audit.unresolved
        aggregate_audit["raw_matches"] += match_audit["raw_matches"]
        aggregate_audit["canonical_matches"] += match_audit["canonical_matches"]
        aggregate_audit["new_matches_revealed"] += match_audit["new_matches_revealed"]

    print("\n" + "=" * 78)
    print("AGGREGATE NORMALIZATION & MATCHING SUMMARY")
    print("=" * 78)
    total = aggregate_audit["total_identifiers"]
    resolved = aggregate_audit["resolved"]
    rate = round(resolved / total * 100, 2) if total > 0 else 100.0
    print(f"Total Identifiers Audited : {total}")
    print(f"Gene Symbols              : {aggregate_audit['gene_symbols']}")
    print(f"UniProt Accessions        : {aggregate_audit['uniprot_accessions']}")
    print(f"Other                     : {aggregate_audit['other_identifiers']}")
    print(f"Resolved                  : {resolved}")
    print(f"Unresolved                : {aggregate_audit['unresolved']}")
    print(f"Resolution Rate           : {rate}%")
    print(f"Raw Matches               : {aggregate_audit['raw_matches']}")
    print(f"Canonical Matches         : {aggregate_audit['canonical_matches']}")
    print(f"Additional Matches        : {aggregate_audit['new_matches_revealed']}")


if __name__ == "__main__":
    asyncio.run(main())
