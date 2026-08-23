"""Hypothesis entity — parent entity for drug-disease repurposing query.

Reference: 02_DOMAIN_MODEL.md §4.2
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from backend.core.enums.lifecycle import HypothesisLifecycleState
from backend.core.enums.retrieval_policy import RetrievalPolicy


class Hypothesis(BaseModel):
    """The primary parent entity representing the drug-disease repurposing query.

    Mutable — lifecycle state transitions update this entity.
    Duplicate concurrent queries for the same drug-disease key are blocked
    at the Orchestrator level.

    Attributes:
        id: Internal UUID.
        drug_name: Input drug query string.
        disease_name: Input disease query string.
        drug_chembl_id: Resolved ChEMBL ID of the drug (set after ID resolution).
        disease_mesh_id: Resolved MeSH ID of the disease (set after ID resolution).
        retrieval_policy: Controls depth and scope of retrieval.
        lifecycle_state: Current state in the evaluation pipeline.
        created_at: UTC timestamp of creation.
        updated_at: UTC timestamp of last state change.
        trace_id: Unique trace identifier for request logging.
        error_message: Set if lifecycle_state transitions to FAILED.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    drug_name: str = Field(..., min_length=1, description="Input drug query string.")
    disease_name: str = Field(..., min_length=1, description="Input disease query string.")
    drug_chembl_id: str | None = Field(None, description="Resolved ChEMBL ID (set after ID resolution).")
    disease_mesh_id: str | None = Field(None, description="Resolved MeSH ID (set after ID resolution).")
    retrieval_policy: RetrievalPolicy = Field(
        default=RetrievalPolicy.STANDARD,
        description="Controls depth and scope of retrieval.",
    )
    lifecycle_state: HypothesisLifecycleState = Field(
        default=HypothesisLifecycleState.INITIALIZED,
        description="Current lifecycle state.",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="UTC creation timestamp.")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="UTC last update timestamp.")
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique trace identifier.")
    error_message: str | None = Field(None, description="Set if lifecycle_state is FAILED.")

    def transition_to(self, state: HypothesisLifecycleState, error: str | None = None) -> None:
        """Transition this Hypothesis to a new lifecycle state.

        Args:
            state: The new HypothesisLifecycleState.
            error: Optional error message (required if state is FAILED).
        """
        object.__setattr__(self, "lifecycle_state", state)
        object.__setattr__(self, "updated_at", datetime.utcnow())
        if error:
            object.__setattr__(self, "error_message", error)

    @property
    def query_key(self) -> str:
        """Canonical key for deduplication: drug_name::disease_name (lowercased)."""
        return f"{self.drug_name.lower()}::{self.disease_name.lower()}"
