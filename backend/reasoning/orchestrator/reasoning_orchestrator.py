"""ReasoningOrchestrator — coordinates the full reasoning pipeline.

Phase 2 Enhanced version integrating:
- PriorKnowledgeAgent (Step 0: prior knowledge context)
- ClinicalSafetyAgent (enhanced safety analysis)
- MultiHopReasoner (replaces simple mechanistic scoring)
- AdvancedConflictResolver (replaces simple contradiction detection)

Phase 3 Fix:
- Mechanistic score capped at MEDIUM when pathway_count == 0 (Issue #2)
- Support score broken down by evidence type (Issue #6, #3)
- Human-readable target names in chain — gene symbol + protein name (Issue #3)
- Confidence narrative uses plain English, not raw numbers (Issue #9)
- Audit report includes agent verdicts, next steps, citations (Issues #12, #15, #17)

Reference: 04_REASONING_SPECIFICATION.md, 08_IMPLEMENTATION_GUIDE.md §5.6
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from collections import Counter
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
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.reasoning.extraction.claim_extraction_agent import ClaimExtractionAgent
from backend.reasoning.agents.clinical_safety_agent import ClinicalSafetyAgent, SafetyProfile
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeAgent, PriorKnowledgeContext
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner, MechanisticPath
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator
from backend.reasoning.conflict.conflict_resolver import AdvancedConflictResolver, ConflictResolutionReport
from backend.reasoning.context.scientific_context_builder import (
    ScientificContext,
    ScientificContextBuilder,
)
from backend.infrastructure.knowledge.knowledge_store import KnowledgeStore
from backend.core.value_objects.source_url_builder import SourceURLBuilder

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Evidence type groupings for quality breakdown
# ─────────────────────────────────────────────

_CLINICAL_TYPES = {EvidenceType.RCT, EvidenceType.META_ANALYSIS}
_ANIMAL_TYPES = {EvidenceType.IN_VIVO}
_CELL_TYPES = {EvidenceType.IN_VITRO}
_REVIEW_TYPES = {EvidenceType.OBSERVATIONAL}

# ERW ceiling per evidence tier (limits inflated scores from low-quality data)
_ERW_CEILING_BY_TYPE: dict[EvidenceType, float] = {
    EvidenceType.META_ANALYSIS: 1.00,
    EvidenceType.RCT: 0.95,
    EvidenceType.OBSERVATIONAL: 0.75,
    EvidenceType.IN_VIVO: 0.65,
    EvidenceType.IN_VITRO: 0.55,
}

# ─────────────────────────────────────────────
# Suggested next steps by recommendation status
# ─────────────────────────────────────────────

_NEXT_STEPS: dict[str, list[str]] = {
    "PROMISING": [
        "Design a phase II clinical trial targeting the identified mechanism.",
        "Validate gene expression reversal in disease-relevant cell lines (GEO datasets).",
        "Perform molecular docking to confirm target binding affinity.",
        "Search TCGA/LINCS for transcriptomic evidence of pathway modulation.",
        "Conduct ADMET profiling to confirm safety for new indication.",
        "Evaluate pharmacokinetics in animal models relevant to the disease.",
    ],
    "UNCERTAIN": [
        "Expand literature retrieval — search OpenAlex and Semantic Scholar for additional evidence.",
        "Search GEO datasets for gene expression data in the disease context.",
        "Validate mechanism against additional Reactome/WikiPathways databases.",
        "Identify completed observational studies (cohort, registry data).",
        "Consult DisGeNET for gene-disease association evidence.",
        "Perform in vitro target validation assays before animal studies.",
        "Consider LINCS L1000 perturbation data to assess transcriptomic reversal.",
    ],
    "NOT_RECOMMENDED": [
        "Review safety data in detail — consult FDA adverse event database (FAERS).",
        "Investigate alternative targets in the same pathway.",
        "Consider drug combination approaches to mitigate risk.",
        "Search for structural analogs with improved safety profiles.",
        "Evaluate mechanistic validity for different disease subtypes.",
    ],
    "INSUFFICIENT_DATA": [
        "Expand retrieval policy to COMPREHENSIVE.",
        "Manually search PubMed for relevant literature.",
        "Contact authors of related studies for unpublished data.",
        "Search ClinicalTrials.gov directly for ongoing trials.",
    ],
}


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
        """Initialize the ReasoningOrchestrator."""
        self._extraction_agent = ClaimExtractionAgent(model=llm_model, api_key=llm_api_key, db_path=db_path)
        self._knowledge_store = KnowledgeStore(db_path=db_path)
        self._prior_knowledge_agent = PriorKnowledgeAgent(
            knowledge_store=self._knowledge_store
        )
        self._safety_agent = ClinicalSafetyAgent()
        self._multi_hop_reasoner = MultiHopReasoner()
        self._mechanism_validator = MechanismValidator()
        self._conflict_resolver = AdvancedConflictResolver()

    async def reason(self, package: RetrievalPackage) -> ReasoningResult:
        """Execute the full reasoning pipeline over a RetrievalPackage."""
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
        # Pass the live ChEMBL approval_signal so the agent infers from
        # retrieved data, not from any hardcoded source.
        prior_ctx = self._prior_knowledge_agent.retrieve(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
            approval_signal=package.approval_signal,
        )

        # ── Step 1: Extract claims from literature evidence ──────────────
        all_claims = await self._extract_all_claims(package)

        # ── Classify claim extraction method for transparency ------------
        # Inspect claim raw_text for the keyword-extraction prefix inserted
        # by _rule_based_fallback.  This is the only reliable per-record signal
        # available after asyncio.gather has collected all results.
        if not package.literature_evidence:
            claim_extraction_method = "none"
        else:
            has_fallback = any(
                "[keyword-extracted" in (c.raw_text or "")
                for c in all_claims
            )
            has_llm = any(
                "[keyword-extracted" not in (c.raw_text or "")
                for c in all_claims
            ) if all_claims else False
            if has_llm and has_fallback:
                claim_extraction_method = "mixed"
            elif has_fallback:
                claim_extraction_method = "rule_based_fallback"
            elif has_llm:
                claim_extraction_method = "llm"
            else:
                claim_extraction_method = "none"

        # ── Build data_source_failures from retrieval failures -----------
        # Each entry is a human-readable statement naming the source,
        # what it would have contributed, and the scoring impact.
        # These are forwarded verbatim to the frontend -- never absorbed
        # into scores.
        _SOURCE_DESCRIPTIONS: dict[str, str] = {
            "chembl": (
                "ChEMBL -- drug-target mechanism and bioactivity data. "
                "Targets and mechanistic paths may be absent or degraded."
            ),
            "uniprot": (
                "UniProt -- protein organism and annotation data. "
                "Organism validation could not run; non-human proteins may have "
                "passed undetected into the mechanistic chain."
            ),
            "pubmed": (
                "PubMed -- primary literature evidence. "
                "Support Score is based on reduced or absent literature."
            ),
            "openalex": (
                "OpenAlex -- supplementary literature evidence. "
                "Literature coverage is reduced."
            ),
            "semantic_scholar": (
                "Semantic Scholar -- citation-weighted literature evidence. "
                "Literature coverage is reduced."
            ),
            "reactome": (
                "Reactome -- biological pathway data. "
                "Mechanistic Score pathway component is absent; multi-hop paths "
                "could not be validated against pathway membership."
            ),
            "clinicaltrials": (
                "ClinicalTrials.gov -- human clinical trial safety data. "
                "Risk Score cannot incorporate trial failure signals."
            ),
            "disgenet": (
                "DisGeNET -- gene-disease association evidence. "
                "Gene-disease penalty on unvalidated targets did not run."
            ),
        }
        data_source_failures: list[str] = [
            _SOURCE_DESCRIPTIONS.get(
                src,
                f"{src} -- retrieval failed (no further description available).",
            )
            for src in package.sources_failed
        ]
        if claim_extraction_method in ("rule_based_fallback", "none") and package.literature_evidence:
            data_source_failures.append(
                "LLM Claim Extraction -- LLM provider (Groq/Gemini) was unavailable or unconfigured "
                "(quota exhausted or invalid API key). Claims were extracted using keyword matching, "
                "not LLM reasoning. Claim quality and Support Score accuracy are degraded."
            )

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
            self._compute_mechanistic_score(package, mechanistic_paths, prior_ctx, all_claims)
        )
        risk_task = asyncio.create_task(
            self._compute_risk_score(contradictions, package, safety_profile, conflict_report, all_claims)
        )

        support_assessment, mechanistic_assessment, risk_assessment = await asyncio.gather(
            support_task, mechanistic_task, risk_task
        )

        # ── Step 6b: Assemble dimensional ScientificContext ──────────────
        # A descriptive/transparency layer over signals the pipeline already
        # computed. Rule -1 consumes only scientific_context.regulatory.
        scientific_context = ScientificContextBuilder.build(
            prior_ctx=prior_ctx,
            support=support_assessment,
            mechanistic=mechanistic_assessment,
            mechanistic_paths=mechanistic_paths,
            package=package,
        )

        # ── Step 7: Apply recommendation rules ──────────────────────────
        recommendation_status, reasons = self._apply_rules(
            support_assessment,
            mechanistic_assessment,
            risk_assessment,
            contradictions,
            package,
            safety_profile,
            prior_ctx,
            scientific_context,
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
            scientific_context=scientific_context,
            safety_profile=safety_profile,
            mechanistic_paths=mechanistic_paths,
            conflict_report=conflict_report,
            package=package,
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
            rule_set_version="2.0",
            reasoning_duration_ms=round(duration_ms, 2),
            completed_at=datetime.utcnow(),
            data_source_failures=data_source_failures,
            claim_extraction_method=claim_extraction_method,
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
            for ev in lit_evidence[:10]  # cap at 10 records for optimal rate-limit & throughput
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
        """Construct a ClaimGraph from a list of Claims.

        P5 Fix: Implements spec §8.3 direction-consistent hop gating.
        After adding all claim nodes, wires directed edges between pairs where
        claim_A.object matches claim_B.subject (downstream biological cascade).
        Edge weight = min(confidence_A, confidence_B) — weakest-link per hop.

        Previously add_relation() was never called, leaving the graph with zero
        edges and making direction-consistent gating impossible.
        """
        from backend.core.domain.claim_graph import ClaimRelation

        graph = ClaimGraph(hypothesis_id=hypothesis_id)
        for claim in claims:
            graph.add_claim(claim)

        # Wire direction-consistent edges: A.object → B.subject
        # Normalise for case-insensitive substring matching to catch partial overlaps
        # (e.g. "PDE5A" in "PDE5A (P33402)").
        for c_a in claims:
            obj_lower = c_a.object.strip().lower()
            if not obj_lower:
                continue
            for c_b in claims:
                if c_a.id == c_b.id:
                    continue
                subj_lower = c_b.subject.strip().lower()
                # Match if one contains the other (handles abbreviated vs full names)
                if obj_lower in subj_lower or subj_lower in obj_lower:
                    relation = ClaimRelation(
                        source_claim_id=c_a.id,
                        target_claim_id=c_b.id,
                        relation_type=c_b.predicate,
                        weight=round(min(c_a.confidence, c_b.confidence), 4),
                    )
                    graph.add_relation(relation)

        return graph

    # ─────────────────────────────────────────────
    # Step 6a: Support Score — quality-weighted
    # ─────────────────────────────────────────────

    async def _compute_support_score(
        self,
        claims: list[Claim],
        package: RetrievalPackage,
        prior_ctx: PriorKnowledgeContext,
    ) -> SupportAssessment:
        """Compute the Support Score (SS) with quality-weighted breakdown.

        FIX (Issue #3, #6): Evidence is broken down by type (clinical, animal,
        cell-line, review) and ERW values are capped per tier. This prevents
        24 low-quality reviews from inflating SS to 0.911.

        Score formula: SS = 1 - exp(-k * quality_weighted_sum)
        where quality_weighted_sum = Σ min(erw, erw_ceiling_for_type)
        """
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
            if prior_ctx.evidence_boost > 0:
                score = round(min(0.4, prior_ctx.evidence_boost), 4)
                return SupportAssessment(
                    score=score,
                    level="LOW" if score < 0.4 else "MEDIUM",
                    evidence_count=0,
                    weighted_sum=0.0,
                    rationale=(
                        f"No direct evidence found. Prior knowledge provides a boost of "
                        f"{prior_ctx.evidence_boost:.3f}. {prior_ctx.narrative}"
                    ),
                )
            return SupportAssessment(
                score=0.0,
                level="NONE",
                evidence_count=0,
                weighted_sum=0.0,
                rationale="No supporting evidence or claims found.",
            )

        # ── Quality-tier breakdown ────────────────────────────────────
        type_buckets: dict[str, list[float]] = {
            "clinical": [],
            "animal": [],
            "cell_line": [],
            "review": [],
            "claim": [],
        }

        raw_weighted_sum = 0.0
        quality_weighted_sum = 0.0

        for ev in package.evidence_records:
            ceiling = _ERW_CEILING_BY_TYPE.get(ev.evidence_type, 0.60)
            capped_erw = min(ev.erw.value, ceiling)
            raw_weighted_sum += ev.erw.value
            quality_weighted_sum += capped_erw

            if ev.evidence_type in _CLINICAL_TYPES:
                type_buckets["clinical"].append(capped_erw)
            elif ev.evidence_type in _ANIMAL_TYPES:
                type_buckets["animal"].append(capped_erw)
            elif ev.evidence_type in _CELL_TYPES:
                type_buckets["cell_line"].append(capped_erw)
            else:
                type_buckets["review"].append(capped_erw)

        for c in supporting_claims:
            capped = min(c.erw.value, 0.80)
            quality_weighted_sum += capped
            raw_weighted_sum += c.erw.value
            type_buckets["claim"].append(capped)

        count = len(supporting_claims) + len(package.evidence_records)

        # Diminishing returns formula with quality-weighted sum
        k = 0.12
        raw_score = 1.0 - math.exp(-k * quality_weighted_sum)

        # Prior knowledge boost
        raw_score = raw_score + prior_ctx.evidence_boost * (1.0 - raw_score)
        score = round(min(1.0, raw_score), 4)
        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")

        # Build quality breakdown text
        breakdown_parts = []
        if type_buckets["clinical"]:
            avg = sum(type_buckets["clinical"]) / len(type_buckets["clinical"])
            breakdown_parts.append(
                f"Clinical/RCT: {len(type_buckets['clinical'])} records (avg ERW: {avg:.2f})"
            )
        if type_buckets["animal"]:
            avg = sum(type_buckets["animal"]) / len(type_buckets["animal"])
            breakdown_parts.append(
                f"Animal (in vivo): {len(type_buckets['animal'])} records (avg ERW: {avg:.2f})"
            )
        if type_buckets["cell_line"]:
            avg = sum(type_buckets["cell_line"]) / len(type_buckets["cell_line"])
            breakdown_parts.append(
                f"Cell-line (in vitro): {len(type_buckets['cell_line'])} records (avg ERW: {avg:.2f})"
            )
        if type_buckets["review"]:
            avg = sum(type_buckets["review"]) / len(type_buckets["review"])
            breakdown_parts.append(
                f"Reviews/Observational: {len(type_buckets['review'])} records (avg ERW: {avg:.2f})"
            )
        if type_buckets["claim"]:
            breakdown_parts.append(
                f"Extracted claims: {len(type_buckets['claim'])}"
            )

        prior_note = (
            f" Prior knowledge boost: {prior_ctx.evidence_boost:+.3f} applied."
            if prior_ctx.evidence_boost != 0 else ""
        )

        breakdown_text = "; ".join(breakdown_parts) if breakdown_parts else "No breakdown available."

        rationale = (
            f"Support Score (SS) from {count} evidence records.\n"
            f"Breakdown: {breakdown_text}\n"
            f"Formula: SS = 1 - exp(-0.12 × quality_weighted_sum). "
            f"Quality-weighted sum = {quality_weighted_sum:.2f} "
            f"(raw ERW sum would be {raw_weighted_sum:.2f}, "
            f"capped to prevent inflation from low-quality records).{prior_note}\n"
            f"Final SS = {score:.3f} ({level})."
        )

        return SupportAssessment(
            score=score,
            level=level,
            evidence_count=count,
            weighted_sum=round(quality_weighted_sum, 4),
            rationale=rationale,
            supporting_claim_ids=[str(c.id) for c in supporting_claims[:10]],
        )

    # ─────────────────────────────────────────────
    # Step 6b: Mechanistic Score — pathway-aware
    # ─────────────────────────────────────────────

    async def _compute_mechanistic_score(
        self,
        package: RetrievalPackage,
        paths: list[MechanisticPath],
        prior_ctx: PriorKnowledgeContext,
        all_claims: list[Claim] | None = None,
    ) -> MechanisticAssessment:
        """Compute the Mechanistic Score (MS) and discover Candidate Biological Mechanisms.

        Fix 3: MS score is derived DIRECTLY from candidate mechanism quality via
        compute_mechanistic_score_from_candidates(). Score and level are always consistent.

        Fix 4: Hop-level claim mapping populates each candidate's literature_grounding_level
        based on whether specific hops are supported by extracted literature claims, not just
        a global claim count.
        """
        target_count = len(package.targets)
        pathway_count = len(package.pathways)

        # Early exit: no targets retrieved
        if target_count == 0 and not paths:
            target_sources_failed = [
                s for s in (package.sources_failed or [])
                if s.lower() in ("chembl", "uniprot")
            ]
            if target_sources_failed:
                ev_status = "SOURCE_UNAVAILABLE"
                rationale = (
                    f"MS = 0.0 (NONE) — SOURCE UNAVAILABLE: "
                    f"Target-retrieval sources failed: [{', '.join(target_sources_failed)}]. "
                    "Drug targets could not be retrieved. This is a retrieval failure, NOT a biological negative."
                )
            else:
                ev_status = "INSUFFICIENT_EVIDENCE"
                rationale = (
                    "MS = 0.0 (NONE) — INSUFFICIENT EVIDENCE: "
                    "No drug targets were returned by ChEMBL/UniProt for this compound. "
                    "It is NOT a scientific statement that the drug has no targets."
                )
            return MechanisticAssessment(
                score=0.0,
                level="NONE",
                pathway_count=0,
                mechanistic_chain=[],
                candidate_mechanisms=[],
                evidence_status=ev_status,
                literature_grounding_level="UNAVAILABLE",
                rationale=rationale,
            )

        # No traversable paths: targets exist but no disease connection
        if not paths:
            failed_src = ", ".join(package.sources_failed) if package.sources_failed else "none logged"
            failed_normalised = {source.lower() for source in (package.sources_failed or [])}
            missing_disease_association_source = (
                not package.validated_disease_genes
                and bool(failed_normalised & {"opentargets", "disgenet"})
            )
            missing_pathway_source = not package.pathways and "reactome" in failed_normalised
            critical_source_failure = bool(failed_normalised & {"chembl", "uniprot"}) or missing_disease_association_source or missing_pathway_source
            evidence_status = "SOURCE_UNAVAILABLE" if critical_source_failure else "MECHANISTICALLY_UNSUPPORTED"
            outcome = (
                "SOURCE UNAVAILABLE: a critical mechanism source failed, so the absence of a path is not a biological negative."
                if critical_source_failure
                else "No retrieved database evidence supported a biological connection to the queried disease."
            )
            return MechanisticAssessment(
                score=0.0,
                level="NONE",
                pathway_count=pathway_count,
                mechanistic_chain=[],
                candidate_mechanisms=[],
                evidence_status=evidence_status,
                literature_grounding_level="NONE",
                rationale=(
                    f"Mechanistic Score (MS) = 0.0 (NONE). "
                    f"{target_count} target(s) were retrieved but no biological mechanism "
                    f"{outcome} "
                    f"Pathway count: {pathway_count}. "
                    f"Failed retrieval sources: [{failed_src}]."
                ),
            )

        # --- Fix 3: Discover candidates first, derive MS from their quality ---
        candidates = self._multi_hop_reasoner.discover_candidate_mechanisms(package, paths)

        # Stage B: graph paths are only structural candidates until the
        # biological bridge is validated against canonical-entity mapped
        # literature claims. Prior knowledge is deliberately not an input.
        candidates = self._mechanism_validator.validate(package, candidates, all_claims or [])
        candidates.sort(key=lambda candidate: candidate.confidence_score, reverse=True)

        # Derive MS score AND level from candidate quality (Fix 3: always consistent)
        if candidates:
            score, level = self._multi_hop_reasoner.compute_mechanistic_score_from_candidates(candidates)
            best = candidates[0]
            if best.support_level == "CONTRADICTED":
                ev_status = "CONTRADICTED"
            elif best.support_level in ("STRONGLY_SUPPORTED", "MODERATELY_SUPPORTED"):
                ev_status = "MECHANISTICALLY_PLAUSIBLE"
            else:
                ev_status = "INSUFFICIENT_EVIDENCE"
        else:
            score, level = 0.0, "NONE"
            ev_status = "MECHANISTICALLY_UNSUPPORTED"

        # Compute global literature grounding for reporting (not for scoring)
        lit_claims_count = len(all_claims or [])
        if not package.literature_evidence and "pubmed" in (package.sources_failed or []):
            lit_grounding = "UNAVAILABLE"
        elif any(
            getattr(c, "literature_grounding_level", "DATABASE_ONLY") in ("STRONG", "MODERATE")
            for c in candidates
        ):
            lit_grounding = "MODERATE"
        elif lit_claims_count >= 3:
            lit_grounding = "MODERATE"
        elif lit_claims_count >= 1:
            lit_grounding = "DATABASE_ONLY"
        else:
            lit_grounding = "DATABASE_ONLY" if candidates else "NONE"

        # Build primary mechanistic chain
        chain = self._build_mechanistic_chain(package, paths, prior_ctx)
        serialized_candidates = [c.to_dict() for c in candidates]

        # Rationale
        candidates_note = f"Discovered {len(candidates)} candidate biological mechanism(s). "
        best_level = candidates[0].support_level if candidates else "NONE"
        lit_note = f"Literature grounding: {lit_grounding} ({lit_claims_count} claim(s)). "

        rationale = (
            f"Mechanistic Score (MS) derived from candidate mechanism quality. "
            f"Best candidate support level: {best_level}. "
            f"{candidates_note}{lit_note}"
            f"Final MS = {score:.3f} ({level})."
        )

        return MechanisticAssessment(
            score=score,
            level=level,
            pathway_count=pathway_count,
            mechanistic_chain=chain,
            candidate_mechanisms=serialized_candidates,
            evidence_status=ev_status,
            literature_grounding_level=lit_grounding,
            rationale=rationale,
        )

    def _build_mechanistic_chain(
        self,
        package: RetrievalPackage,
        paths: list[MechanisticPath],
        prior_ctx: PriorKnowledgeContext,
    ) -> list[str]:
        """Build a human-readable, multi-step mechanistic chain from retrieved data.

        Every node in the chain comes from retrieved biological entities:
        - Drug node: drug.name
        - Target nodes: Gene symbol + Protein name from UniProt (retrieved)
        - Pathway nodes: Reactome pathway names (retrieved)
        - Disease gene nodes: Gene symbols from DisGeNET evidence (retrieved)
        - Disease node: disease.name

        No drug-specific mechanism strings are hardcoded. If a UniProt lookup
        failed during retrieval, the target is shown with mechanism type and
        a clear '[UniProt API unavailable]' label rather than a raw accession.
        Prior knowledge hints are included only as supplementary annotation.

        Args:
            package: Sealed RetrievalPackage with all retrieved entities.
            paths: Multi-hop mechanistic paths from MultiHopReasoner.
            prior_ctx: Prior knowledge context (supplementary hints only).

        Returns:
            List of chain node strings for display.
        """
        # Build protein lookup from retrieved UniProt data: accession → (gene_symbol, name)
        protein_lookup: dict[str, tuple[str, str]] = {}
        for p in package.proteins:
            protein_lookup[p.uniprot_accession] = (p.gene_symbol, p.name)

        if paths:
            # Use the best multi-hop path (highest confidence first).
            # New: use per-hop predicate + source from graph-based MechanisticHop.
            best_path = paths[0]
            readable_chain: list[str] = []
            for i, h in enumerate(best_path.hops):
                # Replace any raw UniProt accessions still in names with readable form
                node_name = h.name
                for uniprot, (gene_sym, prot_name) in protein_lookup.items():
                    if uniprot and uniprot in node_name:
                        node_name = node_name.replace(
                            uniprot, f"{gene_sym} ({prot_name}) [UniProt: {uniprot}]"
                        )
                if i == 0:
                    readable_chain.append(f"{h.label}: {node_name}")
                else:
                    pred_str = ""
                    if h.predicate:
                        pred_str = f" [{h.predicate}"
                        if h.source:
                            pred_str += f" via {h.source}"
                        pred_str += "]"
                    readable_chain.append(f"{h.label}: {node_name}{pred_str}")
            return readable_chain

        # Build chain from retrieved package entities
        chain = [package.drug.name]

        # Target nodes — from ChEMBL bioactivity + UniProt retrieval
        seen_targets: set[str] = set()
        for t in package.targets[:3]:
            uid = t.protein_uniprot
            if uid in seen_targets:
                continue
            seen_targets.add(uid)
            mechanism = t.mechanism.lower().replace("_", " ").replace("unknown", "modulates target")
            gene_sym, prot_name = protein_lookup.get(uid, ("", ""))
            if gene_sym:
                # Full readable name available from UniProt retrieval
                chain.append(
                    f"{gene_sym} ({prot_name}) — {mechanism} [UniProt: {uid}]"
                )
            else:
                # UniProt retrieval failed — show mechanism type, not raw ID
                chain.append(
                    f"Target protein [UniProt: {uid}, protein name unavailable — UniProt API error] "
                    f"— {mechanism}"
                )
            if len(chain) >= 4:
                break

        # Pathway nodes — from Reactome retrieval
        for pw in package.pathways[:2]:
            chain.append(f"Pathway: {pw.name} [Reactome: {pw.reactome_id}]")

        # Disease gene associations — from DisGeNET evidence (if available)
        disgenet_genes: list[str] = []
        for ev in package.evidence_records:
            provenance = getattr(ev, "provenance", None)
            if provenance and getattr(provenance, "source_name", "") == "DisGeNET":
                # Extract gene from title: "DisGeNET association: GENEX — disease"
                title = ev.title or ""
                if "DisGeNET association:" in title:
                    parts = title.split(":")
                    if len(parts) > 1:
                        gene_part = parts[1].split("—")[0].strip()
                        if gene_part and gene_part not in disgenet_genes:
                            disgenet_genes.append(gene_part)
        if disgenet_genes:
            chain.append(
                f"Disease-gene association: {', '.join(disgenet_genes[:2])} "
                f"→ {package.disease.name} [DisGeNET]"
            )

        chain.append(package.disease.name)
        return chain

    def _map_claims_to_candidates(
        self,
        candidates: list,
        all_claims: list[Claim],
    ) -> list:
        """Fix 4: Map extracted literature claims to specific candidate mechanism hops.

        For each CandidateMechanism, checks whether any extracted claim's subject/object
        textually matches the hop's entity names. This turns claim coverage from a global
        count into per-candidate, per-hop validation.

        Updates each CandidateMechanism with:
          - literature_citations: list of citation keys for claims supporting this candidate
          - literature_grounding_level: STRONG (>=2 hops covered), MODERATE (>=1 hop),
            DATABASE_ONLY (no claim matches this candidate's specific hops)
        """
        if not all_claims:
            return candidates

        updated_candidates = []
        for candidate in candidates:
            matched_claim_ids: list[str] = []
            hops_with_claim_support: set[int] = set()

            for hop_idx, hop in enumerate(getattr(candidate, "hops", [])):
                from_entity = (hop.from_node or "").lower()
                to_entity = (hop.to_node or "").lower()

                for claim in all_claims:
                    subj = (getattr(claim, "subject", "") or "").lower()
                    obj = (getattr(claim, "object", "") or "").lower()
                    subj_hit = (
                        subj in from_entity or from_entity in subj
                        or any(tok in from_entity for tok in subj.split() if len(tok) > 3)
                    )
                    obj_hit = (
                        obj in to_entity or to_entity in obj
                        or any(tok in to_entity for tok in obj.split() if len(tok) > 3)
                    )
                    if subj_hit and obj_hit:
                        claim_key = getattr(claim, "id", None)
                        if claim_key and str(claim_key) not in matched_claim_ids:
                            matched_claim_ids.append(str(claim_key))
                        hops_with_claim_support.add(hop_idx)

            covered_hops = len(hops_with_claim_support)
            total_hops = len(getattr(candidate, "hops", []))
            if covered_hops >= 2 or (total_hops > 0 and covered_hops / total_hops >= 0.5):
                grounding = "STRONG"
            elif covered_hops >= 1:
                grounding = "MODERATE"
            else:
                grounding = "DATABASE_ONLY"

            # Create updated immutable copy for Pydantic / dataclass candidate
            cites = [{"claim_id": cid} for cid in matched_claim_ids[:10]]
            if hasattr(candidate, "model_copy"):
                cand_copy = candidate.model_copy(update={"literature_citations": cites})
                object.__setattr__(cand_copy, "literature_grounding_level", grounding)
                updated_candidates.append(cand_copy)
            else:
                setattr(candidate, "literature_citations", cites)
                setattr(candidate, "literature_grounding_level", grounding)
                updated_candidates.append(candidate)

        return updated_candidates



    async def _compute_risk_score(
        self,
        contradictions: list[Contradiction],
        package: RetrievalPackage,
        safety_profile: SafetyProfile,
        conflict_report: ConflictResolutionReport,
        claims: list[Claim] | None = None,
    ) -> RiskAssessment:
        """Compute the Risk Score (RS) with trial termination WHY-analysis.

        Fix 5: Trial terminations are now categorized by reason:
          SAFETY_TERMINATED     -> counts strongly toward risk (1.8x weight)
          EFFICACY_TERMINATED   -> counts toward risk (1.0x weight)
          ADMINISTRATIVE_TERMINATED -> does NOT count toward risk
          COVID_TERMINATED      -> does NOT count toward risk

        This prevents administrative/enrollment failures from being treated as
        clinical evidence against the drug, which was the root cause of the
        Alteplase-style NOT_RECOMMENDED false positives.
        """
        # Categorize trials by termination reason
        safety_terminated: list = []
        efficacy_terminated: list = []
        administrative_terminated: list = []
        covid_terminated: list = []
        other_failed: list = []

        _ADMIN_KEYWORDS = (
            "enrollment", "enrolment", "funding", "sponsor", "administrative",
            "business decision", "feasibility", "recruitment", "accrual",
            "withdrawn", "logistic", "protocol deviation",
        )
        _COVID_KEYWORDS = ("covid", "pandemic", "sars-cov", "coronavirus")

        for t in package.clinical_trials:
            if t.status not in (
                TrialOutcomeStatus.COMPLETED_FAILURE,
                TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                TrialOutcomeStatus.TERMINATED_SAFETY,
            ):
                continue

            why = (getattr(t, "why_stopped", "") or "").lower()

            if t.status == TrialOutcomeStatus.TERMINATED_SAFETY:
                safety_terminated.append(t)
            elif any(k in why for k in _COVID_KEYWORDS):
                covid_terminated.append(t)
            elif any(k in why for k in _ADMIN_KEYWORDS):
                administrative_terminated.append(t)
            elif t.status == TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY:
                efficacy_terminated.append(t)
            else:
                other_failed.append(t)

        # Only safety + efficacy failures count toward clinical risk
        clinically_significant_failures = safety_terminated + efficacy_terminated + other_failed

        raw_risk = 0.0
        raw_risk += len(safety_terminated) * 1.8      # safety failures: highest weight
        raw_risk += len(efficacy_terminated) * 1.0    # efficacy failures: standard weight
        raw_risk += len(other_failed) * 0.6           # ambiguous failures: low weight
        # Administrative/COVID terminations: do NOT add to risk
        raw_risk += conflict_report.net_conflict_score * len(contradictions) * 0.5

        # Harmful / contraindication claims. Ordinary adverse-effect mentions
        # such as fluid retention are safety-monitoring signals, not evidence
        # that the drug is contraindicated for the queried disease.
        harmful_claims = []
        for c in (claims or []):
            text = (getattr(c, "raw_text", "") or f"{c.subject} {c.predicate.value} {c.object}").lower()
            if (
                "contraindicat" in text
                or "exacerbat" in text
                or "worsen" in text
                or "causes heart failure" in text
            ):
                harmful_claims.append(c)
        if harmful_claims:
            raw_risk += min(len(harmful_claims), 3) * 1.2

        grade_penalty = {"D": 3.0, "C": 0.8, "B": 0.2, "A": 0.0}.get(
            safety_profile.overall_safety_grade, 0.5
        )

        if safety_profile.has_boxed_warning:
            raw_risk += 3.5
        else:
            raw_risk += grade_penalty

        k = 0.3
        score = round(1.0 - math.exp(-k * raw_risk), 4) if raw_risk > 0 else 0.0
        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")
        if score == 0.0:
            level = "NONE"

        # Build plain-English risk breakdown with WHY categorization
        risk_factors = []
        if safety_terminated:
            risk_factors.append(f"Safety-terminated trials: {len(safety_terminated)} [HIGH RISK]")
        if efficacy_terminated:
            risk_factors.append(f"Efficacy-terminated trials: {len(efficacy_terminated)}")
        if other_failed:
            risk_factors.append(f"Other failed trials: {len(other_failed)}")
        if administrative_terminated:
            risk_factors.append(
                f"Administrative/enrollment terminations: {len(administrative_terminated)} "
                "[NOT counted in risk — not a clinical signal]"
            )
        if covid_terminated:
            risk_factors.append(
                f"COVID/pandemic terminations: {len(covid_terminated)} "
                "[NOT counted in risk — external disruption]"
            )
        if contradictions:
            risk_factors.append(
                f"Contradictory evidence: {len(contradictions)} conflict(s) "
                f"(net score: {conflict_report.net_conflict_score:.2f})"
            )
        if harmful_claims:
            risk_factors.append(
                f"Contraindication/exacerbation claims: {len(harmful_claims)} "
                f"({min(len(harmful_claims), 3)} counted after cap)"
            )
        if safety_profile.has_boxed_warning:
            risk_factors.append("FDA Boxed Warning detected")
        if safety_profile.adverse_events:
            severe_aes = [ae for ae in safety_profile.adverse_events if ae.severity in ("SEVERE", "FATAL")]
            if severe_aes:
                risk_factors.append(
                    f"Severe adverse events detected: "
                    f"{', '.join(ae.event_type for ae in severe_aes[:3])}"
                )
        risk_factors.append(
            f"Safety grade: {safety_profile.overall_safety_grade} "
            f"(grade penalty: {0.0 if safety_profile.has_boxed_warning else grade_penalty:.1f})"
        )

        rationale = (
            f"Risk Score (RS) computed from clinically significant safety signals.\n"
            f"Trial analysis: {len(clinically_significant_failures)} clinically significant failure(s); "
            f"{len(administrative_terminated + covid_terminated)} administrative/external termination(s) excluded.\n"
            f"Risk factors: {'; '.join(risk_factors) if risk_factors else 'None identified'}.\n"
            f"Formula: RS = 1 - exp(-0.30 x raw_risk_burden). "
            f"Raw burden = {raw_risk:.2f}. Final RS = {score:.3f} ({level})."
        )

        return RiskAssessment(
            score=score,
            level=level,
            failed_trial_count=len(clinically_significant_failures),
            contradiction_count=len(contradictions),
            rationale=rationale,
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
        prior_ctx: "PriorKnowledgeContext",
        scientific_context: ScientificContext,
    ) -> tuple[RecommendationStatus, list[str]]:
        """Apply deterministic recommendation rules over (SS, MS, RS).

        Rule Set v3.1 — Evidence-First Architecture:
        Evidence-based rules (3, 1) fire before the data-availability lock (Rule 4).

        - Rule -1 (APPROVED INDICATION): ChEMBL signals approved for this disease
            → PROMISING, bypass ClinicalTrials safety lock (Rule 4)
            → Safety veto still applies (Rules 0 and 3)
        - Rule 0 (SAFETY_VETO): Boxed warning + HIGH risk → NOT_RECOMMENDED
        - Rule 3 (SAFETY_VETO): RS >= 0.70 → NOT_RECOMMENDED
        - Rule 1 (PROMISING): SS >= MEDIUM AND MS >= MEDIUM AND RS <= LOW
        - Rule 4 (SAFETY_LOCK): ClinicalTrials failed AND not approved → cap at UNCERTAIN
        - Rule 5 (UNCERTAIN): default

        Critically: Rule -1 fires ONLY when the dimensional Regulatory Status is
        APPROVED — which is True only from the live ChEMBL ApprovalSignal
        (max_phase_for_ind == 4 for this disease, confidence >= 0.35). No drug
        name checks. No hardcoded disease lists. All other dimensions are purely
        descriptive and grant no rule-bypass privilege.
        """
        reasons: list[str] = []

        # Build evidence checklist
        checks = self._build_evidence_checks(support, mechanistic, risk, contradictions, package)

        # Check Source Availability / Pipeline Failure Gate
        if mechanistic.evidence_status == "SOURCE_UNAVAILABLE" or ("chembl" in package.sources_failed and "uniprot" in package.sources_failed):
            reasons.append(
                f"Rule -2 (DATA AVAILABILITY FAILURE): Critical target/mechanism databases "
                f"failed during retrieval: [{', '.join(package.sources_failed)}]. "
                "Unable to evaluate hypothesis due to source unavailability."
            )
            reasons.extend(checks)
            return RecommendationStatus.INSUFFICIENT_DATA, reasons

        # Rule: Approved indication pathway (evidence-driven, not hardcoded)
        if scientific_context.regulatory.status == "APPROVED":
            reasons.append(
                f"Rule -1 (APPROVED INDICATION): ChEMBL indication data indicates this drug "
                f"is approved (max_phase_for_ind = 4) for an indication matching '{package.disease.name}' "
                f"(regulatory confidence {scientific_context.regulatory.confidence:.0%}). "
                f"Matched ChEMBL term: '{prior_ctx.matched_indication_term}'. "
                "ClinicalTrials.gov safety lock (Rule 4) bypassed for approved therapies. "
                "Standard safety vetoes (Rules 0 and 3) still apply."
            )
            # Safety veto still applies even for approved drugs
            if safety_profile.has_boxed_warning and risk.score >= 0.6:
                reasons.append(
                    f"Rule 0 override: Despite approved status, boxed warning AND "
                    f"Risk Score = {risk.score:.3f} (HIGH). "
                    "Safety concerns override even for approved indications."
                )
                reasons.extend(checks)
                return RecommendationStatus.NOT_RECOMMENDED, reasons
            if risk.score >= 0.7:
                reasons.append(
                    f"Rule 3 override: Despite approved status, Risk Score is HIGH ({risk.score:.3f}). "
                    "Significant safety signals detected."
                )
                reasons.extend(checks)
                return RecommendationStatus.UNCERTAIN, reasons
            reasons.extend(checks)
            return RecommendationStatus.PROMISING, reasons

        # Rule 0: Safety & Contraindication Veto — boxed warning or high-concern safety profile
        if safety_profile.has_boxed_warning or safety_profile.overall_safety_grade == "D" or risk.score >= 0.6:
            reasons.append(
                f"Rule 0 (SAFETY VETO): ⚠ Boxed warning / contraindication detected. Risk Score = "
                f"{risk.score:.3f}. Safety grade: {safety_profile.overall_safety_grade}. "
                "NOT RECOMMENDED due to unacceptable safety profile / disease contraindication."
            )
            reasons.extend(checks)
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Rule 2: Clinical Trial Failure Assessment — multiple clinically significant trial failures or high risk burden
        if risk.score >= 0.60 or (risk.failed_trial_count >= 2 and risk.score >= 0.50):
            reasons.append(
                f"Rule 2 (CLINICAL FAILURE VETO): Risk Score = {risk.score:.3f} "
                f"with {risk.failed_trial_count} clinically significant trial failure(s). "
                "NOT RECOMMENDED due to documented clinical endpoint failures or safety signals."
            )
            reasons.extend(checks)
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Rule 3: Safety veto — high risk score (evidence-based, fires before data-lock)
        if risk.score >= 0.7:
            reasons.append(
                f"Rule 3 (SAFETY VETO): Risk Score is HIGH ({risk.score:.3f}). "
                f"Triggered by {risk.failed_trial_count} failed trial(s) and "
                f"{risk.contradiction_count} contradiction(s). "
                f"Safety grade: {safety_profile.overall_safety_grade}."
            )
            reasons.extend(checks)
            return RecommendationStatus.NOT_RECOMMENDED, reasons

        # Rule 1: Promising criteria (evidence-based, fires before data-lock)
        if support.score >= 0.4 and mechanistic.score >= 0.4 and risk.score <= 0.39:
            reasons.append(
                f"Rule 1 (PROMISING): SS = {support.score:.3f} (≥ 0.40), "
                f"MS = {mechanistic.score:.3f} (≥ 0.40), "
                f"RS = {risk.score:.3f} (≤ 0.39). "
                f"Safety grade: {safety_profile.overall_safety_grade}."
            )
            reasons.extend(checks)
            return RecommendationStatus.PROMISING, reasons

        # Rule 4: Safety lock — clinical trials data unavailable (fallback, after evidence)
        if "clinicaltrials" in package.sources_failed:
            reasons.append(
                "Rule 4 (SAFETY LOCK): ClinicalTrials.gov data unavailable. "
                "Without human clinical evidence, the maximum confidence level is UNCERTAIN. "
                "This is a conservative safety constraint for repurposing hypotheses, "
                "not a scientific negative."
            )
            reasons.extend(checks)
            return RecommendationStatus.UNCERTAIN, reasons

        # Rule 5: Default uncertain
        reasons.append(
            f"Rule 5 (UNCERTAIN): Mixed or sparse evidence. "
            f"SS={support.score:.3f}, MS={mechanistic.score:.3f}, RS={risk.score:.3f}. "
            f"Safety grade: {safety_profile.overall_safety_grade}."
        )
        reasons.extend(checks)
        return RecommendationStatus.UNCERTAIN, reasons

    def _build_evidence_checks(
        self,
        support: SupportAssessment,
        mechanistic: MechanisticAssessment,
        risk: RiskAssessment,
        contradictions: list[Contradiction],
        package: RetrievalPackage,
    ) -> list[str]:
        """Build evidence checklist for transparent recommendation display.

        FIX (Issue #6, #1): Shows clear signal/gap breakdown instead of
        just a single recommendation label.
        """
        checks = []
        checks.append("Evidence signals:")
        checks.append(
            f"  {'[PASS]' if support.score >= 0.5 else '[FAIL]'} Literature support: "
            f"SS = {support.score:.3f} ({support.level}) from {support.evidence_count} records"
        )
        checks.append(
            f"  {'[PASS]' if mechanistic.score >= 0.4 else '[FAIL]'} Mechanistic plausibility: "
            f"MS = {mechanistic.score:.3f} ({mechanistic.level}), "
            f"{mechanistic.pathway_count} pathway(s)"
        )
        checks.append(
            f"  {'[FAIL]' if risk.score >= 0.4 else '[PASS]'} Safety/Risk acceptable: "
            f"RS = {risk.score:.3f} ({risk.level})"
        )
        checks.append(
            f"  {'[FAIL]' if contradictions else '[PASS]'} Evidence consistency: "
            f"{'No contradictions' if not contradictions else f'{len(contradictions)} contradiction(s) detected'}"
        )
        checks.append(
            f"  {'[PASS]' if 'clinicaltrials' not in package.sources_failed else '[FAIL]'} "
            f"Human clinical data: "
            f"{'Available' if 'clinicaltrials' not in package.sources_failed else 'Unavailable (ClinicalTrials.gov)'}"
        )
        return checks

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
        scientific_context: ScientificContext,
        safety_profile: SafetyProfile,
        mechanistic_paths: list[MechanisticPath],
        conflict_report: ConflictResolutionReport,
        package: RetrievalPackage,
    ) -> ScientificAuditReport:
        """Generate the enhanced scientific audit report.

        FIX (Issues #9, #10, #11, #12, #13, #15, #16, #17):
        - Plain-English confidence narrative (no raw "weighted_sum: 15.25")
        - Safety grade legend embedded
        - Data gaps show confidence penalty
        - Citations/PMIDs in evidence
        - Agent assessment verdicts
        - Suggested next steps
        """
        supporting = [
            c for c in all_claims
            if c.predicate in (
                PredicateType.ACTIVATES, PredicateType.INHIBITS,
                PredicateType.BINDS, PredicateType.PREVENTS
            )
        ][:10]

        contradicting_ids = [str(c.claim_id_a) for c in contradictions[:5]]

        # ── Data gaps with confidence penalty (FIX Issue #11) ────────────
        data_gaps: list[str] = []
        confidence_penalty = 0.0

        if mechanistic.pathway_count == 0:
            data_gaps.append(
                "No Reactome pathway data retrieved — Mechanistic Score capped at MEDIUM "
                "(−0.15 confidence penalty applied)."
            )
            confidence_penalty += 0.15

        if support.evidence_count < 5:
            data_gaps.append(
                f"Sparse evidence base ({support.evidence_count} records). "
                "Consider COMPREHENSIVE retrieval policy (−0.10 confidence penalty)."
            )
            confidence_penalty += 0.10

        if "clinicaltrials" in package.sources_failed:
            # For approved indications, the message is different
            if scientific_context.regulatory.status == "APPROVED":
                data_gaps.append(
                    "ClinicalTrials.gov unavailable — unable to verify current trial status. "
                    "This does NOT cap the recommendation for approved therapies "
                    "(the drug has an established approval record in ChEMBL)."
                )
                confidence_penalty += 0.05
            else:
                data_gaps.append(
                    "ClinicalTrials.gov unavailable — no human clinical trial outcomes "
                    "(−0.25 confidence penalty; recommendation capped at UNCERTAIN for repurposing hypotheses)."
                )
                confidence_penalty += 0.25

        if scientific_context.knowledge_maturity.status in ("SPECULATIVE", "ESTABLISHED") and not prior_ctx.top_entries:
            data_gaps.append(
                "No prior knowledge entries found for this drug-disease pair. "
                "This appears to be a genuinely novel repurposing hypothesis "
                "(−0.05 confidence penalty)."
            )
            confidence_penalty += 0.05
        elif scientific_context.knowledge_maturity.status == "SPECULATIVE":
            data_gaps.append(
                "Prior-knowledge cache signal is weak for this drug-disease pair. "
                "No established prior hypothesis."
            )

        if "uniprot" in package.sources_failed:
            data_gaps.append(
                "UniProt protein data unavailable — target annotation may be incomplete "
                "(−0.10 confidence penalty)."
            )
            confidence_penalty += 0.10

        # ── Citations from evidence records (FIX Issue #12, P4) ──────────
        citations = self._extract_citations(package.evidence_records[:15])

        # ── Claim citation mapping: claim UUID → list of PMID/DOI keys ──────
        # Resolves Claim.evidence_ids → Evidence.citation_key for traceability.
        # No new storage needed — assembles from already-available data.
        evidence_by_id = {str(ev.id): ev for ev in package.evidence_records}
        claim_citations: dict[str, list[str]] = {}
        for claim in all_claims:
            keys = [
                evidence_by_id[str(eid)].citation_key
                for eid in claim.evidence_ids
                if str(eid) in evidence_by_id
            ]
            claim_citations[str(claim.id)] = [k for k in keys if k]

        # ── Agent assessment verdicts (FIX Issue #17) ────────────────────
        agent_verdicts = self._compute_agent_verdicts(
            support, mechanistic, risk, contradictions, safety_profile, scientific_context
        )

        # ── Next steps (FIX Issue #15) ───────────────────────────────────
        next_steps = _NEXT_STEPS.get(recommendation.value, _NEXT_STEPS["UNCERTAIN"])

        # ── Summary (FIX Issue #1) — explains why scores ≠ recommendation ─
        prior_note = (
            f" Prior knowledge: regulatory {scientific_context.regulatory.status} "
            f"({scientific_context.regulatory.confidence:.0%}), "
            f"repurposing {scientific_context.repurposing.status}, "
            f"mechanistic {scientific_context.mechanistic.status}, "
            f"clinical {scientific_context.clinical.status}, "
            f"knowledge maturity {scientific_context.knowledge_maturity.status}."
        )
        safety_note = (
            f" Safety grade: {safety_profile.overall_safety_grade}"
            f"{'  ⚠ Boxed warning detected' if safety_profile.has_boxed_warning else ''}."
        )
        paths_note = (
            f" {len(mechanistic_paths)} mechanistic path(s) traced."
            if mechanistic_paths else " No multi-hop paths traced."
        )

        # Explain score vs recommendation mismatch clearly
        score_conflict_note = ""
        if support.level == "HIGH" and mechanistic.level in ("HIGH", "MEDIUM") and recommendation.value == "UNCERTAIN":
            score_conflict_note = (
                " Note: Despite strong evidence scores, the recommendation is UNCERTAIN "
                "because critical data sources are missing (see Data Gaps below). "
                "Strong scores do not guarantee a PROMISING recommendation when human "
                "clinical validation data is unavailable."
            )

        # ── Claims breakdown by literature source ────────
        claims_by_source: dict[str, int] = {}
        for c in all_claims:
            src = (c.provenance.source_name if c.provenance and c.provenance.source_name else "literature").lower()
            claims_by_source[src] = claims_by_source.get(src, 0) + 1

        if claims_by_source:
            src_parts = [f"{count} from {src}" for src, count in claims_by_source.items()]
            source_breakdown_str = f" ({', '.join(src_parts)})"
        else:
            source_breakdown_str = ""

        summary = (
            f"CYNTHERA v2.0 analysis of {package.drug.name} → {package.disease.name} "
            f"produced a recommendation of '{recommendation.value}'.\n"
            f"Evidence Strength: {support.score:.1%} ({support.level}) | "
            f"Mechanistic Plausibility: {mechanistic.score:.1%} ({mechanistic.level}) | "
            f"Risk Level: {risk.score:.1%} ({risk.level}).\n"
            f"{len(all_claims)} claim(s) extracted from literature{source_breakdown_str}, "
            f"{len(contradictions)} contradiction(s) detected."
            f"{prior_note}{safety_note}{paths_note}"
            f"{score_conflict_note}"
        )

        # ── Confidence Narrative (FIX Issue #9) — plain English ──────────
        base_confidence = 1.0 - confidence_penalty
        evidence_quality_desc = (
            "high-quality clinical evidence" if support.level == "HIGH" and any(
                ev.evidence_type in _CLINICAL_TYPES for ev in package.evidence_records
            ) else
            "moderate-quality mixed evidence" if support.level in ("HIGH", "MEDIUM") else
            "limited or low-quality evidence"
        )

        # Safety grade legend (FIX Issue #10)
        safety_grade_legend = {
            "A": "Excellent — clean safety record across all trials",
            "B": "Acceptable — minor concerns, generally safe",
            "C": "Moderate concerns — monitoring and caution recommended",
            "D": "Significant safety concerns — strong contraindications identified",
        }
        safety_desc = safety_grade_legend.get(safety_profile.overall_safety_grade, "Unknown")

        confidence_narrative = (
            f"Overall confidence is estimated at {base_confidence:.0%} after accounting for "
            f"data gaps (total penalty: −{confidence_penalty:.0%}).\n\n"
            f"Evidence quality: The analysis is based on {support.evidence_count} retrieved records "
            f"representing {evidence_quality_desc}. ERW values are capped per evidence tier to "
            f"prevent inflation from low-quality records (e.g., reviews and hypotheses).\n\n"
            f"Safety assessment: Grade {safety_profile.overall_safety_grade} — {safety_desc}. "
            f"{'A boxed warning was detected.' if safety_profile.has_boxed_warning else 'No boxed warning detected.'}\n\n"
            f"Safety grade scale: A = Excellent | B = Acceptable | C = Caution | D = Unsafe.\n\n"
            f"Prior knowledge: {prior_ctx.narrative[:200] if prior_ctx.narrative else 'No prior knowledge context available.'}"
        )

        # ── Recommendation rationale (rich, with all context) ────────────
        rationale_lines = list(reasons)
        rationale_lines.append("")
        rationale_lines.append("Agent Assessment Summary:")
        for agent_name, verdict in agent_verdicts.items():
            rationale_lines.append(f"  {agent_name}: {verdict}")
        rationale_lines.append("")
        rationale_lines.append("Suggested Next Steps:")
        for step in next_steps[:5]:
            rationale_lines.append(f"  → {step}")
        if citations:
            rationale_lines.append("")
            rationale_lines.append(f"Top Citations ({len(citations)} shown):")
            for citation in citations[:5]:
                rationale_lines.append(f"  • {citation}")

        # ── Positive and Negative Factors (from evidence checks) ────────────
        checks = self._build_evidence_checks(
            support, mechanistic, risk, contradictions, package
        )
        positive_factors: list[str] = []
        negative_factors: list[str] = []
        for check in checks:
            clean_chk = check.strip()
            if clean_chk.startswith("[PASS]"):
                positive_factors.append(clean_chk[6:].strip())
            elif clean_chk.startswith("[FAIL]"):
                negative_factors.append(clean_chk[6:].strip())
        if scientific_context.regulatory.status == "APPROVED":
            positive_factors.insert(
                0,
                f"FDA/EMA approved indication: {prior_ctx.matched_indication_term} "
                f"(ChEMBL, match confidence {scientific_context.regulatory.confidence:.0%})",
            )

        # ── Safety Breakdown (from SafetyProfile) ────────────────────────────
        safety_brkdown: dict = {
            "overall_grade": safety_profile.overall_safety_grade,
            "has_boxed_warning": safety_profile.has_boxed_warning,
            "adverse_events": [
                {
                    "event": ae.event_name if hasattr(ae, "event_name") else str(ae),
                    "severity": ae.severity if hasattr(ae, "severity") else "unknown",
                    "frequency": ae.frequency if hasattr(ae, "frequency") else "unknown",
                }
                for ae in getattr(safety_profile, "adverse_events", [])[:10]
            ],
            "drug_interactions": [
                str(di) for di in getattr(safety_profile, "drug_interactions", [])[:5]
            ],
            "population_restrictions": [
                str(pr) for pr in getattr(safety_profile, "population_restrictions", [])[:5]
            ],
            "hepatotoxicity_signal": getattr(safety_profile, "hepatotoxicity_signal", False),
            "cardiotoxicity_signal": getattr(safety_profile, "cardiotoxicity_signal", False),
            "nephrotoxicity_signal": getattr(safety_profile, "nephrotoxicity_signal", False),
        }

        ct_status = getattr(package, "clinical_trial_retrieval_status", "NOT_ATTEMPTED")

        # ── Sources accessed list ──────────────────────────────────────────
        sources_accessed: list[dict[str, str]] = []
        u_chembl = SourceURLBuilder.chembl_compound_url(package.drug.chembl_id) if package.drug.chembl_id else None
        sources_accessed.append({
            "name": "ChEMBL",
            "status": "FAILED" if "chembl" in package.sources_failed else "SUCCESS",
            "url": u_chembl or "https://www.ebi.ac.uk/chembl/",
            "label": "Open ChEMBL",
        })
        sources_accessed.append({
            "name": "UniProt",
            "status": "FAILED" if "uniprot" in package.sources_failed else "SUCCESS",
            "url": "https://www.uniprot.org/",
            "label": "Open UniProt",
        })
        sources_accessed.append({
            "name": "Reactome",
            "status": "FAILED" if "reactome" in package.sources_failed else "SUCCESS",
            "url": "https://reactome.org/",
            "label": "Open Reactome",
        })
        u_ot = SourceURLBuilder.opentargets_disease_url(package.disease.mesh_id or package.disease.name)
        sources_accessed.append({
            "name": "Open Targets",
            "status": "SUCCESS" if package.validated_disease_genes else "NONE",
            "url": u_ot or "https://platform.opentargets.org/",
            "label": "Open Open Targets",
        })
        sources_accessed.append({
            "name": "DisGeNET",
            "status": "FAILED" if "disgenet" in package.sources_failed else "SUCCESS",
            "url": "https://www.disgenet.org/",
            "label": "Open DisGeNET",
        })
        sources_accessed.append({
            "name": "PubMed",
            "status": "FAILED" if "pubmed" in package.sources_failed else "SUCCESS",
            "url": "https://pubmed.ncbi.nlm.nih.gov/",
            "label": "Open PubMed",
        })
        sources_accessed.append({
            "name": "Europe PMC",
            "status": "SUCCESS",
            "url": "https://europepmc.org/",
            "label": "Open Europe PMC",
        })
        sources_accessed.append({
            "name": "ClinicalTrials.gov",
            "status": "FAILED" if "clinicaltrials" in package.sources_failed else "SUCCESS",
            "url": "https://clinicaltrials.gov/",
            "label": "Open ClinicalTrials.gov",
        })

        # ── Fix 6: Separate Narrative Sections ────────────────────────────────
        mechanistic_narrative = (
            f"Mechanistic Assessment: {mechanistic.level} (Score = {mechanistic.score:.3f}).\n"
            f"Literature Grounding: {mechanistic.literature_grounding_level}.\n"
            f"Candidate Biological Mechanisms Discovered: {len(mechanistic.candidate_mechanisms)}.\n"
            f"Primary Mechanistic Chain: {' → '.join(mechanistic.mechanistic_chain) if mechanistic.mechanistic_chain else 'None identified'}.\n"
            f"Rationale: {mechanistic.rationale}"
        )

        clinical_narrative = (
            f"Clinical Evidence Assessment: {support.level} Literature Support (Score = {support.score:.3f}).\n"
            f"Clinical Trial Status: {ct_status}.\n"
            f"Clinical Trial Findings: {len(package.clinical_trials)} trial(s) evaluated, {risk.failed_trial_count} clinically significant failure(s).\n"
            f"Literature Support Rationale: {support.rationale}"
        )

        safety_narrative = (
            f"Safety & Risk Assessment: Grade {safety_profile.overall_safety_grade} — {safety_desc} (Risk Score = {risk.score:.3f}, {risk.level}).\n"
            f"Boxed Warning: {'YES' if safety_profile.has_boxed_warning else 'NO'}.\n"
            f"Risk Factors & Signal Analysis: {risk.rationale}"
        )

        final_synthesis = (
            f"Synthesis & Recommendation: {recommendation.value}.\n"
            f"Regulatory Status: {scientific_context.regulatory.status} (Term: {prior_ctx.matched_indication_term or 'N/A'}).\n"
            f"1. Mechanistic Plausibility: {mechanistic.level} ({mechanistic.score:.3f})\n"
            f"2. Literature/Clinical Support: {support.level} ({support.score:.3f})\n"
            f"3. Risk & Safety Profile: {risk.level} ({risk.score:.3f}, Grade {safety_profile.overall_safety_grade})\n"
            f"Conclusion Summary: {reasons[0] if reasons else 'No recommendation reasons generated.'}"
        )

        return ScientificAuditReport(
            summary=summary,
            key_supporting_claim_ids=[str(c.id) for c in supporting],
            key_contradicting_claim_ids=contradicting_ids,
            data_gaps=data_gaps,
            confidence_narrative=confidence_narrative,
            recommendation_rationale="\n".join(rationale_lines),
            mechanistic_narrative=mechanistic_narrative,
            clinical_narrative=clinical_narrative,
            safety_narrative=safety_narrative,
            final_synthesis=final_synthesis,
            agent_verdicts=agent_verdicts,
            evaluation_pathway=prior_ctx.evaluation_pathway,
            clinical_trial_status=ct_status,
            top_citations=citations[:10],
            claims_by_source=claims_by_source,
            safety_breakdown=safety_brkdown,
            positive_factors=positive_factors,
            negative_factors=negative_factors,
            scientific_context=scientific_context.to_dict(),
            claim_citations=claim_citations,
            candidate_mechanisms=mechanistic.candidate_mechanisms,
            sources_accessed=sources_accessed,
        )

    def _extract_citations(self, evidence_records: list) -> list[str]:
        """Extract human-readable citations from evidence records.

        FIX (Issue #12, P4): Returns formatted citation strings with PMID/DOI,
        evidence type, and ERW weight. Handles both 'doi:10.' prefix (OpenAlex)
        and plain '10.' prefix, with cross-source deduplication by normalised
        DOI so the same paper does not appear twice from different sources.
        """
        citations = []
        seen_dois: set[str] = set()  # dedup: same paper from PubMed+EuropePMC+OpenAlex
        for ev in evidence_records:
            key = ev.citation_key
            ev_type = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type)
            erw = ev.erw.value
            title_short = (ev.title[:60] + "...") if ev.title and len(ev.title) > 60 else (ev.title or "")

            if key.startswith("PMID:") or key.isdigit():
                pmid = key.replace("PMID:", "").strip()
                citations.append(
                    f"PMID:{pmid} [{ev_type}, ERW:{erw:.2f}] — {title_short}"
                )
            elif key.startswith("doi:") or key.startswith("10."):
                # P4 Fix: OpenAlex produces 'doi:10.xxx', Semantic Scholar 'doi:10.xxx',
                # EuropePMC also 'doi:10.xxx'. Normalise to 'DOI:10.xxx' for display
                # and deduplicate across sources.
                doi_clean = key.replace("doi:", "").strip()
                if doi_clean in seen_dois:
                    continue  # cross-source duplicate — skip
                seen_dois.add(doi_clean)
                citations.append(
                    f"DOI:{doi_clean} [{ev_type}, ERW:{erw:.2f}] — {title_short}"
                )
            else:
                citations.append(
                    f"{key} [{ev_type}, ERW:{erw:.2f}] — {title_short}"
                )
        return citations

    def _compute_agent_verdicts(
        self,
        support: SupportAssessment,
        mechanistic: MechanisticAssessment,
        risk: RiskAssessment,
        contradictions: list[Contradiction],
        safety_profile: SafetyProfile,
        scientific_context: ScientificContext,
    ) -> dict[str, str]:
        """Compute agent-level verdicts for the report.

        FIX (Issue #17): Exposes the multi-agent architecture in the output.
        Each agent gives a verdict that maps to the underlying reasoning step.
        """
        verdicts = {}

        # Mechanistic Expert Agent
        if mechanistic.score >= 0.7:
            verdicts["Mechanistic Expert Agent"] = f"HIGH ({mechanistic.score:.3f}) — strong target-pathway evidence"
        elif mechanistic.score >= 0.4:
            verdicts["Mechanistic Expert Agent"] = f"MEDIUM ({mechanistic.score:.3f}) — partial mechanistic support"
        else:
            verdicts["Mechanistic Expert Agent"] = f"LOW ({mechanistic.score:.3f}) — insufficient mechanistic data"

        # Clinical Evidence Expert Agent
        if risk.failed_trial_count == 0 and support.evidence_count >= 5:
            verdicts["Clinical Evidence Agent"] = f"MEDIUM — {support.evidence_count} records, 0 failed trials"
        elif risk.failed_trial_count > 0:
            verdicts["Clinical Evidence Agent"] = f"LOW — {risk.failed_trial_count} failed/terminated trial(s)"
        else:
            verdicts["Clinical Evidence Agent"] = "LOW — insufficient clinical data"

        # Support Assessment Agent
        verdicts["Support Assessment Agent"] = (
            f"{support.level} ({support.score:.3f}) — "
            f"{support.evidence_count} evidence records"
        )

        # Risk Assessment Agent
        verdicts["Risk Assessment Agent"] = (
            f"{risk.level} risk ({risk.score:.3f}) — "
            f"safety grade {safety_profile.overall_safety_grade}"
        )

        # Contradiction Analysis Agent
        if not contradictions:
            verdicts["Contradiction Analysis Agent"] = "CLEAR — no directional conflicts detected"
        else:
            verdicts["Contradiction Analysis Agent"] = (
                f"CONFLICT ({len(contradictions)} contradiction(s) detected, "
                f"net score: {sum(c.contradiction_score for c in contradictions) / len(contradictions):.2f})"
            )

        # Prior Knowledge Agent (dimensional)
        sc = scientific_context
        verdicts["Prior Knowledge Agent"] = (
            f"Regulatory: {sc.regulatory.status} ({sc.regulatory.confidence:.0%}) | "
            f"Repurposing: {sc.repurposing.status} ({sc.repurposing.confidence:.0%}) | "
            f"Mechanistic: {sc.mechanistic.status} ({sc.mechanistic.confidence:.0%}) | "
            f"Clinical: {sc.clinical.status} ({sc.clinical.confidence:.0%}) | "
            f"Knowledge: {sc.knowledge_maturity.status} ({sc.knowledge_maturity.confidence:.0%})"
        )

        # Clinical Safety Agent
        verdicts["Clinical Safety Agent"] = (
            f"Grade {safety_profile.overall_safety_grade} — "
            f"{'⚠ boxed warning; ' if safety_profile.has_boxed_warning else ''}"
            f"{safety_profile.safety_termination_count} safety termination(s), "
            f"{len(safety_profile.adverse_events)} adverse event signal(s)"
        )

        return verdicts
