"""Unit tests for StorageRepository — SQLite persistence layer."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime

import pytest

from backend.core.domain.claim import Claim
from backend.core.domain.claim_graph import ClaimGraph
from backend.core.domain.contradiction import Contradiction
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.evidence import Evidence
from backend.core.domain.hypothesis import Hypothesis
from backend.core.domain.reasoning_result import (
    MechanisticAssessment,
    ReasoningResult,
    RiskAssessment,
    ScientificAuditReport,
    SupportAssessment,
)
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.lifecycle import HypothesisLifecycleState
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.identifier import ResolvedIdentifierSet
from backend.storage.repository import StorageRepository


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path) -> StorageRepository:
    """StorageRepository backed by a temporary database file."""
    db_path = str(tmp_path / "test.db")
    return StorageRepository(db_path=db_path)


@pytest.fixture
def hypothesis() -> Hypothesis:
    return Hypothesis(drug_name="Sildenafil", disease_name="Pulmonary Arterial Hypertension")


def _make_prov() -> ProvenanceReference:
    return ProvenanceReference(
        source_name="PubMed",
        source_version="2024",
        record_id="PM12345678",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
    )


def _make_evidence() -> Evidence:
    erw = ERW.from_base(base_weight=EvidenceType.RCT.base_erw)
    return Evidence(
        evidence_type=EvidenceType.RCT,
        erw=erw,
        citation_key="PM:12345678",
        title="RCT on Sildenafil for PAH",
        abstract="Sildenafil inhibits PDE5 and reduces vascular resistance in PAH.",
        provenance=_make_prov(),
    )


def _make_drug() -> Drug:
    ids = ResolvedIdentifierSet(entity_name="Sildenafil", entity_type="drug")
    return Drug(name="Sildenafil", identifiers=ids)


def _make_disease() -> Disease:
    ids = ResolvedIdentifierSet(entity_name="Pulmonary Arterial Hypertension", entity_type="disease")
    return Disease(name="Pulmonary Arterial Hypertension", identifiers=ids)


def _make_retrieval_package(hypothesis: Hypothesis) -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=hypothesis.id,
        drug=_make_drug(),
        disease=_make_disease(),
        evidence_records=[_make_evidence()],
    )


def _make_reasoning_result(hypothesis: Hypothesis) -> ReasoningResult:
    return ReasoningResult(
        hypothesis_id=hypothesis.id,
        support_assessment=SupportAssessment(
            score=0.75,
            level="HIGH",
            evidence_count=5,
            weighted_sum=3.5,
            rationale="Strong evidence support.",
        ),
        mechanistic_assessment=MechanisticAssessment(
            score=0.6,
            level="MEDIUM",
            pathway_count=2,
            mechanistic_chain=["Drug: Sildenafil", "Target: PDE5A (O76074)"],
            rationale="Mechanistic pathway found.",
        ),
        risk_assessment=RiskAssessment(
            score=0.2,
            level="LOW",
            failed_trial_count=0,
            contradiction_count=0,
            rationale="No major risks.",
        ),
        recommendation_status=RecommendationStatus.PROMISING,
        recommendation_reasons=["High support score", "Known mechanism"],
        audit_report=ScientificAuditReport(
            summary="Sildenafil shows promise for PAH treatment.",
            data_gaps=["Limited long-term data"],
            confidence_narrative="High confidence based on 5 RCTs.",
            recommendation_rationale="Rule 1: SS >= 0.6 → PROMISING",
        ),
        reasoning_duration_ms=1234.5,
    )


# ─────────────────────────────────────────────
# Tests: Hypothesis
# ─────────────────────────────────────────────


class TestHypothesisPersistence:
    def test_save_and_retrieve(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        retrieved = tmp_db.get_hypothesis(str(hypothesis.id))
        assert retrieved is not None
        assert retrieved.drug_name == "Sildenafil"
        assert retrieved.disease_name == "Pulmonary Arterial Hypertension"

    def test_upsert_updates_state(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        hypothesis.transition_to(HypothesisLifecycleState.ID_RESOLVED)
        tmp_db.save_hypothesis(hypothesis)
        retrieved = tmp_db.get_hypothesis(str(hypothesis.id))
        assert retrieved.lifecycle_state == HypothesisLifecycleState.ID_RESOLVED

    def test_get_missing_returns_none(self, tmp_db: StorageRepository):
        result = tmp_db.get_hypothesis(str(uuid.uuid4()))
        assert result is None


# ─────────────────────────────────────────────
# Tests: RetrievalPackage
# ─────────────────────────────────────────────


class TestRetrievalPackagePersistence:
    def test_save_and_retrieve(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        package = _make_retrieval_package(hypothesis)
        tmp_db.save_retrieval_package(package)
        retrieved = tmp_db.get_retrieval_package(str(hypothesis.id))
        assert retrieved is not None
        assert retrieved.drug.name == "Sildenafil"
        assert len(retrieved.evidence_records) == 1

    def test_get_missing_returns_none(self, tmp_db: StorageRepository):
        result = tmp_db.get_retrieval_package(str(uuid.uuid4()))
        assert result is None


# ─────────────────────────────────────────────
# Tests: ReasoningResult
# ─────────────────────────────────────────────


class TestReasoningResultPersistence:
    def test_save_and_retrieve(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        result = _make_reasoning_result(hypothesis)
        tmp_db.save_reasoning_result(result)
        retrieved = tmp_db.get_reasoning_result(str(hypothesis.id))
        assert retrieved is not None
        assert retrieved.recommendation_status == RecommendationStatus.PROMISING
        assert retrieved.support_assessment.score == 0.75

    def test_audit_report_survives_roundtrip(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        result = _make_reasoning_result(hypothesis)
        tmp_db.save_reasoning_result(result)
        retrieved = tmp_db.get_reasoning_result(str(hypothesis.id))
        assert "Sildenafil" in retrieved.audit_report.summary
        assert len(retrieved.audit_report.data_gaps) == 1


# ─────────────────────────────────────────────
# Tests: Evaluation History
# ─────────────────────────────────────────────


class TestEvaluationHistory:
    def test_list_evaluations_empty(self, tmp_db: StorageRepository):
        evaluations = tmp_db.list_evaluations()
        assert evaluations == []

    def test_list_evaluations_with_data(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        package = _make_retrieval_package(hypothesis)
        tmp_db.save_retrieval_package(package)
        result = _make_reasoning_result(hypothesis)
        tmp_db.save_reasoning_result(result)

        evaluations = tmp_db.list_evaluations()
        assert len(evaluations) == 1
        ev = evaluations[0]
        assert ev["drug_name"] == "Sildenafil"
        assert ev["recommendation"] == "PROMISING"
        assert ev["support_score"] == pytest.approx(0.75)

    def test_delete_hypothesis(self, tmp_db: StorageRepository, hypothesis: Hypothesis):
        tmp_db.save_hypothesis(hypothesis)
        deleted = tmp_db.delete_hypothesis(str(hypothesis.id))
        assert deleted is True
        assert tmp_db.get_hypothesis(str(hypothesis.id)) is None

    def test_delete_nonexistent_returns_false(self, tmp_db: StorageRepository):
        deleted = tmp_db.delete_hypothesis(str(uuid.uuid4()))
        assert deleted is False


# ─────────────────────────────────────────────
# Tests: ClaimGraph Traversal
# ─────────────────────────────────────────────


class TestClaimGraphTraversal:
    def _make_claim(
        self,
        subject: str,
        predicate: PredicateType,
        obj: str,
        hyp_id: uuid.UUID | None = None,
    ) -> Claim:
        erw = ERW.from_base(base_weight=EvidenceType.RCT.base_erw)
        prov = ProvenanceReference(
            source_name="PubMed",
            source_version="2024",
            record_id="PM99999",
            url="https://pubmed.ncbi.nlm.nih.gov/99999/",
        )
        return Claim(
            subject=subject,
            predicate=predicate,
            object=obj,
            confidence=0.8,
            erw=erw,
            provenance=prov,
            evidence_ids=[],
        )

    def test_get_claims_by_subject(self):
        hyp_id = uuid.uuid4()
        graph = ClaimGraph(hypothesis_id=hyp_id)
        c1 = self._make_claim("Sildenafil", PredicateType.INHIBITS, "PDE5", hyp_id)
        c2 = self._make_claim("Sildenafil", PredicateType.ACTIVATES, "cGMP", hyp_id)
        c3 = self._make_claim("Ritonavir", PredicateType.INHIBITS, "CYP3A4", hyp_id)
        graph.add_claim(c1)
        graph.add_claim(c2)
        graph.add_claim(c3)

        sildenafil_claims = graph.get_claims_by_subject("Sildenafil")
        assert len(sildenafil_claims) == 2
        subjects = {c.subject for c in sildenafil_claims}
        assert subjects == {"Sildenafil"}

    def test_find_conflicts_detects_activates_inhibits(self):
        hyp_id = uuid.uuid4()
        graph = ClaimGraph(hypothesis_id=hyp_id)
        c1 = self._make_claim("Sildenafil", PredicateType.ACTIVATES, "PDE5", hyp_id)
        c2 = self._make_claim("Sildenafil", PredicateType.INHIBITS, "PDE5", hyp_id)
        graph.add_claim(c1)
        graph.add_claim(c2)

        conflicts = graph.find_conflicts()
        assert len(conflicts) == 1
        claim_a, claim_b, conflict_type = conflicts[0]
        assert conflict_type == "directional"
        predicates = {claim_a.predicate, claim_b.predicate}
        assert PredicateType.ACTIVATES in predicates
        assert PredicateType.INHIBITS in predicates

    def test_find_conflicts_no_conflict(self):
        hyp_id = uuid.uuid4()
        graph = ClaimGraph(hypothesis_id=hyp_id)
        c1 = self._make_claim("Sildenafil", PredicateType.INHIBITS, "PDE5", hyp_id)
        c2 = self._make_claim("Sildenafil", PredicateType.BINDS, "PDE5", hyp_id)
        graph.add_claim(c1)
        graph.add_claim(c2)

        conflicts = graph.find_conflicts()
        assert len(conflicts) == 0
