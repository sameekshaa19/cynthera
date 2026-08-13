"""CandidateMechanism domain entity — represents a discovered, candidate biological mechanism.

Models the candidate biological mechanisms connecting Drug → Target → Biological Process / Pathway → Disease.
Each candidate mechanism contains detailed hop-by-hop evidence, status ratings, and direct source links.
"""
from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, Field

from backend.core.value_objects.source_url_builder import EvidenceLink


class MechanismHop(BaseModel):
    """A single validated or unverified hop in a candidate mechanism chain."""

    model_config = {"frozen": True}

    from_node: str = Field(..., description="Source node name and label (e.g., 'Drug: Dapagliflozin').")
    to_node: str = Field(..., description="Target node name and label (e.g., 'Target: SLC5A2').")
    predicate: str = Field(..., description="Biological interaction predicate (e.g., 'INHIBITOR', 'PARTICIPATES_IN').")
    status: str = Field(default="VALID", description="'VALID' | 'UNVERIFIED' | 'REJECTED'")
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    source_database: str = Field(..., description="Database source (e.g., 'ChEMBL', 'Reactome', 'Open Targets').")
    provenance_note: str = Field(default="", description="Detailed rationale or measurement note.")
    links: list[EvidenceLink] = Field(default_factory=list, description="Clickable URL links for this hop.")


class CandidateMechanism(BaseModel):
    """A complete candidate biological mechanism discovered between Drug and Disease."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_index: int = Field(default=1, description="Index of this candidate mechanism (1-based).")
    name: str = Field(..., description="Human-readable title (e.g., 'SLC5A2 inhibition → Renal Glucose Reabsorption').")
    support_level: str = Field(
        ...,
        description="Rating: 'STRONGLY_SUPPORTED' | 'MODERATELY_SUPPORTED' | 'WEAK_SPECULATIVE' | 'CONTRADICTED' | 'UNSUPPORTED'",
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary_chain: list[str] = Field(default_factory=list, description="Ordered chain strings (Drug → ... → Disease).")
    hops: list[MechanismHop] = Field(default_factory=list, description="Detailed hop-by-hop evidence breakdown.")
    literature_citations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Citations supporting this specific candidate mechanism with links.",
    )
    rationale: str = Field(default="", description="Scientific justification explaining why this mechanism is supported/rejected.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_index": self.candidate_index,
            "name": self.name,
            "support_level": self.support_level,
            "confidence_score": self.confidence_score,
            "summary_chain": self.summary_chain,
            "hops": [
                {
                    "from_node": h.from_node,
                    "to_node": h.to_node,
                    "predicate": h.predicate,
                    "status": h.status,
                    "evidence_strength": h.evidence_strength,
                    "source_database": h.source_database,
                    "provenance_note": h.provenance_note,
                    "links": [l.to_dict() for l in h.links],
                }
                for h in self.hops
            ],
            "literature_citations": self.literature_citations,
            "rationale": self.rationale,
        }
