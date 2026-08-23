"""
CYNTHERA Diagnostic Test Suite

Purpose
-------
This is NOT the final scientific benchmark.

It is a diagnostic integration suite designed to answer:

    "Which part of CYNTHERA is currently behaving incorrectly?"

It runs real evaluations through the API, retrieves the full ReasoningResult,
and checks the internal output for obvious scientific/architectural failures.

Run:
    pytest -s tests/diagnostic/test_cynthera_diagnostic.py

For a faster run:
    pytest -s tests/diagnostic/test_cynthera_diagnostic.py -k "mechanism"

Requirements:
    pip install pytest pytest-asyncio httpx
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import pytest


# ============================================================
# Configuration
# ============================================================

BASE_URL = os.getenv(
    "CYNTHERA_BASE_URL",
    "http://localhost:8000",
)

API_PREFIX = "/api/v1"

RESULTS_DIR = Path("tests/diagnostic/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Test Cases
# ============================================================

@dataclass(frozen=True)
class DiagnosticCase:
    id: str
    drug: str
    disease: str

    # What we expect scientifically.
    expected_class: str

    # Which subsystem this case primarily probes.
    primary_test: str

    # Human-readable expectation.
    expectation: str


CASES = [

    # --------------------------------------------------------
    # POSITIVE MECHANISTIC CASES
    # --------------------------------------------------------

    DiagnosticCase(
        id="T01",
        drug="Sildenafil",
        disease="Pulmonary Arterial Hypertension",
        expected_class="STRONG_POSITIVE",
        primary_test="MECHANISM",
        expectation=(
            "A credible mechanistic chain should be discoverable. "
            "The system should not return zero mechanistic paths."
        ),
    ),

    DiagnosticCase(
        id="T02",
        drug="Metformin",
        disease="Type 2 Diabetes",
        expected_class="STRONG_POSITIVE",
        primary_test="MECHANISM",
        expectation=(
            "A well-established drug-disease relationship should produce "
            "substantial supporting evidence and a plausible mechanism."
        ),
    ),

    # --------------------------------------------------------
    # NEGATIVE / INSUFFICIENT CASES
    # --------------------------------------------------------

    DiagnosticCase(
        id="T03",
        drug="Sildenafil",
        disease="Alzheimer Disease",
        expected_class="INSUFFICIENT",
        primary_test="HALLUCINATION",
        expectation=(
            "The system should not manufacture a confident mechanistic "
            "chain merely because both entities have extensive literature."
        ),
    ),

    DiagnosticCase(
        id="T04",
        drug="Paracetamol",
        disease="Melanoma",
        expected_class="INSUFFICIENT",
        primary_test="SCORING",
        expectation=(
            "Weak or indirect evidence should not automatically produce "
            "a very high support/confidence score."
        ),
    ),

    # --------------------------------------------------------
    # CONTRADICTION CASES
    # --------------------------------------------------------

    DiagnosticCase(
        id="T05",
        drug="Hydroxychloroquine",
        disease="COVID-19",
        expected_class="CONTRADICTORY",
        primary_test="CONTRADICTION",
        expectation=(
            "The system should preserve and expose conflicting evidence "
            "rather than treating literature volume as simple support."
        ),
    ),

    DiagnosticCase(
        id="T06",
        drug="Ivermectin",
        disease="COVID-19",
        expected_class="CONTRADICTORY",
        primary_test="CONTRADICTION",
        expectation=(
            "The system should identify evidence disagreement and avoid "
            "an unjustifiably high confidence score."
        ),
    ),
]


# ============================================================
# Helpers
# ============================================================

def get_nested(
    obj: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """
    Safely retrieve nested dictionary values.

    Example:
        get_nested(result, "mechanistic_assessment", "score")
    """
    current: Any = obj

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def first_present(
    obj: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """
    Return the first existing key.
    """
    for key in keys:
        if key in obj:
            return obj[key]

    return default


def find_values(
    obj: Any,
    target_keys: set[str],
) -> list[Any]:
    """
    Recursively find values for keys anywhere inside a JSON object.

    This intentionally makes the diagnostic test tolerant of small
    response-schema changes.
    """

    found: list[Any] = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            if key.lower() in target_keys:
                found.append(value)

            found.extend(find_values(value, target_keys))

    elif isinstance(obj, list):

        for item in obj:
            found.extend(find_values(item, target_keys))

    return found


def extract_paths(result: dict[str, Any]) -> list[Any]:
    """
    Locate mechanistic paths regardless of their exact nesting.
    """

    candidates = find_values(
        result,
        {
            "mechanistic_paths",
            "candidate_paths",
            "paths",
            "mechanisms",
            "candidate_mechanisms",
        },
    )

    # Flatten one level if needed.
    paths: list[Any] = []

    for value in candidates:

        if isinstance(value, list):
            paths.extend(value)

        elif isinstance(value, dict):
            paths.append(value)

    return paths


def extract_contradictions(result: dict[str, Any]) -> list[Any]:
    """
    Locate contradiction objects.
    """

    candidates = find_values(
        result,
        {
            "contradictions",
            "contradiction_reports",
            "conflicts",
            "conflict_items",
        },
    )

    contradictions: list[Any] = []

    for value in candidates:

        if isinstance(value, list):
            contradictions.extend(value)

        elif isinstance(value, dict):
            contradictions.append(value)

    return contradictions


def extract_score(
    result: dict[str, Any],
    *possible_paths: tuple[str, ...],
) -> float | None:

    for path in possible_paths:

        value = get_nested(
            result,
            *path,
        )

        if isinstance(value, (int, float)):
            return float(value)

    return None


def score_to_percentage(value: float | None) -> float | None:

    if value is None:
        return None

    if value <= 1.0:
        return value * 100.0

    return value


# ============================================================
# API Runner
# ============================================================

async def run_evaluation(
    client: httpx.AsyncClient,
    case: DiagnosticCase,
) -> tuple[dict[str, Any], dict[str, Any]]:

    payload = {
        "drug_name": case.drug,
        "disease_name": case.disease,
        "retrieval_policy": "COMPREHENSIVE",
        "bypass_cache": True,
    }

    response = await client.post(
        f"{API_PREFIX}/evaluate",
        json=payload,
        timeout=180.0,
    )

    response.raise_for_status()

    summary = response.json()

    hypothesis_id = summary["hypothesis_id"]

    result_response = await client.get(
        f"{API_PREFIX}/results/{hypothesis_id}",
        timeout=30.0,
    )

    result_response.raise_for_status()

    result = result_response.json()

    return summary, result


# ============================================================
# Diagnostic Analysis
# ============================================================

def analyse_case(
    case: DiagnosticCase,
    summary: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:

    diagnostics: dict[str, Any] = {
        "case_id": case.id,
        "drug": case.drug,
        "disease": case.disease,
        "primary_test": case.primary_test,
        "expected_class": case.expected_class,
        "expectation": case.expectation,
        "checks": {},
    }

    checks = diagnostics["checks"]

    # --------------------------------------------------------
    # 1. Identity / retrieval
    # --------------------------------------------------------

    sources_queried = summary.get(
        "sources_queried",
        [],
    )

    sources_failed = summary.get(
        "sources_failed",
        [],
    )

    checks["retrieval"] = {
        "status": (
            "FAIL"
            if not sources_queried
            else "WARN" if sources_failed else "PASS"
        ),
        "sources_queried": sources_queried,
        "sources_failed": sources_failed,
    }

    # --------------------------------------------------------
    # 2. Scores
    # --------------------------------------------------------

    support_score = extract_score(
        result,
        ("support_assessment", "score"),
        ("support_score",),
    )

    mechanism_score = extract_score(
        result,
        ("mechanistic_assessment", "score"),
        ("mechanistic_score",),
    )

    risk_score = extract_score(
        result,
        ("risk_assessment", "score"),
        ("risk_score",),
    )

    confidence = first_present(
        result,
        "overall_confidence",
        "confidence",
    )

    checks["scores"] = {
        "support_score": support_score,
        "mechanistic_score": mechanism_score,
        "risk_score": risk_score,
        "overall_confidence": confidence,
    }

    # --------------------------------------------------------
    # 3. Mechanistic paths
    # --------------------------------------------------------

    paths = extract_paths(result)

    checks["mechanism"] = {
        "path_count": len(paths),
        "status": "PASS" if paths else "FAIL",
    }

    # Strong positives should have a mechanism.
    if case.expected_class == "STRONG_POSITIVE":

        if not paths:
            checks["mechanism"]["diagnostic"] = (
                "CRITICAL: strong positive case produced zero "
                "mechanistic paths."
            )

        else:
            checks["mechanism"]["diagnostic"] = (
                "Mechanistic path(s) found."
            )

    # Hard/insufficient cases should NOT fabricate mechanisms.
    elif case.expected_class == "INSUFFICIENT":

        if paths and mechanism_score is not None and mechanism_score > 0.8:
            checks["mechanism"]["diagnostic"] = (
                "CRITICAL: insufficient-evidence case has both "
                "mechanistic paths and very high mechanistic score."
            )

        else:
            checks["mechanism"]["diagnostic"] = (
                "No obvious overconfident mechanistic conclusion detected."
            )

    # --------------------------------------------------------
    # 4. Contradictions
    # --------------------------------------------------------

    contradictions = extract_contradictions(result)

    checks["contradictions"] = {
        "count": len(contradictions),
        "status": (
            "PASS"
            if case.expected_class != "CONTRADICTORY"
            else "PASS" if contradictions else "FAIL"
        ),
    }

    if case.expected_class == "CONTRADICTORY":

        if not contradictions:
            checks["contradictions"]["diagnostic"] = (
                "CRITICAL: known controversial case produced "
                "zero contradiction objects."
            )

        else:
            checks["contradictions"]["diagnostic"] = (
                "Contradiction evidence detected."
            )

    # --------------------------------------------------------
    # 5. Confidence sanity
    # --------------------------------------------------------

    confidence_numeric: float | None = None

    if isinstance(confidence, (int, float)):
        confidence_numeric = float(confidence)

    elif isinstance(confidence, str):

        try:
            confidence_numeric = float(
                confidence.replace("%", "").strip()
            )
        except ValueError:
            confidence_numeric = None

    if confidence_numeric is not None:

        confidence_pct = (
            confidence_numeric * 100
            if confidence_numeric <= 1
            else confidence_numeric
        )

        checks["confidence"] = {
            "value_percent": round(confidence_pct, 2),
            "status": "PASS",
        }

        # Very weak cases should not get 95%+ confidence.
        if case.expected_class in {
            "INSUFFICIENT",
            "CONTRADICTORY",
        } and confidence_pct >= 95:

            checks["confidence"]["status"] = "FAIL"

            checks["confidence"]["diagnostic"] = (
                "CRITICAL: uncertain/contradictory case received "
                f"{confidence_pct:.1f}% confidence."
            )

    else:

        checks["confidence"] = {
            "value_percent": None,
            "status": "WARN",
            "diagnostic": "Could not locate numeric confidence.",
        }

    # --------------------------------------------------------
    # 6. Support score sanity
    # --------------------------------------------------------

    support_pct = score_to_percentage(
        support_score
    )

    if support_pct is not None:

        checks["support_sanity"] = {
            "support_percent": round(support_pct, 2),
            "status": "PASS",
        }

        if case.expected_class in {
            "INSUFFICIENT",
            "CONTRADICTORY",
        } and support_pct >= 95:

            checks["support_sanity"]["status"] = "FAIL"

            checks["support_sanity"]["diagnostic"] = (
                "CRITICAL: weak/contradictory case has "
                f"{support_pct:.1f}% support."
            )

    # --------------------------------------------------------
    # 7. Mechanism score sanity
    # --------------------------------------------------------

    mechanism_pct = score_to_percentage(
        mechanism_score
    )

    if mechanism_pct is not None:

        checks["mechanism_score_sanity"] = {
            "mechanistic_percent": round(mechanism_pct, 2),
            "status": "PASS",
        }

        if (
            case.expected_class == "STRONG_POSITIVE"
            and mechanism_pct == 0
        ):

            checks["mechanism_score_sanity"]["status"] = "FAIL"

            checks["mechanism_score_sanity"]["diagnostic"] = (
                "CRITICAL: known positive case has zero "
                "mechanistic score."
            )

    # --------------------------------------------------------
    # 8. Risk sanity
    # --------------------------------------------------------

    risk_pct = score_to_percentage(
        risk_score
    )

    checks["risk"] = {
        "risk_percent": (
            round(risk_pct, 2)
            if risk_pct is not None
            else None
        ),
    }

    # --------------------------------------------------------
    # 9. Final recommendation
    # --------------------------------------------------------

    recommendation = summary.get(
        "recommendation"
    )

    checks["recommendation"] = {
        "value": recommendation,
        "status": "INFO",
    }

    diagnostics["summary"] = {
        "recommendation": recommendation,
        "support_score": support_score,
        "mechanistic_score": mechanism_score,
        "risk_score": risk_score,
        "confidence": confidence,
        "path_count": len(paths),
        "contradiction_count": len(contradictions),
        "sources_failed": sources_failed,
    }

    # --------------------------------------------------------
    # Root-cause heuristic
    # --------------------------------------------------------

    failures: list[str] = []

    for check_name, check in checks.items():

        if isinstance(check, dict):

            if check.get("status") == "FAIL":
                failures.append(check_name)

    diagnostics["likely_failure_areas"] = failures

    if "mechanism" in failures:
        diagnostics["likely_root_cause"] = (
            "MECHANISTIC GRAPH / MULTI-HOP REASONING"
        )

    elif "contradictions" in failures:
        diagnostics["likely_root_cause"] = (
            "CONTRADICTION DETECTION / EVIDENCE STANCE"
        )

    elif "support_sanity" in failures:
        diagnostics["likely_root_cause"] = (
            "SUPPORT EVIDENCE WEIGHTING / SCORING"
        )

    elif "confidence" in failures:
        diagnostics["likely_root_cause"] = (
            "CONFIDENCE CALIBRATION / CONSENSUS"
        )

    elif "retrieval" in failures:
        diagnostics["likely_root_cause"] = (
            "RETRIEVAL / SOURCE RESOLUTION"
        )

    else:
        diagnostics["likely_root_cause"] = "NO_OBVIOUS_FAILURE"

    return diagnostics


# ============================================================
# Pretty Terminal Report
# ============================================================

def print_diagnostic(report: dict[str, Any]) -> None:

    print("\n" + "=" * 78)
    print(
        f"{report['case_id']} | "
        f"{report['drug']} -> {report['disease']}"
    )
    print("=" * 78)

    summary = report["summary"]

    print(
        f"Recommendation : {summary['recommendation']}"
    )

    print(
        f"Support        : {summary['support_score']}"
    )

    print(
        f"Mechanistic    : {summary['mechanistic_score']}"
    )

    print(
        f"Risk           : {summary['risk_score']}"
    )

    print(
        f"Confidence     : {summary['confidence']}"
    )

    print(
        f"Mechanisms     : {summary['path_count']}"
    )

    print(
        f"Contradictions : {summary['contradiction_count']}"
    )

    print(
        f"Failed sources : "
        f"{', '.join(summary['sources_failed']) or 'None'}"
    )

    print("\nDIAGNOSTICS")

    for name, check in report["checks"].items():

        if not isinstance(check, dict):
            continue

        status = check.get(
            "status",
            "INFO",
        )

        diagnostic = check.get(
            "diagnostic",
            "",
        )

        print(
            f"  [{status:4}] "
            f"{name:28}"
            f"{'  ' + diagnostic if diagnostic else ''}"
        )

    print(
        "\nLIKELY ROOT CAUSE:",
        report["likely_root_cause"],
    )


# ============================================================
# Full Diagnostic Runner
# ============================================================

@pytest.mark.asyncio
async def test_cynthera_diagnostic_suite():

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={
            "Content-Type": "application/json",
        },
    ) as client:

        # ----------------------------------------------------
        # Health check
        # ----------------------------------------------------

        health = await client.get(
            f"{API_PREFIX}/health",
            timeout=10,
        )

        assert health.status_code == 200, (
            "CYNTHERA API is not running. "
            "Start the backend before running diagnostics."
        )

        all_reports: list[dict[str, Any]] = []

        # ----------------------------------------------------
        # Run cases
        # ----------------------------------------------------

        for case in CASES:

            try:

                summary, result = await run_evaluation(
                    client,
                    case,
                )

                report = analyse_case(
                    case,
                    summary,
                    result,
                )

                all_reports.append(report)

                print_diagnostic(report)

                # Save raw result too.
                raw_path = (
                    RESULTS_DIR
                    / f"{case.id}_raw.json"
                )

                raw_path.write_text(
                    json.dumps(
                        {
                            "case": asdict(case),
                            "summary": summary,
                            "result": result,
                        },
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )

            except Exception as exc:

                failure_report = {
                    "case_id": case.id,
                    "drug": case.drug,
                    "disease": case.disease,
                    "primary_test": case.primary_test,
                    "status": "PIPELINE_FAILURE",
                    "error": repr(exc),
                }

                all_reports.append(
                    failure_report
                )

                print(
                    f"\n[{case.id}] PIPELINE FAILURE"
                )

                print(
                    f"{case.drug} -> {case.disease}"
                )

                print(
                    repr(exc)
                )

        # ----------------------------------------------------
        # Save complete diagnostic report
        # ----------------------------------------------------

        report_path = (
            RESULTS_DIR
            / "diagnostic_report.json"
        )

        report_path.write_text(
            json.dumps(
                all_reports,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print("\n")
        print("=" * 78)
        print("CYNTHERA DIAGNOSTIC SUMMARY")
        print("=" * 78)

        root_causes: dict[str, int] = {}

        for report in all_reports:

            root = report.get(
                "likely_root_cause"
            )

            if root:
                root_causes[root] = (
                    root_causes.get(root, 0) + 1
                )

        for root, count in sorted(
            root_causes.items(),
            key=lambda x: -x[1],
        ):

            print(
                f"{count:2} case(s) -> {root}"
            )

        print(
            "\nFull report:"
            f"\n{report_path}"
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # This suite deliberately does NOT assert that every
        # scientific expectation is correct.
        #
        # We want the complete diagnostic output first.
        # Once the pipeline is fixed, convert the verified
        # expectations into hard assertions.
        # ----------------------------------------------------


# ============================================================
# Optional focused tests
# ============================================================

@pytest.mark.asyncio
async def test_positive_mechanism_cases():

    cases = [
        c for c in CASES
        if c.expected_class == "STRONG_POSITIVE"
    ]

    async with httpx.AsyncClient(
        base_url=BASE_URL,
    ) as client:

        health = await client.get(
            f"{API_PREFIX}/health"
        )

        assert health.status_code == 200

        for case in cases:

            summary, result = await run_evaluation(
                client,
                case,
            )

            paths = extract_paths(result)

            print(
                f"\n{case.drug} -> {case.disease}"
            )

            print(
                f"Mechanistic paths: {len(paths)}"
            )

            if not paths:

                print(
                    "!!! POSSIBLE MECHANISTIC REASONING FAILURE !!!"
                )


@pytest.mark.asyncio
async def test_contradiction_cases():

    cases = [
        c for c in CASES
        if c.expected_class == "CONTRADICTORY"
    ]

    async with httpx.AsyncClient(
        base_url=BASE_URL,
    ) as client:

        health = await client.get(
            f"{API_PREFIX}/health"
        )

        assert health.status_code == 200

        for case in cases:

            summary, result = await run_evaluation(
                client,
                case,
            )

            contradictions = extract_contradictions(
                result
            )

            print(
                f"\n{case.drug} -> {case.disease}"
            )

            print(
                f"Contradictions: "
                f"{len(contradictions)}"
            )

            if not contradictions:

                print(
                    "!!! POSSIBLE CONTRADICTION "
                    "DETECTION FAILURE !!!"
                )
