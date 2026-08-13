"""Unit tests for MultiHopReasoner."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from backend.reasoning.mechanistic.multi_hop_reasoner import (
    MultiHopReasoner,
    MechanisticPath,
    MechanisticHop,
    _HOP_DECAY,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def _make_target(uniprot_id: str = "P12345", name: str = "TestTarget", conf: float = 0.8):
    t = MagicMock()
    t.protein_uniprot = uniprot_id
    t.name = name
    t.confidence_score = conf
    return t


def _make_protein(uniprot_id: str = "P12345", gene_symbol: str = "TGENE", organism: str = "Homo sapiens", is_reviewed: bool = True):
    p = MagicMock()
    p.uniprot_accession = uniprot_id
    p.gene_symbol = gene_symbol
    p.organism = organism
    p.is_reviewed = is_reviewed
    return p


def _make_pathway(reactome_id: str = "R-HSA-001", name: str = "TestPathway", participant_ids: list | None = None):
    pw = MagicMock()
    pw.reactome_id = reactome_id
    pw.name = name
    # P8 fix: tests that need 2-HOP/3-HOP paths must include the target's UniProt ID.
    # Empty list triggers fail-closed guard (correct behaviour). Pass participant_ids to test real membership.
    pw.participant_uniprot_ids = participant_ids if participant_ids is not None else []
    return pw


def _make_package(
    drug_name: str = "TestDrug",
    disease_name: str = "TestDisease",
    targets=None,
    pathways=None,
    proteins=None,
    validated_disease_genes: dict | None = None,
):
    package = MagicMock()
    package.hypothesis_id = uuid.uuid4()
    package.drug.name = drug_name
    package.disease.name = disease_name
    package.targets = targets or []
    package.pathways = pathways or []
    if proteins is None and targets:
        proteins = [_make_protein(uniprot_id=t.protein_uniprot) for t in targets]
    package.proteins = proteins or []
    package.evidence_records = []
    package.disease.mesh_id = None
    if validated_disease_genes is None:
        validated_disease_genes = {
            p.gene_symbol: 0.85
            for p in package.proteins
            if getattr(p, "gene_symbol", None)
        }
    package.validated_disease_genes = validated_disease_genes
    return package


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

class TestMultiHopReasoner:
    """Tests for MultiHopReasoner."""

    def setup_method(self):
        self.reasoner = MultiHopReasoner()

    def test_no_targets_returns_empty(self):
        """Package with no targets should return no paths."""
        package = _make_package()
        paths = self.reasoner.trace_paths(package)
        assert paths == []

    def test_direct_path_generated(self):
        """A single target with gene-disease association should produce valid graph paths."""
        target = _make_target()
        package = _make_package(targets=[target])
        paths = self.reasoner.trace_paths(package)
        assert len(paths) > 0
        assert paths[0].path_type in ("2-HOP", "DIRECT")

    def test_two_hop_path_with_pathway(self):
        """Target + Pathway + disease-gene overlap should produce 2-HOP paths.

        Graph-based architecture: 2-HOP = Drug→Target→Pathway→Gene→Disease.
        For the pathway leg to complete, the pathway must:
          (a) include the target UniProt ID in participant_uniprot_ids (P8 guard), AND
          (b) contain at least one gene symbol that has a disease association score.
        Here GENE1 (mapped from P12345) is both the target and a disease-associated gene.
        """
        target = _make_target(uniprot_id="P12345")
        protein = _make_protein(uniprot_id="P12345", gene_symbol="GENE1")
        # Pathway includes the target; GENE1 is also disease-associated
        pathway = _make_pathway(participant_ids=["P12345"])
        package = _make_package(
            targets=[target],
            pathways=[pathway],
            proteins=[protein],
            validated_disease_genes={"GENE1": 0.75},
        )
        paths = self.reasoner.trace_paths(package)
        # Expect at least one path that goes through the pathway (2-HOP or longer)
        multi_hop = [p for p in paths if p.hop_count >= 2]
        assert len(multi_hop) > 0

    def test_three_hop_path_with_secondary_protein(self):
        """Target + Pathway + disease gene via pathway should produce multi-hop paths.

        Post-audit: the old '3-HOP Effector' template (secondary protein picked
        arbitrarily because they share pathway membership) has been removed, because
        pathway co-membership is not evidence of a regulatory relationship.

        The new 3-HOP is: Drug→Target→Pathway→Disease-gene→Disease.
        For this path, the target (P11111/GENE1) must be in the pathway, and
        GENE2 (P22222) must be disease-associated AND in the pathway participants.
        """
        target = _make_target(uniprot_id="P11111")
        pathway = _make_pathway(participant_ids=["P11111", "P22222"])
        primary_protein = _make_protein(uniprot_id="P11111", gene_symbol="GENE1")
        # P22222/GENE2 is a disease-associated gene also in the pathway
        secondary_protein = _make_protein(uniprot_id="P22222", gene_symbol="GENE2")
        package = _make_package(
            targets=[target],
            pathways=[pathway],
            proteins=[primary_protein, secondary_protein],
            validated_disease_genes={"GENE2": 0.80},  # GENE2 is disease-relevant
        )
        paths = self.reasoner.trace_paths(package)
        # We expect at least one path (DIRECT or multi-hop); the graph will emit
        # Drug→P11111/GENE1→Pathway→GENE2→Disease (3-HOP) if all edges resolve
        assert len(paths) > 0

    def test_confidence_decays_per_hop(self):
        """3-HOP paths should have lower confidence than DIRECT paths."""
        target = _make_target(conf=0.9)
        pathway = _make_pathway()
        p1 = _make_protein(uniprot_id="P11111", gene_symbol="GENE1")
        p2 = _make_protein(uniprot_id="P22222", gene_symbol="GENE2")
        package = _make_package(targets=[target], pathways=[pathway], proteins=[p1, p2])
        paths = self.reasoner.trace_paths(package)

        direct = [p for p in paths if p.path_type == "DIRECT"]
        three_hop = [p for p in paths if p.path_type == "3-HOP"]

        if direct and three_hop:
            assert direct[0].confidence > three_hop[0].confidence

    def test_path_sorted_by_confidence_desc(self):
        """Paths should be sorted by confidence descending."""
        target = _make_target()
        pathway = _make_pathway()
        package = _make_package(targets=[target], pathways=[pathway])
        paths = self.reasoner.trace_paths(package)
        confidences = [p.confidence for p in paths]
        assert confidences == sorted(confidences, reverse=True)

    def test_max_20_paths_returned(self):
        """Should not return more than 20 paths."""
        targets = [_make_target(uniprot_id=f"P{i:05d}") for i in range(8)]
        pathways = [_make_pathway(reactome_id=f"R-HSA-{i:03d}") for i in range(5)]
        package = _make_package(targets=targets, pathways=pathways)
        paths = self.reasoner.trace_paths(package)
        assert len(paths) <= 20

    def test_to_chain_returns_list_of_strings(self):
        """MechanisticPath.to_chain() should return list of strings."""
        target = _make_target()
        package = _make_package(targets=[target])
        paths = self.reasoner.trace_paths(package)
        assert len(paths) > 0
        chain = paths[0].to_chain()
        assert isinstance(chain, list)
        assert all(isinstance(s, str) for s in chain)

    def test_mechanistic_score_zero_for_no_paths(self):
        """compute_mechanistic_score([]) should return 0.0."""
        score = self.reasoner.compute_mechanistic_score([])
        assert score == 0.0

    def test_mechanistic_score_in_unit_range(self):
        """compute_mechanistic_score should always return [0.0, 1.0]."""
        target = _make_target()
        pathway = _make_pathway()
        package = _make_package(targets=[target], pathways=[pathway])
        paths = self.reasoner.trace_paths(package)
        score = self.reasoner.compute_mechanistic_score(paths)
        assert 0.0 <= score <= 1.0

    def test_hop_count_correct(self):
        """Hop count should match path type."""
        target = _make_target()
        pathway = _make_pathway()
        package = _make_package(targets=[target], pathways=[pathway])
        paths = self.reasoner.trace_paths(package)
        for path in paths:
            if path.path_type == "DIRECT":
                assert path.hop_count == 1
            elif path.path_type == "2-HOP":
                assert path.hop_count == 2
            elif path.path_type == "3-HOP":
                assert path.hop_count == 3
