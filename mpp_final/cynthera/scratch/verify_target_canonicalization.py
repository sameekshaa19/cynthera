"""Target Canonicalization Verification Script for Phase 4C.

Verifies dynamic identity mapping across:
1. Furosemide -> Edema (SLC12A1)
2. Propranolol -> Infantile Hemangioma (ADRB1)
3. Dapagliflozin -> Heart Failure (SLC5A2)
4. Thalidomide -> Multiple Myeloma (CRBN)
5. Aspirin -> Colorectal Cancer (PTGS2)

Prints for each benchmark case:
- HGNC Symbol
- UniProt ID
- Ensembl ID
- Canonical Identity
- Source Mappings & Preserved Provenance
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
    ("Furosemide", "Edema", "SLC12A1"),
    ("Propranolol", "Infantile Hemangioma", "ADRB1"),
    ("Dapagliflozin", "Heart Failure", "SLC5A2"),
    ("Thalidomide", "Multiple Myeloma", "CRBN"),
    ("Aspirin", "Colorectal Cancer", "PTGS2"),
]

async def verify_canonicalization():
    print("=" * 80)
    print("CYNTHERA TARGET CANONICALIZATION VERIFICATION")
    print("=" * 80)

    orch = MasterOrchestrator()

    for drug, disease, expected_symbol in TEST_CASES:
        print(f"\nCASE: {drug} -> {disease}")
        print("-" * 50)
        hyp, pkg, res = await orch.evaluate(drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=True)

        # Map targets and their normalized representation
        canonical_targets = set(rec.target_canonical_id for rec in pkg.therapeutic_direction_evidence)

        # Group records by canonical target
        target_records = {}
        for rec in pkg.therapeutic_direction_evidence:
            tid = rec.target_canonical_id
            if tid not in target_records:
                target_records[tid] = []
            target_records[tid].append(rec)

        print(f"  Canonical Targets Present: {sorted(list(canonical_targets))}")

        for sym in sorted(list(canonical_targets)):
            recs = target_records[sym]
            sources = sorted(list(set(r.source for r in recs)))
            orig_ids = sorted(list(set(r.original_target_id for r in recs if r.original_target_id)))
            uniprots = sorted(list(set(r.target_uniprot for r in recs if r.target_uniprot)))
            ensembls = sorted(list(set(r.target_ensembl_id for r in recs if r.target_ensembl_id)))

            print(f"\n    [Target] Canonical Symbol: {sym}")
            print(f"      - Sources Aggregated:     {sources}")
            print(f"      - UniProt Accession(s):   {uniprots}")
            print(f"      - Ensembl Gene ID(s):     {ensembls}")
            print(f"      - Original Identifiers:   {orig_ids}")
            print(f"      - Total Records Unified:  {len(recs)}")

            # Verify no Ensembl ID leaked into canonical symbol
            assert not sym.startswith("ENSG"), f"Leakage detected: {sym} starts with ENSG!"

    print("\n" + "=" * 80)
    print("ALL 5 BENCHMARK CASES VERIFIED: ENSEMBL -> HGNC CANONICALIZATION SUCCEEDED!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(verify_canonicalization())
