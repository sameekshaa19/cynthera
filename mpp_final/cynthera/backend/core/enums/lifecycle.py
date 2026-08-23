"""HypothesisLifecycleState enum — lifecycle states of a Hypothesis entity.

Reference: 02_DOMAIN_MODEL.md §4.2
"""
from enum import Enum


class HypothesisLifecycleState(str, Enum):
    """Lifecycle state machine for a Hypothesis evaluation."""

    INITIALIZED = "INITIALIZED"
    """Created with validated input strings."""

    ID_RESOLVED = "ID_RESOLVED"
    """Standard biological taxonomies have successfully mapped the names."""

    DATA_RETRIEVED = "DATA_RETRIEVED"
    """External raw responses have been collected and cached."""

    NORMALIZED = "NORMALIZED"
    """Raw data has been converted to Canonical Domain Models."""

    REASONED = "REASONED"
    """Stances have been mapped and target pathway traces are complete."""

    EVALUATED = "EVALUATED"
    """Three-dimensional scores (SS, MS, RS) have been computed."""

    COMPLETED = "COMPLETED"
    """Recommendation rules have run, and the report has been written."""

    FAILED = "FAILED"
    """Pipeline terminated at any prior stage due to a non-recoverable error."""
