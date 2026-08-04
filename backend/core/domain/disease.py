"""Disease entity — canonical disease representation.

Reference: 02_DOMAIN_MODEL.md §4.8
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator
from backend.core.value_objects.identifier import ResolvedIdentifierSet


class Disease(BaseModel):
    """Canonical disease entity mapped to standard biological taxonomies.

    Immutable once constructed. Created by the IdentifierResolutionService.
    Must contain a standard vocabulary identifier: MeSH ID or UMLS CUI.

    Attributes:
        id: Internal UUID for this Disease instance.
        name: Common name of the disease.
        identifiers: Resolved cross-database identifier set.
        description: Short description of the disease.
        synonyms: Alternative names for this disease.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    name: str = Field(..., min_length=1, description="Disease common name.")
    identifiers: ResolvedIdentifierSet = Field(..., description="Resolved cross-database identifiers.")
    description: str | None = Field(None, description="Short disease description.")
    synonyms: list[str] = Field(default_factory=list, description="Alternative disease names.")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        """Validate that the name is a non-empty string."""
        if not v.strip():
            raise ValueError("Disease name must be a non-empty string.")
        return v.strip()

    @property
    def mesh_id(self) -> str | None:
        """Convenience property for MeSH ID."""
        return self.identifiers.mesh_id

    @property
    def mondo_id(self) -> str | None:
        """Convenience property for Open Targets MONDO disease ID.

        Populated when IdentifierResolutionService successfully resolves
        the disease name against the Open Targets search endpoint.
        Used as the resolved identifier for OpenTargetsConnector queries
        and as the stable cache key for Open Targets association data.
        Returns None if OT resolution was unavailable — callers must
        handle this gracefully (skip OT fetch or fall back to inline search).
        """
        return self.identifiers.mondo_id

