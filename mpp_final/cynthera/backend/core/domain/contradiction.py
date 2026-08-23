"""Contradiction entity — directional conflict between claims or evidence.

Reference: 02_DOMAIN_MODEL.md §4.14
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator


class Contradiction(BaseModel):
    """An analytical model documenting a directional conflict between two claims/evidence records.

    Immutable. Created by the ContradictionAnalysisAgent.
    Target subject and object must be identical across both conflicting claims.
    Contradiction Score must be float [0.0, 1.0].

    Attributes:
        id: Internal UUID.
        claim_id_a: UUID of the first conflicting Claim.
        claim_id_b: UUID of the second conflicting Claim.
        conflict_type: Description of the conflict type (e.g., 'directional', 'trial_failure').
        contradiction_score: Severity score [0.0, 1.0] where 1.0 is maximum conflict.
        shared_subject: The shared biological entity that is the subject of conflict.
        explanation: Human-readable explanation of the contradiction.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    claim_id_a: uuid.UUID = Field(..., description="UUID of the first conflicting Claim.")
    claim_id_b: uuid.UUID = Field(..., description="UUID of the second conflicting Claim.")
    conflict_type: str = Field(..., description="Type of conflict (e.g., 'directional', 'trial_failure').")
    contradiction_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Severity score [0.0, 1.0].",
    )
    shared_subject: str = Field(
        ...,
        description="The shared biological entity that is the subject of conflict.",
    )
    explanation: str = Field(..., description="Human-readable explanation of the contradiction.")

    @field_validator("contradiction_score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        """Round contradiction score to 4 decimal places."""
        return round(v, 4)
