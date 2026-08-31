"""Evaluation metrics and confusion matrix computation for Phase 4E."""
from __future__ import annotations

import math
from typing import Sequence
from backend.evaluation.benchmark_models import (
    BenchmarkClass,
    BenchmarkMetrics,
    ConfusionMatrix3x3,
    BenchmarkCaseResult,
)


def compute_benchmark_metrics(results: Sequence[BenchmarkCaseResult]) -> BenchmarkMetrics:
    """Calculate comprehensive benchmark metrics across evaluation results.
    
    Handles missing class scenarios gracefully: unavailable metrics evaluate to None.
    """
    total = len(results)
    if total == 0:
        return BenchmarkMetrics(notes=["Empty benchmark results dataset."])

    cm = ConfusionMatrix3x3()
    pos_cases = 0
    neg_cases = 0
    unc_cases = 0
    correct = 0
    incorrect = 0
    unresolved = 0
    notes: list[str] = []

    for r in results:
        exp_raw = r.case.expected_class
        pred_raw = r.predicted_class
        exp = BenchmarkClass(exp_raw) if not isinstance(exp_raw, BenchmarkClass) else exp_raw
        pred = BenchmarkClass(pred_raw) if not isinstance(pred_raw, BenchmarkClass) else pred_raw
        cm.record(exp, pred)

        if exp == BenchmarkClass.POSITIVE:
            pos_cases += 1
        elif exp == BenchmarkClass.NEGATIVE:
            neg_cases += 1
        elif exp == BenchmarkClass.UNCERTAIN:
            unc_cases += 1

        if exp == pred:
            correct += 1
        else:
            if pred == BenchmarkClass.UNCERTAIN:
                unresolved += 1
            else:
                incorrect += 1

    accuracy = round(correct / total, 4) if total > 0 else None

    # Binary/Directional metrics over POSITIVE vs NEGATIVE
    tp = cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE)
    fp = cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE)
    fn = cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE)
    tn = cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE)

    # Precision: Positive Predictive Value
    if (tp + fp) > 0:
        precision = round(tp / (tp + fp), 4)
    else:
        precision = None
        notes.append("Precision unavailable (no positive predictions made).")

    # Recall / Sensitivity: True Positive Rate
    if pos_cases > 0:
        recall = round(tp / pos_cases, 4)
    else:
        recall = None
        notes.append("Recall unavailable (no positive ground-truth cases in benchmark).")

    # Specificity: True Negative Rate
    if neg_cases > 0:
        specificity = round(tn / neg_cases, 4)
    else:
        specificity = None
        notes.append("Specificity unavailable (no negative ground-truth cases in benchmark).")

    # F1 Score
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1_score = round(2 * (precision * recall) / (precision + recall), 4)
    else:
        f1_score = None

    # Matthews Correlation Coefficient (MCC)
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom > 0:
        mcc = round(((tp * tn) - (fp * fn)) / denom, 4)
    else:
        mcc = None
        notes.append("MCC unavailable due to zero-variance in one or more marginal classes.")

    return BenchmarkMetrics(
        total_cases=total,
        positive_cases=pos_cases,
        negative_cases=neg_cases,
        uncertain_cases=unc_cases,
        correct_predictions=correct,
        incorrect_predictions=incorrect,
        unresolved_predictions=unresolved,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        specificity=specificity,
        f1_score=f1_score,
        mcc=mcc,
        confusion_matrix=cm,
        notes=notes,
    )
