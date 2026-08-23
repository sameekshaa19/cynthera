"""Unit tests for CYNTHERA domain models.

Tests: Drug, Disease, Protein, Target, Evidence, Claim, ClaimGraph,
       Contradiction, ClinicalTrial, ERW, Identifiers.
"""
import uuid
import pytest
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.protein import Protein
from backend.core.domain.target import Target
from backend.core.domain.evidence import Evidence
from backend.core.domain.claim import Claim
from backend.core.domain.claim_graph import ClaimGraph, ClaimRelation
from backend.core.domain.contradiction import Contradiction
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.exceptions import SealedGraphMutationError


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def drug_id_set() -> ResolvedIdentifierSet:
    return ResolvedIdentifierSet(
        entity_name="Sildenafil",
        entity_type="drug",
        identifiers=[
            CanonicalIdentifier(namespace="chembl", value="CHEMBL192"),
            CanonicalIdentifier(namespace="pubchem", value="135398513"),
        ],
    )


@pytest.fixture
def disease_id_set() -> ResolvedIdentifierSet:
    return ResolvedIdentifierSet(
        entity_name="Pulmonary Arterial Hypertension",
        entity_type="disease",
        identifiers=[CanonicalIdentifier(namespace="mesh", value="D000081029")],
    )


@pytest.fixture
def provenance() -> ProvenanceReference:
    return ProvenanceReference(
        source_name="ChEMBL",
        source_version="v33",
        record_id="activity_123",
        url="https://www.ebi.ac.uk/chembl/",
    )


@pytest.fixture
def erw_in_vitro() -> ERW:
    return ERW.from_base(base_weight=EvidenceType.IN_VITRO.base_erw)


# ─────────────────────────────────────────────
# ERW Tests
# ─────────────────────────────────────────────

class TestERW:
    def test_from_base_in_vitro(self) -> None:
        erw = ERW.from_base(base_weight=0.30)
        assert erw.value == 0.30
        assert erw.base_weight == 0.30

    def test_from_base_meta_analysis(self) -> None:
        erw = ERW.from_base(base_weight=1.00)
        assert erw.value == 1.00

    def test_clamps_below_minimum(self) -> None:
        erw = ERW.from_base(base_weight=0.30, conflict_penalty=0.5)
        assert erw.value == 0.15  # clamped to minimum

    def test_clamps_above_maximum(self) -> None:
        erw = ERW.from_base(base_weight=1.00, replication_modifier=1.5)
        assert erw.value == 1.00  # clamped to maximum

    def test_invalid_range_raises(self) -> None:
        with pytest.raises(Exception):
            ERW(value=0.10, base_weight=0.10)  # below 0.15

    def test_erw_base_weight_property(self) -> None:
        assert EvidenceType.META_ANALYSIS.base_erw == 1.00
        assert EvidenceType.COMPUTATIONAL.base_erw == 0.15
        assert EvidenceType.IN_VITRO.base_erw == 0.30


# ─────────────────────────────────────────────
# Drug Tests
# ─────────────────────────────────────────────

class TestDrug:
    def test_create_valid_drug(self, drug_id_set: ResolvedIdentifierSet) -> None:
        drug = Drug(name="Sildenafil", identifiers=drug_id_set)
        assert drug.name == "Sildenafil"
        assert drug.chembl_id == "CHEMBL192"

    def test_empty_name_raises(self, drug_id_set: ResolvedIdentifierSet) -> None:
        with pytest.raises(Exception):
            Drug(name="", identifiers=drug_id_set)

    def test_whitespace_name_stripped(self, drug_id_set: ResolvedIdentifierSet) -> None:
        drug = Drug(name="  Sildenafil  ", identifiers=drug_id_set)
        assert drug.name == "Sildenafil"

    def test_drug_is_immutable(self, drug_id_set: ResolvedIdentifierSet) -> None:
        drug = Drug(name="Sildenafil", identifiers=drug_id_set)
        with pytest.raises(Exception):
            drug.name = "Aspirin"  # type: ignore


