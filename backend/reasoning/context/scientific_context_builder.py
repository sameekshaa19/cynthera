"""ScientificContextBuilder — assembles a dimensional prior-knowledge context.

Architecture: a pure assembly stage (no retrieval, no scoring). Each dimension
is produced by the specialist component that already owns that signal:

  - Regulatory         ← PriorKnowledgeAgent (live ChEMBL ApprovalSignal)
  - Repurposing        ← PriorKnowledgeAgent (approved-elsewhere count) + pair literature
  - Mechanistic        ← MultiHopReasoner / MechanisticAssessment (validated paths)
  - Clinical           ← package.clinical_trials + evidence record types
  - KnowledgeMaturity  ← KnowledgeStore TF-IDF cache (via prior_ctx.top_entries)

Every dimension carries a status, a confidence [0.0, 1.0], and evidence
provenance. No dimension outranks another — they are orthogonal descriptors
that may legitimately overlap (e.g. a pair can be EMERGING-repurposing AND
HUMAN_EVIDENCE AND STRONG-mechanism).

The Rule Engine consumes exactly one field for its single prior-knowledge
gate: ``regulatory.status == APPROVED`` (Rule -1). Everything else is a
descriptive/transparency layer and grants no rule-bypass privilege.

Reference: prior_knowledge_agent redesign — Multi-Category / Dimensional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.core.domain.retrieval_package import RetrievalPackage

from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus

# ─────────────────────────────────────────────
# Thresholds & constants
# ─────────────────────────────────────────────

# Minimum fuzzy match confidence for a ChEMBL indication to count as "this disease"
_APPROVAL_MATCH_THRESHOLD: float = 0.35

# KnowledgeStore similarity thresholds (must mirror prior_knowledge_agent)
_CACHE_EXACT_SIM: float = 0.6
_CACHE_RELATED_SIM: float = 0.25

# Human/literature evidence types that indicate off-label or repurposing use
_HUMAN_LIT_TYPES = {
    EvidenceType.META_ANALYSIS,
    EvidenceType.RCT,
    EvidenceType.OBSERVATIONAL,
    EvidenceType.LITERATURE,
}

_HUMAN_CLINICAL_TYPES = {
    EvidenceType.META_ANALYSIS,
    EvidenceType.RCT,
    EvidenceType.OBSERVATIONAL,
}

_TERMINATED_TRIAL_STATUSES = {
    TrialOutcomeStatus.COMPLETED_FAILURE,
    TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
    TrialOutcomeStatus.TERMINATED_SAFETY,
}

# ─────────────────────────────────────────────
# Status values per dimension
# ─────────────────────────────────────────────

REGULATORY_APPROVED = "APPROVED"
REGULATORY_INVESTIGATIONAL = "INVESTIGATIONAL"
REGULATORY_NONE = "NONE"

REPURPOSING_ESTABLISHED = "ESTABLISHED"
REPURPOSING_EMERGING = "EMERGING"
REPURPOSING_NOVEL = "NOVEL"

MECHANISTIC_STRONG = "STRONG"
MECHANISTIC_MODERATE = "MODERATE"
MECHANISTIC_WEAK = "WEAK"

CLINICAL_HUMAN = "HUMAN_EVIDENCE"
CLINICAL_ANIMAL = "ANIMAL_ONLY"
CLINICAL_NONE = "NONE"

MATURITY_ESTABLISHED = "ESTABLISHED"
MATURITY_GROWING = "GROWING"
MATURITY_SPECULATIVE = "SPECULATIVE"


@dataclass
class DimensionalAssessment:
    """A single dimension of the scientific context.

    Attributes:
        dimension: Dimension name ('regulatory', 'repurposing', 'mechanistic',
            'clinical', 'knowledge_maturity').
        status: Categorical status for this dimension.
        confidence: Confidence in the assignment [0.0, 1.0].
        evidence: Human-readable provenance statements supporting the status.
    """

    dimension: str
    status: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
        }


@dataclass
class ScientificContext:
    """Orthogonal, evidence-grounded description of prior knowledge.

    Fields are independent dimensions — no priority hierarchy. Rule -1 grants
    the approved-indication bypass only when ``regulatory.status == APPROVED``.
    """

    regulatory: DimensionalAssessment
    repurposing: DimensionalAssessment
    mechanistic: DimensionalAssessment
    clinical: DimensionalAssessment
    knowledge_maturity: DimensionalAssessment
    related_pairs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        """True only when the live ChEMBL signal shows approval for this disease."""
        return self.regulatory.status == REGULATORY_APPROVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "regulatory": self.regulatory.to_dict(),
            "repurposing": self.repurposing.to_dict(),
            "mechanistic": self.mechanistic.to_dict(),
            "clinical": self.clinical.to_dict(),
            "knowledge_maturity": self.knowledge_maturity.to_dict(),
            "related_pairs": self.related_pairs,
        }


class ScientificContextBuilder:
    """Pure assembly stage combining specialist outputs into a ScientificContext.

    The builder performs no retrieval and no scoring. It reads signals that the
    pipeline has already computed and annotates them with source-reliability
    notes when a contributing source is listed in ``package.sources_failed``.
    """

    # ── Public API ──────────────────────────────

    @classmethod
    def build(
        cls,
        prior_ctx: Any,
        support: Any,
        mechanistic: Any,
        mechanistic_paths: list[Any],
        package: "RetrievalPackage",
    ) -> ScientificContext:
        """Assemble the dimensional ScientificContext from existing outputs.

        Args:
            prior_ctx: PriorKnowledgeContext from PriorKnowledgeAgent.
            support: SupportAssessment (pair-scoped literature/claims summary).
            mechanistic: MechanisticAssessment from MultiHopReasoner scoring.
            mechanistic_paths: Raw MechanisticPath list from MultiHopReasoner.
            package: Sealed RetrievalPackage (trials, evidence, approval signal).
        """
        regulatory = cls._regulatory(package)
        repurposing = cls._repurposing(prior_ctx, package)
        mechanistic_dim = cls._mechanistic(mechanistic, mechanistic_paths, package)
        clinical = cls._clinical(package)
        maturity, related_pairs = cls._maturity(prior_ctx, package)

        return ScientificContext(
            regulatory=regulatory,
            repurposing=repurposing,
            mechanistic=mechanistic_dim,
            clinical=clinical,
            knowledge_maturity=maturity,
            related_pairs=related_pairs,
        )

    # ── Dimension mappers ───────────────────────

    @staticmethod
    def _regulatory(package: "RetrievalPackage") -> DimensionalAssessment:
        """Regulatory Status — live ChEMBL ApprovalSignal only."""
        signal = getattr(package, "approval_signal", None)
        sources_failed = getattr(package, "sources_failed", [])

        if signal is None:
            if "chembl" in sources_failed:
                return DimensionalAssessment(
                    "regulatory", REGULATORY_NONE, 0.0,
                    ["ChEMBL unavailable (source failed)"],
                )
            return DimensionalAssessment(
                "regulatory", REGULATORY_NONE, 0.0,
                ["No ChEMBL indication match found for this disease"],
            )

        if signal.is_approved and signal.match_confidence >= _APPROVAL_MATCH_THRESHOLD:
            return DimensionalAssessment(
                "regulatory", REGULATORY_APPROVED, round(signal.match_confidence, 4),
                [
                    f"ChEMBL max_phase_for_ind = 4 for '{signal.matched_indication_term}'",
                    f"match confidence {signal.match_confidence:.0%}",
                ],
            )

        if signal.max_phase in (1, 2, 3) and signal.match_confidence >= _APPROVAL_MATCH_THRESHOLD:
            phase_conf = {1: 0.45, 2: 0.60, 3: 0.75}.get(signal.max_phase, 0.45)
            return DimensionalAssessment(
                "regulatory", REGULATORY_INVESTIGATIONAL, phase_conf,
                [
                    f"ChEMBL {signal.phase_label} for '{signal.matched_indication_term}' "
                    f"(max_phase_for_ind = {signal.max_phase})",
                ],
            )

        return DimensionalAssessment(
            "regulatory", REGULATORY_NONE, 0.0,
            [f"No ChEMBL indication match above confidence {_APPROVAL_MATCH_THRESHOLD:.0%}"],
        )

    @staticmethod
    def _repurposing(prior_ctx: Any, package: "RetrievalPackage") -> DimensionalAssessment:
        """Repurposing Status — approved elsewhere + off-label pair evidence."""
        approved_elsewhere = getattr(prior_ctx, "approved_indications_count", 0) >= 1
        this_approved = bool(getattr(prior_ctx, "is_approved_indication", False))
        pair_lit = any(
            getattr(ev, "evidence_type", None) in _HUMAN_LIT_TYPES
            for ev in getattr(package, "evidence_records", [])
        )

        if approved_elsewhere and not this_approved and pair_lit:
            return DimensionalAssessment(
                "repurposing", REPURPOSING_ESTABLISHED, 0.8,
                [
                    f"Drug approved for {prior_ctx.approved_indications_count} other "
                    "indication(s) in ChEMBL",
                    "Pair-scoped human literature supports off-label use for this disease",
                ],
            )

        if (approved_elsewhere and not this_approved) or pair_lit:
            evidence: list[str] = []
            if approved_elsewhere and not this_approved:
                evidence.append(
                    f"Drug approved for {prior_ctx.approved_indications_count} other "
                    "indication(s) in ChEMBL (off-label for this disease)"
                )
            if pair_lit:
                evidence.append("Pair-scoped literature exists for this disease")
            return DimensionalAssessment("repurposing", REPURPOSING_EMERGING, 0.5, evidence)

        return DimensionalAssessment(
            "repurposing", REPURPOSING_NOVEL, 0.0,
            ["No established off-label or repurposing evidence for this pair"],
        )

    @staticmethod
    def _mechanistic(
        mechanistic: Any,
        mechanistic_paths: list[Any],
        package: "RetrievalPackage",
    ) -> DimensionalAssessment:
        """Mechanistic Status — validated MultiHopReasoner paths + score."""
        score = float(getattr(mechanistic, "score", 0.0))
        if score >= 0.7:
            status = MECHANISTIC_STRONG
        elif score >= 0.4:
            status = MECHANISTIC_MODERATE
        else:
            status = MECHANISTIC_WEAK

        evidence: list[str] = []
        for path in (mechanistic_paths or [])[:2]:
            desc = getattr(path, "description", "") or ""
            if desc:
                evidence.append(f"Validated path: {desc}")
        if not evidence:
            evidence.append("No validated mechanistic paths traced")

        if "reactome" in getattr(package, "sources_failed", []):
            evidence.append("Reactome unavailable — mechanism dimension understated")
        if "chembl" in getattr(package, "sources_failed", []):
            evidence.append("ChEMBL unavailable — target data may be degraded")

        return DimensionalAssessment("mechanistic", status, round(score, 4), evidence)

    @staticmethod
    def _clinical(package: "RetrievalPackage") -> DimensionalAssessment:
        """Clinical Status — registered trials + evidence record types."""
        trials = getattr(package, "clinical_trials", [])
        ct_failed = "clinicaltrials" in getattr(package, "sources_failed", [])
        ev_types = {
            getattr(ev, "evidence_type", None)
            for ev in getattr(package, "evidence_records", [])
        }
        has_human_rec = bool(ev_types & _HUMAN_CLINICAL_TYPES)
        has_animal_rec = EvidenceType.IN_VIVO in ev_types

        evidence: list[str] = []
        if trials:
            statuses = {t.status for t in trials}
            has_active = TrialOutcomeStatus.ACTIVE in statuses
            has_success = TrialOutcomeStatus.COMPLETED_SUCCESS in statuses
            has_terminated = bool(statuses & _TERMINATED_TRIAL_STATUSES)
            if has_active:
                conf = 0.8
            elif has_success:
                conf = 0.9
            elif has_terminated:
                conf = 0.5
            else:
                conf = 0.7
            trials_summary = ", ".join(
                f"{t.nct_id} ({t.phase}, {t.status.value})" for t in trials[:5]
            )
            evidence.append(
                f"{len(trials)} registered trial(s) for this pair: {trials_summary}"
            )
            status = CLINICAL_HUMAN
        elif has_human_rec:
            status = CLINICAL_HUMAN
            conf = 0.7
            evidence.append(
                "Human clinical literature (RCT / meta-analysis / observational) for this pair"
            )
        elif has_animal_rec:
            status = CLINICAL_ANIMAL
            conf = 0.4
            evidence.append("Animal (in vivo) evidence only for this pair")
        else:
            status = CLINICAL_NONE
            conf = 0.0
            evidence.append("No human or animal clinical evidence for this pair")

        if ct_failed:
            evidence.append("ClinicalTrials.gov unavailable — trial status incomplete")
            if status == CLINICAL_HUMAN and not trials:
                conf = min(conf, 0.2)

        return DimensionalAssessment("clinical", status, round(conf, 4), evidence)

    @staticmethod
    def _maturity(
        prior_ctx: Any, package: "RetrievalPackage"
    ) -> tuple[DimensionalAssessment, list[dict[str, Any]]]:
        """Knowledge Maturity — KnowledgeStore TF-IDF cache similarity."""
        entries = list(getattr(prior_ctx, "top_entries", []) or [])
        if not entries:
            return (
                DimensionalAssessment(
                    "knowledge_maturity", MATURITY_SPECULATIVE, 0.0,
                    ["No prior knowledge cache entries for this pair"],
                ),
                [],
            )

        top = entries[0]
        sim = float(top.get("similarity", 0.0))
        drug_l = package.drug.name.lower()
        disease_l = package.disease.name.lower()
        exact = (
            str(top.get("drug", "")).lower() == drug_l
            and str(top.get("disease", "")).lower() == disease_l
        )
        established = bool(top.get("established"))

        related_pairs = [
            {
                "drug": e.get("drug"),
                "disease": e.get("disease"),
                "similarity": round(float(e.get("similarity", 0.0)), 4),
            }
            for e in entries[:3]
        ]

        if exact and established and sim >= _CACHE_EXACT_SIM:
            return (
                DimensionalAssessment(
                    "knowledge_maturity", MATURITY_ESTABLISHED, round(min(1.0, 0.6 + sim * 0.4), 4),
                    [
                        f"Exact-pair cache entry ({sim:.0%} similarity, "
                        f"{top.get('evidence_level', 'unknown')} evidence level)"
                    ],
                ),
                related_pairs,
            )

        if sim >= _CACHE_RELATED_SIM:
            return (
                DimensionalAssessment(
                    "knowledge_maturity", MATURITY_GROWING, round(sim, 4),
                    [
                        f"Related cache entry: {top.get('drug')} → {top.get('disease')} "
                        f"(similarity {sim:.2f})"
                    ],
                ),
                related_pairs,
            )

        evidence = (
            [f"Weak cache signal (similarity {sim:.2f})"]
            if sim > 0
            else ["No prior knowledge cache entries for this pair"]
        )
        return (
            DimensionalAssessment(
                "knowledge_maturity", MATURITY_SPECULATIVE, round(sim, 4), evidence
            ),
            related_pairs,
        )
