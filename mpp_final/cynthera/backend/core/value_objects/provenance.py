"""ProvenanceReference — source citation and provenance tracking.

Reference: 02_DOMAIN_MODEL.md §4.10, SPECIFICATION.md §5.1
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ProvenanceReference(BaseModel):
    """Immutable reference to the external source of a claim or evidence record.

    Every entity, node, relation, or value in the system must maintain a
    ProvenanceReference so that its exact origin is programmatically traceable.

    Attributes:
        source_name: Human-readable name of the data source (e.g., 'ChEMBL', 'PubMed').
        source_version: Database release version (e.g., 'v33', '2024-01-01').
        record_id: Unique identifier within the source (e.g., PMID, ChEMBL target ID).
        url: Persistent URI to the original record.
        retrieved_at: UTC timestamp when this record was fetched.
    """

    model_config = {"frozen": True}

    source_name: str = Field(..., description="Human-readable data source name.")
    source_version: str = Field(..., description="Database release version.")
    record_id: str = Field(..., description="Unique identifier within the source.")
    url: str | None = Field(None, description="Persistent URI to the original record.")
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when this record was fetched.",
    )
