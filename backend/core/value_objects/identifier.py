"""Identifier value objects — canonical cross-database identifier mapping.

Reference: 02_DOMAIN_MODEL.md §5 (future domain extensions), 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CanonicalIdentifier(BaseModel):
    """A single identifier in a specific taxonomy system.

    Attributes:
        namespace: The identifier system (e.g., 'chembl', 'pubchem', 'uniprot', 'mesh').
        value: The raw identifier string (e.g., 'CHEMBL941', 'O76074').
    """

    model_config = {"frozen": True}

    namespace: str = Field(..., description="Identifier taxonomy namespace (e.g., 'chembl', 'mesh').")
    value: str = Field(..., description="Raw identifier string value.")

    def __str__(self) -> str:
        return f"{self.namespace}:{self.value}"


class ResolvedIdentifierSet(BaseModel):
    """A complete set of cross-referenced identifiers for a single biological entity.

    Created by the IdentifierResolutionService. Contains all resolved IDs
    across multiple taxonomy systems for a drug or disease entity.

    Attributes:
        entity_name: The original input name string.
        entity_type: One of 'drug' or 'disease'.
        identifiers: All resolved canonical identifiers across namespaces.
        resolution_confidence: Float [0.0, 1.0] indicating resolution quality.
    """

    model_config = {"frozen": True}

    entity_name: str = Field(..., description="Original input name string.")
    entity_type: str = Field(..., pattern="^(drug|disease)$", description="Either 'drug' or 'disease'.")
    identifiers: list[CanonicalIdentifier] = Field(
        default_factory=list,
        description="All resolved canonical identifiers.",
    )
    resolution_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in identifier resolution quality.",
    )

    def get(self, namespace: str) -> str | None:
        """Retrieve an identifier value by namespace.

        Args:
            namespace: The identifier taxonomy (e.g., 'chembl', 'uniprot').

        Returns:
            The identifier value string, or None if not found.
        """
        for ident in self.identifiers:
            if ident.namespace == namespace:
                return ident.value
        return None

    @property
    def chembl_id(self) -> str | None:
        """Convenience accessor for ChEMBL ID."""
        return self.get("chembl")

    @property
    def pubchem_cid(self) -> str | None:
        """Convenience accessor for PubChem CID."""
        return self.get("pubchem")

    @property
    def mesh_id(self) -> str | None:
        """Convenience accessor for MeSH ID."""
        return self.get("mesh")

    @property
    def uniprot_id(self) -> str | None:
        """Convenience accessor for UniProt accession."""
        return self.get("uniprot")
