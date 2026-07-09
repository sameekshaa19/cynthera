"""EvidenceType enum — empirical origin of retrieved evidence.

Reference: 02_DOMAIN_MODEL.md §2.2
"""
from enum import Enum


# Base Evidence Reliability Weights (ERW) per evidence type.
# These are the DEFAULT weights. Context modifiers are applied on top.
ERW_BASE_WEIGHTS: dict[str, float] = {
    "META_ANALYSIS": 1.00,
    "RCT": 0.85,
    "OBSERVATIONAL": 0.65,
    "IN_VIVO": 0.50,
    "IN_VITRO": 0.30,
    "COMPUTATIONAL": 0.15,
}


class EvidenceType(str, Enum):
    """Categorizes the empirical origin of retrieved evidence.

    ERW base weight ranges:
        META_ANALYSIS  → 1.00  (highest)
        RCT            → 0.85
        OBSERVATIONAL  → 0.65
        IN_VIVO        → 0.50
        IN_VITRO       → 0.30
        COMPUTATIONAL  → 0.15  (lowest)
    """

    META_ANALYSIS = "META_ANALYSIS"
    """Statistical synthesis of multiple clinical trials (highest clinical rank)."""

    RCT = "RCT"
    """Double-blind, randomized controlled clinical trial."""

    OBSERVATIONAL = "OBSERVATIONAL"
    """Human clinical cohort, case-control, or epidemiological study."""

    IN_VIVO = "IN_VIVO"
    """Animal model experiment (e.g., mouse, rat preclinical trial)."""

    IN_VITRO = "IN_VITRO"
    """Cell line, membrane binding, or molecular assay experiment."""

    COMPUTATIONAL = "COMPUTATIONAL"
    """Machine learning binding predictions, graph network proximity scoring, or homology modeling."""

    @property
    def base_erw(self) -> float:
        """Return the base Evidence Reliability Weight for this evidence type."""
        return ERW_BASE_WEIGHTS[self.value]
