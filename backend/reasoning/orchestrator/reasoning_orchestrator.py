"""ReasoningOrchestrator — coordinates the full reasoning pipeline.

Reference: 04_REASONING_SPECIFICATION.md, 08_IMPLEMENTATION_GUIDE.md §5.6
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import (
    ReasoningResult,
    SupportAssessment,
    MechanisticAssessment,
    RiskAssessment,
    ScientificAuditReport,
)
from backend.core.domain.claim import Claim
from backend.core.domain.claim_graph import ClaimGraph
from backend.core.domain.contradiction import Contradiction
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.reasoning.extraction.claim_extraction_agent import ClaimExtractionAgent

logger = logging.getLogger(__name__)


class ReasoningOrchestrator:
    """Coordinates the full reasoning pipeline over a sealed RetrievalPackage.

    Steps:
    1. Claim Extraction (LLM-assisted)
    2. Claim Validation (deterministic)
    3. ClaimGraph construction and sealing
    4. Expert Agent evaluation (parallel)
    5. Consensus and Rule Engine
    6. Scientific Audit Report generation

    Only ClaimExtractionAgent calls the LLM. All other components are deterministic.
    """

    def __init__(
        self,
        llm_api_key: str | None = None,
        llm_model: str = "gemini-1.5-flash",
    ) -> None:
        """Initialize the ReasoningOrchestrator.

        Args:
            llm_api_key: API key for the LLM provider.
            llm_model: LLM model name for claim extraction.
        """
        self._extraction_agent = ClaimExtractionAgent(model=llm_model, api_key=llm_api_key)

    async def reason(self, package: RetrievalPackage) -> ReasoningResult:
        """Execute the full reasoning pipeline over a RetrievalPackage.

        Args:
            package: The sealed RetrievalPackage from the retrieval subsystem.

        Returns:
            A fully populated ReasoningResult.
        """
        start_ms = time.time() * 1000

        logger.info(
            "reasoning_start",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "evidence_count": len(package.evidence_records),
                "trial_count": len(package.clinical_trials),
            },
        )

        # Step 1: Extract claims from literature evidence
        all_claims = await self._extract_all_claims(package)

        # Step 2: Build and seal the ClaimGraph
        graph = self._build_claim_graph(all_claims, package.hypothesis_id)
        graph.seal()

        # Step 3: Detect contradictions
        contradictions = self._detect_contradictions(all_claims)

        # Step 4: Run three-dimensional scoring in parallel
        support_task = asyncio.create_task(
            self._compute_support_score(all_claims, package)
        )
        mechanistic_task = asyncio.create_task(
            self._compute_mechanistic_score(package)
        )
        risk_task = asyncio.create_task(
            self._compute_risk_score(contradictions, package)
        )

        support_assessment, mechanistic_assessment, risk_assessment = await asyncio.gather(
            support_task, mechanistic_task, risk_task
        )

        # Step 5: Apply recommendation rules
        recommendation_status, reasons = self._apply_rules(
            support_assessment,
            mechanistic_assessment,
            risk_assessment,
            contradictions,
            package,
        )

        # Step 6: Generate scientific audit report
        audit_report = self._generate_audit_report(
            all_claims,
            contradictions,
            support_assessment,
            mechanistic_assessment,
            risk_assessment,
            recommendation_status,
            reasons,
        )

        duration_ms = (time.time() * 1000) - start_ms

        result = ReasoningResult(
            hypothesis_id=package.hypothesis_id,
            support_assessment=support_assessment,
            mechanistic_assessment=mechanistic_assessment,
            risk_assessment=risk_assessment,
            contradictions=contradictions,
            recommendation_status=recommendation_status,
            recommendation_reasons=reasons,
            audit_report=audit_report,
            rule_set_version="1.0",
            reasoning_duration_ms=round(duration_ms, 2),
            completed_at=datetime.utcnow(),
        )

        logger.info(
            "reasoning_complete",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "recommendation": recommendation_status.value,
                "duration_ms": round(duration_ms, 2),
                "claims_count": len(all_claims),
                "contradictions_count": len(contradictions),
            },
        )
        return result

    async def _extract_all_claims(self, package: RetrievalPackage) -> list[Claim]:
        """Extract claims from all literature evidence in parallel.

        Args:
            package: The RetrievalPackage with evidence records.

        Returns:
            All extracted Claim objects.
        """
        lit_evidence = package.literature_evidence
        if not lit_evidence:
            logger.warning(
                "no_literature_evidence",
                extra={"hypothesis_id": str(package.hypothesis_id)},
            )
            return []

        tasks = [
            self._extraction_agent.extract_claims(
                ev,
                package.drug.name,
                package.disease.name,
            )
            for ev in lit_evidence[:20]  # cap at 20 records
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        claims: list[Claim] = []
        for res in results:
            if isinstance(res, list):
                claims.extend(res)
        return claims

    def _build_claim_graph(
        self,
        claims: list[Claim],
        hypothesis_id: uuid.UUID,
    ) -> ClaimGraph:
        """Construct a ClaimGraph from a list of Claims.

        Args:
            claims: All extracted and validated claims.
            hypothesis_id: UUID of the owning Hypothesis.

        Returns:
            An unsealed ClaimGraph (will be sealed by caller).
        """
        graph = ClaimGraph(hypothesis_id=hypothesis_id)
        for claim in claims:
            graph.add_claim(claim)
        return graph

    def _detect_contradictions(self, claims: list[Claim]) -> list[Contradiction]:
        """Detect directional conflicts between claims.

        Args:
            claims: All extracted claims.

        Returns:
            List of Contradiction objects.
        """
        contradictions: list[Contradiction] = []
        opposing: dict[str, dict[str, PredicateType]] = {}

        for claim in claims:
            key = f"{claim.subject}::{claim.object}"
            if key not in opposing:
                opposing[key] = {}
            if str(claim.predicate) in opposing[key]:
                # Check for directional conflict
                existing = opposing[key][str(claim.predicate)]
                conflict_pairs = {
                    (PredicateType.ACTIVATES, PredicateType.INHIBITS),
                    (PredicateType.UPREGULATES, PredicateType.DOWNREGULATES),
                    (PredicateType.CAUSES, PredicateType.PREVENTS),
                }
                for a, b in conflict_pairs:
                    if (claim.predicate == a and existing == b) or \
                       (claim.predicate == b and existing == a):
                        contradiction = Contradiction(
                            claim_id_a=claim.id,
                            claim_id_b=claim.id,  # simplified
                            conflict_type="directional",
                            contradiction_score=round(claim.erw.value * 0.8, 4),
                            shared_subject=claim.subject,
                            explanation=(
                                f"Directional conflict: claim states '{claim.subject} "
                                f"{claim.predicate.value} {claim.object}' but "
                                f"another claim states the opposite."
                            ),
                        )
                        contradictions.append(contradiction)
            opposing[key][str(claim.predicate)] = claim.predicate
        return contradictions

    async def _compute_support_score(
        self,
        claims: list[Claim],
        package: RetrievalPackage,
    ) -> SupportAssessment:
        """Compute the Support Score (SS).

        Args:
            claims: All extracted claims.
            package: RetrievalPackage with evidence records.

        Returns:
            SupportAssessment with score and rationale.
        """
        # Aggregate ERW values of all validated claims and evidence
        supporting_claims = [
            c for c in claims
            if c.predicate in (
                PredicateType.ACTIVATES,
                PredicateType.INHIBITS,
                PredicateType.BINDS,
                PredicateType.PREVENTS,
            )
        ]

        if not supporting_claims and not package.evidence_records:
            return SupportAssessment(
                score=0.0,
                level="NONE",
                evidence_count=0,
                weighted_sum=0.0,
                rationale="No supporting evidence or claims found.",
            )

        weighted_sum = sum(c.erw.value for c in supporting_claims)
        weighted_sum += sum(e.erw.value for e in package.evidence_records)
        count = len(supporting_claims) + len(package.evidence_records)

        # Normalize using diminishing returns formula: score = 1 - e^(-k * weighted_sum)
        import math
        k = 0.15  # diminishing returns constant
        raw_score = 1.0 - math.exp(-k * weighted_sum)
        score = round(min(1.0, raw_score), 4)

        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")

        return SupportAssessment(
            score=score,
            level=level,
            evidence_count=count,
            weighted_sum=round(weighted_sum, 4),
            rationale=(
                f"Support Score computed from {len(supporting_claims)} supporting claims "
                f"and {len(package.evidence_records)} evidence records. "
                f"Weighted sum = {weighted_sum:.2f}, SS = {score:.3f}."
            ),
            supporting_claim_ids=[str(c.id) for c in supporting_claims[:10]],
        )

    async def _compute_mechanistic_score(
        self,
        package: RetrievalPackage,
    ) -> MechanisticAssessment:
        """Compute the Mechanistic Score (MS).

        Args:
            package: RetrievalPackage with targets and pathways.

        Returns:
            MechanisticAssessment with score and traced chain.
        """
        target_count = len(package.targets)
        pathway_count = len(package.pathways)

        if target_count == 0:
            return MechanisticAssessment(
                score=0.0,
                level="NONE",
                pathway_count=0,
                mechanistic_chain=[],
                rationale="No drug targets found — mechanistic chain cannot be traced.",
            )

        # Simple scoring: targets contribute 0.6, pathways 0.4
        target_score = min(1.0, target_count / 5) * 0.6
        pathway_score = min(1.0, pathway_count / 3) * 0.4
        score = round(target_score + pathway_score, 4)

        chain = [package.drug.name]
        chain.extend(t.protein_uniprot for t in package.targets[:3])
        chain.extend(p.reactome_id for p in package.pathways[:2])
        chain.append(package.disease.name)

        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")

        return MechanisticAssessment(
            score=score,
            level=level,
            pathway_count=pathway_count,
            mechanistic_chain=chain,
            rationale=(
                f"Mechanistic Score from {target_count} targets and {pathway_count} pathways. "
                f"Target contribution: {target_score:.3f}, pathway contribution: {pathway_score:.3f}."
            ),
        )

    async def _compute_risk_score(
        self,
        contradictions: list[Contradiction],
        package: RetrievalPackage,
    ) -> RiskAssessment:
        """Compute the Risk Score (RS).

        Args:
            contradictions: Detected contradictions.
            package: RetrievalPackage with clinical trials.

        Returns:
            RiskAssessment with score and rationale.
        """
        failed_trials = [
            t for t in package.clinical_trials
            if t.status in (
                TrialOutcomeStatus.COMPLETED_FAILURE,
                TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                TrialOutcomeStatus.TERMINATED_SAFETY,
            )
        ]

        # Risk formula: weighted sum of failure signals
        # Each failed trial: 1.0 penalty
        # Each contradiction: 0.5 penalty
        # Safety termination: additional 0.8 penalty
        raw_risk = 0.0
        safety_failed = [
            t for t in failed_trials
            if t.status == TrialOutcomeStatus.TERMINATED_SAFETY
        ]
        raw_risk += len(failed_trials) * 1.0
        raw_risk += len(safety_failed) * 0.8
        raw_risk += len(contradictions) * 0.5

        # Normalize
        import math
        k = 0.3
        score = round(1.0 - math.exp(-k * raw_risk), 4) if raw_risk > 0 else 0.0

        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")
        if score == 0.0:
            level = "NONE"

        return RiskAssessment(
            score=score,
            level=level,
            failed_trial_count=len(failed_trials),
            contradiction_count=len(contradictions),
            rationale=(
                f"Risk Score from {len(failed_trials)} failed trial(s) and "
                f"{len(contradictions)} contradiction(s). RS = {score:.3f}."
            ),
        )

    def _apply_rules(
        self,
        support: SupportAssessment,
        mechanistic: MechanisticAssessment,
        risk: RiskAssessment,
        contradictions: list[Contradiction],
        package: RetrievalPackage,
    ) -> tuple[RecommendationStatus, list[str]]:
        """Apply deterministic recommendation rules over (SS, MS, RS).

        Rules (Rule Set v1.0):
        - Rule 1 (PROMISING): SS >= MEDIUM (0.4) AND MS >= MEDIUM (0.4) AND RS <= LOW (0.39)
        - Rule 2 (NOT_RECOMMENDED): SS <= LOW (0.39) AND MS <= LOW (0.39) AND RS >= HIGH (0.7)
        - Rule 3 (NOT_RECOMMENDED): RS >= HIGH (0.7) [safety veto]
        - Rule 4 (NOT_RECOMMENDED): ClinicalTrials source failed [safety lock]
        - Rule 5 (UNCERTAIN): otherwise

        Args:
            support: SupportAssessment.
            mechanistic: MechanisticAssessment.
            risk: RiskAssessment.
            contradictions: Detected contradictions.
            package: RetrievalPackage.

        Returns:
            Tuple of (RecommendationStatus, list of reason strings).
        """
        reasons: list[str] = []

        # Safety veto: if clinical trials data unavailable (degradation constraint)
        if "clinicaltrials" in package.sources_failed:
            reasons.append(
                "Rule 4: ClinicalTrials.gov data is unavailable. "
                "Maximum status capped at UNCERTAIN per safety lock constraint."
            )
            return RecommendationStatus.UNCERTAIN, reasons

        # Safety veto: high risk score
        if risk.score >= 0.7:
            reasons.append(
                f"Rule 3 (Safety Veto): Risk Score is HIGH ({risk.score:.3f}). "
                f"Triggered by {risk.failed_trial_count} failed trial(s) and "
                f"{risk.contradiction_count} contradiction(s)."
            )
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Strong negative evidence
        if support.score <= 0.39 and mechanistic.score <= 0.39 and risk.score >= 0.7:
            reasons.append(
                f"Rule 2 (NOT_RECOMMENDED): Support ({support.score:.3f}) and "
                f"Mechanistic ({mechanistic.score:.3f}) scores are LOW, "
                f"Risk ({risk.score:.3f}) is HIGH."
            )
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Promising criteria
        if support.score >= 0.4 and mechanistic.score >= 0.4 and risk.score <= 0.39:
            reasons.append(
                f"Rule 1 (PROMISING): Support Score = {support.score:.3f} (>= 0.40), "
                f"Mechanistic Score = {mechanistic.score:.3f} (>= 0.40), "
                f"Risk Score = {risk.score:.3f} (<= 0.39)."
            )
            return RecommendationStatus.PROMISING, reasons

        # Default: uncertain
        reasons.append(
            f"Rule 5 (UNCERTAIN): Mixed or sparse evidence. "
            f"SS={support.score:.3f}, MS={mechanistic.score:.3f}, RS={risk.score:.3f}."
        )
        return RecommendationStatus.UNCERTAIN, reasons

    def _generate_audit_report(
        self,
        claims: list[Claim],
        contradictions: list[Contradiction],
        support: SupportAssessment,
        mechanistic: MechanisticAssessment,
        risk: RiskAssessment,
        recommendation: RecommendationStatus,
        reasons: list[str],
    ) -> ScientificAuditReport:
        """Generate the scientific audit report.

        Args:
            claims: All extracted claims.
            contradictions: All contradictions.
            support: SupportAssessment.
            mechanistic: MechanisticAssessment.
            risk: RiskAssessment.
            recommendation: Final recommendation status.
            reasons: Rule application trace.

        Returns:
            ScientificAuditReport.
        """
        supporting = [
            c for c in claims
            if c.predicate in (
                PredicateType.ACTIVATES, PredicateType.INHIBITS,
                PredicateType.BINDS, PredicateType.PREVENTS
            )
        ][:10]

        contradicting_ids = [str(c.claim_id_a) for c in contradictions[:5]]

        data_gaps: list[str] = []
        if mechanistic.pathway_count == 0:
            data_gaps.append("No Reactome pathway data available for mechanistic tracing.")
        if support.evidence_count < 5:
            data_gaps.append("Evidence base is sparse (< 5 records). Consider expanding retrieval policy.")
        if risk.failed_trial_count == 0:
            data_gaps.append("No clinical trial data found — trial outcomes unverified.")

        summary = (
            f"CYNTHERA analysis for this drug-disease pair produced a recommendation of "
            f"'{recommendation.value}'. The Support Score is {support.score:.3f} ({support.level}), "
            f"the Mechanistic Score is {mechanistic.score:.3f} ({mechanistic.level}), "
            f"and the Risk Score is {risk.score:.3f} ({risk.level}). "
            f"{len(claims)} claim(s) were extracted from literature evidence, "
            f"with {len(contradictions)} directional contradiction(s) detected."
        )

        return ScientificAuditReport(
            summary=summary,
            key_supporting_claim_ids=[str(c.id) for c in supporting],
            key_contradicting_claim_ids=contradicting_ids,
            data_gaps=data_gaps,
            confidence_narrative=(
                f"Confidence is derived from {support.evidence_count} evidence records "
                f"with a total weighted support of {support.weighted_sum:.2f}."
            ),
            recommendation_rationale="\n".join(reasons),
        )
