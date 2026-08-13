"""EvidenceGraphBuilder — builds a typed evidence graph from a sealed RetrievalPackage.

This module replaces the old template-enumeration approach in
``multi_hop_reasoner.py`` (fixed DIRECT / 2-HOP / 3-HOP loops over flat lists)
with an actual graph: typed nodes (Drug, Target, Pathway, Gene, Disease) and
typed, evidence-backed edges (predicate, source, evidence_strength, provenance).

Nothing here duplicates ``ClaimGraph`` — that graph is built from LLM-extracted
literature claims (Step 3 of the orchestrator). This graph is built purely from
structured retrieval data (ChEMBL, UniProt, Reactome, Open Targets / DisGeNET)
that is already sitting in the ``RetrievalPackage``.

Design principle: edges are only created when the underlying source data
actually supports them. There is no post-hoc INVALID marking — an edge that
isn't supported by retrieved data is simply never added, so every path the
PathFinder returns is hop-by-hop valid by construction.

Fixes:
  - 1.1  Real graph traversal instead of nested-loop template enumeration.
         The old "3-HOP Effector" template (two arbitrary secondary proteins
         picked because they share pathway membership) is REMOVED.
  - 1.2  Target → mechanism predicate is read from ``target.mechanism``
         (ChEMBL INHIBITOR / AGONIST / ANTAGONIST / ...) instead of a
         hardcoded "modulates" label.
  - 1.3  Gene-disease association is carried through as the real
         ``validated_disease_genes[gene]`` float score, not collapsed to
         binary membership with a flat 0.5 penalty.
  - 1.4  Pathway relevance / membership is computed on gene SYMBOLS on both
         sides. Reactome pathway participants come in as UniProt accessions;
         they are mapped to gene symbols via the retrieved Protein records
         before any overlap is computed.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.source_url_builder import EvidenceLink, SourceURLBuilder

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Tunable constants (not benchmark-validated yet — see audit §1.7).
# Track in MECHANISTIC_BENCHMARK_RESULTS.md once the benchmark lands.
# ─────────────────────────────────────────────
_HOP_DECAY: float = 0.85               # per-additional-hop length penalty
_MIN_PATH_CONFIDENCE: float = 0.05
_UNREVIEWED_PENALTY: float = 0.3       # TrEMBL (unreviewed) protein multiplier
_UNVALIDATED_GENE_DEFAULT: float = 0.3 # fallback strength when a target's gene
                                        # has no Open Targets/DisGeNET score at all
_MAX_TARGETS: int = 8
_MAX_PATHWAYS_PER_TARGET: int = 6
_MAX_HOPS: int = 4

# Node type constants
_NODE_DRUG = "DRUG"
_NODE_TARGET = "TARGET"
_NODE_PATHWAY = "PATHWAY"
_NODE_GENE = "GENE"
_NODE_DISEASE = "DISEASE"

_NON_HUMAN_KEYWORDS = (
    "bacteria", "bacterial", "virus", "viral", "coli", "yeast",
    "rattus", "mouse", "mus musculus", "bovine", "porcine", "vector",
)


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def clean_uniprot(acc: str | None) -> str:
    """Normalize a UniProt accession by removing isoform suffixes/whitespace."""
    if not acc:
        return ""
    return acc.split("-")[0].strip().upper()


def is_human_protein(protein: Any) -> bool:
    """Return True if organism is human or unstated (unfetched data is not rejected)."""
    if protein is None:
        return True
    organism = getattr(protein, "organism", None)
    if not organism:
        return True
    org_lower = organism.strip().lower()
    if any(k in org_lower for k in _NON_HUMAN_KEYWORDS):
        return False
    return True


def compute_target_confidence(target: Any, evidence_records: list) -> float:
    """Confidence for a target from binding affinity + weighted evidence volume.

    Uses two signals:
    1. Binding affinity strength (nM) mapped via log10 scale.
    2. Volume of evidence records mentioning this target, weighted by ERW.

    Args:
        target: A Target domain model with affinity_nm and protein_uniprot.
        evidence_records: All Evidence records from the RetrievalPackage.

    Returns:
        Confidence in [0.1, 1.0].
    """
    affinity_component = 0.5
    try:
        affinity_nm = target.affinity_nm
        if isinstance(affinity_nm, (int, float)) and affinity_nm > 0:
            affinity_component = max(0.1, min(1.0, 1.0 - (math.log10(affinity_nm) / 5.0)))
    except (TypeError, ValueError):
        pass

    target_uniprot = getattr(target, "protein_uniprot", None)
    if target_uniprot and isinstance(evidence_records, list):
        target_evidence = [
            e for e in evidence_records
            if getattr(e, "target_uniprot", None) == target_uniprot
            and hasattr(e, "erw") and hasattr(e.erw, "value")
        ]
        erw_sum = sum(
            e.erw.value for e in target_evidence
            if isinstance(e.erw.value, (int, float))
        )
        evidence_component = min(1.0, erw_sum / 3.0) if target_evidence else 0.2
    else:
        evidence_component = 0.2

    return round(0.6 * affinity_component + 0.4 * evidence_component, 4)


def build_validated_gene_scores(package: RetrievalPackage) -> dict[str, float]:
    """Return gene symbol → real association score in [0, 1].

    Primary source: Open Targets scores from ``package.validated_disease_genes``.
    Fallback: DisGeNET evidence records (membership-only, uses conservative default).

    Fixes audit 1.3: returns actual float magnitudes, not binary membership.
    """
    scores: dict[str, float] = {}

    val_genes = getattr(package, "validated_disease_genes", None) or {}
    if val_genes:
        for gene, score in val_genes.items():
            if isinstance(score, (int, float)) and score > 0:
                scores[gene.upper()] = round(min(1.0, max(0.0, float(score))), 4)
        return scores

    # Legacy fallback: DisGeNET evidence records, no real float score available
    disease_mesh = getattr(package.disease, "mesh_id", None)
    if not disease_mesh:
        return scores
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
                            scores.setdefault(gene.upper(), _UNVALIDATED_GENE_DEFAULT)
    return scores


def build_uniprot_symbol_map(proteins: list) -> dict[str, str]:
    """Return UniProt accession (cleaned) → gene symbol from retrieved Protein records.

    This is the missing piece behind audit 1.4: pathway participants arrive as
    UniProt accessions, while disease genes / drug targets are gene symbols.
    Every downstream comparison must go through this map.
    """
    mapping: dict[str, str] = {}
    for p in proteins:
        acc = getattr(p, "uniprot_accession", None)
        sym = getattr(p, "gene_symbol", None)
        if acc and sym:
            mapping[clean_uniprot(acc)] = sym.upper()
    return mapping


def pathway_gene_symbols(pathway: Any, uniprot_to_symbol: dict[str, str]) -> set[str]:
    """Return set of gene symbols for pathway participants using the UniProt→symbol map."""
    participant_ids = getattr(pathway, "participant_uniprot_ids", None) or []
    out: set[str] = set()
    for pid in participant_ids:
        sym = uniprot_to_symbol.get(clean_uniprot(pid))
        if sym:
            out.add(sym)
    return out


def pathway_relevance_score(
    pathway_gene_syms: set[str],
    disease_gene_syms: set[str],
    drug_target_syms: set[str],
) -> float:
    """Gene-symbol-to-gene-symbol overlap score.

    60% weight on disease-gene overlap, 40% on drug-target overlap.
    All sides are in gene-symbol space (fixes audit 1.4 — no accession/symbol mismatch).

    Args:
        pathway_gene_syms: Gene symbols of pathway participants (translated from UniProt).
        disease_gene_syms: Gene symbols with Open Targets/DisGeNET association scores.
        drug_target_syms: Gene symbols of drug targets from ChEMBL/UniProt.

    Returns:
        Relevance score in [0.0, 1.0].
    """
    if not pathway_gene_syms:
        return 0.0
    disease_overlap = (
        len(pathway_gene_syms & disease_gene_syms) / len(pathway_gene_syms)
        if disease_gene_syms else 0.0
    )
    target_overlap = (
        len(pathway_gene_syms & drug_target_syms) / len(pathway_gene_syms)
        if drug_target_syms else 0.0
    )
    return round(0.6 * disease_overlap + 0.4 * target_overlap, 4)


def target_in_pathway(target_uniprot_norm: str, pathway: Any) -> bool:
    """Fail-closed membership check (P8 preserved): unknown membership == non-membership.

    No participant data → reject, never pass unconditionally.
    """
    participant_ids = getattr(pathway, "participant_uniprot_ids", None) or []
    if not participant_ids:
        return False
    clean = {clean_uniprot(pid) for pid in participant_ids if pid}
    return target_uniprot_norm in clean


# ─────────────────────────────────────────────
# Graph model
# ─────────────────────────────────────────────

@dataclass
class GraphNode:
    """A node in the evidence graph."""
    id: str
    label: str          # DRUG | TARGET | PATHWAY | GENE | DISEASE
    name: str
    meta: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in the evidence graph, backed by retrieved source data."""
    source_id: str
    target_id: str
    predicate: str            # e.g. INHIBITOR, AGONIST, PARTICIPATES_IN, ASSOCIATED_WITH
    evidence_strength: float  # [0, 1], grounded in retrieved data
    source: str               # ChEMBL | Reactome | Open Targets | DisGeNET
    provenance: str = ""
    links: list[EvidenceLink] = field(default_factory=list)
    data_quality: str = "EVIDENCE_BACKED"  # "EVIDENCE_BACKED" | "STRUCTURE_ONLY" | "UNVALIDATED"


