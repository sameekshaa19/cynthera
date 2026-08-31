"""Live execution script for Phase 4E Benchmark and Ablation Study."""
from __future__ import annotations

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.evaluation.benchmark_runner import BenchmarkRunner
from backend.evaluation.benchmark_models import BenchmarkClass
from backend.reporting.evaluation_pdf_exporter import EvaluationPDFExporter


async def main():
    print("=" * 80)
    print("CYNTHERA PHASE 4E — LIVE BENCHMARK & ABLATION STUDY")
    print("=" * 80)

    runner = BenchmarkRunner()
    report = await runner.run_benchmark(bypass_cache=True, include_ablations=True)

    print("\n--- 1. Overall Performance Metrics ---")
    m = report.full_4d_metrics
    b = report.baseline_metrics
    print(f"Total Cases:     {m.total_cases} ({m.positive_cases}P / {m.negative_cases}N / {m.uncertain_cases}U)")
    print(f"Correct Preds:   {m.correct_predictions}/{m.total_cases}")
    acc_s = f"{m.accuracy:.1%}" if m.accuracy is not None else "N/A"
    b_acc_s = f"{b.accuracy:.1%}" if b.accuracy is not None else "N/A"
    print(f"Accuracy:        {acc_s} (Baseline: {b_acc_s})")
    prec_s = f"{m.precision:.1%}" if m.precision is not None else "N/A"
    b_prec_s = f"{b.precision:.1%}" if b.precision is not None else "N/A"
    print(f"Precision:       {prec_s} (Baseline: {b_prec_s})")
    rec_s = f"{m.recall:.1%}" if m.recall is not None else "N/A"
    b_rec_s = f"{b.recall:.1%}" if b.recall is not None else "N/A"
    print(f"Recall:          {rec_s} (Baseline: {b_rec_s})")
    spec_s = f"{m.specificity:.1%}" if m.specificity is not None else "N/A"
    b_spec_s = f"{b.specificity:.1%}" if b.specificity is not None else "N/A"
    print(f"Specificity:     {spec_s} (Baseline: {b_spec_s})")
    f1_s = f"{m.f1_score:.3f}" if m.f1_score is not None else "N/A"
    b_f1_s = f"{b.f1_score:.3f}" if b.f1_score is not None else "N/A"
    print(f"F1 Score:        {f1_s} (Baseline: {b_f1_s})")
    mcc_s = f"{m.mcc:.3f}" if m.mcc is not None else "N/A"
    b_mcc_s = f"{b.mcc:.3f}" if b.mcc is not None else "N/A"
    print(f"MCC:             {mcc_s} (Baseline: {b_mcc_s})")

    print("\n--- 2. 3x3 Confusion Matrix ---")
    cm = m.confusion_matrix
    print(f"Exp POSITIVE -> Pred: P={cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE)}, N={cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE)}, U={cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.UNCERTAIN)}")
    print(f"Exp NEGATIVE -> Pred: P={cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE)}, N={cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE)}, U={cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.UNCERTAIN)}")
    print(f"Exp UNCERTAIN -> Pred: P={cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.POSITIVE)}, N={cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.NEGATIVE)}, U={cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN)}")

    print("\n--- 3. Per-Case Results ---")
    for cr in report.case_results:
        is_pass = "PASS" if cr.is_correct else "FAIL"
        print(f"[{is_pass}] {cr.case.case_id}: {cr.case.drug} -> {cr.case.disease}")
        print(f"       Expected: {cr.case.expected_class.value} | Predicted: {cr.predicted_class.value} ({cr.predicted_alignment})")
        print(f"       Target: {cr.primary_target} | Concordance: {cr.directional_concordance:.2f} (Supp: {cr.supporting_group_count} / Opp: {cr.opposing_group_count})")
        print(f"       Explanation: {cr.explanation}")

    print("\n--- 4. Ablation Analysis ---")
    for ab in report.ablation_results:
        m_ab = ab.metrics
        acc_s = f"{m_ab.accuracy:.1%}" if m_ab.accuracy is not None else "N/A"
        prec_s = f"{m_ab.precision:.1%}" if m_ab.precision is not None else "N/A"
        rec_s = f"{m_ab.recall:.1%}" if m_ab.recall is not None else "N/A"
        f1_s = f"{m_ab.f1_score:.3f}" if m_ab.f1_score is not None else "N/A"
        print(f"{ab.config_name.value:25} | Acc: {acc_s:6} | Prec: {prec_s:6} | Rec: {rec_s:6} | F1: {f1_s:6} | Shifted: {len(ab.changed_cases_from_full)}")
        for ch in ab.changed_cases_from_full:
            print(f"   -> Shifted: {ch.get('drug')} -> {ch.get('disease')}: {ch.get('full_prediction')} -> {ch.get('ablated_prediction')}")

    print("\n--- 5. Generating Test PDF ---")
    exporter = EvaluationPDFExporter(report)
    pdf_bytes = exporter.generate_pdf_bytes()
    pdf_path = "scratch/phase4e_evaluation_report.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Wrote {len(pdf_bytes)} bytes to {pdf_path}")

    print("\n" + "=" * 80)
    print("PHASE 4E LIVE BENCHMARK EXECUTION COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
