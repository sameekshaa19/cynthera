"""Evidence entity — empirical observation or literature record.

Reference: 02_DOMAIN_MODEL.md §4.11
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator

from backend.core.enums.evidence_type import EvidenceType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference


class Evidence(BaseModel):
    """An empirical observation, assay data, or literature record retrieved from a Source.

    Immutable. Created by the Normalization Layer.
    ERW must be between 0.15 and 1.00.
    Must contain a valid citation key (DOI, PMID, or NCT ID).

    Attributes:
        id: Internal UUID for this evidence record.
        evidence_type: Empirical origin classification (EvidenceType enum).
        erw: Evidence Reliability Weight [0.15, 1.00].
        citation_key: DOI, PMID, or NCT ID. Required.
        title: Title of the publication or record.
        abstract: Abstract text (for literature records).
        provenance: Full source provenance reference.
        drug_chembl_id: ChEMBL ID of the associated drug.
        disease_identifier: MeSH or UMLS identifier of the disease.
        target_uniprot: UniProt accession if this evidence relates to a specific protein.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    evidence_type: EvidenceType = Field(..., description="Empirical origin classification.")
    erw: ERW = Field(..., description="Evidence Reliability Weight [0.15, 1.00].")
    citation_key: str = Field(
        ...,
        min_length=1,
        description="DOI, PMID, or NCT ID identifying this record.",
    )
    title: str | None = Field(None, description="Publication or record title.")
    abstract: str | None = Field(None, description="Abstract text for literature records.")
    provenance: ProvenanceReference = Field(..., description="Full source provenance reference.")
    drug_chembl_id: str | None = Field(None, description="Associated drug ChEMBL ID.")
    disease_identifier: str | None = Field(None, description="Associated disease identifier.")
    target_uniprot: str | None = Field(None, description="Associated target UniProt accession.")

    @field_validator("citation_key")
    @classmethod
    def citation_key_not_empty(cls, v: str) -> str:
        """Validate that the citation key is non-empty."""
        if not v.strip():
            raise ValueError("Evidence citation_key must be a non-empty string.")
        return v.strip()
