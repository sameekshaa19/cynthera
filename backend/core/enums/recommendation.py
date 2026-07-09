"""RecommendationStatus enum — indication classification output.

Reference: 02_DOMAIN_MODEL.md §2.3
"""
from enum import Enum


class RecommendationStatus(str, Enum):
    """The indication classification output by the recommendation engine."""

    PROMISING = "PROMISING"
    """High-quality supporting evidence with plausible biological pathways and low safety/failure risks."""

    UNCERTAIN = "UNCERTAIN"
    """Conflicting or sparse evidence, or incomplete pathway connectivity."""

    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    """Strong contradictory evidence, failed clinical trials, or high biological risks."""
