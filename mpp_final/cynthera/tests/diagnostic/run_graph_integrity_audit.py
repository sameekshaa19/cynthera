"""
Multi-case runner for Graph Integrity Audit.

Executes live, uncached retrieval across representative drug-disease cases, runs
GraphIntegrityAuditor, formats the Markdown output reports, and produces summary metrics.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
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
from backend.reasoning.mechanistic.graph_integrity_audit import GraphIntegrityAuditor


CASES = [
    ("Sildenafil", "Pulmonary Arterial Hypertension"),
    ("Metformin", "Type 2 Diabetes"),
    ("Propranolol", "Infantile Hemangioma"),
    ("Dapagliflozin", "Heart Failure"),
    ("Thalidomide", "Multiple Myeloma"),
]


async def run():
    clean_ncbi = sanitize_api_key(os.getenv("NCBI_API_KEY"))
    clean_disgenet = sanitize_api_key(os.getenv("DISGENET_API_KEY"))
    clean_s2 = sanitize_api_key(os.getenv("SEMANTIC_SCHOLAR_API_KEY"))

    resolver_service = IdentifierResolutionService(ncbi_api_key=clean_ncbi)
    retrieval_pipeline = RetrievalPipeline(
        ncbi_api_key=clean_ncbi,
        disgenet_api_key=clean_disgenet,
        semantic_scholar_api_key=clean_s2,
        db_path="data/cynthera.db",
        bypass_raw_cache=True,
    )

    auditor = GraphIntegrityAuditor()
    reports = []

    for drug_name, disease_name in CASES:
        print(f"\n>>> Running Graph Integrity Audit for {drug_name} -> {disease_name}...")
        drug_ids, disease_ids = await asyncio.gather(
            resolver_service.resolve_drug(drug_name),
            resolver_service.resolve_disease(disease_name),
        )
        drug = Drug(name=drug_name, identifiers=drug_ids)
        disease = Disease(name=disease_name, identifiers=disease_ids)

        package = await retrieval_pipeline.execute(drug, disease, uuid.uuid4())
        report = auditor.audit(package)
        reports.append(report)

        formatted = auditor.format_markdown(report)
        print("\n" + formatted)

    # Save summary report
    out_dir = _PROJECT_ROOT / "tests" / "diagnostic" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "graph_integrity_audit_summary.md", "w", encoding="utf-8") as f:
        for r in reports:
            f.write(auditor.format_markdown(r) + "\n\n")


if __name__ == "__main__":
    asyncio.run(run())
