"""Unit tests for ClinicalSafetyAgent."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.reasoning.agents.clinical_safety_agent import (
    ClinicalSafetyAgent,
    SafetyProfile,
    AdverseEvent,
)
from backend.core.enums.trial_outcome import TrialOutcomeStatus


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def _make_trial(
    nct_id: str = "NCT001",
    title: str = "Test Trial",
    status: TrialOutcomeStatus = TrialOutcomeStatus.COMPLETED_FAILURE,
):
    """Create a minimal mock ClinicalTrial."""
    trial = MagicMock()
    trial.nct_id = nct_id
    trial.title = title
    trial.description = ""
    trial.primary_outcome = ""
    trial.status = status
    return trial


def _make_package(trials=None, drug_name="TestDrug", disease_name="TestDisease"):
    """Create a minimal mock RetrievalPackage."""
    package = MagicMock()
    package.hypothesis_id = uuid.uuid4()
    package.drug.name = drug_name
    package.disease.name = disease_name
    package.clinical_trials = trials or []
    return package


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

class TestClinicalSafetyAgent:
    """Tests for ClinicalSafetyAgent."""

    def setup_method(self):
        self.agent = ClinicalSafetyAgent()

    def test_empty_trials_returns_grade_c(self):
        """No trials should return grade C with low confidence."""
        package = _make_package(trials=[])
        profile = self.agent.analyze(package)
        assert isinstance(profile, SafetyProfile)
        assert profile.overall_safety_grade == "C"
        assert profile.confidence < 0.5
        assert "No clinical trial data" in profile.safety_narrative

    def test_boxed_warning_detection(self):
        """Trial with 'black box' in title should trigger has_boxed_warning."""
        trial = _make_trial(
            title="Phase III with black box warning for severe toxicity",
            status=TrialOutcomeStatus.COMPLETED_FAILURE,
        )
        package = _make_package(trials=[trial])
        profile = self.agent.analyze(package)
        assert profile.has_boxed_warning is True

    def test_safety_termination_counted(self):
        """Trials terminated for safety should be counted in safety_termination_count."""
        trial1 = _make_trial(status=TrialOutcomeStatus.TERMINATED_SAFETY)
        trial2 = _make_trial(nct_id="NCT002", status=TrialOutcomeStatus.TERMINATED_SAFETY)
        package = _make_package(trials=[trial1, trial2])
        profile = self.agent.analyze(package)
        assert profile.safety_termination_count == 2

    def test_grade_d_with_boxed_warning_and_safety_terminations(self):
        """Boxed warning + 2 safety terminations → grade D."""
        trial1 = _make_trial(
            title="Fatal adverse events black box",
            status=TrialOutcomeStatus.TERMINATED_SAFETY,
        )
        trial2 = _make_trial(
            nct_id="NCT002",
            title="Death mortality",
            status=TrialOutcomeStatus.TERMINATED_SAFETY,
        )
        package = _make_package(trials=[trial1, trial2])
        profile = self.agent.analyze(package)
        assert profile.overall_safety_grade == "D"

    def test_grade_a_with_clean_trials(self):
        """5+ completed trials with no safety signals → grade A."""
        trials = []
        for i in range(6):
            t = MagicMock()
            t.nct_id = f"NCT{i:03d}"
            t.title = f"Successful efficacy trial {i}"
            t.description = ""
            t.primary_outcome = ""
            t.status = TrialOutcomeStatus.COMPLETED_SUCCESS
            trials.append(t)
        package = _make_package(trials=trials)
        profile = self.agent.analyze(package)
        assert profile.overall_safety_grade in ("A", "B")

    def test_adverse_event_extraction(self):
        """Adverse event keywords should populate adverse_events list."""
        trial = _make_trial(
            title="Severe toxicity and adverse events observed",
            status=TrialOutcomeStatus.TERMINATED_SAFETY,
        )
        package = _make_package(trials=[trial])
        profile = self.agent.analyze(package)
        assert len(profile.adverse_events) > 0
        assert any(ae.severity in ("SEVERE", "FATAL") for ae in profile.adverse_events)

    def test_narrative_contains_drug_name(self):
        """Safety narrative should mention the drug name."""
        package = _make_package(drug_name="Metformin", disease_name="Cancer")
        profile = self.agent.analyze(package)
        assert "Metformin" in profile.safety_narrative

    def test_confidence_scales_with_trial_count(self):
        """More trials should yield higher confidence."""
        few_trials = [_make_trial()]
        many_trials = [_make_trial(nct_id=f"NCT{i}") for i in range(12)]

        pkg_few = _make_package(trials=few_trials)
        pkg_many = _make_package(trials=many_trials)

        conf_few = self.agent.analyze(pkg_few).confidence
        conf_many = self.agent.analyze(pkg_many).confidence

        assert conf_many > conf_few

    def test_to_dict_serializable(self):
        """SafetyProfile.to_dict() should return a JSON-serializable dict."""
        package = _make_package()
        profile = self.agent.analyze(package)
        d = profile.to_dict()
        assert isinstance(d, dict)
        assert "has_boxed_warning" in d
        assert "overall_safety_grade" in d
        assert "adverse_events" in d
        assert isinstance(d["adverse_events"], list)
