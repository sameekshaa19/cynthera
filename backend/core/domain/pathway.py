"""Pathway entity — curated sequence of molecular interactions in a cell.

Reference: 02_DOMAIN_MODEL.md §4.9
"""
from __future__ import annotations

import uuid
import re
from pydantic import BaseModel, Field, field_validator

from backend.core.value_objects.provenance import ProvenanceReference


class Pathway(BaseModel):
    """A curated sequence of molecular interactions and reactions in a cell.

    Immutable. Created by the Normalization Layer (Reactome Analysis connector).
    Must contain a valid Reactome ID (e.g., R-HSA-202127).

    Attributes:
        id: Internal UUID.
        reactome_id: Reactome stable identifier (e.g., 'R-HSA-202127').
        name: Human-readable pathway name.
        description: Detailed pathway description.
        participant_uniprot_ids: UniProt accessions of proteins in this pathway.
        provenance: Citation to the Reactome record.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    reactome_id: str = Field(..., description="Reactome stable identifier (e.g., 'R-HSA-202127').")
    name: str = Field(..., description="Human-readable pathway name.")
    description: str | None = Field(None, description="Detailed pathway description.")
    participant_uniprot_ids: list[str] = Field(
        default_factory=list,
        description="UniProt accessions of proteins in this pathway.",
    )
    provenance: ProvenanceReference | None = Field(None, description="Citation to Reactome record.")

    @field_validator("reactome_id")
    @classmethod
    def validate_reactome_id(cls, v: str) -> str:
        """Validate Reactome stable identifier format."""
        pattern = r"^R-[A-Z]+-\d+$"
        if not re.match(pattern, v.strip()):
            raise ValueError(
                f"Invalid Reactome ID format: '{v}'. Expected format: 'R-HSA-XXXXXX'."
            )
        return v.strip()
