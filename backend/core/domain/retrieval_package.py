"""RetrievalPackage entity — sealed output of the retrieval subsystem.

Reference: 01_SYSTEM_ARCHITECTURE.md §5, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.gene import Gene
from backend.core.domain.pathway import Pathway
from backend.core.domain.evidence import Evidence
from backend.core.domain.clinical_trial import ClinicalTrial


class RetrievalPackage(BaseModel):
    """Sealed, immutable output of the retrieval pipeline.

    Produced by the MasterOrchestrator after all sources have been queried,
    normalized, and quality-gated. Once sealed, it is read-only.

    Attributes:
        id: Internal UUID.
        hypothesis_id: UUID of the owning Hypothesis.
        drug: Resolved Drug entity.
        disease: Resolved Disease entity.
        targets: All drug-protein Target relationships retrieved.
        proteins: All Protein entities referenced by targets.
        genes: All Gene entities associated with targets.
        pathways: All Pathway entities retrieved.
        evidence_records: All Evidence records retrieved.
        clinical_trials: All ClinicalTrial records retrieved.
        retrieval_confidence: Overall confidence in data completeness ('HIGH', 'MEDIUM', 'LOW').
        sources_queried: Names of all data sources successfully queried.
        sources_failed: Names of all data sources that failed during retrieval.
        sealed_at: UTC timestamp when this package was sealed.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Package unique identifier.")
    hypothesis_id: uuid.UUID = Field(..., description="UUID of the owning Hypothesis.")
    drug: Drug = Field(..., description="Resolved Drug entity.")
    disease: Disease = Field(..., description="Resolved Disease entity.")
    targets: list[Target] = Field(default_factory=list, description="Drug-protein Target relationships.")
    proteins: list[Protein] = Field(default_factory=list, description="Protein entities.")
    genes: list[Gene] = Field(default_factory=list, description="Gene entities.")
    pathways: list[Pathway] = Field(default_factory=list, description="Pathway entities.")
    evidence_records: list[Evidence] = Field(default_factory=list, description="Evidence records.")
    clinical_trials: list[ClinicalTrial] = Field(default_factory=list, description="ClinicalTrial records.")
    retrieval_confidence: str = Field(
        default="MEDIUM",
        pattern="^(HIGH|MEDIUM|LOW)$",
        description="Overall data completeness confidence.",
    )
    sources_queried: list[str] = Field(default_factory=list, description="Successfully queried sources.")
    sources_failed: list[str] = Field(default_factory=list, description="Failed data sources.")
    sealed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC sealing timestamp.")

    @property
    def literature_evidence(self) -> list[Evidence]:
        """Filter to evidence records with abstract text (for claim extraction)."""
        from backend.core.enums.evidence_type import EvidenceType
        return [
            e for e in self.evidence_records
            if e.evidence_type in (
                EvidenceType.META_ANALYSIS,
                EvidenceType.RCT,
                EvidenceType.OBSERVATIONAL,
            ) and e.abstract
        ]