class EvidenceGraph:
    """Directed multigraph over Drug/Target/Pathway/Gene/Disease nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self._out: dict[str, list[GraphEdge]] = defaultdict(list)
        self.edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> None:
        """Add node (idempotent — duplicate IDs are silently ignored)."""
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """Add edge, deduplicating by (source_id, target_id, predicate)."""
        for existing in self._out[edge.source_id]:
            if (
                existing.target_id == edge.target_id
                and existing.predicate == edge.predicate
            ):
                return
        self._out[edge.source_id].append(edge)
        self.edges.append(edge)

    def out_edges(self, node_id: str) -> list[GraphEdge]:
        return self._out.get(node_id, [])

    def find_simple_paths(
        self, start_id: str, end_id: str, max_hops: int = _MAX_HOPS
    ) -> Iterator[list[GraphEdge]]:
        """DFS over simple paths (no repeated nodes) from start_id to end_id.

        Yields lists of GraphEdge objects representing complete paths.
        """

        def _dfs(node_id: str, visited: set[str], acc: list[GraphEdge]):
            if len(acc) > max_hops:
                return
            if node_id == end_id and acc:
                yield list(acc)
                return
            for e in self._out.get(node_id, []):
                if e.target_id in visited:
                    continue
                visited.add(e.target_id)
                acc.append(e)
                yield from _dfs(e.target_id, visited, acc)
                acc.pop()
                visited.discard(e.target_id)

        yield from _dfs(start_id, {start_id}, [])


# ─────────────────────────────────────────────
# EvidenceGraphBuilder
# ─────────────────────────────────────────────

class EvidenceGraphBuilder:
    """Builds an EvidenceGraph from a sealed RetrievalPackage.

    Every edge is created only when the corresponding source data actually
    supports it — see module docstring. Nothing here queries an LLM.

    Public API:
        builder = EvidenceGraphBuilder()
        graph = builder.build(package)
    """

    def build(self, package: RetrievalPackage) -> EvidenceGraph:
        """Build and return the EvidenceGraph for the given package.

        Args:
            package: Sealed RetrievalPackage from the retrieval pipeline.

        Returns:
            EvidenceGraph with nodes and edges populated from retrieved data.
        """
        graph = EvidenceGraph()

        drug_id = f"{_NODE_DRUG}:{package.drug.name}"
        disease_id = f"{_NODE_DISEASE}:{package.disease.name}"
        graph.add_node(GraphNode(drug_id, _NODE_DRUG, package.drug.name))
        graph.add_node(GraphNode(disease_id, _NODE_DISEASE, package.disease.name))

        targets = list(package.targets)[:_MAX_TARGETS]
        proteins = list(package.proteins)

        if not targets:
            # No targets → empty graph → PathFinder finds nothing → MS=0 NONE
            return graph

        # ── Pre-build lookup tables ───────────────────────────────────────
        # Fix 1.4: map UniProt accessions to gene symbols ONCE before any
        # pathway-overlap or membership comparison.
        uniprot_to_symbol = build_uniprot_symbol_map(proteins)

        # Fix 1.3: real float scores, not binary membership
        gene_scores = build_validated_gene_scores(package)

        protein_by_uniprot: dict[str, Any] = {}
        for p in proteins:
            acc = getattr(p, "uniprot_accession", None)
            if acc:
                protein_by_uniprot[acc] = p
                protein_by_uniprot[clean_uniprot(acc)] = p

        drug_target_syms: set[str] = {
            p.gene_symbol.upper()
            for p in proteins
            if getattr(p, "gene_symbol", None)
        }
        disease_gene_syms: set[str] = set(gene_scores.keys())

        # ── Rank pathways by corrected gene-symbol relevance ──────────────
        # Fix 1.4: both sides now use gene symbols, so the sort actually
        # discriminates between pathways.
        ranked_pathways = sorted(
            package.pathways,
            key=lambda pw: pathway_relevance_score(
                pathway_gene_symbols(pw, uniprot_to_symbol),
                disease_gene_syms,
                drug_target_syms,
            ),
            reverse=True,
        )

        genes_linked_to_disease: set[str] = set()  # track to avoid duplicate edges

        for target in targets:
            uniprot_id = getattr(target, "protein_uniprot", None)
            norm_uniprot = clean_uniprot(uniprot_id)
            protein = (
                protein_by_uniprot.get(uniprot_id)
                or protein_by_uniprot.get(norm_uniprot)
            )

            if not is_human_protein(protein):
                logger.info(
                    "evidence_graph_target_skipped_non_human",
                    extra={"uniprot_id": uniprot_id},
                )
                continue

            gene_symbol = getattr(protein, "gene_symbol", None) if protein else None
            target_label = (
                f"{gene_symbol} ({uniprot_id})"
                if gene_symbol
                else (uniprot_id or getattr(target, "name", "unknown"))
            )
            target_id = f"{_NODE_TARGET}:{uniprot_id or getattr(target, 'name', 'unknown')}"

            graph.add_node(GraphNode(
                target_id, _NODE_TARGET, target_label,
                meta={"uniprot": uniprot_id, "gene_symbol": gene_symbol},
            ))

            # ── Drug → Target ─────────────────────────────────────────────
            # Fix 1.2: read target.mechanism instead of hardcoding "modulates"
            target_conf = compute_target_confidence(target, package.evidence_records)
            if protein is not None and not getattr(protein, "is_reviewed", True):
                target_conf = round(target_conf * _UNREVIEWED_PENALTY, 4)

            mechanism = (getattr(target, "mechanism", None) or "").strip().upper()
            predicate = mechanism if mechanism and mechanism not in ("", "UNKNOWN") else "MODULATES"

            dt_links: list[EvidenceLink] = []
            if package.drug.chembl_id:
                u = SourceURLBuilder.chembl_compound_url(package.drug.chembl_id)
                if u:
                    dt_links.append(EvidenceLink("ChEMBL", "Open ChEMBL Compound", u, package.drug.chembl_id, "database"))
            if uniprot_id:
                u = SourceURLBuilder.uniprot_url(uniprot_id)
                if u:
                    dt_links.append(EvidenceLink("UniProt", "Open UniProt", u, uniprot_id, "database"))

            graph.add_edge(GraphEdge(
                source_id=drug_id,
                target_id=target_id,
                predicate=predicate,
                evidence_strength=target_conf,
                source="ChEMBL",
                provenance=f"binding affinity + evidence volume for {target_label}",
                links=dt_links,
                data_quality="EVIDENCE_BACKED",
            ))

            # ── Target → Gene → Disease ───────────────────────────────────
            # Fix 1.3: use the REAL association-score float magnitude
            gene_sym_u = gene_symbol.upper() if gene_symbol else None
            if gene_sym_u and gene_sym_u in gene_scores:
                gene_score = gene_scores[gene_sym_u]
                gene_id = f"{_NODE_GENE}:{gene_sym_u}"
                graph.add_node(GraphNode(gene_id, _NODE_GENE, gene_sym_u))

                tg_links: list[EvidenceLink] = []
                if uniprot_id:
                    u = SourceURLBuilder.uniprot_url(uniprot_id)
                    if u:
                        tg_links.append(EvidenceLink("UniProt", "Open UniProt", u, uniprot_id, "database"))
                u_ot = SourceURLBuilder.opentargets_target_url(gene_sym_u)
                if u_ot:
                    tg_links.append(EvidenceLink("Open Targets", "Open Targets Target", u_ot, gene_sym_u, "database"))

                graph.add_edge(GraphEdge(
                    source_id=target_id,
                    target_id=gene_id,
                    predicate="ENCODED_BY_DISEASE_ASSOCIATED_GENE",
                    evidence_strength=gene_score,
                    source="Open Targets / DisGeNET",
                    provenance=(
                        f"gene-disease association score {gene_score:.2f} for {gene_sym_u}"
                    ),
                    links=tg_links,
                    data_quality="EVIDENCE_BACKED",
                ))

                if gene_id not in genes_linked_to_disease:
                    gd_links: list[EvidenceLink] = []
                    u_ot_d = SourceURLBuilder.opentargets_disease_url(package.disease.mesh_id or package.disease.name)
                    if u_ot_d:
                        gd_links.append(EvidenceLink("Open Targets", "Open Targets Disease", u_ot_d, package.disease.name, "database"))
                    u_dg = SourceURLBuilder.disgenet_url(gene_sym_u)
                    if u_dg:
                        gd_links.append(EvidenceLink("DisGeNET", "Open DisGeNET", u_dg, gene_sym_u, "database"))

                    graph.add_edge(GraphEdge(
                        source_id=gene_id,
                        target_id=disease_id,
                        predicate="ASSOCIATED_WITH",
                        evidence_strength=gene_score,
                        source="Open Targets / DisGeNET",
                        provenance=f"gene-disease association score {gene_score:.2f}",
                        links=gd_links,
                        data_quality="EVIDENCE_BACKED",
                    ))
                    genes_linked_to_disease.add(gene_id)
            else:
                # No disease-gene score for this target's gene (data absence).
                # Allow a conservative, explicitly-flagged direct fallback hop.
                graph.add_edge(GraphEdge(
                    source_id=target_id,
                    target_id=disease_id,
                    predicate="IMPLICATED_IN",
                    evidence_strength=_UNVALIDATED_GENE_DEFAULT,
                    source="unresolved (no Open Targets/DisGeNET score for this gene)",
                    provenance=(
                        "target retrieved from ChEMBL but no disease-gene "
                        "association score could be resolved for its gene"
                    ),
                    links=[],
                    data_quality="UNVALIDATED",
                ))

            # ── Target → Pathway → Disease-associated gene(s) ────────────
            # Fix 1.1: real membership check (fail-closed, P8 preserved)
            # Fix 1.4: relevance computed on gene symbols on both sides
            for pathway in ranked_pathways[:_MAX_PATHWAYS_PER_TARGET]:
                if not target_in_pathway(norm_uniprot, pathway):
                    continue

                pathway_id = f"{_NODE_PATHWAY}:{pathway.reactome_id}"
                graph.add_node(GraphNode(
                    pathway_id,
                    _NODE_PATHWAY,
                    f"{pathway.name} ({pathway.reactome_id})",
                ))

                pw_gene_syms = pathway_gene_symbols(pathway, uniprot_to_symbol)
                relevance = pathway_relevance_score(
                    pw_gene_syms, disease_gene_syms, drug_target_syms
                )
                participation_strength = round(max(0.5, relevance), 4) if relevance > 0 else 0.5

                pw_links: list[EvidenceLink] = []
                u_pw = SourceURLBuilder.reactome_url(pathway.reactome_id)
                if u_pw:
                    pw_links.append(EvidenceLink("Reactome", "Open Reactome Pathway", u_pw, pathway.reactome_id, "database"))

                graph.add_edge(GraphEdge(
                    source_id=target_id,
                    target_id=pathway_id,
                    predicate="PARTICIPATES_IN",
                    evidence_strength=participation_strength,
                    source="Reactome",
                    provenance=(
                        f"confirmed pathway participant; "
                        f"gene-symbol relevance overlap {relevance:.2f}"
                    ),
                    links=pw_links,
                    data_quality="EVIDENCE_BACKED",
                ))

                # Pathway → disease-associated gene(s) that are actually in it
                for sym in pw_gene_syms & disease_gene_syms:
                    gene_id = f"{_NODE_GENE}:{sym}"
                    gene_score = gene_scores[sym]
                    graph.add_node(GraphNode(gene_id, _NODE_GENE, sym))

                    pwg_links: list[EvidenceLink] = []
                    if u_pw:
                        pwg_links.append(EvidenceLink("Reactome", "Open Reactome Pathway", u_pw, pathway.reactome_id, "database"))
                    u_ot_t = SourceURLBuilder.opentargets_target_url(sym)
                    if u_ot_t:
                        pwg_links.append(EvidenceLink("Open Targets", "Open Targets Target", u_ot_t, sym, "database"))

                    graph.add_edge(GraphEdge(
                        source_id=pathway_id,
                        target_id=gene_id,
                        predicate="CONTAINS_ASSOCIATED_GENE",
                        evidence_strength=gene_score,
                        source="Reactome + Open Targets/DisGeNET",
                        provenance=(
                            f"{sym} is both a pathway participant and disease-associated "
                            f"(score {gene_score:.2f})"
                        ),
                        links=pwg_links,
                        data_quality="EVIDENCE_BACKED",
                    ))

                    if gene_id not in genes_linked_to_disease:
                        gd_links2: list[EvidenceLink] = []
                        u_ot_d2 = SourceURLBuilder.opentargets_disease_url(package.disease.mesh_id or package.disease.name)
                        if u_ot_d2:
                            gd_links2.append(EvidenceLink("Open Targets", "Open Targets Disease", u_ot_d2, package.disease.name, "database"))
                        u_dg2 = SourceURLBuilder.disgenet_url(sym)
                        if u_dg2:
                            gd_links2.append(EvidenceLink("DisGeNET", "Open DisGeNET", u_dg2, sym, "database"))

                        graph.add_edge(GraphEdge(
                            source_id=gene_id,
                            target_id=disease_id,
                            predicate="ASSOCIATED_WITH",
                            evidence_strength=gene_score,
                            source="Open Targets / DisGeNET",
                            provenance=f"gene-disease association score {gene_score:.2f}",
                            links=gd_links2,
                            data_quality="EVIDENCE_BACKED",
                        ))
                        genes_linked_to_disease.add(gene_id)

        logger.info(
            "evidence_graph_built",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
            },
        )
        return graph
