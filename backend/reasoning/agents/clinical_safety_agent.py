"""ClinicalSafetyAgent — enhanced clinical trial and safety signal analysis.

Phase 2 enhancement: deep-analyzes clinical trial records for adverse events,
safety terminations, boxed warnings, and population restrictions to produce
a structured SafetyProfile that enriches the RiskAssessment.

Reference: 05_AGENT_SPECIFICATIONS.md, Phase 2 enhancements
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.trial_outcome import TrialOutcomeStatus

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Safety Domain Constants
# ─────────────────────────────────────────────

_BOXED_WARNING_KEYWORDS: list[str] = [
    "black box", "boxed warning", "black-box", "serious adverse",
    "life-threatening", "fatal", "death", "mortality", "severe toxicity",
    "hepatotoxicity", "cardiotoxicity", "nephrotoxicity", "myelosuppression",
]

_ADVERSE_EVENT_KEYWORDS: list[str] = [
    "adverse", "side effect", "toxicity", "discontinuation", "withdrawal",
    "hypersensitivity", "anaphylaxis", "QT prolongation", "arrhythmia",
    "hepatic", "renal impairment", "neutropenia", "thrombocytopenia",
    "hypertension", "hypotension", "bleeding", "thrombosis",
]

_INTERACTION_KEYWORDS: list[str] = [
    "interaction", "contraindicated", "CYP450", "CYP3A4", "P-glycoprotein",
    "warfarin", "anticoagulant", "inhibitor", "inducer", "substrate",
]

_POPULATION_RESTRICTION_KEYWORDS: list[str] = [
    "pregnancy", "pediatric", "geriatric", "renal impairment",
    "hepatic impairment", "elderly", "children", "lactation", "nursing",
]


# ─────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────

@dataclass
class AdverseEvent:
    """A detected adverse event signal from trial data."""
    event_type: str
    severity: str  # "MILD" | "MODERATE" | "SEVERE" | "FATAL"
    source_trial_id: str
    description: str
    frequency_estimate: float = 0.0  # 0.0–1.0


@dataclass
class SafetyProfile:
    """Structured safety characterization of a drug-disease pair.

    Attributes:
        has_boxed_warning: Whether boxed/black-box warnings were detected.
        adverse_events: List of detected adverse event signals.
        drug_interactions: Detected interaction signals.
        population_restrictions: Populations where use is restricted.
        safety_termination_count: Trials terminated for safety reasons.
        overall_safety_grade: 'A' (safest) to 'D' (high concern).
        safety_narrative: Human-readable safety summary.
        confidence: Confidence in this safety profile [0.0, 1.0].
    """
    has_boxed_warning: bool = False
    adverse_events: list[AdverseEvent] = field(default_factory=list)
    drug_interactions: list[str] = field(default_factory=list)
    population_restrictions: list[str] = field(default_factory=list)
    safety_termination_count: int = 0
    overall_safety_grade: str = "C"  # A, B, C, D
    safety_narrative: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage / API response."""
        return {
            "has_boxed_warning": self.has_boxed_warning,
            "adverse_events": [
                {
                    "event_type": ae.event_type,
                    "severity": ae.severity,
                    "source_trial_id": ae.source_trial_id,
                    "description": ae.description,
                    "frequency_estimate": ae.frequency_estimate,
                }
                for ae in self.adverse_events
            ],
            "drug_interactions": self.drug_interactions,
            "population_restrictions": self.population_restrictions,
            "safety_termination_count": self.safety_termination_count,
            "overall_safety_grade": self.overall_safety_grade,
            "safety_narrative": self.safety_narrative,
            "confidence": self.confidence,
        }


# ─────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────

