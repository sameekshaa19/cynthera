"""Drug entity — canonical representation of a therapeutic compound.

Reference: 02_DOMAIN_MODEL.md §4.3
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator
from backend.core.value_objects.identifier import ResolvedIdentifierSet


class Drug(BaseModel):
    """Canonical representation of an active chemical compound or biological agent.

    Immutable once constructed. Created by the IdentifierResolutionService.

    Attributes:
        id: Internal UUID for this Drug instance.
        name: Common name of the drug (e.g., 'Sildenafil').
        identifiers: Resolved cross-database identifier set.
        approved_indications: Known approved therapeutic indications.
        molecular_formula: Chemical molecular formula (if available).
        smiles: SMILES notation string (if available).
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    name: str = Field(..., min_length=1, description="Drug common name.")
    identifiers: ResolvedIdentifierSet = Field(..., description="Resolved cross-database identifiers.")
    approved_indications: list[str] = Field(
        default_factory=list,
        description="Known approved therapeutic indications.",
    )
    molecular_formula: str | None = Field(None, description="Chemical molecular formula.")
    smiles: str | None = Field(None, description="SMILES notation.")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        """Validate that the name is a non-empty string."""
        if not v.strip():
            raise ValueError("Drug name must be a non-empty string.")
        return v.strip()

    def has_identifier(self, namespace: str) -> bool:
        """Check whether a specific identifier namespace is resolved.

        Args:
            namespace: The identifier taxonomy to check (e.g., 'chembl').

        Returns:
            True if the identifier exists in the resolved set.
        """
        return self.identifiers.get(namespace) is not None

    @property
    def chembl_id(self) -> str | None:
        """Convenience property for ChEMBL ID."""
        return self.identifiers.chembl_id

    @property
    def pubchem_cid(self) -> str | None:
        """Convenience property for PubChem CID."""
        return self.identifiers.pubchem_cid
