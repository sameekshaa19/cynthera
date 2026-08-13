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
from typing import TYPE_CHECKING, Any

from backend.core.domain.retrieval_package import RetrievalPackage
from utils.confidence_scoring import calculate_pathway_relevance_score

if TYPE_CHECKING:
    from backend.core.domain.target import Target

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

# ─────────────────────────────────────────────
# Organism validation
# ─────────────────────────────────────────────

_HUMAN_ORGANISM_MARKERS: frozenset[str] = frozenset({
    "homo sapiens",
    "human",
})


def _clean_uniprot(acc: str | None) -> str:
    """Normalize UniProt accession by removing isoform suffixes and whitespace."""
    if not acc:
        return ""
    return acc.split("-")[0].strip().upper()


def _is_human_protein(protein: Any) -> bool:
    """Return True if the protein's organism is human or unstated/unfetched.

    Returns False only for explicitly non-human organisms (e.g., bacterial, viral, rodent).
    Handles string variations like 'Homo sapiens (Human)', 'Homo sapiens (9606)', 'Human', etc.

    Args:
        protein: A Protein domain model, or None.

    Returns:
        True if organism is human or unstated, False for non-human organisms.
    """
    if protein is None:
        return True  # If protein details were not fetched, do not reject valid target
    organism = getattr(protein, "organism", None)
    if not organism:
        return True
    org_lower = organism.strip().lower()
    
    # Explicit non-human keywords check
    non_human_keywords = (
        "bacteria", "bacterial", "virus", "viral", "coli", "yeast",
        "rattus", "mouse", "mus musculus", "bovine", "porcine", "vector"
    )
    if any(k in org_lower for k in non_human_keywords):
        return False

    # Check for human keywords / taxon ID
    human_keywords = ("homo sapiens", "human", "9606", "swiss-prot")
    if any(k in org_lower for k in human_keywords):
        return True
    return True


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
        proteins = package.proteins

        if not targets:
            # No targets — cannot trace any path
            return []

        # ── P6: Rank pathways by gene-overlap relevance before iteration ────
        # calculate_pathway_relevance_score combines disease-gene overlap (60%)
        # and drug-target overlap (40%) to prioritise biologically relevant pathways.
        # Replaces insertion-order [:4] slice which selected arbitrary pathways.
        drug_target_genes = [p.gene_symbol for p in proteins if p.gene_symbol]
        disease_genes = list((getattr(package, "validated_disease_genes", None) or {}).keys())

        def _pathway_relevance(pw) -> float:
            return calculate_pathway_relevance_score(
                pathway_genes=pw.participant_uniprot_ids or [],
                disease_genes=disease_genes,
                drug_targets=drug_target_genes,
            )

        pathways = sorted(package.pathways, key=_pathway_relevance, reverse=True)

        # Build protein lookup by UniProt accession (supporting both raw and clean accessions)
        protein_by_uniprot: dict[str, Any] = {}
        for p in proteins:
            if p.uniprot_accession:
                protein_by_uniprot[p.uniprot_accession] = p
                clean_acc = _clean_uniprot(p.uniprot_accession)
                if clean_acc:
                    protein_by_uniprot[clean_acc] = p

        # Build set of gene symbols validated by DisGeNET for this disease
        validated_genes = _build_validated_gene_set(package)

        for target in targets[:6]:  # cap at 6 targets
            uniprot_id = target.protein_uniprot
            norm_uniprot = _clean_uniprot(uniprot_id)

            # Resolve protein label
            protein = protein_by_uniprot.get(uniprot_id) or protein_by_uniprot.get(norm_uniprot)

            # ── Organism guard ──────────────────────────────────────────────────
            # Reject any target whose protein is explicitly confirmed non-human.
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
                # ── P8: Fail-closed pathway membership guard ─────────────────
                # Reject the hop if we have NO participant data (unknown membership
                # is treated as non-membership). Previously the guard was fail-open:
                # empty participant_ids let any target pass unconditionally.
                participant_ids = pathway.participant_uniprot_ids or []
                if not participant_ids:
                    logger.debug(
                        "pathway_membership_data_absent_skip",
                        extra={"uniprot_id": uniprot_id, "pathway": pathway.reactome_id},
                    )
                    continue

                clean_participants = {_clean_uniprot(pid) for pid in participant_ids if pid}
                if (
                    clean_participants
                    and norm_uniprot not in clean_participants
                    and uniprot_id not in participant_ids
                ):
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
                    # ── P8: Same fail-closed guard for 3-HOP paths ───────────
                    participant_ids = pathway.participant_uniprot_ids or []
                    if not participant_ids:
                        logger.debug(
                            "pathway_membership_data_absent_skip_3hop",
                            extra={"uniprot_id": uniprot_id, "pathway": pathway.reactome_id},
                        )
                        continue

                    clean_participants = {_clean_uniprot(pid) for pid in participant_ids if pid}
                    if (
                        clean_participants
                        and norm_uniprot not in clean_participants
                        and uniprot_id not in participant_ids
                    ):
                        continue

                    # Use secondary proteins as downstream effectors.
                    secondary_proteins = [
                        p for p in proteins
                        if _clean_uniprot(p.uniprot_accession) != norm_uniprot
                        and _is_human_protein(p)
                    ][:2]

                    for sec_protein in secondary_proteins:
                        sec_norm = _clean_uniprot(sec_protein.uniprot_accession)
                        if (
                            clean_participants
                            and sec_norm not in clean_participants
                            and sec_protein.uniprot_accession not in participant_ids
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

        P7 Fix: Replaces union-inflation formula with weakest-link + diminishing
        returns (DeepRoot arXiv 2606.15931 informed).

        Old formula: score = 1 - prod(1 - conf_i)
          Problem: 3 paths at 0.40 → 0.784 (HIGH) — unjustified when no single
          path exceeds 40% confidence.

        New formula: score = best_conf × (1 - exp(-0.5 × n_paths))
          The best (highest-confidence) path drives the score. Additional
          corroborating paths add diminishing returns via the exponential factor:
            n=1 → ×0.394  (single path, no corroboration)
            n=2 → ×0.632  (one corroborating path)
            n=3 → ×0.777  (two corroborating paths)
          Result: 3 paths at 0.40 → 0.40 × 0.777 = 0.311 (LOW-MEDIUM) ✓

        Args:
            paths: List of MechanisticPath objects sorted by confidence descending.

        Returns:
            Mechanistic Score in [0.0, 1.0].
        """
        if not paths:
            return 0.0

        top = paths[:3]
        best_conf = top[0].confidence  # paths already sorted descending
        n = len(top)
        # Weakest-link: best path confidence × diminishing-returns coverage factor
        score = round(best_conf * (1.0 - math.exp(-0.5 * n)), 4)
        return min(1.0, score)
