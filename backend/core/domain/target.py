"""Target entity — drug-protein interaction relationship.

Reference: 02_DOMAIN_MODEL.md §4.4
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator

from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference


class Target(BaseModel):
    """Relationship entity documenting a drug's interaction with a specific protein.

    Decouples compound-target affinity and interaction metadata from physical
    protein properties. Created by the Normalization Layer.

    A Target relationship is ignored if measured binding affinity value falls
    below a reliability threshold (configurable, default 10_000 nM for Ki/IC50/Kd).

    Attributes:
        id: Internal UUID.
        drug_chembl_id: ChEMBL ID of the drug entity.
        protein_uniprot: UniProt accession of the target protein.
        affinity_nm: Measured binding affinity in nanomolar (Ki, IC50, or Kd).
        affinity_type: Measurement type ('Ki', 'IC50', 'Kd', 'percent_inhibition').
        mechanism: Interaction classification ('INHIBITOR', 'AGONIST', 'ANTAGONIST', etc.).
        erw: Evidence Reliability Weight for this target relationship.
        provenance: Citation to the supporting database record.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    drug_chembl_id: str = Field(..., description="ChEMBL ID of the drug.")
    protein_uniprot: str = Field(..., description="UniProt accession of the target protein.")
    affinity_nm: float = Field(
        ...,
        gt=0,
        description="Measured binding affinity in nanomolar.",
    )
    affinity_type: str = Field(
        ...,
        description="Measurement type: 'Ki', 'IC50', 'Kd', or 'percent_inhibition'.",
    )
    mechanism: str = Field(
        ...,
        description="Interaction classification (e.g., 'INHIBITOR', 'AGONIST').",
    )
    erw: ERW = Field(..., description="Evidence Reliability Weight for this target relationship.")
    provenance: ProvenanceReference = Field(..., description="Citation to supporting database record.")

    @field_validator("affinity_type")
    @classmethod
    def validate_affinity_type(cls, v: str) -> str:
        """Validate that affinity type is a recognized measurement."""
        valid = {"Ki", "IC50", "Kd", "percent_inhibition", "EC50", "Potency"}
        val = v.strip()
        if val not in valid:
            raise ValueError(f"Affinity type '{val}' is not recognized. Valid types: {valid}.")
        return val
