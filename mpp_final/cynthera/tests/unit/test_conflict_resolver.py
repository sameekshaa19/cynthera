"""Unit tests for AdvancedConflictResolver."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from backend.reasoning.conflict.conflict_resolver import (
    AdvancedConflictResolver,
    ConflictResolutionReport,
    ConflictResolution,
)
from backend.core.enums.predicate_type import PredicateType


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def _make_claim(
    subject: str = "Drug",
    obj: str = "Target",
    predicate: PredicateType = PredicateType.ACTIVATES,
    erw_value: float = 0.5,
    evidence_type: str = "RCT",
    pub_year: int = 2020,
):
    """Build a minimal mock Claim."""
    claim = MagicMock()
    claim.id = uuid.uuid4()
    claim.subject = subject
    claim.object = obj
    claim.predicate = predicate
    claim.erw.value = erw_value
    claim.evidence_type = evidence_type
    claim.publication_year = pub_year
    return claim


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

class TestAdvancedConflictResolver:
    """Tests for AdvancedConflictResolver."""

    def setup_method(self):
        self.resolver = AdvancedConflictResolver()

    def test_no_contradictions_for_consistent_claims(self):
        """Claims with no directional conflicts should produce empty contradictions."""
        claims = [
            _make_claim(predicate=PredicateType.ACTIVATES),
            _make_claim(subject="Drug2", obj="Target2", predicate=PredicateType.BINDS),
        ]
        report = self.resolver.resolve(claims)
        assert isinstance(report, ConflictResolutionReport)
        assert len(report.contradictions) == 0

    def test_activates_vs_inhibits_detected(self):
        """ACTIVATES vs INHIBITS on same (subject, object) should be detected."""
        c1 = _make_claim(predicate=PredicateType.ACTIVATES, erw_value=0.8)
        c2 = _make_claim(predicate=PredicateType.INHIBITS, erw_value=0.3)
        report = self.resolver.resolve([c1, c2])
        assert len(report.contradictions) == 1

    def test_upregulates_vs_downregulates_detected(self):
        """UPREGULATES vs DOWNREGULATES should be detected as a conflict."""
        c1 = _make_claim(predicate=PredicateType.UPREGULATES, erw_value=0.6)
        c2 = _make_claim(predicate=PredicateType.DOWNREGULATES, erw_value=0.4)
        report = self.resolver.resolve([c1, c2])
        assert len(report.contradictions) == 1

    def test_clear_resolution_by_weight(self):
        """High ERW claim should win over low ERW claim with sufficient differential."""
        # Meta-analysis (weight 1.0) vs case report (weight 0.4)
        c1 = _make_claim(
            predicate=PredicateType.ACTIVATES,
            erw_value=0.9,
            evidence_type="META_ANALYSIS",
        )
        c2 = _make_claim(
            predicate=PredicateType.INHIBITS,
            erw_value=0.2,
            evidence_type="CASE_REPORT",
        )
        report = self.resolver.resolve([c1, c2])
        assert len(report.resolutions) == 1
        res = report.resolutions[0]
        assert res.winner_claim_id == str(c1.id)
        assert res.resolution_strategy == "WEIGHT_DIFFERENTIAL"

    def test_close_weights_yield_unresolved(self):
        """Claims with similar weights should produce UNRESOLVED status."""
        c1 = _make_claim(
            predicate=PredicateType.ACTIVATES,
            erw_value=0.51,
            evidence_type="COHORT_STUDY",
        )
        c2 = _make_claim(
            predicate=PredicateType.INHIBITS,
            erw_value=0.49,
            evidence_type="COHORT_STUDY",
        )
        report = self.resolver.resolve([c1, c2])
        if report.resolutions:
            # Should be UNRESOLVED due to small delta
            unresolved = [r for r in report.resolutions if r.winner_claim_id is None]
            assert len(unresolved) > 0

    def test_net_conflict_score_zero_for_no_conflicts(self):
        """No contradictions should yield net_conflict_score = 0.0."""
        claims = [_make_claim(predicate=PredicateType.BINDS)]
        report = self.resolver.resolve(claims)
        assert report.net_conflict_score == 0.0

    def test_net_conflict_score_positive_for_conflicts(self):
        """Contradictions should produce positive net_conflict_score."""
        c1 = _make_claim(predicate=PredicateType.ACTIVATES, erw_value=0.7)
        c2 = _make_claim(predicate=PredicateType.INHIBITS, erw_value=0.6)
        report = self.resolver.resolve([c1, c2])
        assert report.net_conflict_score > 0.0

    def test_net_conflict_score_in_unit_range(self):
        """net_conflict_score should always be in [0.0, 1.0]."""
        claims = []
        for i in range(5):
            claims.append(_make_claim(predicate=PredicateType.ACTIVATES, erw_value=0.8))
            claims.append(_make_claim(predicate=PredicateType.INHIBITS, erw_value=0.7))
        report = self.resolver.resolve(claims)
        assert 0.0 <= report.net_conflict_score <= 1.0

    def test_recency_boost_applied(self):
        """More recent claim should have higher computed weight."""
        c_recent = _make_claim(
            predicate=PredicateType.ACTIVATES,
            erw_value=0.6,
            pub_year=2024,
        )
        c_old = _make_claim(
            predicate=PredicateType.ACTIVATES,
            erw_value=0.6,
            pub_year=2005,
        )
        weight_recent = self.resolver._compute_claim_weight(c_recent)
        weight_old = self.resolver._compute_claim_weight(c_old)
        assert weight_recent > weight_old

    def test_to_dict_serializable(self):
        """ConflictResolutionReport.to_dict() should be serializable."""
        c1 = _make_claim(predicate=PredicateType.ACTIVATES, erw_value=0.8)
        c2 = _make_claim(predicate=PredicateType.INHIBITS, erw_value=0.3)
        report = self.resolver.resolve([c1, c2])
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "contradiction_count" in d
        assert "net_conflict_score" in d
        assert "resolutions" in d
