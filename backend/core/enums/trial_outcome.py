"""TrialOutcomeStatus enum — clinical status of a human clinical study.

Reference: 02_DOMAIN_MODEL.md §2.4
"""
from enum import Enum


class TrialOutcomeStatus(str, Enum):
    """The clinical status of a human clinical study."""

    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    """Trial finished, meeting primary clinical endpoints."""

    COMPLETED_FAILURE = "COMPLETED_FAILURE"
    """Trial finished, failing to meet primary endpoints."""

    TERMINATED_LACK_OF_EFFICACY = "TERMINATED_LACK_OF_EFFICACY"
    """Trial stopped early due to insufficient therapeutic effect."""

    TERMINATED_SAFETY = "TERMINATED_SAFETY"
    """Trial stopped early due to unacceptable toxicity or adverse events."""

    ACTIVE = "ACTIVE"
    """Trial currently recruiting or running."""

    UNKNOWN = "UNKNOWN"
    """Trial status could not be determined from available data."""
