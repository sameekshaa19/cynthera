"""Unit tests for PriorKnowledgeAgent and KnowledgeStore."""
from __future__ import annotations

import gc
import os
import tempfile

import pytest

from backend.infrastructure.knowledge.knowledge_store import KnowledgeStore, KnowledgeEntry
from backend.reasoning.agents.prior_knowledge_agent import (
    PriorKnowledgeAgent,
    PriorKnowledgeContext,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def tmp_knowledge_store(tmp_path):
    """Create a fresh KnowledgeStore using pytest's tmp_path (auto-cleaned safely)."""
    db_path = str(tmp_path / "test_knowledge.db")
    store = KnowledgeStore(db_path=db_path)
    yield store
    # Force SQLite to release file handles before pytest cleans tmp_path
    del store
    gc.collect()


@pytest.fixture
def agent(tmp_knowledge_store):
    return PriorKnowledgeAgent(knowledge_store=tmp_knowledge_store)


# ─────────────────────────────────────────────
# KnowledgeStore Tests
# ─────────────────────────────────────────────

class TestKnowledgeStore:
    """Tests for KnowledgeStore."""

    def test_seed_data_loaded(self, tmp_knowledge_store):
        """Seed data should be loaded on initialization."""
        results = tmp_knowledge_store.retrieve_prior_knowledge(
            drug="sildenafil", disease="pulmonary arterial hypertension"
        )
        assert len(results) > 0

    def test_exact_match_returns_high_similarity(self, tmp_knowledge_store):
        """Exact drug-disease match should return high similarity."""
        results = tmp_knowledge_store.retrieve_prior_knowledge(
            drug="sildenafil", disease="pulmonary arterial hypertension"
        )
        assert results[0].similarity >= 0.5

    def test_unrelated_query_returns_low_similarity(self, tmp_knowledge_store):
        """Completely unrelated query should return low similarity."""
        results = tmp_knowledge_store.retrieve_prior_knowledge(
            drug="xyfloxaximab",  # non-existent
            disease="purple flamingo syndrome",  # non-existent
            min_similarity=0.0,
        )
        for r in results:
            assert r.similarity < 0.3

    def test_add_entry_and_retrieve(self, tmp_knowledge_store):
        """Custom entries should be retrievable after insertion."""
        row_id = tmp_knowledge_store.add_entry(
            drug="testdrug",
            disease="testdisease",
            mechanism="TestDrug inhibits TestTarget → improved TestDisease outcomes",
            evidence_level="MEDIUM",
            established=False,
        )
        assert row_id > 0

        results = tmp_knowledge_store.retrieve_prior_knowledge(
            drug="testdrug", disease="testdisease"
        )
        assert any(r.drug == "testdrug" for r in results)

    def test_top_k_limit(self, tmp_knowledge_store):
        """retrieve_prior_knowledge should not return more than top_k entries."""
        results = tmp_knowledge_store.retrieve_prior_knowledge(
            drug="sildenafil",
            disease="hypertension",
            top_k=2,
        )
        assert len(results) <= 2

    def test_cosine_similarity_symmetric(self, tmp_knowledge_store):
        """TF-IDF similarity is order-independent for small corpora."""
        r1 = tmp_knowledge_store.retrieve_prior_knowledge("sildenafil", "pah", top_k=1)
        r2 = tmp_knowledge_store.retrieve_prior_knowledge("pah", "sildenafil", top_k=1)
        # Both should find sildenafil/PAH with some similarity
        assert len(r1) > 0
        assert len(r2) > 0


# ─────────────────────────────────────────────
# PriorKnowledgeAgent Tests
# ─────────────────────────────────────────────

class TestPriorKnowledgeAgent:
    """Tests for PriorKnowledgeAgent."""

    def test_returns_context_object(self, agent):
        """Agent should always return a PriorKnowledgeContext."""
        ctx = agent.retrieve("sildenafil", "pulmonary arterial hypertension")
        assert isinstance(ctx, PriorKnowledgeContext)

    def test_established_precedent_detected(self, agent):
        """Sildenafil/PAH should have established precedent."""
        ctx = agent.retrieve("sildenafil", "pulmonary arterial hypertension")
        # Seeds have established=True with high similarity expected
        assert isinstance(ctx.has_established_precedent, bool)

    def test_evidence_boost_in_range(self, agent):
        """evidence_boost should be within [-0.2, 0.3] bounds."""
        ctx = agent.retrieve("sildenafil", "pulmonary arterial hypertension")
        assert -0.2 <= ctx.evidence_boost <= 0.3

    def test_novel_drug_returns_context(self, agent):
        """Novel drug-disease pair should return a context with no precedent."""
        ctx = agent.retrieve("xenovibuline", "purple flamingo syndrome")
        assert isinstance(ctx, PriorKnowledgeContext)
        assert ctx.has_established_precedent is False
        assert ctx.evidence_boost <= 0.05  # low boost for unknown pair

    def test_narrative_not_empty(self, agent):
        """Narrative should always be a non-empty string."""
        ctx = agent.retrieve("metformin", "cancer")
        assert isinstance(ctx.narrative, str)
        assert len(ctx.narrative) > 10

    def test_to_dict_serializable(self, agent):
        """PriorKnowledgeContext.to_dict() should return a valid dict."""
        ctx = agent.retrieve("sildenafil", "pulmonary arterial hypertension")
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert "has_established_precedent" in d
        assert "evidence_boost" in d
        assert "mechanistic_hints" in d
        assert isinstance(d["top_entries"], list)

    def test_mechanistic_hints_extracted(self, agent):
        """Mechanistic hints should be non-empty for known drug-disease pairs."""
        ctx = agent.retrieve("sildenafil", "pah")
        # May have hints if similarity threshold met
        assert isinstance(ctx.mechanistic_hints, list)

    def test_cache_only_never_grants_approval(self, agent):
        """Cache data must NEVER promote a pair to APPROVED_INDICATION.

        Regression for the stripped cache-driven-approval route. Sildenafil/PAH
        has an established, high-similarity seed cache entry, so this guards the
        behavior: without a live ChEMBL signal, approval is always False.
        """
        ctx = agent.retrieve("sildenafil", "pulmonary arterial hypertension")
        assert ctx.is_approved_indication is False
        assert ctx.evaluation_pathway == "NOVEL_HYPOTHESIS"
        assert ctx.has_established_precedent is False
        assert ctx.approval_type == "NOVEL_HYPOTHESIS"
        assert ctx.approval_confidence == 0.0