class ClinicalSafetyAgent:
    """Enhanced clinical and safety analysis agent.

    Analyzes clinical trial records to extract structured safety signals:
    - Boxed warning detection from trial descriptions
    - Adverse event pattern extraction with severity classification
    - Drug interaction signal identification
    - Population restriction detection
    - Safety-terminated trial counting

    All analysis is deterministic (no LLM calls). Uses keyword-based NLP
    over trial title/description text combined with structured outcome data.
    """

    def __init__(self) -> None:
        """Initialize the ClinicalSafetyAgent."""
        logger.info("ClinicalSafetyAgent initialized")

    def analyze(self, package: RetrievalPackage) -> SafetyProfile:
        """Analyze a RetrievalPackage to produce a SafetyProfile.

        Args:
            package: The sealed RetrievalPackage containing clinical trial data.

        Returns:
            SafetyProfile with structured safety characterization.
        """
        trials = package.clinical_trials
        drug_name = package.drug.name.lower()

        logger.info(
            "clinical_safety_analysis_start",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "trial_count": len(trials),
                "drug": package.drug.name,
            },
        )

        if not trials:
            return SafetyProfile(
                overall_safety_grade="C",
                safety_narrative=(
                    f"No clinical trial data available for {package.drug.name}. "
                    "Safety profile could not be assessed."
                ),
                confidence=0.1,
            )

        # Run all analyses
        has_boxed_warning = self._detect_boxed_warnings(trials, drug_name)
        adverse_events = self._extract_adverse_events(trials)
        drug_interactions = self._detect_drug_interactions(trials, drug_name)
        population_restrictions = self._detect_population_restrictions(trials)
        safety_terminations = self._count_safety_terminations(trials)

        # Compute safety grade
        grade = self._compute_safety_grade(
            has_boxed_warning=has_boxed_warning,
            safety_termination_count=safety_terminations,
            severe_ae_count=sum(1 for ae in adverse_events if ae.severity in ("SEVERE", "FATAL")),
            total_trials=len(trials),
        )

        confidence = self._compute_confidence(trials)

        narrative = self._build_narrative(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
            has_boxed_warning=has_boxed_warning,
            adverse_events=adverse_events,
            drug_interactions=drug_interactions,
            population_restrictions=population_restrictions,
            safety_terminations=safety_terminations,
            grade=grade,
        )

        profile = SafetyProfile(
            has_boxed_warning=has_boxed_warning,
            adverse_events=adverse_events,
            drug_interactions=drug_interactions,
            population_restrictions=population_restrictions,
            safety_termination_count=safety_terminations,
            overall_safety_grade=grade,
            safety_narrative=narrative,
            confidence=confidence,
        )

        logger.info(
            "clinical_safety_analysis_complete",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "safety_grade": grade,
                "has_boxed_warning": has_boxed_warning,
                "adverse_events_found": len(adverse_events),
                "safety_terminations": safety_terminations,
            },
        )

        return profile

    # ─────────────────────────────────────────────
    # Private Analysis Methods
    # ─────────────────────────────────────────────

    def _get_trial_text(self, trial: ClinicalTrial) -> str:
        """Concatenate all searchable text fields from a trial."""
        parts: list[str] = [trial.title]
        if hasattr(trial, "description") and trial.description:
            parts.append(trial.description)
        if hasattr(trial, "primary_outcome") and trial.primary_outcome:
            parts.append(trial.primary_outcome)
        return " ".join(parts).lower()

    def _detect_boxed_warnings(
        self, trials: list[ClinicalTrial], drug_name: str
    ) -> bool:
        """Detect boxed/black-box warning signals in trial text."""
        for trial in trials:
            text = self._get_trial_text(trial)
            for keyword in _BOXED_WARNING_KEYWORDS:
                if keyword in text:
                    logger.debug(
                        "boxed_warning_detected",
                        extra={"trial_id": trial.nct_id, "keyword": keyword},
                    )
                    return True
        return False

    def _extract_adverse_events(
        self, trials: list[ClinicalTrial]
    ) -> list[AdverseEvent]:
        """Extract adverse event signals from trial records."""
        events: list[AdverseEvent] = []

        for trial in trials:
            text = self._get_trial_text(trial)

            for keyword in _ADVERSE_EVENT_KEYWORDS:
                if keyword in text:
                    severity = self._classify_ae_severity(text, keyword)
                    events.append(
                        AdverseEvent(
                            event_type=keyword,
                            severity=severity,
                            source_trial_id=trial.nct_id,
                            description=self._extract_ae_context(text, keyword),
                            frequency_estimate=self._estimate_ae_frequency(
                                trial, severity
                            ),
                        )
                    )
                    break  # One AE per trial to avoid duplicates

        # Deduplicate by event_type
        seen: set[str] = set()
        unique: list[AdverseEvent] = []
        for ae in events:
            key = f"{ae.event_type}:{ae.severity}"
            if key not in seen:
                seen.add(key)
                unique.append(ae)

        return unique[:15]  # Cap at 15 adverse events

    def _classify_ae_severity(self, text: str, keyword: str) -> str:
        """Classify AE severity based on surrounding context."""
        fatal_markers = ["fatal", "death", "mortality", "life-threatening"]
        severe_markers = ["severe", "serious", "grade 3", "grade 4", "hospitali"]
        moderate_markers = ["moderate", "grade 2", "significant"]

        for marker in fatal_markers:
            if marker in text:
                return "FATAL"
        for marker in severe_markers:
            if marker in text:
                return "SEVERE"
        for marker in moderate_markers:
            if marker in text:
                return "MODERATE"
        return "MILD"

    def _extract_ae_context(self, text: str, keyword: str) -> str:
        """Extract a short snippet of context around the keyword."""
        idx = text.find(keyword)
        if idx == -1:
            return keyword
        start = max(0, idx - 60)
        end = min(len(text), idx + 100)
        snippet = text[start:end].strip()
        return f"...{snippet}..."

    def _estimate_ae_frequency(
        self, trial: ClinicalTrial, severity: str
    ) -> float:
        """Estimate AE frequency based on trial outcome and severity."""
        if trial.status == TrialOutcomeStatus.TERMINATED_SAFETY:
            return 0.7 if severity in ("SEVERE", "FATAL") else 0.4
        if trial.status == TrialOutcomeStatus.COMPLETED_FAILURE:
            return 0.3
        if severity == "FATAL":
            return 0.2
        if severity == "SEVERE":
            return 0.15
        return 0.05

    def _detect_drug_interactions(
        self, trials: list[ClinicalTrial], drug_name: str
    ) -> list[str]:
        """Detect drug interaction signals."""
        interactions: list[str] = []
        for trial in trials:
            text = self._get_trial_text(trial)
            for keyword in _INTERACTION_KEYWORDS:
                if keyword in text and keyword not in interactions:
                    interactions.append(keyword)
        return interactions[:10]

    def _detect_population_restrictions(
        self, trials: list[ClinicalTrial]
    ) -> list[str]:
        """Detect population-specific use restrictions."""
        restrictions: list[str] = []
        for trial in trials:
            text = self._get_trial_text(trial)
            for keyword in _POPULATION_RESTRICTION_KEYWORDS:
                if keyword in text and keyword not in restrictions:
                    restrictions.append(keyword)
        return restrictions[:8]

    def _count_safety_terminations(self, trials: list[ClinicalTrial]) -> int:
        """Count trials terminated for safety reasons."""
        return sum(
            1 for t in trials
            if t.status == TrialOutcomeStatus.TERMINATED_SAFETY
        )

    def _compute_safety_grade(
        self,
        has_boxed_warning: bool,
        safety_termination_count: int,
        severe_ae_count: int,
        total_trials: int,
    ) -> str:
        """Compute an overall safety grade (A=safest, D=high concern).

        Grading logic:
        - D: boxed warning OR >= 2 safety terminations OR >= 3 severe AEs
        - C: 1 safety termination OR 1-2 severe AEs OR limited data
        - B: no safety terminations, <= 1 severe AE, >= 5 trials
        - A: strong clean safety record across many trials
        """
        if has_boxed_warning or safety_termination_count >= 2 or severe_ae_count >= 3:
            return "D"
        if safety_termination_count == 1 or severe_ae_count >= 1:
            return "C"
        if total_trials >= 5 and severe_ae_count == 0 and safety_termination_count == 0:
            return "A"
        if total_trials >= 2:
            return "B"
        return "C"

    def _compute_confidence(self, trials: list[ClinicalTrial]) -> float:
        """Compute confidence in the safety profile based on data richness."""
        n = len(trials)
        if n >= 10:
            return 0.9
        if n >= 5:
            return 0.75
        if n >= 2:
            return 0.55
        return 0.3

    def _build_narrative(
        self,
        drug_name: str,
        disease_name: str,
        has_boxed_warning: bool,
        adverse_events: list[AdverseEvent],
        drug_interactions: list[str],
        population_restrictions: list[str],
        safety_terminations: int,
        grade: str,
    ) -> str:
        """Build a human-readable safety narrative."""
        parts: list[str] = [
            f"Safety profile for {drug_name} in {disease_name}: Grade {grade}."
        ]

        if has_boxed_warning:
            parts.append(
                "⚠️ Boxed/black-box warning signals detected in clinical trial records."
            )

        if safety_terminations > 0:
            parts.append(
                f"{safety_terminations} trial(s) terminated due to safety concerns."
            )

        severe_aes = [ae for ae in adverse_events if ae.severity in ("SEVERE", "FATAL")]
        if severe_aes:
            ae_types = ", ".join(ae.event_type for ae in severe_aes[:3])
            parts.append(f"Severe adverse events detected: {ae_types}.")

        if drug_interactions:
            parts.append(
                f"Drug interaction signals: {', '.join(drug_interactions[:3])}."
            )

        if population_restrictions:
            parts.append(
                f"Population considerations: {', '.join(population_restrictions[:3])}."
            )

        grade_notes = {
            "A": "Strong clean safety record — no significant concerns identified.",
            "B": "Acceptable safety profile with minor concerns.",
            "C": "Moderate safety concerns — careful monitoring recommended.",
            "D": "Significant safety concerns — additional preclinical/clinical review required.",
        }
        parts.append(grade_notes.get(grade, ""))

        return " ".join(parts)
