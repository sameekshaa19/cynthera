"""PredicateType enum — directional mechanism of a claim triplet.

Reference: 02_DOMAIN_MODEL.md §2.1
"""
from enum import Enum


class PredicateType(str, Enum):
    """Represents the directional mechanism of a claims triplet."""

    ACTIVATES = "ACTIVATES"
    """Increases the target protein's functional activity."""

    INHIBITS = "INHIBITS"
    """Decreases or blocks the target protein's functional activity."""

    BINDS = "BINDS"
    """Physically associates with the target without specified functional direction."""

    UPREGULATES = "UPREGULATES"
    """Increases the expression level (transcription/translation) of a gene or protein."""

    DOWNREGULATES = "DOWNREGULATES"
    """Decreases the expression level of a gene or protein."""

    CAUSES = "CAUSES"
    """Induces a downstream pathological state or process."""

    PREVENTS = "PREVENTS"
    """Halts or reverses a downstream pathological state or process."""

    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    """Statistically correlates with, but without implied direct physical causality."""

    NO_EFFECT = "NO_EFFECT"
    """Explicitly shown to have no directional, regulatory, or binding impact."""
