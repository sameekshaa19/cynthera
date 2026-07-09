"""
MoA Cross-Verification & Conflict Mapping Agent.

Validates targets, scores mechanism strength, and detects
conflicting MoA claims. Acts as a biological quality gate
between MoA Enumeration and Disease Relevance.
"""
from typing import List, Dict, Tuple, Optional
from enum import Enum

from models.data_models import (
    MOAChain,
    Target,
    Pathway,
    Conflict,
    Evidence,
    EvidenceSource,
    ConfidenceScore,
    ConfidenceLevel,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class MechanismStrength(str, Enum):
    """Mechanism strength classification."""
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


# Organism / cell-line names that sometimes leak through as targets
NON_PROTEIN_BLACKLIST = {
    'homo sapiens', 'mus musculus', 'rattus norvegicus',
    'cavia porcellus', 'canis lupus familiaris',
    'hepatocyte', 'l6', 'k562', 'hela', 'hek293',
    'cho', 'jurkat', 'mcf-7', 'mcf7', 'a549',
    'admet', 'unchecked', 'unknown', 'unknown target',
    'no relevant target', 'not determined', 'not assigned',
    'unspecified', 'selectivity', 'cell',
}


class MoACrossVerificationAgent:
    """
    Agent responsible for validating and cross-verifying mechanisms of action.

    Performs three functions:
    1. Target Validation  - enforces molecular identity requirements
    2. Strength Scoring   - classifies mechanism evidence as STRONG/MEDIUM/WEAK
    3. Conflict Detection - flags contradictory action types for the same target
    """

    def __init__(self):
        """Initialize the cross-verification agent."""
        logger.info("MoA Cross-Verification Agent initialized")

    def process(
        self,
        moa_chains: List[MOAChain]
    ) -> Tuple[List[MOAChain], List[Conflict], Dict[str, str]]:
        """
        Main processing method.

        Args:
            moa_chains: Raw MoA chains from the enumeration agent

        Returns:
            Tuple of:
            - Cleaned MoA chains (with validated targets)
            - List of detected Conflict objects
            - Verification summary dict (for synthesis agent)
        """
        logger.info("--- Phase 1.5: MoA Cross-Verification ---")

        all_targets_before = 0
        all_targets_after = 0
        cleaned_chains = []
        all_conflicts: List[Conflict] = []
        strength_distribution: Dict[str, int] = {
            MechanismStrength.STRONG: 0,
            MechanismStrength.MEDIUM: 0,
            MechanismStrength.WEAK: 0,
        }

        for chain in moa_chains:
            all_targets_before += len(chain.targets)

            # Step 1: Validate targets
            valid_targets = self._validate_targets(chain.targets)
            all_targets_after += len(valid_targets)

            # Step 2: Deduplicate by UniProt ID (post-verification)
            valid_targets = self._deduplicate_targets(valid_targets)

            # Step 3: Score mechanism strength per target
            target_strengths = {}
            for target in valid_targets:
                strength = self._score_mechanism_strength(target)
                target_strengths[target.gene_symbol or target.name] = strength
                strength_distribution[strength] += 1

            # Step 4: Detect conflicts within this chain
            conflicts = self._detect_conflicts(valid_targets)
            all_conflicts.extend(conflicts)

            # Rebuild chain with validated targets
            if valid_targets:
                cleaned_chain = chain.copy(update={
                    'targets': valid_targets,
                })
                cleaned_chains.append(cleaned_chain)
            else:
                logger.warning(
                    f"Chain '{chain.mechanism_description[:60]}' "
                    f"dropped: no valid targets survived verification"
                )

        # Calculate mechanism quality score
        removed = all_targets_before - all_targets_after
        removal_ratio = removed / max(all_targets_before, 1)
        mechanism_quality = max(1.0 - removal_ratio, 0.0)

        # Build verification summary
        summary = {
            'targets_before': str(all_targets_before),
            'targets_after': str(all_targets_after),
            'targets_removed': str(removed),
            'conflict_count': str(len(all_conflicts)),
            'mechanism_quality': f"{mechanism_quality:.2f}",
            'strength_strong': str(strength_distribution[MechanismStrength.STRONG]),
            'strength_medium': str(strength_distribution[MechanismStrength.MEDIUM]),
            'strength_weak': str(strength_distribution[MechanismStrength.WEAK]),
        }

        logger.info(
            f"Cross-verification complete: "
            f"{all_targets_before} -> {all_targets_after} targets "
            f"({removed} removed, quality={mechanism_quality:.2f}), "
            f"{len(all_conflicts)} conflict(s) detected"
        )
        logger.info(
            f"Mechanism strengths: "
            f"STRONG={strength_distribution[MechanismStrength.STRONG]}, "
            f"MEDIUM={strength_distribution[MechanismStrength.MEDIUM]}, "
            f"WEAK={strength_distribution[MechanismStrength.WEAK]}"
        )

        return cleaned_chains, all_conflicts, summary

    def _validate_targets(self, targets: List[Target]) -> List[Target]:
        """
        Validate targets for molecular identity.

        Requirements:
        - Must have gene_symbol OR uniprot_id
        - Name must not be a known non-protein entity
        """
        valid = []
        for target in targets:
            name_lower = target.name.lower().strip()

            # Check blacklist
            if name_lower in NON_PROTEIN_BLACKLIST:
                logger.debug(f"Filtering blacklisted target: '{target.name}'")
                continue

            # Must have molecular identity
            if not target.gene_symbol and not target.uniprot_id:
                logger.debug(
                    f"Filtering target without identity: '{target.name}'"
                )
                continue

            valid.append(target)

        if len(valid) < len(targets):
            logger.info(
                f"Target validation: {len(targets)} -> {len(valid)} "
                f"({len(targets) - len(valid)} removed)"
            )

        return valid

    def _deduplicate_targets(self, targets: List[Target]) -> List[Target]:
        """
        Deduplicate targets by UniProt ID (primary) or gene symbol (fallback).
        Merges evidence from duplicate entries.
        """
        unique: Dict[str, Target] = {}
        for target in targets:
            key = (
                target.uniprot_id
                or target.gene_symbol
                or target.name
            ).lower().strip()

            if key not in unique:
                unique[key] = target
            else:
                # Merge evidence
                unique[key].evidence.extend(target.evidence)

        if len(unique) < len(targets):
            logger.info(
                f"Target deduplication: {len(targets)} -> {len(unique)}"
            )

        return list(unique.values())

    def _score_mechanism_strength(self, target: Target) -> MechanismStrength:
        """
        Score mechanism strength based on evidence hierarchy.

        Rules:
        - STRONG: Has curated mechanism from ChEMBL + gene_symbol resolved
        - MEDIUM: Has experimental bioactivity + uniprot_id
        - WEAK: Literature-only or missing key identifiers
        """
        has_gene = bool(target.gene_symbol)
        has_uniprot = bool(target.uniprot_id)
        has_curated = any(
            ev.source == EvidenceSource.CURATED
            for ev in target.evidence
        )
        has_experimental = any(
            ev.source == EvidenceSource.EXPERIMENTAL
            for ev in target.evidence
        )

        if has_curated and has_gene:
            return MechanismStrength.STRONG
        elif has_experimental and (has_gene or has_uniprot):
            return MechanismStrength.MEDIUM
        else:
            return MechanismStrength.WEAK

    def _detect_conflicts(self, targets: List[Target]) -> List[Conflict]:
        """
        Detect action-type contradictions for the same target.

        Example: one source says AGONIST, another says ANTAGONIST
        for the same gene_symbol.
        """
        # Group activities by gene symbol
        gene_activities: Dict[str, List[Tuple[str, Evidence]]] = {}
        for target in targets:
            gene = target.gene_symbol or target.name
            activity = (target.activity or '').upper().strip()
            if not activity or activity == 'UNKNOWN':
                continue

            if gene not in gene_activities:
                gene_activities[gene] = []
            gene_activities[gene].append((
                activity,
                target.evidence[0] if target.evidence else None
            ))

        # Look for contradictions
        conflicts = []
        contradictory_pairs = {
            frozenset({'AGONIST', 'ANTAGONIST'}),
            frozenset({'ACTIVATOR', 'INHIBITOR'}),
            frozenset({'POSITIVE MODULATOR', 'NEGATIVE MODULATOR'}),
            frozenset({'PARTIAL AGONIST', 'ANTAGONIST'}),
            frozenset({'OPENER', 'BLOCKER'}),
        }

        for gene, activities in gene_activities.items():
            unique_actions = set(a for a, _ in activities)
            if len(unique_actions) <= 1:
                continue

            # Check each pair
            for action_pair in contradictory_pairs:
                if action_pair.issubset(unique_actions):
                    actions = list(action_pair)

                    # Find evidence for each side
                    ev_a = [ev for act, ev in activities if act == actions[0] and ev]
                    ev_b = [ev for act, ev in activities if act == actions[1] and ev]

                    conflict = Conflict(
                        claim_a=f"{gene} is a {actions[0]} target",
                        claim_b=f"{gene} is a {actions[1]} target",
                        evidence_a=ev_a[:3],
                        evidence_b=ev_b[:3],
                        resolution=f"Conflicting action types for {gene} - "
                                   f"requires manual review or dose-dependency analysis",
                        confidence_impact=f"Reduces confidence in {gene} mechanism directionality"
                    )
                    conflicts.append(conflict)
                    logger.warning(
                        f"CONFLICT: {gene} has contradictory actions: "
                        f"{actions[0]} vs {actions[1]}"
                    )

        return conflicts
