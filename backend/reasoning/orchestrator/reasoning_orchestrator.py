"""ReasoningOrchestrator — coordinates the full reasoning pipeline.

Phase 2 Enhanced version integrating:
- PriorKnowledgeAgent (Step 0: prior knowledge context)
- ClinicalSafetyAgent (enhanced safety analysis)
- MultiHopReasoner (replaces simple mechanistic scoring)
- AdvancedConflictResolver (replaces simple contradiction detection)

Reference: 04_REASONING_SPECIFICATION.md, 08_IMPLEMENTATION_GUIDE.md §5.6
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from datetime import datetime
from typing import Any

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
from backend.reasoning.agents.clinical_safety_agent import ClinicalSafetyAgent, SafetyProfile
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeAgent, PriorKnowledgeContext
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner, MechanisticPath
from backend.reasoning.conflict.conflict_resolver import AdvancedConflictResolver, ConflictResolutionReport
from backend.infrastructure.knowledge.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class ReasoningOrchestrator:
    """Coordinates the full reasoning pipeline over a sealed RetrievalPackage.

    Steps:
    0. Prior Knowledge retrieval (KnowledgeStore semantic search)
    1. Claim Extraction (LLM-assisted)
    2. Claim Validation (deterministic)
    3. ClaimGraph construction and sealing
    4. Advanced Conflict Resolution (weighted multi-factor)
    5. Multi-hop Mechanistic Path Tracing
    6. Clinical Safety Analysis (enhanced)
    7. Expert Agent parallel scoring (SS / MS / RS)
    8. Consensus and Rule Engine
    9. Scientific Audit Report generation

    Only ClaimExtractionAgent calls the LLM. All other components are deterministic.
    """

    def __init__(
        self,
        llm_api_key: str | None = None,
        llm_model: str = "gemini-1.5-flash",
        db_path: str = "data/cynthera.db",
    ) -> None:
        """Initialize the ReasoningOrchestrator.

        Args:
            llm_api_key: API key for the LLM provider.
            llm_model: LLM model name for claim extraction.
            db_path: Path to SQLite DB for KnowledgeStore.
        """
        self._extraction_agent = ClaimExtractionAgent(model=llm_model, api_key=llm_api_key)
        # Phase 2: Shared KnowledgeStore (seeded on first use)
        self._knowledge_store = KnowledgeStore(db_path=db_path)
        self._prior_knowledge_agent = PriorKnowledgeAgent(
            knowledge_store=self._knowledge_store
        )
        self._safety_agent = ClinicalSafetyAgent()
        self._multi_hop_reasoner = MultiHopReasoner()
        self._conflict_resolver = AdvancedConflictResolver()

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

        # ── Step 0: Prior Knowledge ──────────────────────────────────────
        prior_ctx = self._prior_knowledge_agent.retrieve(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
        )

        # ── Step 1: Extract claims from literature evidence ──────────────
        all_claims = await self._extract_all_claims(package)

        # ── Step 2: Build and seal the ClaimGraph ───────────────────────
        graph = self._build_claim_graph(all_claims, package.hypothesis_id)
        graph.seal()

        # ── Step 3: Advanced Conflict Resolution ─────────────────────────
        conflict_report = self._conflict_resolver.resolve(all_claims)
        contradictions = conflict_report.contradictions

        # ── Step 4: Multi-hop Mechanistic Path Tracing ───────────────────
        mechanistic_paths = self._multi_hop_reasoner.trace_paths(package)

        # ── Step 5: Clinical Safety Analysis ────────────────────────────
        safety_profile = self._safety_agent.analyze(package)

        # ── Step 6: Run three-dimensional scoring in parallel ────────────
        support_task = asyncio.create_task(
            self._compute_support_score(all_claims, package, prior_ctx)
        )
        mechanistic_task = asyncio.create_task(
            self._compute_mechanistic_score(package, mechanistic_paths, prior_ctx)
        )
        risk_task = asyncio.create_task(
            self._compute_risk_score(contradictions, package, safety_profile, conflict_report)
        )

        support_assessment, mechanistic_assessment, risk_assessment = await asyncio.gather(
            support_task, mechanistic_task, risk_task
        )

        # ── Step 7: Apply recommendation rules ──────────────────────────
        recommendation_status, reasons = self._apply_rules(
            support_assessment,
            mechanistic_assessment,
            risk_assessment,
            contradictions,
            package,
            safety_profile,
        )

        # ── Step 8: Generate scientific audit report ─────────────────────
        audit_report = self._generate_audit_report(
            all_claims=all_claims,
            contradictions=contradictions,
            support=support_assessment,
            mechanistic=mechanistic_assessment,
            risk=risk_assessment,
            recommendation=recommendation_status,
            reasons=reasons,
            prior_ctx=prior_ctx,
            safety_profile=safety_profile,
            mechanistic_paths=mechanistic_paths,
            conflict_report=conflict_report,
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
            rule_set_version="2.0",  # Phase 2 rule set
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
                "mechanistic_paths": len(mechanistic_paths),
                "safety_grade": safety_profile.overall_safety_grade,
                "prior_knowledge": prior_ctx.has_established_precedent,
            },
        )
        return result

    # ─────────────────────────────────────────────
    # Step 1: Claim Extraction
    # ─────────────────────────────────────────────

    async def _extract_all_claims(self, package: RetrievalPackage) -> list[Claim]:
        """Extract claims from all literature evidence in parallel."""
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

    # ─────────────────────────────────────────────
    # Step 2: ClaimGraph
    # ─────────────────────────────────────────────

    def _build_claim_graph(
        self, claims: list[Claim], hypothesis_id: uuid.UUID
    ) -> ClaimGraph:
        """Construct a ClaimGraph from a list of Claims."""
        graph = ClaimGraph(hypothesis_id=hypothesis_id)
        for claim in claims:
            graph.add_claim(claim)
        return graph

    # ─────────────────────────────────────────────
    # Step 6: Three-Dimensional Scoring
    # ─────────────────────────────────────────────

    async def _compute_support_score(
        self,
        claims: list[Claim],
        package: RetrievalPackage,
        prior_ctx: PriorKnowledgeContext,
    ) -> SupportAssessment:
        """Compute the Support Score (SS) with prior knowledge boost."""
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
            # Apply prior knowledge boost even with no evidence
            if prior_ctx.evidence_boost > 0:
                score = round(min(0.4, prior_ctx.evidence_boost), 4)
                return SupportAssessment(
                    score=score,
                    level="LOW" if score < 0.4 else "MEDIUM",
                    evidence_count=0,
                    weighted_sum=0.0,
                    rationale=(
                        f"No direct evidence found, but prior knowledge provides a boost "
                        f"of {prior_ctx.evidence_boost:.3f}. {prior_ctx.narrative}"
                    ),
                )
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
        k = 0.15
        raw_score = 1.0 - math.exp(-k * weighted_sum)

        # Apply prior knowledge boost
        raw_score = raw_score + prior_ctx.evidence_boost * (1.0 - raw_score)
        score = round(min(1.0, raw_score), 4)
        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")

        prior_note = (
            f" Prior knowledge boost applied: {prior_ctx.evidence_boost:+.3f}."
            if prior_ctx.evidence_boost != 0 else ""
        )

        return SupportAssessment(
            score=score,
            level=level,
            evidence_count=count,
            weighted_sum=round(weighted_sum, 4),
            rationale=(
                f"Support Score from {len(supporting_claims)} supporting claims "
                f"and {len(package.evidence_records)} evidence records. "
                f"Weighted sum = {weighted_sum:.2f}, SS = {score:.3f}.{prior_note}"
            ),
            supporting_claim_ids=[str(c.id) for c in supporting_claims[:10]],
        )

    async def _compute_mechanistic_score(
        self,
        package: RetrievalPackage,
        paths: list[MechanisticPath],
        prior_ctx: PriorKnowledgeContext,
    ) -> MechanisticAssessment:
        """Compute the Mechanistic Score (MS) from multi-hop paths."""
        target_count = len(package.targets)
        pathway_count = len(package.pathways)

        if target_count == 0 and not paths:
            return MechanisticAssessment(
                score=0.0,
                level="NONE",
                pathway_count=0,
                mechanistic_chain=[],
                rationale="No drug targets found — mechanistic chain cannot be traced.",
            )

        # Use multi-hop reasoner score if paths available
        if paths:
            ms_from_paths = self._multi_hop_reasoner.compute_mechanistic_score(paths)
        else:
            # Fallback to simple scoring
            target_score = min(1.0, target_count / 5) * 0.6
            pathway_score = min(1.0, pathway_count / 3) * 0.4
            ms_from_paths = target_score + pathway_score

        # Apply prior knowledge mechanistic hints
        if prior_ctx.mechanistic_hints and ms_from_paths < 0.9:
            hint_boost = min(0.1, len(prior_ctx.mechanistic_hints) * 0.03)
            ms_from_paths = min(1.0, ms_from_paths + hint_boost)

        score = round(min(1.0, ms_from_paths), 4)
        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")

        # Use best path chain for display
        if paths:
            best_path = paths[0]
            chain = best_path.to_chain()
            path_type = best_path.path_type
        else:
            # Simple chain from package data
            chain = [f"Drug: {package.drug.name}"]
            for t in package.targets[:3]:
                chain.append(f"Target: {t.protein_uniprot or t.name}")
            for pw in package.pathways[:2]:
                chain.append(f"Pathway: {pw.name} ({pw.reactome_id})")
            chain.append(f"Disease: {package.disease.name}")
            path_type = "DIRECT"

        paths_summary = (
            f"{len(paths)} mechanistic path(s) traced ({path_type} to "
            f"{paths[-1].path_type if len(paths) > 1 else path_type}). "
            if paths else "No multi-hop paths traced. "
        )

        return MechanisticAssessment(
            score=score,
            level=level,
            pathway_count=pathway_count,
            mechanistic_chain=chain,
            rationale=(
                f"Mechanistic Score from {target_count} target(s) and {pathway_count} pathway(s). "
                f"{paths_summary}MS = {score:.3f}."
            ),
        )

    async def _compute_risk_score(
        self,
        contradictions: list[Contradiction],
        package: RetrievalPackage,
        safety_profile: SafetyProfile,
        conflict_report: ConflictResolutionReport,
    ) -> RiskAssessment:
        """Compute the Risk Score (RS) enhanced with safety profile data."""
        failed_trials = [
            t for t in package.clinical_trials
            if t.status in (
                TrialOutcomeStatus.COMPLETED_FAILURE,
                TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                TrialOutcomeStatus.TERMINATED_SAFETY,
            )
        ]

        # Phase 2 enhanced risk formula incorporating safety profile
        raw_risk = 0.0
        safety_failed = [
            t for t in failed_trials
            if t.status == TrialOutcomeStatus.TERMINATED_SAFETY
        ]
        raw_risk += len(failed_trials) * 1.0
        raw_risk += len(safety_failed) * 0.8
        raw_risk += conflict_report.net_conflict_score * len(contradictions) * 0.5

        # Safety grade penalty
        grade_penalty = {"D": 2.0, "C": 0.8, "B": 0.2, "A": 0.0}.get(
            safety_profile.overall_safety_grade, 0.5
        )
        raw_risk += grade_penalty

        # Boxed warning penalty
        if safety_profile.has_boxed_warning:
            raw_risk += 1.5

        k = 0.3
        score = round(1.0 - math.exp(-k * raw_risk), 4) if raw_risk > 0 else 0.0
        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")
        if score == 0.0:
            level = "NONE"

        safety_note = (
            f" Safety grade: {safety_profile.overall_safety_grade}"
            f"{'(⚠️ boxed warning)' if safety_profile.has_boxed_warning else ''}."
        )

        return RiskAssessment(
            score=score,
            level=level,
            failed_trial_count=len(failed_trials),
            contradiction_count=len(contradictions),
            rationale=(
                f"Risk Score from {len(failed_trials)} failed trial(s) and "
                f"{len(contradictions)} contradiction(s) "
                f"(net conflict score: {conflict_report.net_conflict_score:.3f}).{safety_note} "
                f"RS = {score:.3f}."
            ),
        )

    # ─────────────────────────────────────────────
    # Step 7: Rule Engine
    # ─────────────────────────────────────────────

    def _apply_rules(
        self,
        support: SupportAssessment,
        mechanistic: MechanisticAssessment,
        risk: RiskAssessment,
        contradictions: list[Contradiction],
        package: RetrievalPackage,
        safety_profile: SafetyProfile,
    ) -> tuple[RecommendationStatus, list[str]]:
        """Apply deterministic recommendation rules over (SS, MS, RS).

        Rule Set v2.0:
        - Rule 0 (SAFETY_VETO): Boxed warning + HIGH risk → NOT_RECOMMENDED
        - Rule 1 (PROMISING): SS >= MEDIUM AND MS >= MEDIUM AND RS <= LOW
        - Rule 2 (NOT_RECOMMENDED): SS <= LOW AND MS <= LOW AND RS >= HIGH
        - Rule 3 (NOT_RECOMMENDED): RS >= HIGH (safety veto)
        - Rule 4 (NOT_RECOMMENDED): ClinicalTrials source failed (safety lock)
        - Rule 5 (UNCERTAIN): otherwise

        Args:
            support: SupportAssessment.
            mechanistic: MechanisticAssessment.
            risk: RiskAssessment.
            contradictions: Detected contradictions.
            package: RetrievalPackage.
            safety_profile: ClinicalSafetyAgent output.

        Returns:
            Tuple of (RecommendationStatus, list of reason strings).
        """
        reasons: list[str] = []

        # Rule 0: Safety veto — boxed warning with high risk
        if safety_profile.has_boxed_warning and risk.score >= 0.6:
            reasons.append(
                f"Rule 0 (SAFETY VETO): Boxed warning detected AND Risk Score is "
                f"{risk.score:.3f}. Safety grade: {safety_profile.overall_safety_grade}. "
                "NOT RECOMMENDED due to high safety concern."
            )
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Rule 4: Safety lock — clinical trials data unavailable
        if "clinicaltrials" in package.sources_failed:
            reasons.append(
                "Rule 4: ClinicalTrials.gov data is unavailable. "
                "Maximum status capped at UNCERTAIN per safety lock constraint."
            )
            return RecommendationStatus.UNCERTAIN, reasons

        # Rule 3: Safety veto — high risk score
        if risk.score >= 0.7:
            reasons.append(
                f"Rule 3 (Safety Veto): Risk Score is HIGH ({risk.score:.3f}). "
                f"Triggered by {risk.failed_trial_count} failed trial(s) and "
                f"{risk.contradiction_count} contradiction(s). "
                f"Safety grade: {safety_profile.overall_safety_grade}."
            )
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Rule 2: Strong negative evidence
        if support.score <= 0.39 and mechanistic.score <= 0.39 and risk.score >= 0.7:
            reasons.append(
                f"Rule 2 (NOT_RECOMMENDED): Support ({support.score:.3f}) and "
                f"Mechanistic ({mechanistic.score:.3f}) scores are LOW, "
                f"Risk ({risk.score:.3f}) is HIGH."
            )
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Rule 1: Promising criteria
        if support.score >= 0.4 and mechanistic.score >= 0.4 and risk.score <= 0.39:
            reasons.append(
                f"Rule 1 (PROMISING): Support Score = {support.score:.3f} (>= 0.40), "
                f"Mechanistic Score = {mechanistic.score:.3f} (>= 0.40), "
                f"Risk Score = {risk.score:.3f} (<= 0.39). "
                f"Safety grade: {safety_profile.overall_safety_grade}."
            )
            return RecommendationStatus.PROMISING, reasons

        # Rule 5: Default uncertain
        reasons.append(
            f"Rule 5 (UNCERTAIN): Mixed or sparse evidence. "
            f"SS={support.score:.3f}, MS={mechanistic.score:.3f}, RS={risk.score:.3f}. "
            f"Safety grade: {safety_profile.overall_safety_grade}."
        )
        return RecommendationStatus.UNCERTAIN, reasons

    # ─────────────────────────────────────────────
    # Step 8: Scientific Audit Report
    # ─────────────────────────────────────────────

    def _generate_audit_report(
        self,
        all_claims: list[Claim],
        contradictions: list[Contradiction],
        support: SupportAssessment,
        mechanistic: MechanisticAssessment,
        risk: RiskAssessment,
        recommendation: RecommendationStatus,
        reasons: list[str],
        prior_ctx: PriorKnowledgeContext,
        safety_profile: SafetyProfile,
        mechanistic_paths: list[MechanisticPath],
        conflict_report: ConflictResolutionReport,
    ) -> ScientificAuditReport:
        """Generate the enhanced scientific audit report."""
        supporting = [
            c for c in all_claims
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
        if not prior_ctx.top_entries:
            data_gaps.append("No prior knowledge entries found for this drug-disease pair.")

        # Enrich summary with Phase 2 data
        prior_note = (
            f" Prior knowledge: {'established precedent' if prior_ctx.has_established_precedent else 'novel hypothesis'}."
        )
        safety_note = (
            f" Safety grade: {safety_profile.overall_safety_grade}"
            f"{'(⚠️ boxed warning)' if safety_profile.has_boxed_warning else ''}."
        )
        paths_note = (
            f" {len(mechanistic_paths)} mechanistic path(s) traced."
            if mechanistic_paths else ""
        )
        conflict_note = (
            f" Conflict resolution: {conflict_report.resolution_narrative}"
            if conflict_report.resolution_narrative else ""
        )

        summary = (
            f"CYNTHERA v2.0 analysis produced a recommendation of "
            f"'{recommendation.value}'. "
            f"Support Score: {support.score:.3f} ({support.level}), "
            f"Mechanistic Score: {mechanistic.score:.3f} ({mechanistic.level}), "
            f"Risk Score: {risk.score:.3f} ({risk.level}). "
            f"{len(all_claims)} claim(s) extracted, "
            f"{len(contradictions)} contradiction(s) detected.{prior_note}{safety_note}{paths_note}"
        )

        confidence_narrative = (
            f"Confidence from {support.evidence_count} evidence records "
            f"(weighted sum: {support.weighted_sum:.2f}). "
            f"Prior knowledge confidence adjustment: {prior_ctx.confidence_adjustment:+.3f}. "
            f"Clinical safety confidence: {safety_profile.confidence:.2f}."
        )

        return ScientificAuditReport(
            summary=summary,
            key_supporting_claim_ids=[str(c.id) for c in supporting],
            key_contradicting_claim_ids=contradicting_ids,
            data_gaps=data_gaps,
            confidence_narrative=confidence_narrative,
            recommendation_rationale="\n".join(reasons),
        )
