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
import math
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


def _compute_target_confidence(
    target: "Target",
    evidence_records: list,
) -> float:
    """Derive a confidence score for a target from retrieved evidence.

    Uses two signals:
    1. Binding affinity strength (nM) mapped via log10 scale.
    2. Volume of evidence records mentioning this target, weighted by ERW.

    Args:
        target: A Target domain model with affinity_nm and protein_uniprot.
        evidence_records: All Evidence records from the RetrievalPackage.

    Returns:
        Confidence in [0.1, 1.0].
    """
    # 1. Binding strength component: sub-100nM = strong, >10uM = weak
    affinity_component = 0.5
    try:
        affinity_nm = target.affinity_nm
        if isinstance(affinity_nm, (int, float)) and affinity_nm > 0:
            affinity_component = max(0.1, min(1.0, 1.0 - (math.log10(affinity_nm) / 5.0)))
    except (TypeError, ValueError):
        pass

    # 2. Evidence volume component: ERW-weighted sum of records mentioning this target
    target_uniprot = getattr(target, "protein_uniprot", None)
    if target_uniprot and isinstance(evidence_records, list):
        target_evidence = [
            e for e in evidence_records
            if getattr(e, "target_uniprot", None) == target_uniprot
            and hasattr(e, "erw") and hasattr(e.erw, "value")
        ]
        erw_sum = sum(e.erw.value for e in target_evidence if isinstance(e.erw.value, (int, float)))
        evidence_component = min(1.0, erw_sum / 3.0) if target_evidence else 0.2
    else:
        evidence_component = 0.2

    return round(0.6 * affinity_component + 0.4 * evidence_component, 4)


def _build_validated_gene_set(package: RetrievalPackage) -> set[str]:
    """Build set of gene symbols / UniProt accessions with Open Targets or DisGeNET association.

    Gap 1 Fix: Reads from package.validated_disease_genes (populated by Open Targets
    as primary, or DisGeNET as fallback). Stores both gene symbols and UniProt IDs
    that have a positive association score with the target disease.

    Falls back to legacy string parsing of evidence_records if validated_disease_genes
    is empty (for backwards compatibility with cached packages created before Phase 4).
    """
    validated: set[str] = set()

    # Primary path: read structured validated_disease_genes from package
    val_genes = getattr(package, "validated_disease_genes", {})
    if val_genes:
        for k, score in val_genes.items():
            if score > 0:
                validated.add(k)
        return validated

    # Legacy fallback path: string-parse evidence_records if DisGeNET evidence is present
    disease_mesh = getattr(package.disease, "mesh_id", None)
    if not disease_mesh:
        return validated
    for ev in getattr(package, "evidence_records", []):
        prov = getattr(ev, "provenance", None)
        if prov and getattr(prov, "source_name", "") == "DisGeNET":
            if getattr(ev, "disease_identifier", None) == disease_mesh:
                title = ev.title or ""
                if "DisGeNET association:" in title:
                    parts = title.split(":")
                    if len(parts) > 1:
                        gene = parts[1].split("—")[0].strip()
                        if gene:
                            validated.add(gene)
    return validated


# ─────────────────────────────────────────────
# Organism validation
# ─────────────────────────────────────────────

_HUMAN_ORGANISM_MARKERS: frozenset[str] = frozenset({
    "homo sapiens",
    "human",
})


def _is_human_protein(protein: Any) -> bool:
    """Return True only if the protein's organism is confirmed Homo sapiens.

    Errs on the side of exclusion: a protein with an unknown or missing organism
    field is NOT trusted as a human mechanism. Only explicitly Homo sapiens records
    are accepted. This prevents bacterial, viral, or yeast proteins from ChEMBL
    cross-references contributing to a human-disease mechanistic hypothesis.

    Args:
        protein: A Protein domain model, or None.

    Returns:
        True if organism is Homo sapiens, False for None / unknown / non-human.
    """
    if protein is None:
        return False
    organism = getattr(protein, "organism", None)
    if not organism:
        return False
    return organism.strip().lower() in _HUMAN_ORGANISM_MARKERS


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

        # Build set of gene symbols validated by DisGeNET for this disease
        validated_genes = _build_validated_gene_set(package)

        for target in targets[:6]:  # cap at 6 targets
            uniprot_id = target.protein_uniprot

            # Resolve protein label
            protein = protein_by_uniprot.get(uniprot_id)

            # ── Organism guard (Fix C) ───────────────────────────────────────────
            # Reject any target whose protein is not confirmed Homo sapiens.
            # This is the primary guard preventing bacterial/viral/non-human
            # proteins from appearing as "mechanisms" in human-disease hypotheses.
            # Note: if protein is None (target outside the UniProt fetch cap of 5),
            # the target is also excluded — this is safe but means RC-06 (UniProt
            # cap) can incidentally exclude legitimate human targets 6+.
            if not _is_human_protein(protein):
                logger.info(
                    "mechanistic_target_skipped_non_human",
                    extra={
                        "uniprot_id": uniprot_id,
                        "organism": (
                            getattr(protein, "organism", "unknown")
                            if protein else "no_protein_record"
                        ),
                    },
                )
                continue

            target_label = (
                f"{protein.gene_symbol} ({uniprot_id})"
                if protein and protein.gene_symbol
                else uniprot_id or target.name
            )

            # Base confidence from retrieved evidence (affinity + literature volume)
            base_conf = _compute_target_confidence(target, package.evidence_records)
            # Penalize unreviewed (TrEMBL) proteins — an antibody fragment is not a mechanism
            if protein and not protein.is_reviewed:
                base_conf = round(base_conf * 0.3, 4)
            # Penalize targets whose gene has no DisGeNET evidence linking it to this disease
            if validated_genes and protein and protein.gene_symbol not in validated_genes:
                base_conf = round(base_conf * 0.5, 4)

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
                # ── Pathway membership guard (Fix B3) ───────────────────────────
                # Only proceed if this target's protein is a known participant in
                # this pathway. If participant_uniprot_ids is [] (participant fetch
                # failed or not yet populated), the guard is skipped to degrade
                # gracefully to pre-Fix-B behaviour rather than blocking all paths.
                if pathway.participant_uniprot_ids and uniprot_id not in pathway.participant_uniprot_ids:
                    logger.debug(
                        "mechanistic_2hop_skipped_non_participant",
                        extra={"uniprot_id": uniprot_id, "pathway": pathway.reactome_id},
                    )
                    continue
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
                    # ── Pathway membership guard — primary target (Fix B3) ───────
                    if pathway.participant_uniprot_ids and uniprot_id not in pathway.participant_uniprot_ids:
                        continue

                    # Use secondary proteins as downstream effectors.
                    # Restrict to human proteins only (Gap 1 fix).
                    secondary_proteins = [
                        p for p in proteins
                        if p.uniprot_accession != uniprot_id
                        and _is_human_protein(p)  # Gap 1: organism filter on effector
                    ][:2]

                    for sec_protein in secondary_proteins:
                        # ── Pathway membership guard — effector protein (Gap 2 fix) ─
                        # Both hops in a 3-HOP chain need grounding. The effector
                        # must also participate in the same pathway — not just the
                        # primary target.
                        if (
                            pathway.participant_uniprot_ids
                            and sec_protein.uniprot_accession not in pathway.participant_uniprot_ids
                        ):
                            logger.debug(
                                "mechanistic_3hop_skipped_effector_non_participant",
                                extra={
                                    "effector_uniprot": sec_protein.uniprot_accession,
                                    "pathway": pathway.reactome_id,
                                },
                            )
                            continue

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
