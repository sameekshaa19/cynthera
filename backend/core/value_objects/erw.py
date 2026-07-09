"""ERW — Evidence Reliability Weight computation rules and modifiers.

Reference: 02_DOMAIN_MODEL.md §4.11, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ERW(BaseModel):
    """Immutable value object representing the Evidence Reliability Weight of a piece of evidence.

    The ERW is a float in [0.15, 1.00] anchored to an EvidenceType base weight,
    then adjusted by context modifiers (replication, sample size, conflict penalty).
    """

    model_config = {"frozen": True}

    value: float = Field(
        ...,
        ge=0.15,
        le=1.00,
        description="Evidence Reliability Weight between 0.15 (lowest) and 1.00 (highest).",
    )
    base_weight: float = Field(
        ...,
        ge=0.15,
        le=1.00,
        description="Unmodified base weight derived from EvidenceType.",
    )
    replication_modifier: float = Field(
        default=1.0,
        ge=0.5,
        le=1.5,
        description="Modifier for independent study replication (>1 boosts, <1 penalizes).",
    )
    conflict_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=0.5,
        description="Penalty subtracted when contradicting claims exist for this evidence.",
    )

    @field_validator("value")
    @classmethod
    def validate_range(cls, v: float) -> float:
        """Ensure ERW value is within the canonical range."""
        if not (0.15 <= v <= 1.00):
            raise ValueError(f"ERW value {v} is outside the canonical range [0.15, 1.00].")
        return round(v, 4)

    @classmethod
    def from_base(
        cls,
        base_weight: float,
        replication_modifier: float = 1.0,
        conflict_penalty: float = 0.0,
    ) -> "ERW":
        """Compute an ERW from a base weight and modifiers.

        Args:
            base_weight: The EvidenceType.base_erw value.
            replication_modifier: Float multiplier for replication (default 1.0).
            conflict_penalty: Float to subtract for contradicting claims (default 0.0).

        Returns:
            A new ERW value object with the computed weight clamped to [0.15, 1.00].
        """
        raw = (base_weight * replication_modifier) - conflict_penalty
        clamped = max(0.15, min(1.00, raw))
        return cls(
            value=round(clamped, 4),
            base_weight=base_weight,
            replication_modifier=replication_modifier,
            conflict_penalty=conflict_penalty,
        )
