"""Protein entity — physiological polypeptide performing cellular functions.

Reference: 02_DOMAIN_MODEL.md §4.5
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator


class Protein(BaseModel):
    """A physiological polypeptide that performs cellular biological functions.

    Immutable. Created by the Normalization Layer (mapping UniProt target details).

    Attributes:
        id: Internal UUID.
        uniprot_accession: UniProt accession number (e.g., 'O76074'). Required.
        gene_symbol: HGNC gene symbol in uppercase (e.g., 'PDE5A'). Required.
        name: Full protein name.
        organism: Source organism (e.g., 'Homo sapiens').
        pathway_ids: Reactome pathway IDs this protein participates in.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    uniprot_accession: str = Field(..., description="UniProt accession (e.g., 'O76074').")
    gene_symbol: str = Field(..., description="HGNC gene symbol in uppercase (e.g., 'PDE5A').")
    name: str = Field(..., description="Full protein name.")
    organism: str = Field(default="Homo sapiens", description="Source organism.")
    pathway_ids: list[str] = Field(
        default_factory=list,
        description="Reactome pathway IDs this protein participates in.",
    )

    @field_validator("uniprot_accession")
    @classmethod
    def validate_uniprot(cls, v: str) -> str:
        """Validate UniProt accession format (e.g., O76074, P12345)."""
        import re
        pattern = r"^[A-Z][0-9][A-Z0-9]{3}[0-9]$|^[A-Z][0-9][A-Z0-9]{3}[0-9]-[0-9]+$|^[A-Z0-9]{6,10}$"
        if not re.match(pattern, v.strip()):
            raise ValueError(f"Invalid UniProt accession format: '{v}'.")
        return v.strip()

    @field_validator("gene_symbol")
    @classmethod
    def validate_gene_symbol(cls, v: str) -> str:
        """Validate that gene symbol is uppercase."""
        return v.strip().upper()
