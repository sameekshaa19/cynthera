"""PriorKnowledgeAgent — infers prior knowledge status from retrieved biomedical evidence.

Architecture: This agent does NOT contain biomedical facts.
It receives the sealed RetrievalPackage (which contains live ChEMBL indication data,
approval signals, and literature evidence) and INFERS the drug-disease relationship
status from that retrieved evidence.

Classification logic (all evidence-driven):
  APPROVED_INDICATION     → ChEMBL max_phase_for_ind == 4 AND indication matches disease
  PHASE_III_INVESTIGATION → ChEMBL max_phase_for_ind == 3 AND indication matches disease
  PHASE_II_INVESTIGATION  → ChEMBL max_phase_for_ind == 2 AND indication matches disease
  PHASE_I_INVESTIGATION   → ChEMBL max_phase_for_ind == 1 AND indication matches disease
  NOVEL_HYPOTHESIS        → No matching indication found OR max_phase == 0

Approval status is established ONLY from the live ChEMBL ApprovalSignal.
The KnowledgeStore (TF-IDF cache) NEVER grants approval — cache entries are
retrieved as a secondary signal (related pairs, mechanistic hints, evidence
boost) but the evaluation_pathway is never promoted to APPROVED_INDICATION
from cache data. A richer, multi-dimensional interpretation of this context
is assembled downstream by ScientificContextBuilder.

Reference: 04_REASONING_SPECIFICATION.md, 05_AGENT_SPECIFICATIONS.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core.domain.retrieval_package import RetrievalPackage

from backend.core.domain.approval_signal import ApprovalSignal
from backend.infrastructure.knowledge.knowledge_store import (
    KnowledgeEntry,
    KnowledgeStore,
)

logger = logging.getLogger(__name__)

# Minimum approval confidence to treat a drug-disease pair as approved
_APPROVAL_CONFIDENCE_THRESHOLD = 0.30

# Phase labels for human-readable output
_PHASE_NARRATIVE: dict[str, str] = {
    "APPROVED_INDICATION": (
        "This drug has an FDA/EMA approved indication that matches the queried disease "
        "(ChEMBL max_phase_for_ind = 4). This is an established therapeutic use, "
        "not a repurposing hypothesis."
    ),
    "PHASE_III_INVESTIGATION": (
        "This drug is in Phase III clinical trials for an indication matching "
        "the queried disease (ChEMBL max_phase_for_ind = 3). "
        "Strong clinical evidence available."
    ),
    "PHASE_II_INVESTIGATION": (
        "This drug is in Phase II clinical trials for an indication matching "
        "the queried disease (ChEMBL max_phase_for_ind = 2). "
        "Early clinical evidence available."
    ),
    "PHASE_I_INVESTIGATION": (
        "This drug has Phase I trial data for an indication related to "
        "the queried disease (ChEMBL max_phase_for_ind = 1). "
        "Safety data available, efficacy evidence limited."
    ),
    "NOVEL_HYPOTHESIS": (
        "No prior indication match found for this drug-disease pair in ChEMBL. "
        "This is a novel repurposing hypothesis. "
        "All evidence should be treated as exploratory."
    ),
}


@dataclass
class PriorKnowledgeContext:
    """Structured prior knowledge context inferred from retrieved biomedical data.

    All fields are inferred from retrieved evidence (ChEMBL indications,
    literature signals). None are hardcoded.

    Attributes:
        evaluation_pathway: Classification of the drug-disease relationship.
        is_approved_indication: True if ChEMBL indicates max_phase_for_ind == 4.
        approval_type: Detailed classification string.
        approval_confidence: Confidence in the approval status inference [0.0, 1.0].
        matched_indication_term: The indication term from ChEMBL that matched.
        has_established_precedent: True if approved or strong Phase III evidence.
        mechanistic_hints: Pathway/mechanism hints from prior knowledge cache.
        evidence_boost: Score adjustment signal [-0.2, +0.3] for scoring.
        confidence_adjustment: Modifier for overall confidence [-0.1, +0.1].
        narrative: Human-readable summary of prior knowledge status.
        top_entries: Most relevant knowledge cache entries (retrieved data only).
        approved_indications_count: Total approved indications for this drug.
    """

    evaluation_pathway: str = "NOVEL_HYPOTHESIS"
    is_approved_indication: bool = False
    approval_type: str = "NOVEL_HYPOTHESIS"
    approval_confidence: float = 0.0
    matched_indication_term: str = ""
    has_established_precedent: bool = False
    mechanistic_hints: list[str] = field(default_factory=list)
    evidence_boost: float = 0.0
    confidence_adjustment: float = 0.0
    narrative: str = ""
    top_entries: list[dict[str, Any]] = field(default_factory=list)
    approved_indications_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_pathway": self.evaluation_pathway,
            "is_approved_indication": self.is_approved_indication,
            "approval_type": self.approval_type,
            "approval_confidence": self.approval_confidence,
            "matched_indication_term": self.matched_indication_term,
            "has_established_precedent": self.has_established_precedent,
            "mechanistic_hints": self.mechanistic_hints,
            "evidence_boost": self.evidence_boost,
            "confidence_adjustment": self.confidence_adjustment,
            "narrative": self.narrative,
            "top_entries": self.top_entries,
            "approved_indications_count": self.approved_indications_count,
        }


class PriorKnowledgeAgent:
    """Agent that infers prior drug-disease relationship status from retrieved evidence.

    This agent operates in two modes:

    1. PRIMARY MODE: Reads the ApprovalSignal from the RetrievalPackage.
       The signal was produced by the retrieval pipeline from live ChEMBL
       drug_indication API calls. The agent interprets this signal to
       classify the evaluation pathway.

    2. SECONDARY MODE: Queries the KnowledgeStore TF-IDF cache for
       additional context from previously retrieved pairs. The cache
       stores only data that was originally retrieved externally.

    Critically: this agent does NOT contain any drug names, disease names,
    or approval facts in its source code. All conclusions are drawn from
    retrieved data passed to it.

    Args:
        knowledge_store: KnowledgeStore instance (cache of retrieved data).
    """

    # Similarity thresholds for secondary knowledge cache
    _HIGH_SIM: float = 0.6
    _MED_SIM: float = 0.25
    _LOW_SIM: float = 0.05

    def __init__(self, knowledge_store: KnowledgeStore | None = None) -> None:
        self._store = knowledge_store or KnowledgeStore()
        logger.info("PriorKnowledgeAgent initialized")

    def retrieve(
        self,
        drug_name: str,
        disease_name: str,
        approval_signal: ApprovalSignal | None = None,
    ) -> PriorKnowledgeContext:
        """Infer prior knowledge status for a drug-disease pair.

        Args:
            drug_name: Drug name (for cache lookup and narrative).
            disease_name: Disease name (for cache lookup and narrative).
            approval_signal: ApprovalSignal retrieved from ChEMBL by the
                pipeline. If None, falls back to cache-only inference.

        Returns:
            PriorKnowledgeContext with inferred evaluation pathway and signals.
        """
        logger.info(
            "prior_knowledge_retrieval_start",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "has_approval_signal": approval_signal is not None,
            },
        )

        # ── Primary: infer from ChEMBL approval signal ───────────────────
        if approval_signal is not None:
            ctx = self._infer_from_approval_signal(
                drug_name, disease_name, approval_signal
            )
        else:
            ctx = self._infer_from_cache_only(drug_name, disease_name)

        logger.info(
            "prior_knowledge_retrieval_complete",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "evaluation_pathway": ctx.evaluation_pathway,
                "is_approved": ctx.is_approved_indication,
                "approval_confidence": ctx.approval_confidence,
            },
        )
        return ctx

    # ─────────────────────────────────────────────
    # Primary Inference: From ApprovalSignal
    # ─────────────────────────────────────────────

    def _infer_from_approval_signal(
        self,
        drug_name: str,
        disease_name: str,
        signal: ApprovalSignal,
    ) -> PriorKnowledgeContext:
        """Build context from a live ChEMBL ApprovalSignal.

        No drug names, disease names, or approval facts are referenced here.
        All classification is based on the numeric max_phase value and the
        match_confidence from fuzzy disease name matching.
        """
        pathway = signal.evaluation_pathway
        is_approved = signal.is_approved
        confidence = signal.match_confidence

        # Secondary: supplement with cache entries
        cache_entries = self._store.retrieve_prior_knowledge(
            drug=drug_name.lower(),
            disease=disease_name.lower(),
            top_k=3,
            min_similarity=self._LOW_SIM,
        )
        mechanistic_hints = self._extract_mechanistic_hints(cache_entries)

        # Compute score boosts from approval signal
        evidence_boost = self._compute_evidence_boost_from_signal(signal)
        confidence_adj = self._compute_confidence_adjustment_from_signal(signal)

        # Build narrative from retrieved evidence
        narrative = self._build_signal_narrative(
            drug_name, disease_name, signal, cache_entries
        )

        has_precedent = is_approved or (
            signal.max_phase >= 3 and confidence >= _APPROVAL_CONFIDENCE_THRESHOLD
        )

        return PriorKnowledgeContext(
            evaluation_pathway=pathway,
            is_approved_indication=is_approved,
            approval_type=pathway,
            approval_confidence=confidence,
            matched_indication_term=signal.matched_indication_term,
            has_established_precedent=has_precedent,
            mechanistic_hints=mechanistic_hints,
            evidence_boost=evidence_boost,
            confidence_adjustment=confidence_adj,
            narrative=narrative,
            top_entries=[e.to_dict() for e in cache_entries[:3]],
            approved_indications_count=signal.approved_indications_count,
        )

    # ─────────────────────────────────────────────
    # Fallback: Cache-Only Inference
    # ─────────────────────────────────────────────

    def _infer_from_cache_only(
        self,
        drug_name: str,
        disease_name: str,
    ) -> PriorKnowledgeContext:
        """Infer from KnowledgeStore cache only (used when ChEMBL signal unavailable).

        The cache contains only previously retrieved knowledge, never manually
        authored entries (except for the small seed set of known repurposing
        cases that serves as a warm start until the database accumulates
        retrieved data).

        IMPORTANT: cache data never grants approval. Without a live ChEMBL
        signal the pathway is always NOVEL_HYPOTHESIS and is_approved_indication
        is always False. Cache evidence still contributes an evidence boost,
        confidence adjustment, mechanistic hints, and related-pair context.
        """
        entries = self._store.retrieve_prior_knowledge(
            drug=drug_name.lower(),
            disease=disease_name.lower(),
            top_k=5,
            min_similarity=self._LOW_SIM,
        )

        pathway = "NOVEL_HYPOTHESIS"
        is_approved = False
        has_precedent = False

        evidence_boost = self._compute_evidence_boost_from_cache(entries)
        confidence_adj = self._compute_confidence_adjustment_from_cache(entries)
        mechanistic_hints = self._extract_mechanistic_hints(entries)

        if not entries:
            narrative = (
                f"No ChEMBL indication data available and no cache entries found "
                f"for {drug_name} → {disease_name}. "
                "Treating as a novel repurposing hypothesis. "
                "Evidence evaluated on its own merits."
            )
        else:
            narrative = self._build_cache_narrative(
                drug_name, disease_name, entries, evidence_boost
            )

        top = entries[0] if entries else None

        return PriorKnowledgeContext(
            evaluation_pathway=pathway,
            is_approved_indication=is_approved,
            approval_type=pathway,
            approval_confidence=0.0,
            matched_indication_term=(
                f"{top.drug} → {top.disease}" if top else ""
            ),
            has_established_precedent=has_precedent,
            mechanistic_hints=mechanistic_hints,
            evidence_boost=evidence_boost,
            confidence_adjustment=confidence_adj,
            narrative=narrative,
            top_entries=[e.to_dict() for e in entries[:3]],
            approved_indications_count=0,
        )

    # ─────────────────────────────────────────────
    # Score Computation Helpers
    # ─────────────────────────────────────────────

    def _compute_evidence_boost_from_signal(self, signal: ApprovalSignal) -> float:
        """Compute evidence boost from ChEMBL approval signal.

        Logic is generic — based on phase number, not drug/disease names:
        - Phase 4 (approved): +0.25 boost (established clinical use)
        - Phase 3: +0.15 boost (strong clinical evidence)
        - Phase 2: +0.08 boost (early clinical evidence)
        - Phase 1: +0.03 boost (safety data only)
        - Phase 0: 0.0 (no clinical data)
        """
        phase_boost = {4: 0.25, 3: 0.15, 2: 0.08, 1: 0.03, 0: 0.0}
        base = phase_boost.get(signal.max_phase, 0.0)
        # Scale by match confidence
        return round(min(0.30, base * max(0.5, signal.match_confidence)), 4)

    def _compute_confidence_adjustment_from_signal(self, signal: ApprovalSignal) -> float:
        """Compute confidence adjustment from approval signal."""
        if signal.max_phase == 4 and signal.match_confidence >= 0.5:
            return 0.10
        if signal.max_phase >= 3 and signal.match_confidence >= 0.30:
            return 0.05
        return 0.0

    def _compute_evidence_boost_from_cache(self, entries: list[KnowledgeEntry]) -> float:
        """Compute evidence boost from cache entries."""
        if not entries:
            return 0.0
        boost = 0.0
        for entry in entries[:3]:
            sim = entry.similarity
            level_multiplier = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}.get(entry.evidence_level, 0.2)
            established_bonus = 0.1 if entry.established else 0.0
            boost += sim * level_multiplier * 0.3 + established_bonus * sim
        return round(min(0.3, max(-0.2, boost)), 4)

    def _compute_confidence_adjustment_from_cache(self, entries: list[KnowledgeEntry]) -> float:
        """Compute confidence adjustment from cache entries."""
        if not entries:
            return 0.0
        top = entries[0]
        if top.similarity >= self._HIGH_SIM and top.established:
            return 0.1
        if top.similarity >= self._MED_SIM:
            return 0.05
        return 0.0

    def _extract_mechanistic_hints(self, entries: list[KnowledgeEntry]) -> list[str]:
        """Extract mechanistic pathway hints from cache entries."""
        hints: list[str] = []
        for entry in entries[:3]:
            if entry.similarity >= self._LOW_SIM and entry.mechanism:
                hints.append(f"[Cache] {entry.mechanism}")
        return hints[:5]

    # ─────────────────────────────────────────────
    # Narrative Builders
    # ─────────────────────────────────────────────

    def _build_signal_narrative(
        self,
        drug_name: str,
        disease_name: str,
        signal: ApprovalSignal,
        cache_entries: list[KnowledgeEntry],
    ) -> str:
        """Build a human-readable narrative from the approval signal."""
        base_narrative = _PHASE_NARRATIVE.get(
            signal.evaluation_pathway,
            "Evaluation pathway unknown. Evidence evaluated on its own merits.",
        )

        parts = [base_narrative]

        if signal.matched_indication_term:
            parts.append(
                f"ChEMBL indication match: '{signal.matched_indication_term}' "
                f"(match confidence: {signal.match_confidence:.2%}, "
                f"max_phase_for_ind: {signal.max_phase})."
            )

        if signal.approved_indications_count > 0:
            parts.append(
                f"This drug has {signal.approved_indications_count} total "
                f"approved indication(s) in ChEMBL."
            )

        if cache_entries:
            top = cache_entries[0]
            if top.similarity >= self._MED_SIM:
                parts.append(
                    f"Related cache entry: {top.drug.title()} → {top.disease.title()} "
                    f"(cache similarity: {top.similarity:.2f})."
                )

        return " ".join(parts)

    def _build_cache_narrative(
        self,
        drug_name: str,
        disease_name: str,
        entries: list[KnowledgeEntry],
        evidence_boost: float,
    ) -> str:
        """Build narrative from cache entries only.

        Cache data never grants approval — the narrative reports related
        prior knowledge but always notes that live ChEMBL data was unavailable.
        """
        parts: list[str] = []
        top = entries[0]

        if top.similarity >= self._MED_SIM:
            parts.append(
                f"Related cache entry found (similarity: {top.similarity:.2f}): "
                f"{top.drug.title()} → {top.disease.title()}."
            )
        else:
            parts.append(
                f"Weak cache signal for {drug_name} → {disease_name}. "
                "Treating as novel repurposing hypothesis. "
                "ChEMBL live indication data was unavailable."
            )

        if evidence_boost > 0.1:
            parts.append(
                f"Cache provides a positive evidence boost of {evidence_boost:.2f}."
            )

        return " ".join(parts)
