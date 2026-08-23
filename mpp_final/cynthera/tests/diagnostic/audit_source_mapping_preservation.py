"""
Dynamic Retrieval Integration Audit for Source Mapping Preservation.

Measures:
1. Open Targets association rows, symbols, UniProt accessions, paired rows, mappings preserved.
2. Reactome participants, UniProt accessions, gene symbols, paired mappings preserved.
3. RetrievalPackage total mappings, unique canonical symbols, unique UniProt accessions, paired mappings.
4. Resolver identifiers supplied, resolved, unresolved, resolution rate.
5. Before / After resolution rate comparison.
"""
from __future__ import annotations

import asyncio
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
from backend.core.utils.api_keys import sanitize_api_key
from backend.engineering.identity.resolution_service import IdentifierResolutionService
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)
from backend.reasoning.normalization.normalization_audit import (
    build_package_normalization_audit,
)


CASES = [
    ("Sildenafil", "Pulmonary Arterial Hypertension"),
    ("Metformin", "Type 2 Diabetes"),
    ("Paracetamol", "Melanoma"),
]


async def run_audit():
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

    agg = {
        "ot_rows": 0,
        "ot_symbol_rows": 0,
        "ot_uniprot_rows": 0,
        "ot_both_rows": 0,
        "ot_mappings": 0,
        "reactome_participants": 0,
        "reactome_uniprot": 0,
        "reactome_symbol": 0,
        "reactome_paired": 0,
        "pkg_mappings": 0,
        "unique_symbols": set(),
        "unique_uniprots": set(),
        "paired_mappings": 0,
        "supplied_ids": 0,
        "resolved_ids": 0,
        "unresolved_ids": 0,
    }

    print("============================================================")
    print("SOURCE MAPPING PRESERVATION AUDIT (LIVE RUN)")
    print("============================================================")

    for drug_name, disease_name in CASES:
        import uuid
        drug_ids, disease_ids = await asyncio.gather(
            resolver_service.resolve_drug(drug_name),
            resolver_service.resolve_disease(disease_name),
        )
        drug = Drug(name=drug_name, identifiers=drug_ids)
        disease = Disease(name=disease_name, identifiers=disease_ids)

        package = await retrieval.execute(drug, disease, uuid.uuid4())

        # Audit Open Targets mappings
        ot_mappings = [m for m in package.identifier_mappings if m.source == "OpenTargets"]
        ot_rows = len({m.original_identifiers for m in ot_mappings})
        ot_sym = sum(1 for m in ot_mappings if m.canonical_symbol)
        ot_uni = sum(1 for m in ot_mappings if m.uniprot_accession)
        ot_both = sum(1 for m in ot_mappings if m.canonical_symbol and m.uniprot_accession)

        agg["ot_rows"] += ot_rows
        agg["ot_symbol_rows"] += ot_sym
        agg["ot_uniprot_rows"] += ot_uni
        agg["ot_both_rows"] += ot_both
        agg["ot_mappings"] += len(ot_mappings)

        # Audit Reactome mappings
        reactome_mappings = [m for m in package.identifier_mappings if m.source == "Reactome"]
        r_uni = sum(1 for m in reactome_mappings if m.uniprot_accession)
        r_sym = sum(1 for m in reactome_mappings if m.canonical_symbol)
        r_paired = sum(1 for m in reactome_mappings if m.canonical_symbol and m.uniprot_accession)

        agg["reactome_participants"] += len(reactome_mappings)
        agg["reactome_uniprot"] += r_uni
        agg["reactome_symbol"] += r_sym
        agg["reactome_paired"] += r_paired

        # Audit Package Mappings
        for m in package.identifier_mappings:
            agg["pkg_mappings"] += 1
            if m.canonical_symbol:
                agg["unique_symbols"].add(m.canonical_symbol)
            if m.uniprot_accession:
                agg["unique_uniprots"].add(m.uniprot_accession)
            if m.canonical_symbol and m.uniprot_accession:
                agg["paired_mappings"] += 1

        # Audit Resolver Resolution
        audit = build_package_normalization_audit(package)
        agg["supplied_ids"] += audit.total_identifiers
        agg["resolved_ids"] += audit.resolved
        agg["unresolved_ids"] += audit.unresolved

        print(f"\n--- {drug_name} -> {disease_name} ---")
        print(f"  Open Targets mappings preserved: {len(ot_mappings)} (paired: {ot_both})")
        print(f"  Reactome mappings preserved    : {len(reactome_mappings)} (paired: {r_paired})")
        print(f"  Package total mappings         : {len(package.identifier_mappings)}")
        print(f"  Resolver resolution rate       : {audit.resolution_rate * 100:.1f}% ({audit.resolved}/{audit.total_identifiers})")

    print("\n============================================================")
    print("AGGREGATE AUDIT SUMMARY")
    print("============================================================")
    print(f"Open Targets:")
    print(f"    association rows: {agg['ot_rows']}")
    print(f"    rows with symbol: {agg['ot_symbol_rows']}")
    print(f"    rows with UniProt: {agg['ot_uniprot_rows']}")
    print(f"    rows containing BOTH: {agg['ot_both_rows']}")
    print(f"    mappings preserved: {agg['ot_mappings']}")

    print(f"\nReactome:")
    print(f"    participants: {agg['reactome_participants']}")
    print(f"    participants with UniProt: {agg['reactome_uniprot']}")
    print(f"    participants with gene symbol: {agg['reactome_symbol']}")
    print(f"    paired mappings preserved: {agg['reactome_paired']}")

    print(f"\nRetrievalPackage:")
    print(f"    total identifier mappings: {agg['pkg_mappings']}")
    print(f"    unique canonical symbols: {len(agg['unique_symbols'])}")
    print(f"    unique UniProt accessions: {len(agg['unique_uniprots'])}")
    print(f"    paired mappings: {agg['paired_mappings']}")

    rate = (agg['resolved_ids'] / agg['supplied_ids'] * 100) if agg['supplied_ids'] > 0 else 100.0
    print(f"\nResolver:")
    print(f"    identifiers supplied: {agg['supplied_ids']}")
    print(f"    resolved: {agg['resolved_ids']}")
    print(f"    unresolved: {agg['unresolved_ids']}")
    print(f"    resolution rate: {rate:.2f}%")


if __name__ == "__main__":
    asyncio.run(run_audit())
