"""Gene entity — hereditary DNA unit encoding functional RNA/protein products.

Reference: 02_DOMAIN_MODEL.md §4.6
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field, field_validator


class Gene(BaseModel):
    """A hereditary unit of DNA encoding a functional RNA or protein product.

    Bridges proteins to disease associations via DisGeNET, HGNC, and NCBI Gene.

    Attributes:
        id: Internal UUID.
        hgnc_symbol: HGNC-approved gene symbol (e.g., 'PDE5A'). Required.
        ncbi_gene_id: NCBI Gene integer ID (e.g., 8654). Required.
        name: Full gene name.
        protein_ids: UniProt accessions of encoded proteins.
        disease_associations: DisGeNET gene-disease association scores keyed by disease identifier.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    hgnc_symbol: str = Field(..., description="HGNC-approved gene symbol (e.g., 'PDE5A').")
    ncbi_gene_id: int = Field(..., gt=0, description="NCBI Gene integer ID (e.g., 8654).")
    name: str = Field(..., description="Full gene name.")
    protein_ids: list[str] = Field(
        default_factory=list,
        description="UniProt accessions of proteins encoded by this gene.",
    )
    disease_associations: dict[str, float] = Field(
        default_factory=dict,
        description="DisGeNET disease association scores keyed by disease identifier.",
    )

    @field_validator("hgnc_symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate HGNC symbol is non-empty uppercase."""
        if not v.strip():
            raise ValueError("HGNC gene symbol must be non-empty.")
        return v.strip().upper()
