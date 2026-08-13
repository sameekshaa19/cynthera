from __future__ import annotations
import math, uuid
from unittest.mock import MagicMock
import pytest
from backend.reasoning.mechanistic.multi_hop_reasoner import (
    MultiHopReasoner, MechanisticPath, MechanisticHop,
)

def _mp(confidence):
    return MechanisticPath(
        hops=[MechanisticHop('Drug','X',0), MechanisticHop('Disease','Y',1)],
        hop_count=1, confidence=confidence, path_type='DIRECT', description='t',
    )

class TestWeakestLinkFormula:
    def test_three_weak_paths_not_high(self):
        r = MultiHopReasoner()
        score = r.compute_mechanistic_score([_mp(0.40)]*3)
        assert score < 0.50, f'Got {score:.4f}, expected < 0.50'

    def test_old_formula_was_inflated(self):
        old = round(1.0 - 0.6**3, 4)
        assert abs(old - 0.784) < 0.01

    def test_new_lower_than_old(self):
        r = MultiHopReasoner()
        new = r.compute_mechanistic_score([_mp(0.40)]*3)
        assert new < (1.0 - 0.6**3)

    def test_empty_returns_zero(self):
        assert MultiHopReasoner().compute_mechanistic_score([]) == 0.0

    def test_corroboration_increases_score(self):
        r = MultiHopReasoner()
        s1 = r.compute_mechanistic_score([_mp(0.5)])
        s2 = r.compute_mechanistic_score([_mp(0.5)]*2)
        s3 = r.compute_mechanistic_score([_mp(0.5)]*3)
        assert s1 < s2 < s3
        assert (s2 - s1) > (s3 - s2)

    def test_bounded(self):
        r = MultiHopReasoner()
        for c in [0.0, 0.5, 1.0]:
            s = r.compute_mechanistic_score([_mp(c)]*3)
            assert 0.0 <= s <= 1.0

class TestDOIFormatting:
    def _ev(self, key):
        e = MagicMock()
        e.citation_key = key; e.evidence_type.value = 'LITERATURE'
        e.erw.value = 0.5; e.title = 'Test'
        return e

    def _run(self, evs):
        from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
        o = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        return o._extract_citations(evs)

    def test_doi_prefix_openalex(self):
        c = self._run([self._ev('doi:10.1016/j.jacc.2022.01.001')])
        assert c[0].startswith('DOI:10.'), f'Got: {c[0]}'

    def test_doi_plain_prefix(self):
        c = self._run([self._ev('10.1038/nature12345')])
        assert c[0].startswith('DOI:10.')

    def test_pmid_unchanged(self):
        c = self._run([self._ev('PMID:12345678')])
        assert c[0].startswith('PMID:12345678')

    def test_cross_source_dedup(self):
        c = self._run([self._ev('doi:10.1000/182'), self._ev('doi:10.1000/182')])
        assert len(c) == 1, f'Expected 1, got {len(c)}'

    def test_different_dois_both_present(self):
        c = self._run([self._ev('doi:10.1000/182'), self._ev('doi:10.1234/test')])
        assert len(c) == 2

class TestClaimGraphEdges:
    def _claim(self, subj, obj, conf=0.7):
        from backend.core.domain.claim import Claim
        from backend.core.enums.predicate_type import PredicateType
        from backend.core.value_objects.erw import ERW
        from backend.core.value_objects.provenance import ProvenanceReference
        prov = ProvenanceReference(source_name="test", source_version="1", record_id="test-001")
        return Claim(subject=subj, predicate=PredicateType.INHIBITS, object=obj,
                     confidence=conf, erw=ERW(value=0.5), evidence_ids=[], is_validated=False,
                     provenance=prov)

    def _orch(self):
        from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
        return ReasoningOrchestrator.__new__(ReasoningOrchestrator)

    def test_edge_created_on_match(self):
        c1 = self._claim('Sildenafil', 'PDE5')
        c2 = self._claim('PDE5', 'cGMP pathway')
        g = self._orch()._build_claim_graph([c1, c2], uuid.uuid4())
        assert len(g.relations) >= 1

    def test_no_edge_no_overlap(self):
        c1 = self._claim('Sildenafil', 'PDE5')
        c2 = self._claim('Metformin', 'AMPK')
        g = self._orch()._build_claim_graph([c1, c2], uuid.uuid4())
        assert len(g.relations) == 0

    def test_edge_weight_weakest_link(self):
        c1 = self._claim('Sildenafil', 'PDE5', conf=0.8)
        c2 = self._claim('PDE5', 'cGMP', conf=0.6)
        g = self._orch()._build_claim_graph([c1, c2], uuid.uuid4())
        if g.relations:
            assert abs(g.relations[0].weight - 0.6) < 0.01

class TestLiteratureFilter:
    def test_literature_included(self):
        from backend.core.enums.evidence_type import EvidenceType
        ev_lit = MagicMock(); ev_lit.evidence_type = EvidenceType.LITERATURE; ev_lit.abstract = 'text'
        ev_obs = MagicMock(); ev_obs.evidence_type = EvidenceType.OBSERVATIONAL; ev_obs.abstract = 'text'
        ev_none = MagicMock(); ev_none.evidence_type = EvidenceType.LITERATURE; ev_none.abstract = None
        from backend.core.domain.retrieval_package import RetrievalPackage
        rp = RetrievalPackage.__new__(RetrievalPackage)
        object.__setattr__(rp, 'evidence_records', [ev_lit, ev_obs, ev_none])
        result = rp.literature_evidence
        assert ev_lit in result
        assert ev_obs in result
        assert ev_none not in result

class TestPathwayRelevance:
    def test_importable(self):
        from utils.confidence_scoring import calculate_pathway_relevance_score
        s = calculate_pathway_relevance_score(['PPARA','PPARG'], ['PPARA'], ['PPARG'])
        assert 0.0 <= s <= 1.0

    def test_higher_overlap_higher_score(self):
        from utils.confidence_scoring import calculate_pathway_relevance_score
        low = calculate_pathway_relevance_score(['A','B'], ['C'], ['D'])
        high = calculate_pathway_relevance_score(['A','B'], ['A'], ['B'])
        assert high > low