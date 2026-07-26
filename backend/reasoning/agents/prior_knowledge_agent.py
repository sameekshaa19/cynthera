"""PriorKnowledgeAgent — retrieves and structures prior repurposing knowledge.

Phase 2 enhancement: queries the KnowledgeStore for semantically similar
drug-disease pairs and returns a PriorKnowledgeContext that enriches the
reasoning pipeline with established scientific knowledge.

Reference: Phase 2 — Prior Knowledge Agent
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.infrastructure.knowledge.knowledge_store import (
    KnowledgeEntry,
    KnowledgeStore,
)

logger = logging.getLogger(__name__)


@dataclass
class PriorKnowledgeContext:
    """Structured prior knowledge context for a drug-disease evaluation.

    Attributes:
        has_established_precedent: True if an approved repurposing is known.
        top_entries: Most relevant knowledge entries (ranked by similarity).
        mechanistic_hints: Key mechanistic pathway hints from prior knowledge.
        evidence_boost: Score adjustment signal [−0.2, +0.3] for scoring.
        confidence_adjustment: Modifier for overall confidence [−0.1, +0.1].
        narrative: Human-readable summary of prior knowledge.
    """

    has_established_precedent: bool = False
    top_entries: list[dict[str, Any]] = field(default_factory=list)
    mechanistic_hints: list[str] = field(default_factory=list)
    evidence_boost: float = 0.0
    confidence_adjustment: float = 0.0
    narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_established_precedent": self.has_established_precedent,
            "top_entries": self.top_entries,
            "mechanistic_hints": self.mechanistic_hints,
            "evidence_boost": self.evidence_boost,
            "confidence_adjustment": self.confidence_adjustment,
            "narrative": self.narrative,
        }


class PriorKnowledgeAgent:
    """Agent that retrieves and structures prior drug repurposing knowledge.

    Queries the KnowledgeStore for semantically similar known cases and
    computes score adjustment signals based on established precedent.

    The evidence_boost is used to adjust the Support Score and Mechanistic
    Score in the reasoning pipeline based on prior knowledge quality.

    Args:
        knowledge_store: KnowledgeStore instance (injected or shared).
    """

    # Similarity thresholds
    _HIGH_SIM: float = 0.6  # Very likely same pair
    _MED_SIM: float = 0.25  # Related case
    _LOW_SIM: float = 0.05  # Weak signal

    def __init__(self, knowledge_store: KnowledgeStore | None = None) -> None:
        """Initialize PriorKnowledgeAgent.

        Args:
            knowledge_store: Shared KnowledgeStore. Creates one if not provided.
        """
        self._store = knowledge_store or KnowledgeStore()
        logger.info("PriorKnowledgeAgent initialized")

    def retrieve(self, drug_name: str, disease_name: str) -> PriorKnowledgeContext:
        """Retrieve prior knowledge for a drug-disease pair.

        Args:
            drug_name: Drug name to query.
            disease_name: Disease name to query.

        Returns:
            PriorKnowledgeContext with enrichment signals.
        """
        logger.info(
            "prior_knowledge_retrieval_start",
            extra={"drug": drug_name, "disease": disease_name},
        )

        entries = self._store.retrieve_prior_knowledge(
            drug=drug_name.lower(),
            disease=disease_name.lower(),
            top_k=5,
            min_similarity=self._LOW_SIM,
        )

        if not entries:
            return PriorKnowledgeContext(
                narrative=(
                    f"No prior knowledge found for {drug_name} in {disease_name}. "
                    "This appears to be a novel repurposing hypothesis."
                )
            )

        top = entries[0]
        has_established = top.established and top.similarity >= self._HIGH_SIM

        evidence_boost = self._compute_evidence_boost(entries)
        confidence_adjustment = self._compute_confidence_adjustment(entries)
        mechanistic_hints = self._extract_mechanistic_hints(entries)

        narrative = self._build_narrative(
            drug_name=drug_name,
            disease_name=disease_name,
            entries=entries,
            has_established=has_established,
            evidence_boost=evidence_boost,
        )

        ctx = PriorKnowledgeContext(
            has_established_precedent=has_established,
            top_entries=[e.to_dict() for e in entries[:3]],
            mechanistic_hints=mechanistic_hints,
            evidence_boost=evidence_boost,
            confidence_adjustment=confidence_adjustment,
            narrative=narrative,
        )

        logger.info(
            "prior_knowledge_retrieval_complete",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "entries_found": len(entries),
                "has_established_precedent": has_established,
                "evidence_boost": evidence_boost,
            },
        )

        return ctx

    # ─────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────

    def _compute_evidence_boost(self, entries: list[KnowledgeEntry]) -> float:
        """Compute evidence score boost based on prior knowledge quality.

        Returns a value in [−0.2, +0.3]:
        - Established HIGH evidence, high similarity → +0.25 to +0.30
        - Established MEDIUM, moderate similarity → +0.10 to +0.20
        - Unestablished, low similarity → 0.0 to +0.05
        - No relevant entries → 0.0
        """
        if not entries:
            return 0.0

        boost = 0.0
        for entry in entries[:3]:
            sim = entry.similarity
            level_multiplier = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}.get(
                entry.evidence_level, 0.2
            )
            established_bonus = 0.1 if entry.established else 0.0
            boost += sim * level_multiplier * 0.3 + established_bonus * sim

        return round(min(0.3, max(-0.2, boost)), 4)

    def _compute_confidence_adjustment(self, entries: list[KnowledgeEntry]) -> float:
        """Compute confidence adjustment based on prior knowledge depth.

        Returns a value in [−0.1, +0.1].
        """
        if not entries:
            return 0.0
        top = entries[0]
        if top.similarity >= self._HIGH_SIM and top.established:
            return 0.1
        if top.similarity >= self._MED_SIM:
            return 0.05
        return 0.0

    def _extract_mechanistic_hints(self, entries: list[KnowledgeEntry]) -> list[str]:
        """Extract mechanistic pathway hints from top entries."""
        hints: list[str] = []
        for entry in entries[:3]:
            if entry.similarity >= self._LOW_SIM and entry.mechanism:
                # Split mechanism into steps and take the most relevant
                steps = entry.mechanism.split("→")
                if steps:
                    hints.append(f"[{entry.drug.title()}] {entry.mechanism}")
        return hints[:5]

    def _build_narrative(
        self,
        drug_name: str,
        disease_name: str,
        entries: list[KnowledgeEntry],
        has_established: bool,
        evidence_boost: float,
    ) -> str:
        """Build a human-readable prior knowledge narrative."""
        parts: list[str] = []

        if has_established:
            top = entries[0]
            parts.append(
                f"✅ Established precedent found: {drug_name} has been repurposed "
                f"for {disease_name} (or a closely related indication). "
                f"Evidence level: {top.evidence_level}."
            )
            if top.notes:
                parts.append(top.notes)
        else:
            top = entries[0]
            if top.similarity >= self._MED_SIM:
                parts.append(
                    f"Related prior knowledge found (similarity: {top.similarity:.2f}): "
                    f"{top.drug.title()} in {top.disease.title()} — {top.mechanism}."
                )
            else:
                parts.append(
                    f"Weak prior knowledge signal for {drug_name} in {disease_name}. "
                    "This may be a genuinely novel repurposing hypothesis."
                )

        if evidence_boost > 0.1:
            parts.append(
                f"Prior knowledge contributes a positive evidence boost of {evidence_boost:.2f} "
                "to the support and mechanistic scores."
            )
        elif evidence_boost < 0:
            parts.append(
                "Prior knowledge suggests this repurposing hypothesis may have been investigated "
                "with limited success — modest evidence penalty applied."
            )

        return " ".join(parts)
