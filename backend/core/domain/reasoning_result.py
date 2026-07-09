"""ReasoningResult entity — complete output of the reasoning subsystem.

Reference: 04_REASONING_SPECIFICATION.md, 02_DOMAIN_MODEL.md §4.16, §4.17
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from backend.core.enums.recommendation import RecommendationStatus
from backend.core.domain.contradiction import Contradiction


class SupportAssessment(BaseModel):
    """Support Score assessment from the SupportAssessmentAgent.

    Attributes:
        score: Support Score (SS) float [0.0, 1.0].
        level: Categorical level ('HIGH', 'MEDIUM', 'LOW').
        evidence_count: Number of evidence records contributing to the score.
        weighted_sum: Sum of all ERW values contributing.
        rationale: Human-readable explanation.
        supporting_claim_ids: UUIDs of Claims contributing positively.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Support Score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NONE)$", description="Categorical level.")
    evidence_count: int = Field(default=0, ge=0)
    weighted_sum: float = Field(default=0.0, ge=0.0)
    rationale: str = Field(default="", description="Human-readable explanation.")
    supporting_claim_ids: list[str] = Field(default_factory=list)


class MechanisticAssessment(BaseModel):
    """Mechanistic Score assessment from the MechanisticExpertAgent.

    Attributes:
        score: Mechanistic Score (MS) float [0.0, 1.0].
        level: Categorical level ('HIGH', 'MEDIUM', 'LOW', 'NONE').
        pathway_count: Number of overlapping pathways traced.
        mechanistic_chain: List of nodes in the traced chain (Drug→Target→Pathway→Disease).
        rationale: Human-readable explanation.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Mechanistic Score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NONE)$", description="Categorical level.")
    pathway_count: int = Field(default=0, ge=0)
    mechanistic_chain: list[str] = Field(
        default_factory=list,
        description="Nodes in the mechanistic chain (Drug→Target→Pathway→Disease).",
    )
    rationale: str = Field(default="", description="Human-readable explanation.")


class RiskAssessment(BaseModel):
    """Risk Score assessment from the RiskAssessmentAgent.

    Attributes:
        score: Risk Score (RS) float [0.0, 1.0] where 1.0 = maximum risk.
        level: Categorical level ('HIGH', 'MEDIUM', 'LOW').
        failed_trial_count: Number of failed/terminated clinical trials found.
        contradiction_count: Number of contradictions detected.
        rationale: Human-readable explanation.
        risk_claim_ids: UUIDs of Claims contributing to risk.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Risk Score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NONE)$", description="Categorical level.")
    failed_trial_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    rationale: str = Field(default="", description="Human-readable explanation.")
    risk_claim_ids: list[str] = Field(default_factory=list)


class ScientificAuditReport(BaseModel):
    """Complete audit trail of the reasoning process.

    Attributes:
        summary: LLM-generated executive summary.
        key_supporting_claim_ids: Claim IDs supporting the recommendation.
        key_contradicting_claim_ids: Claim IDs contradicting the hypothesis.
        data_gaps: Identified gaps in evidence.
        confidence_narrative: Text explaining the confidence calculation.
        recommendation_rationale: Step-by-step rule application trace.
    """

    model_config = {"frozen": True}

    summary: str = Field(..., description="LLM-generated executive summary.")
    key_supporting_claim_ids: list[str] = Field(default_factory=list)
    key_contradicting_claim_ids: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    confidence_narrative: str = Field(default="")
    recommendation_rationale: str = Field(default="")


class ReasoningResult(BaseModel):
    """Complete output of the reasoning pipeline for a Hypothesis evaluation.

    Immutable. The final artifact produced by the ReasoningOrchestrator.

    Attributes:
        id: Internal UUID.
        hypothesis_id: UUID of the evaluated Hypothesis.
        support_assessment: Full SupportAssessmentAgent output.
        mechanistic_assessment: Full MechanisticExpertAgent output.
        risk_assessment: Full RiskAssessmentAgent output.
        contradictions: All Contradiction objects detected.
        recommendation_status: Final RecommendationStatus.
        recommendation_reasons: Ordered list of rule-based reasons.
        audit_report: Full ScientificAuditReport.
        rule_set_version: Version of the RuleEngine rule set used.
        reasoning_duration_ms: Total reasoning pipeline duration.
        completed_at: UTC timestamp of completion.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    hypothesis_id: uuid.UUID = Field(..., description="UUID of the evaluated Hypothesis.")
    support_assessment: SupportAssessment = Field(..., description="Support assessment output.")
    mechanistic_assessment: MechanisticAssessment = Field(..., description="Mechanistic assessment output.")
    risk_assessment: RiskAssessment = Field(..., description="Risk assessment output.")
    contradictions: list[Contradiction] = Field(default_factory=list, description="Detected contradictions.")
    recommendation_status: RecommendationStatus = Field(..., description="Final recommendation status.")
    recommendation_reasons: list[str] = Field(
        default_factory=list,
        description="Ordered list of rule-based reasons for the recommendation.",
    )
    audit_report: ScientificAuditReport = Field(..., description="Full scientific audit report.")
    rule_set_version: str = Field(default="1.0", description="RuleEngine rule set version used.")
    reasoning_duration_ms: float = Field(default=0.0, ge=0.0, description="Total reasoning duration ms.")
    completed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC completion timestamp.")