# ─────────────────────────────────────────────
# Evidence Tests
# ─────────────────────────────────────────────

class TestEvidence:
    def test_create_valid_evidence(
        self, erw_in_vitro: ERW, provenance: ProvenanceReference
    ) -> None:
        ev = Evidence(
            evidence_type=EvidenceType.IN_VITRO,
            erw=erw_in_vitro,
            citation_key="PMID:12345678",
            provenance=provenance,
        )
        assert ev.evidence_type == EvidenceType.IN_VITRO
        assert ev.erw.value == 0.30

    def test_empty_citation_key_raises(
        self, erw_in_vitro: ERW, provenance: ProvenanceReference
    ) -> None:
        with pytest.raises(Exception):
            Evidence(
                evidence_type=EvidenceType.IN_VITRO,
                erw=erw_in_vitro,
                citation_key="",
                provenance=provenance,
            )

    def test_evidence_is_immutable(
        self, erw_in_vitro: ERW, provenance: ProvenanceReference
    ) -> None:
        ev = Evidence(
            evidence_type=EvidenceType.IN_VITRO,
            erw=erw_in_vitro,
            citation_key="PMID:99999",
            provenance=provenance,
        )
        with pytest.raises(Exception):
            ev.citation_key = "altered"  # type: ignore


# ─────────────────────────────────────────────
# ClinicalTrial Tests
# ─────────────────────────────────────────────

class TestClinicalTrial:
    def test_valid_nct_id(self, provenance: ProvenanceReference) -> None:
        trial = ClinicalTrial(
            nct_id="NCT00398918",
            title="Sildenafil in PAH",
            phase="Phase III",
            status=TrialOutcomeStatus.COMPLETED_SUCCESS,
            provenance=provenance,
        )
        assert trial.nct_id == "NCT00398918"

    def test_invalid_nct_format_raises(self, provenance: ProvenanceReference) -> None:
        with pytest.raises(Exception):
            ClinicalTrial(
                nct_id="NCT1234",  # too short
                title="Invalid",
                phase="Phase I",
                status=TrialOutcomeStatus.ACTIVE,
                provenance=provenance,
            )

    def test_invalid_phase_raises(self, provenance: ProvenanceReference) -> None:
        with pytest.raises(Exception):
            ClinicalTrial(
                nct_id="NCT12345678",
                title="Invalid Phase",
                phase="Phase VII",  # invalid
                status=TrialOutcomeStatus.ACTIVE,
                provenance=provenance,
            )


# ─────────────────────────────────────────────
# ClaimGraph Tests
# ─────────────────────────────────────────────

class TestClaimGraph:
    def _make_claim(self, erw: ERW, provenance: ProvenanceReference) -> Claim:
        return Claim(
            subject="Sildenafil",
            predicate=PredicateType.INHIBITS,
            object="PDE5A",
            confidence=0.9,
            erw=erw,
            provenance=provenance,
        )

    def test_add_claim_to_graph(
        self, erw_in_vitro: ERW, provenance: ProvenanceReference
    ) -> None:
        graph = ClaimGraph(hypothesis_id=uuid.uuid4())
        claim = self._make_claim(erw_in_vitro, provenance)
        graph.add_claim(claim)
        assert graph.node_count == 1

    def test_seal_graph(
        self, erw_in_vitro: ERW, provenance: ProvenanceReference
    ) -> None:
        graph = ClaimGraph(hypothesis_id=uuid.uuid4())
        graph.seal()
        assert graph.is_sealed is True

    def test_mutation_after_seal_raises(
        self, erw_in_vitro: ERW, provenance: ProvenanceReference
    ) -> None:
        graph = ClaimGraph(hypothesis_id=uuid.uuid4())
        graph.seal()
        claim = self._make_claim(erw_in_vitro, provenance)
        with pytest.raises(SealedGraphMutationError):
            graph.add_claim(claim)
