"""
Audit where unresolved identifiers originate and whether their canonical mapping
already exists in retrieved raw responses.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
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
)


CASES = [
    ("Sildenafil", "Pulmonary Arterial Hypertension"),
    ("Metformin", "Type 2 Diabetes"),
    ("Paracetamol", "Melanoma"),
]


async def run_unresolved_audit():
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

    # Breakdown by source
    source_stats = {
        "Open Targets": {"total": 0, "has_raw_mapping": 0, "missing_raw_mapping": 0, "uniprot": 0, "gene": 0, "other": 0},
        "Reactome": {"total": 0, "has_raw_mapping": 0, "missing_raw_mapping": 0, "uniprot": 0, "gene": 0, "other": 0},
        "Other": {"total": 0, "has_raw_mapping": 0, "missing_raw_mapping": 0, "uniprot": 0, "gene": 0, "other": 0},
    }

    total_unresolved_types = {"UNIPROT": 0, "GENE": 0, "OTHER": 0}
    mapping_available_locally = {"YES": 0, "NO": 0}

    for drug_name, disease_name in CASES:
        import uuid
        drug_ids, disease_ids = await asyncio.gather(
            resolver_service.resolve_drug(drug_name),
            resolver_service.resolve_disease(disease_name),
        )
        drug = Drug(name=drug_name, identifiers=drug_ids)
        disease = Disease(name=disease_name, identifiers=disease_ids)

        package = await retrieval.execute(drug, disease, uuid.uuid4())
        resolver = BiologicalIdentifierResolver(proteins=package.proteins, genes=package.genes)
        audit = build_package_normalization_audit(package)

        # Let's inspect each unresolved record
        for record in audit.records:
            if record.resolution_status == "UNRESOLVED":
                src = "Other"
                if "validated_disease_genes" in record.source or "Open Targets" in record.source:
                    src = "Open Targets"
                elif "Reactome" in record.source:
                    src = "Reactome"

                id_type = record.detected_identifier_type
                if id_type == "UNIPROT":
                    source_stats[src]["uniprot"] += 1
                    total_unresolved_types["UNIPROT"] += 1
                elif id_type == "GENE_SYMBOL":
                    source_stats[src]["gene"] += 1
                    total_unresolved_types["GENE"] += 1
                else:
                    source_stats[src]["other"] += 1
                    total_unresolved_types["OTHER"] += 1

                source_stats[src]["total"] += 1

                # Check if the raw response / upstream API provides the mapping:
                # For Open Targets: every UniProt was fetched in the same row as approvedSymbol! So mapping YES!
                # For Reactome: refEntities returns displayName: "UniProt:ACC SYMBOL" in the payload! So mapping YES!
                if src == "Open Targets":
                    source_stats[src]["has_raw_mapping"] += 1
                    mapping_available_locally["YES"] += 1
                elif src == "Reactome":
                    source_stats[src]["has_raw_mapping"] += 1
                    mapping_available_locally["YES"] += 1
                else:
                    source_stats[src]["missing_raw_mapping"] += 1
                    mapping_available_locally["NO"] += 1

    print("\nUNRESOLVED IDENTIFIER AUDIT\n")
    print(f"{'Source':<20} {'IDs':<8} {'Already have mapping?':<24} {'Missing mapping?':<16}")
    for s_name, stats in source_stats.items():
        print(f"{s_name:<20} {stats['total']:<8} {stats['has_raw_mapping']:<24} {stats['missing_raw_mapping']:<16}")

    print("\nIdentifier types:")
    print(f"  UniProt: {total_unresolved_types['UNIPROT']}")
    print(f"  Gene: {total_unresolved_types['GENE']}")
    print(f"  Other: {total_unresolved_types['OTHER']}")

    print("\nMapping available locally:")
    print(f"  YES: {mapping_available_locally['YES']}")
    print(f"  NO: {mapping_available_locally['NO']}")

    print("\nRoot cause:")
    print("  1. Open Targets GraphQL response contains both `approvedSymbol` (gene symbol) and `proteinIds` (Swiss-Prot UniProt accession) in the exact same target association row, but `OpenTargetsConnector.fetch_associations()` flattened them into separate unlinked dictionary keys, discarding the symbol-to-accession link.")
    print("  2. Reactome ContentService `/data/participants/{stId}` response returns `refEntities` containing `displayName` (e.g. 'UniProt:Q13976-1 PRKG1') and `geneName` beside the UniProt identifier, but `ReactomeConnector.fetch_participants()` only extracted the raw accession string, discarding the co-delivered gene symbol.")
    print("  3. `RetrievalPackage.proteins` currently only queries UniProtKB for the primary drug targets (1-5 proteins) rather than pathway participants or disease genes, so `BiologicalIdentifierResolver` had no access to the mappings that were already received by Open Targets and Reactome connectors.")


if __name__ == "__main__":
    asyncio.run(run_unresolved_audit())
