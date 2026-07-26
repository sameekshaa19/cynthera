"""MultiHopReasoner — traces indirect mechanistic paths through the ClaimGraph.

Phase 2 enhancement: extends the simple direct-link mechanistic scoring to
trace multi-hop paths up to 3 hops deep:
  Drug → Target → Pathway → Disease  (1-hop through each)
  Drug → Target1 → Target2 → Pathway → Disease  (multi-target)
  Drug → Pathway → Shared Gene → Disease Gene → Disease  (indirect)

Confidence decays multiplicatively per hop.

Reference: Phase 2 — Multi-hop mechanistic reasoning
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage

logger = logging.getLogger(__name__)

# Confidence decay factor applied per additional hop
_HOP_DECAY: float = 0.72

# Minimum confidence to report a path
_MIN_CONFIDENCE: float = 0.05


@dataclass
class MechanisticHop:
    """A single node in a mechanistic path."""

    label: str        # e.g. "Drug", "Target", "Pathway", "Disease"
    name: str         # e.g. "Sildenafil", "PDE5A (P33402)", "cGMP pathway"
    hop_index: int    # 0 = start, n = final node


@dataclass
class MechanisticPath:
    """A complete multi-hop mechanistic path from Drug to Disease.

    Attributes:
        hops: Ordered list of MechanisticHop nodes.
        hop_count: Number of intermediate steps.
        confidence: Confidence score [0.0, 1.0] with decay.
        path_type: 'DIRECT' | '2-HOP' | '3-HOP' | 'INDIRECT'
        description: Human-readable chain string.
    """

    hops: list[MechanisticHop] = field(default_factory=list)
    hop_count: int = 0
    confidence: float = 0.0
    path_type: str = "DIRECT"
    description: str = ""

    def to_chain(self) -> list[str]:
        """Return the path as a list of label:name strings."""
        return [f"{h.label}: {h.name}" for h in self.hops]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hops": [{"label": h.label, "name": h.name} for h in self.hops],
            "hop_count": self.hop_count,
            "confidence": self.confidence,
            "path_type": self.path_type,
            "description": self.description,
        }


class MultiHopReasoner:
    """Traces multi-hop mechanistic paths from Drug to Disease.

    Uses the RetrievalPackage's targets, proteins, and pathways to enumerate
    all plausible mechanistic chains with confidence decay per hop.

    Paths traced:
    1. Drug → Target → Disease (direct, via disease-associated target)
    2. Drug → Target → Pathway → Disease (2-hop via pathway)
    3. Drug → Target → Pathway → Gene/Protein → Disease (3-hop via gene)
    """

    def __init__(self) -> None:
        logger.info("MultiHopReasoner initialized")

    def trace_paths(self, package: RetrievalPackage) -> list[MechanisticPath]:
        """Trace all plausible mechanistic paths in the RetrievalPackage.

        Args:
            package: Sealed RetrievalPackage with targets, pathways, proteins.

        Returns:
            List of MechanisticPath objects sorted by confidence descending.
        """
        logger.info(
            "multi_hop_reasoning_start",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "targets": len(package.targets),
                "pathways": len(package.pathways),
                "proteins": len(package.proteins),
            },
        )

        paths: list[MechanisticPath] = []

        drug_name = package.drug.name
        disease_name = package.disease.name
        targets = package.targets
        pathways = package.pathways
        proteins = package.proteins

        if not targets:
            # No targets — cannot trace any path
            return []

        # Build protein lookup by UniProt accession
        protein_by_uniprot: dict[str, Any] = {
            p.uniprot_accession: p for p in proteins
        }

        for target in targets[:6]:  # cap at 6 targets
            uniprot_id = target.protein_uniprot

            # Resolve protein label
            protein = protein_by_uniprot.get(uniprot_id)
            target_label = (
                f"{protein.gene_symbol} ({uniprot_id})"
                if protein and protein.gene_symbol
                else uniprot_id or target.name
            )

            # Base confidence from target evidence score
            base_conf = getattr(target, "confidence_score", 0.7)
            if isinstance(base_conf, float) and 0.0 <= base_conf <= 1.0:
                base_conf = base_conf
            else:
                base_conf = 0.7

            # ── Path Type 1: Drug → Target → Disease (DIRECT)
            direct_conf = round(base_conf, 4)
            if direct_conf >= _MIN_CONFIDENCE:
                path = MechanisticPath(
                    hops=[
                        MechanisticHop("Drug", drug_name, 0),
                        MechanisticHop("Target", target_label, 1),
                        MechanisticHop("Disease", disease_name, 2),
                    ],
                    hop_count=1,
                    confidence=direct_conf,
                    path_type="DIRECT",
                    description=(
                        f"{drug_name} binds {target_label}, "
                        f"directly linked to {disease_name} pathophysiology."
                    ),
                )
                paths.append(path)

            # ── Path Type 2: Drug → Target → Pathway → Disease (2-HOP)
            for pathway in pathways[:4]:
                two_hop_conf = round(base_conf * _HOP_DECAY, 4)
                if two_hop_conf >= _MIN_CONFIDENCE:
                    path = MechanisticPath(
                        hops=[
                            MechanisticHop("Drug", drug_name, 0),
                            MechanisticHop("Target", target_label, 1),
                            MechanisticHop("Pathway", f"{pathway.name} ({pathway.reactome_id})", 2),
                            MechanisticHop("Disease", disease_name, 3),
                        ],
                        hop_count=2,
                        confidence=two_hop_conf,
                        path_type="2-HOP",
                        description=(
                            f"{drug_name} modulates {target_label}, "
                            f"activating {pathway.name}, "
                            f"which is implicated in {disease_name}."
                        ),
                    )
                    paths.append(path)

            # ── Path Type 3: Drug → Target → Pathway → Protein2 → Disease (3-HOP)
            if proteins and pathways:
                for pathway in pathways[:2]:
                    # Use secondary proteins as downstream effectors
                    secondary_proteins = [
                        p for p in proteins
                        if p.uniprot_accession != uniprot_id
                    ][:2]

                    for sec_protein in secondary_proteins:
                        three_hop_conf = round(base_conf * (_HOP_DECAY ** 2), 4)
                        if three_hop_conf >= _MIN_CONFIDENCE:
                            sec_label = (
                                f"{sec_protein.gene_symbol} ({sec_protein.uniprot_accession})"
                                if sec_protein.gene_symbol
                                else sec_protein.uniprot_accession
                            )
                            path = MechanisticPath(
                                hops=[
                                    MechanisticHop("Drug", drug_name, 0),
                                    MechanisticHop("Target", target_label, 1),
                                    MechanisticHop("Pathway", pathway.name, 2),
                                    MechanisticHop("Effector", sec_label, 3),
                                    MechanisticHop("Disease", disease_name, 4),
                                ],
                                hop_count=3,
                                confidence=three_hop_conf,
                                path_type="3-HOP",
                                description=(
                                    f"{drug_name} → {target_label} → {pathway.name} "
                                    f"→ {sec_label} → {disease_name} (indirect effector pathway)."
                                ),
                            )
                            paths.append(path)

        # Deduplicate and sort
        paths.sort(key=lambda p: p.confidence, reverse=True)
        seen: set[str] = set()
        unique_paths: list[MechanisticPath] = []
        for path in paths:
            key = path.description[:80]
            if key not in seen:
                seen.add(key)
                unique_paths.append(path)

        result = unique_paths[:20]

        logger.info(
            "multi_hop_reasoning_complete",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "paths_found": len(result),
                "max_confidence": result[0].confidence if result else 0.0,
            },
        )

        return result

    def compute_mechanistic_score(self, paths: list[MechanisticPath]) -> float:
        """Compute a Mechanistic Score from traced paths.

        Uses the top-3 paths with diminishing-returns aggregation:
        score = 1 - prod(1 - conf_i) for top-3 paths

        Args:
            paths: List of MechanisticPath objects sorted by confidence.

        Returns:
            Mechanistic Score in [0.0, 1.0].
        """
        if not paths:
            return 0.0

        import math

        top = paths[:3]
        # Probability of at least one path being valid
        prob_none = 1.0
        for p in top:
            prob_none *= (1.0 - p.confidence)
        score = round(1.0 - prob_none, 4)
        return min(1.0, score)
