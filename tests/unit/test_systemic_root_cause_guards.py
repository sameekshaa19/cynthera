from types import SimpleNamespace

from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.trial_applicability import (
    TrialApplicabilityStatus,
    assess_trial_applicability,
)
from backend.reasoning.directional.therapeutic_evidence import (
    TherapeuticDirection,
    classify_therapeutic_direction,
    is_therapeutically_eligible_evidence,
)


def trial(title: str, conditions: list[str]) -> ClinicalTrial:
    return ClinicalTrial(
        nct_id="NCT12345678",
        title=title,
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="test",
            record_id="NCT12345678",
            url="https://clinicaltrials.gov/study/NCT12345678",
        ),
        condition_names=conditions,
    )


def test_biomarker_state_mismatch_is_rejected():
    result = assess_trial_applicability(
        trial("EGFR-negative lung cancer study", ["Lung cancer"]),
        "EGFR-positive lung cancer",
    )
    assert result.status is TrialApplicabilityStatus.SUBTYPE_MISMATCH
    assert result.direct_therapeutic_evidence is False


def test_parent_child_trial_is_context_only_not_direct():
    result = assess_trial_applicability(
        trial("Stroke study", ["Stroke"]),
        "Cardiovascular disease",
    )
    assert result.status is TrialApplicabilityStatus.PARENT_OR_BROAD_CONTEXT
    assert result.direct_therapeutic_evidence is False


def test_harmful_direction_wins_over_treatment_context():
    evidence = SimpleNamespace(
        title="Clinical trial of treatment",
        abstract="Treatment was associated with increased risk of disease and adverse outcomes.",
    )
    direction, _ = classify_therapeutic_direction(evidence)
    eligible, _ = is_therapeutically_eligible_evidence(evidence)
    assert direction in {TherapeuticDirection.INCREASES_RISK, TherapeuticDirection.ADVERSE_EVENT}
    assert eligible is False


def test_positive_therapeutic_direction_remains_eligible():
    evidence = SimpleNamespace(
        title="Treatment efficacy study",
        abstract="The therapy improved response and reduced disease severity.",
    )
    direction, _ = classify_therapeutic_direction(evidence)
    eligible, _ = is_therapeutically_eligible_evidence(evidence)
    assert direction is TherapeuticDirection.IMPROVES
    assert eligible is True
