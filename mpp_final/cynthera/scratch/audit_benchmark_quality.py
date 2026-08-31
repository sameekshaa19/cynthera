"""Phase 4E Benchmark Quality Audit Script.

Reports dataset composition, label provenance coverage, directional evidence
availability, and benchmark construction quality metrics.

Usage:
    python scratch/audit_benchmark_quality.py
"""
from __future__ import annotations
import sys
import os
import io

# Ensure UTF-8 output on Windows (cp1252 doesn't support box-drawing chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.evaluation.benchmark_dataset import (
    BENCHMARK_DATASET_V1,
    get_directionally_suitable_negatives,
    get_unsuitable_negatives,
    get_cases_by_split,
)
from backend.evaluation.benchmark_models import BenchmarkClass, BenchmarkSplit
from backend.evaluation.evaluation_config import EVALUATION_CONFIGS
from backend.evaluation.evidence_weights import WEIGHT_CONFIGS


def bar(label: str, value: str | int | float, width: int = 60) -> None:
    print(f"  {label:<45} {value}")


def section(title: str) -> None:
    print(f"\n{'═' * 65}")
    print(f"  {title}")
    print(f"{'═' * 65}")


def main() -> None:
    print("\n" + "═" * 65)
    print("  CYNTHERA — Phase 4E Benchmark Quality Audit")
    print("═" * 65)

    cases = BENCHMARK_DATASET_V1
    pos_cases = [c for c in cases if c.expected_class == BenchmarkClass.POSITIVE]
    neg_cases = [c for c in cases if c.expected_class == BenchmarkClass.NEGATIVE]
    unc_cases = [c for c in cases if c.expected_class == BenchmarkClass.UNCERTAIN]
    suitable_neg = get_directionally_suitable_negatives()
    unsuitable_neg = get_unsuitable_negatives()

    section("1. Dataset Composition")
    bar("Total benchmark cases", len(cases))
    bar("  POSITIVE cases (ground truth)", len(pos_cases))
    bar("  NEGATIVE cases (ground truth)", len(neg_cases))
    bar("    of which: suitable for directional eval", len(suitable_neg))
    bar("    of which: flagged UNSUITABLE (no pipeline signal)", len(unsuitable_neg))
    bar("  UNCERTAIN cases (ground truth)", len(unc_cases))

    section("2. Dataset Split Distribution")
    for split in BenchmarkSplit:
        split_cases = get_cases_by_split(split)
        bar(f"  {split.value} split", len(split_cases))

    section("3. Label Provenance Coverage")
    provenance_complete = [
        c for c in cases
        if c.label_source.strip() and c.label_reference.strip() and c.label_rationale.strip()
    ]
    bar("Cases with complete label provenance", f"{len(provenance_complete)}/{len(cases)}")

    missing_prov = [c for c in cases if not c.label_source.strip()]
    if missing_prov:
        print("\n  ⚠️  Cases missing label_source:")
        for c in missing_prov:
            print(f"      {c.case_id}: {c.drug} → {c.disease}")
    else:
        print("  ✓ All cases have label_source")

    section("4. Negative Case Quality")
    for c in neg_cases:
        flag = "⚠️  UNSUITABLE" if c.unsuitable_for_directional_negative else "✓ SUITABLE"
        print(f"  {flag}  {c.case_id}: {c.drug} → {c.disease}")
        if c.unsuitable_for_directional_negative:
            print(f"         Expected target: {c.expected_target}")
            print(f"         Reason: Directional annotations absent in pipeline data sources")

    section("5. Evaluation Configuration Registry")
    for cfg_name, cfg in EVALUATION_CONFIGS.items():
        flags = []
        if not cfg.use_open_targets:
            flags.append("NO_OT")
        if not cfg.use_datts:
            flags.append("NO_DATTS")
        if not cfg.use_drugmechdb:
            flags.append("NO_DRUGMECHDB")
        if not cfg.use_independence_grouping:
            flags.append("NO_INDEP")
        if cfg.use_evidence_weighting:
            flags.append(f"WEIGHTED[{cfg.weight_config_name}]")
        flag_str = ", ".join(flags) if flags else "FULL"
        bar(f"  {cfg_name}", flag_str)

    section("6. Evidence Weight Configurations")
    for wc_name, wc in WEIGHT_CONFIGS.items():
        print(f"  {wc_name}: direct={wc.direct}, curated={wc.curated}, inferred={wc.inferred}, "
              f"structural=0.0 (hardcoded), none=0.0 (hardcoded)")

    section("7. Benchmark Quality Flags")
    print("  Ablation correctness criterion:")
    print("    → Evidence component actually removed (evidence_representation_changed=YES)")
    print("    → Prediction change is an OBSERVATION, not a correctness requirement")
    print()
    print("  WeightConfig calibration status:")
    print("    → INITIAL HEURISTIC values — NOT empirically calibrated")
    print("    → Do NOT tune against TEST split cases")
    print()
    print("  Production alignment path:")
    print("    → align_target() / align_package() — equal-vote, UNCHANGED")
    print("    → weighted_align_target() is evaluation-only comparator")

    section("8. Benchmark Case Summary")
    print(f"  {'Case ID':<18} {'Drug':<18} {'Disease':<22} {'Expected':<10} {'Label Source'}")
    print(f"  {'-'*18} {'-'*18} {'-'*22} {'-'*10} {'-'*30}")
    for c in cases:
        flag = " ⚠️" if c.unsuitable_for_directional_negative else ""
        print(f"  {c.case_id:<18} {c.drug:<18} {c.disease:<22} {c.expected_class.value:<10}{flag} {c.label_source[:40]}")

    print()
    print("═" * 65)
    print("  Audit complete.")
    print("═" * 65)


if __name__ == "__main__":
    main()
