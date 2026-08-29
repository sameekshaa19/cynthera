"""Phase 4B Directional Evidence Infrastructure — Unit Tests

25 tests covering:
    1-5:   ChEMBL action_type → MolecularPolarity mapping
    6-11:  Reactome role → MolecularPolarity + CausalGrounding mapping
    12-14: DirectionalEvidence value object construction and provenance
    15-19: Canonical entity gating (ungrounded token blocking)
    20-23: PathPolarity propagation invariants
    24:    Existing Phase 1-3 reaction paths remain intact
    25:    Furosemide regression — ungrounded compound/molecular target contradiction = 0

Reference: Phase 4B implementation plan
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.directional_evidence import DirectionalEvidence
from backend.reasoning.directional.chembl_polarity import (
    chembl_action_to_polarity,
    chembl_action_to_grounding,
)
from backend.reasoning.directional.reactome_polarity import (
    reactome_role_to_polarity,
    reactome_role_to_grounding,
)
from backend.reasoning.directional.canonical_entity_gate import (
    is_canonically_grounded,
    claims_are_comparable,
    _UNGROUNDED_TOKENS,
)
from backend.reasoning.directional.path_polarity import (
    propagate_path_polarity,
    PathPolarity,
    _CAUSAL_GROUNDINGS,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver
from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def populated_resolver():
    """Resolver with real protein/gene mappings for SLC12A1 / NKCC2."""
    protein = MagicMock()
    protein.uniprot_accession = "Q13621"
    protein.gene_symbol = "SLC12A1"

    resolver = BiologicalIdentifierResolver(
        proteins=[protein],
        genes=[],
        mappings=[],
    )
    return resolver


@pytest.fixture
def empty_resolver():
    """Resolver with no mappings — simulates no canonical data retrieved."""
    return BiologicalIdentifierResolver(proteins=[], genes=[], mappings=[])


def _make_claim(subject: str, obj: str, predicate_value: str):
    """Build a minimal mock Claim for conflict resolver tests."""
    from backend.core.enums.predicate_type import PredicateType
    from backend.core.domain.claim import ERW

    claim = MagicMock()
    claim.id = uuid.uuid4()
    claim.subject = subject
    claim.object = obj

    # Map predicate_value to PredicateType
    try:
        claim.predicate = PredicateType(predicate_value)
    except ValueError:
        claim.predicate = MagicMock()
        claim.predicate.value = predicate_value

    claim.erw = MagicMock()
    claim.erw.value = 0.8
    claim.evidence_type = "IN_VITRO"
    claim.publication_year = 2020
    return claim


def _make_edge(polarity: MolecularPolarity, grounding: CausalGrounding, evidence_strength: float = 0.8):
    """Build a mock GraphEdge with typed polarity/grounding."""
    edge = MagicMock()
    edge.polarity = polarity
    edge.causal_grounding = grounding
    edge.evidence_strength = evidence_strength
    return edge


# ─────────────────────────────────────────────
# Tests 1–5: ChEMBL Polarity Mapping
# ─────────────────────────────────────────────

def test_01_chembl_inhibitor_is_negative():
    """ChEMBL INHIBITOR → NEGATIVE polarity."""
    assert chembl_action_to_polarity("INHIBITOR") == MolecularPolarity.NEGATIVE


def test_02_chembl_antagonist_is_negative():
    """ChEMBL ANTAGONIST → NEGATIVE polarity."""
    assert chembl_action_to_polarity("ANTAGONIST") == MolecularPolarity.NEGATIVE


def test_03_chembl_agonist_is_positive():
    """ChEMBL AGONIST → POSITIVE polarity."""
    assert chembl_action_to_polarity("AGONIST") == MolecularPolarity.POSITIVE


def test_04_chembl_activator_is_positive():
    """ChEMBL ACTIVATOR → POSITIVE polarity."""
    assert chembl_action_to_polarity("ACTIVATOR") == MolecularPolarity.POSITIVE


def test_05_chembl_modulator_is_unknown():
    """ChEMBL MODULATOR → UNKNOWN polarity; grounding is NONE."""
    assert chembl_action_to_polarity("MODULATOR") == MolecularPolarity.UNKNOWN
    assert chembl_action_to_grounding("MODULATOR") == CausalGrounding.NONE
    assert chembl_action_to_grounding(None) == CausalGrounding.NONE


# ─────────────────────────────────────────────
# Tests 6–11: Reactome Role Polarity Mapping
# ─────────────────────────────────────────────

def test_06_reactome_positive_regulator_is_positive_curated():
    """Reactome POSITIVE_REGULATOR → POSITIVE + CURATED grounding."""
    assert reactome_role_to_polarity("POSITIVE_REGULATOR") == MolecularPolarity.POSITIVE
    assert reactome_role_to_grounding("POSITIVE_REGULATOR") == CausalGrounding.CURATED


def test_07_reactome_negative_regulator_is_negative_curated():
    """Reactome NEGATIVE_REGULATOR → NEGATIVE + CURATED grounding."""
    assert reactome_role_to_polarity("NEGATIVE_REGULATOR") == MolecularPolarity.NEGATIVE
    assert reactome_role_to_grounding("NEGATIVE_REGULATOR") == CausalGrounding.CURATED


def test_08_reactome_catalyst_is_unknown_structural():
    """CATALYST ≠ ACTIVATES. Reactome CATALYST → UNKNOWN polarity + STRUCTURAL grounding."""
    assert reactome_role_to_polarity("CATALYST") == MolecularPolarity.UNKNOWN
    assert reactome_role_to_grounding("CATALYST") == CausalGrounding.STRUCTURAL


def test_09_reactome_input_is_unknown_structural():
    """INPUT ≠ INHIBITS. Reactome INPUT → UNKNOWN polarity + STRUCTURAL grounding."""
    assert reactome_role_to_polarity("INPUT") == MolecularPolarity.UNKNOWN
    assert reactome_role_to_grounding("INPUT") == CausalGrounding.STRUCTURAL


def test_10_reactome_output_is_unknown_structural():
    """OUTPUT ≠ ACTIVATES. Reactome OUTPUT → UNKNOWN polarity + STRUCTURAL grounding."""
    assert reactome_role_to_polarity("OUTPUT") == MolecularPolarity.UNKNOWN
    assert reactome_role_to_grounding("OUTPUT") == CausalGrounding.STRUCTURAL


def test_11_reactome_unknown_role_is_unknown():
    """Unrecognized Reactome role → UNKNOWN polarity + STRUCTURAL grounding fallback."""
    assert reactome_role_to_polarity("SOME_NEW_ROLE_2025") == MolecularPolarity.UNKNOWN
    assert reactome_role_to_grounding("SOME_NEW_ROLE_2025") == CausalGrounding.STRUCTURAL
    assert reactome_role_to_polarity(None) == MolecularPolarity.UNKNOWN


# ─────────────────────────────────────────────
# Tests 12–14: DirectionalEvidence Construction
# ─────────────────────────────────────────────

def test_12_directional_evidence_preserves_source():
    """DirectionalEvidence must preserve source and source_id for auditability."""
    ev = DirectionalEvidence(
        subject_id="Q13621",
        object_id="SLC12A1_ACTIVITY",
        polarity=MolecularPolarity.NEGATIVE,
        causal_grounding=CausalGrounding.CURATED,
        source="ChEMBL",
        source_id="CHEMBL12345",
        evidence_type="IN_VITRO",
        confidence=0.9,
    )
    assert ev.source == "ChEMBL"
    assert ev.source_id == "CHEMBL12345"
    assert ev.polarity == MolecularPolarity.NEGATIVE
    assert ev.causal_grounding == CausalGrounding.CURATED


def test_13_directional_evidence_preserves_subject():
    """DirectionalEvidence subject_id must be preserved exactly."""
    ev = DirectionalEvidence(
        subject_id="FUROSEMIDE_CHEMBL438",
        object_id="Q13621",
        polarity=MolecularPolarity.NEGATIVE,
        causal_grounding=CausalGrounding.CURATED,
        source="ChEMBL",
        source_id="CHEMBL438",
        evidence_type="IN_VITRO",
    )
    assert ev.subject_id == "FUROSEMIDE_CHEMBL438"


def test_14_directional_evidence_preserves_object():
    """DirectionalEvidence object_id must be preserved exactly."""
    ev = DirectionalEvidence(
        subject_id="Q13621",
        object_id="REACTOME_R-HSA-12345",
        polarity=MolecularPolarity.UNKNOWN,
        causal_grounding=CausalGrounding.STRUCTURAL,
        source="Reactome",
        source_id="R-HSA-12345",
        evidence_type="CURATED_REACTION",
    )
    assert ev.object_id == "REACTOME_R-HSA-12345"
    assert ev.causal_grounding == CausalGrounding.STRUCTURAL


# ─────────────────────────────────────────────
# Tests 15–19: Canonical Entity Gating
# ─────────────────────────────────────────────

def test_15_unresolved_subject_blocks_claim(populated_resolver):
    """A claim whose subject cannot be resolved → claims_are_comparable returns False."""
    claim_a = _make_claim("compound", "SLC12A1", "CAUSES")
    claim_b = _make_claim("compound", "SLC12A1", "PREVENTS")
    assert not claims_are_comparable(claim_a, claim_b, populated_resolver)


def test_16_unresolved_object_blocks_claim(populated_resolver):
    """A claim whose object cannot be resolved → claims_are_comparable returns False."""
    claim_a = _make_claim("SLC12A1", "molecular target", "ACTIVATES")
    claim_b = _make_claim("SLC12A1", "molecular target", "INHIBITS")
    assert not claims_are_comparable(claim_a, claim_b, populated_resolver)


def test_17_compound_subject_does_not_create_contradiction(populated_resolver):
    """'compound' as subject must NOT produce a contradiction entry.
    This is the Furosemide regression: CAUSES vs PREVENTS on 'compound → molecular target'.
    """
    from backend.reasoning.conflict.conflict_resolver import AdvancedConflictResolver
    from backend.core.enums.predicate_type import PredicateType

    claim_causes = _make_claim("compound", "molecular target", "CAUSES")
    claim_prevents = _make_claim("compound", "molecular target", "PREVENTS")

    resolver_instance = AdvancedConflictResolver()
    report = resolver_instance.resolve(
        [claim_causes, claim_prevents],
        resolver=populated_resolver,
    )
    assert report.contradictions == [], (
        f"Expected 0 contradictions for ungrounded 'compound → molecular target', "
        f"got {len(report.contradictions)}: {report.contradictions}"
    )


def test_18_molecular_target_object_does_not_create_contradiction(populated_resolver):
    """'molecular target' as object must NOT produce a contradiction entry."""
    from backend.reasoning.conflict.conflict_resolver import AdvancedConflictResolver

    claim_a = _make_claim("Furosemide", "molecular target", "ACTIVATES")
    claim_b = _make_claim("Furosemide", "molecular target", "INHIBITS")

    resolver_instance = AdvancedConflictResolver()
    report = resolver_instance.resolve(
        [claim_a, claim_b],
        resolver=populated_resolver,
    )
    # "molecular target" is in _UNGROUNDED_TOKENS → no contradiction
    assert len(report.contradictions) == 0


def test_19_canonical_entities_can_still_contradict(populated_resolver):
    """Two claims on real resolved entities (Q13621) SHOULD be comparable.
    This confirms gating does not block valid contradictions.
    """
    # SLC12A1 (Q13621) is a real protein in our populated_resolver.
    # We test that claims_are_comparable returns True when both sides resolve.
    from backend.reasoning.directional.canonical_entity_gate import validate_directional_claim

    claim_a = _make_claim("Q13621", "cellular process of edema", "ACTIVATES")
    # "cellular process of edema" is not a valid canonical identifier — so not comparable.
    result_a = validate_directional_claim(claim_a, populated_resolver)
    assert result_a is None  # because "cellular process of edema" is not canonical biological identifier

    # Now test when both resolve:
    claim_x = _make_claim("Q13621", "SLC12A1", "ACTIVATES")
    claim_y = _make_claim("Q13621", "SLC12A1", "INHIBITS")
    result_x = validate_directional_claim(claim_x, populated_resolver)
    result_y = validate_directional_claim(claim_y, populated_resolver)
    # Both subject and object now resolve via populated_resolver
    assert result_x is not None
    assert result_y is not None
    assert result_x == result_y  # same pair → comparable


# ─────────────────────────────────────────────
# Tests 20–23: PathPolarity Propagation Invariants
# ─────────────────────────────────────────────

def test_20_unknown_polarity_does_not_become_negative():
    """An UNKNOWN polarity edge must never contribute NEGATIVE to path polarity."""
    edges = [
        _make_edge(MolecularPolarity.UNKNOWN, CausalGrounding.STRUCTURAL),
        _make_edge(MolecularPolarity.UNKNOWN, CausalGrounding.STRUCTURAL),
    ]
    result = propagate_path_polarity(edges)
    assert result.polarity == MolecularPolarity.UNKNOWN
    assert result.grounded_edges == 0


def test_21_unknown_polarity_does_not_become_positive():
    """An UNKNOWN polarity edge must never contribute POSITIVE to path polarity."""
    edges = [
        _make_edge(MolecularPolarity.UNKNOWN, CausalGrounding.CURATED),  # CURATED but UNKNOWN → still UNKNOWN
        _make_edge(MolecularPolarity.UNKNOWN, CausalGrounding.NONE),
    ]
    result = propagate_path_polarity(edges)
    assert result.polarity == MolecularPolarity.UNKNOWN


def test_22_structural_edges_do_not_contribute_sign():
    """STRUCTURAL causal grounding edges must not contribute signed polarity even if POSITIVE/NEGATIVE."""
    # This would be an erroneous state in practice, but the propagator must be safe
    edges = [
        _make_edge(MolecularPolarity.POSITIVE, CausalGrounding.STRUCTURAL),
        _make_edge(MolecularPolarity.NEGATIVE, CausalGrounding.STRUCTURAL),
    ]
    result = propagate_path_polarity(edges)
    assert result.polarity == MolecularPolarity.UNKNOWN
    assert result.grounded_edges == 0
    assert not result.has_conflict  # STRUCTURAL edges not counted


def test_23_path_polarity_unknown_when_no_curated_edges():
    """Path with zero CURATED/DIRECT edges → PathPolarity.UNKNOWN, 0 grounded edges."""
    edges = [
        _make_edge(MolecularPolarity.UNKNOWN, CausalGrounding.NONE),
        _make_edge(MolecularPolarity.UNKNOWN, CausalGrounding.STRUCTURAL),
    ]
    result = propagate_path_polarity(edges)
    assert result.polarity == MolecularPolarity.UNKNOWN
    assert result.grounded_edges == 0
    assert result.unknown_edges == 2
    assert not result.has_conflict


# ─────────────────────────────────────────────
# Test 24: Phase 1–3 Reaction Paths Intact
# ─────────────────────────────────────────────

def test_24_phase1_phase3_reaction_paths_intact():
    """Existing reaction-layer paths must not be affected by Phase 4B changes.

    Confirms: Target→Reaction edges still exist, polarity/grounding fields present
    with safe defaults (UNKNOWN, STRUCTURAL/NONE) without breaking path discovery.
    """
    from backend.reasoning.mechanistic.evidence_graph import (
        EvidenceGraphBuilder, GraphEdge, _NODE_REACTION, _NODE_TARGET,
    )

    # Minimal reaction evidence object
    rxn_ev = MagicMock()
    rxn_ev.target_original_id = "Q13621"
    rxn_ev.target_canonical_id = "SLC12A1"
    rxn_ev.pathway_id = "R-HSA-445355"
    rxn_ev.reaction_id = "R-HSA-12345"
    rxn_ev.reaction_name = "SLC12A1 transports solutes"
    rxn_ev.target_role = "CATALYST"
    rxn_ev.direction = "UNKNOWN"
    rxn_ev.schema_class = "BlackBoxEvent"
    rxn_ev.species = "Homo sapiens"
    rxn_ev.compartment = "cytosol"
    rxn_ev.disease_context = None
    rxn_ev.mapping_type = "direct"

    target = MagicMock()
    target.protein_uniprot = "Q13621"
    target.mechanism = "INHIBITOR"
    target.affinity_nm = 10.0
    target.name = "SLC12A1"

    protein = MagicMock()
    protein.uniprot_accession = "Q13621"
    protein.gene_symbol = "SLC12A1"
    protein.organism = "Homo sapiens"
    protein.is_reviewed = True

    pathway = MagicMock()
    pathway.reactome_id = "R-HSA-445355"
    pathway.name = "Transport of inorganic cations"
    pathway.participant_uniprot_ids = ["Q13621"]

    drug = MagicMock()
    drug.name = "Furosemide"
    drug.chembl_id = "CHEMBL438"

    disease = MagicMock()
    disease.name = "Edema"
    disease.mesh_id = "D004487"

    package = MagicMock()
    package.drug = drug
    package.disease = disease
    package.targets = [target]
    package.proteins = [protein]
    package.pathways = [pathway]
    package.genes = []
    package.evidence_records = []
    package.validated_disease_genes = {"SLC12A1": 0.85}
    package.reactome_reaction_evidence = [rxn_ev]
    package.hypothesis_id = uuid.uuid4()
    package.sources_failed = []
    package.identifier_mappings = []

    graph, resolver = EvidenceGraphBuilder().build(package)

    # Reaction node must exist
    rxn_node_id = f"{_NODE_REACTION}:R-HSA-12345"
    assert rxn_node_id in graph.nodes, f"Reaction node missing. Nodes: {list(graph.nodes.keys())}"

    # Target → Reaction edge must exist and have Phase 4B polarity fields
    target_to_rxn = [
        e for e in graph.edges
        if e.source_id.startswith("TARGET:") and e.target_id.startswith("REACTION:")
    ]
    assert len(target_to_rxn) >= 1, "Target→Reaction edge missing"
    edge = target_to_rxn[0]
    # Edge must have Phase 4B polarity and causal_grounding attributes
    assert hasattr(edge, "polarity"), "GraphEdge missing polarity attribute"
    assert hasattr(edge, "causal_grounding"), "GraphEdge missing causal_grounding attribute"
    # For CATALYST role: UNKNOWN + STRUCTURAL
    assert edge.polarity == MolecularPolarity.UNKNOWN
    assert edge.causal_grounding == CausalGrounding.STRUCTURAL


# ─────────────────────────────────────────────
# Test 25: Furosemide Regression (False Contradiction)
# ─────────────────────────────────────────────

def test_25_furosemide_ungrounded_contradiction_is_zero():
    """Regression: 'compound → CAUSES/PREVENTS → molecular target' must produce 0 contradictions.

    This is the confirmed Furosemide false positive from Phase 4A audit.
    With canonical entity gating active (resolver provided), both claims
    fail grounding checks and are silently excluded.
    """
    from backend.reasoning.conflict.conflict_resolver import AdvancedConflictResolver
    from backend.reasoning.normalization.biological_identifier_resolver import (
        BiologicalIdentifierResolver,
    )

    # Real resolver with Furosemide target protein
    protein = MagicMock()
    protein.uniprot_accession = "Q13621"
    protein.gene_symbol = "SLC12A1"

    resolver = BiologicalIdentifierResolver(
        proteins=[protein],
        genes=[],
        mappings=[],
    )

    # Simulate the actual Furosemide claim extraction output from the audit
    # These are the exact generic token claims causing the false positive
    claim_causes = _make_claim("compound", "molecular target", "CAUSES")
    claim_prevents = _make_claim("compound", "molecular target", "PREVENTS")

    conflict_resolver = AdvancedConflictResolver()
    report = conflict_resolver.resolve(
        [claim_causes, claim_prevents],
        resolver=resolver,
    )

    assert len(report.contradictions) == 0, (
        f"Furosemide regression FAILED: expected 0 contradictions, "
        f"got {len(report.contradictions)}. "
        f"First: {report.contradictions[0].explanation if report.contradictions else 'n/a'}"
    )
