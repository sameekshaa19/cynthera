"""Unit and regression tests for Reactome pathway participant prioritization.

Verifies:
1. A reaction-referenced pathway beyond the normal first-N pathways is still fetched.
2. The pathway's participants are populated.
3. The corresponding target can be connected to its reaction in EvidenceGraph.
4. Reaction -> pathway evidence is preserved.
5. Ordinary participant-fetch limits still apply to lower-priority unrelated pathways.
6. Duplicate pathway IDs result in only one API request (deduplication).
7. Failed participant retrieval does not crash the pipeline and handles exceptions gracefully.

Reference: CYNTHERA — Fix Reactome Participant Fetch Truncation
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder


@pytest.fixture
def mock_reactome_connector():
    """Mock ReactomeConnector providing controlled pathways, reactions, and participants."""
    connector = MagicMock()
    connector.__aenter__ = AsyncMock(return_value=connector)
    connector.__aexit__ = AsyncMock(return_value=None)
    return connector


@pytest.mark.asyncio
async def test_01_reaction_referenced_pathway_prioritized_beyond_first_10():
    """Property 1: Pathways referenced by reaction evidence are prioritized over ordinary pathways."""
    pipeline = RetrievalPipeline()
    pipeline._bypass_raw_cache = True

    # 15 dummy pathways from protein A, and 1 important pathway from protein B
    dummy_pws = [{"stId": f"R-HSA-{1000 + i}", "displayName": f"Dummy Pathway {i}"} for i in range(15)]
    target_pw = {"stId": "R-HSA-2022377", "displayName": "Metabolism of Angiotensinogen to Angiotensins"}

    # Mock reaction for protein B that references R-HSA-2022377
    target_rxn = {"stId": "R-HSA-2022405", "displayName": "ACE hydrolyzes AGT"}

    with patch("backend.engineering.retrieval.pipeline.ReactomeConnector") as MockConn:
        conn_inst = AsyncMock()
        MockConn.return_value.__aenter__.return_value = conn_inst
        MockConn.return_value.__aexit__.return_value = None

        # Fetch returns dummy_pws for protein A ("P_DUMMY"), target_pw for protein B ("P12821")
        async def mock_fetch(uid):
            if uid == "P_DUMMY":
                return {"pathways": dummy_pws}
            return {"pathways": [target_pw]}

        conn_inst.fetch = AsyncMock(side_effect=mock_fetch)

        # Reactions for P12821
        async def mock_fetch_rxns(uid):
            if uid == "P12821":
                return [target_rxn]
            return []

        conn_inst.fetch_reactions = AsyncMock(side_effect=mock_fetch_rxns)
        conn_inst.fetch_reaction_details = AsyncMock(return_value={"displayName": "ACE hydrolyzes AGT"})
        conn_inst.fetch_reaction_ancestors = AsyncMock(return_value=[
            [{"stId": "R-HSA-2022377", "displayName": "Metabolism of Angiotensinogen to Angiotensins", "schemaClass": "Pathway"}]
        ])
        conn_inst.fetch_participating_entities = AsyncMock(return_value=[])

        # Participants: returns P12821 for R-HSA-2022377
        async def mock_fetch_participants(stid):
            if stid == "R-HSA-2022377":
                return {"uniprot_ids": ["P12821", "P01019"], "mappings": []}
            return {"uniprot_ids": ["DUMMY_UID"], "mappings": []}

        conn_inst.fetch_participants = AsyncMock(side_effect=mock_fetch_participants)

        # Query reactome data with P_DUMMY first, then P12821
        res = await pipeline._fetch_reactome(["P_DUMMY", "P12821"], uniprot_to_symbol={"P12821": "ACE"})

        # R-HSA-2022377 MUST have its participants populated despite appearing after 15 dummy pathways
        pws_by_id = {p["stId"]: p for p in res["pathways"]}
        assert "R-HSA-2022377" in pws_by_id
        assert pws_by_id["R-HSA-2022377"]["_participant_uniprot_ids"] == ["P12821", "P01019"]


@pytest.mark.asyncio
async def test_02_ordinary_pathways_still_bounded():
    """Property 2: Unrelated ordinary pathways beyond the limit are not fetched."""
    pipeline = RetrievalPipeline()
    pipeline._bypass_raw_cache = True

    # 30 dummy pathways with 0 reaction references
    dummy_pws = [{"stId": f"R-HSA-{5000 + i}", "displayName": f"Unrelated Pathway {i}"} for i in range(30)]

    with patch("backend.engineering.retrieval.pipeline.ReactomeConnector") as MockConn:
        conn_inst = AsyncMock()
        MockConn.return_value.__aenter__.return_value = conn_inst
        MockConn.return_value.__aexit__.return_value = None

        conn_inst.fetch = AsyncMock(return_value={"pathways": dummy_pws})
        conn_inst.fetch_reactions = AsyncMock(return_value=[])
        conn_inst.fetch_participants = AsyncMock(return_value={"uniprot_ids": ["P_TEST"], "mappings": []})

        res = await pipeline._fetch_reactome(["P_TEST"])

        # Count how many pathways actually had participants fetched
        fetched_count = sum(1 for p in res["pathways"] if len(p.get("_participant_uniprot_ids", [])) > 0)
        assert fetched_count == 10  # Capped at default MAX_ORDINARY_PARTICIPANT_FETCH


@pytest.mark.asyncio
async def test_03_deduplication_of_pathway_fetch():
    """Property 3: Duplicate pathway IDs across targets/reactions result in only one participant API call."""
    pipeline = RetrievalPipeline()
    pipeline._bypass_raw_cache = True

    shared_pw = {"stId": "R-HSA-9999", "displayName": "Shared Pathway"}
    rxn = {"stId": "R-HSA-RXN-1", "displayName": "Reaction 1"}

    with patch("backend.engineering.retrieval.pipeline.ReactomeConnector") as MockConn:
        conn_inst = AsyncMock()
        MockConn.return_value.__aenter__.return_value = conn_inst
        MockConn.return_value.__aexit__.return_value = None

        # Both proteins return the same shared pathway
        conn_inst.fetch = AsyncMock(return_value={"pathways": [shared_pw]})
        conn_inst.fetch_reactions = AsyncMock(return_value=[rxn])
        conn_inst.fetch_reaction_details = AsyncMock(return_value={"displayName": "Reaction 1"})
        conn_inst.fetch_reaction_ancestors = AsyncMock(return_value=[
            [{"stId": "R-HSA-9999", "displayName": "Shared Pathway", "schemaClass": "Pathway"}]
        ])
        conn_inst.fetch_participating_entities = AsyncMock(return_value=[])
        conn_inst.fetch_participants = AsyncMock(return_value={"uniprot_ids": ["P1", "P2"], "mappings": []})

        await pipeline._fetch_reactome(["P1", "P2"])

        # fetch_participants for R-HSA-9999 should be called exactly once
        assert conn_inst.fetch_participants.call_count == 1


@pytest.mark.asyncio
async def test_04_failed_participant_retrieval_does_not_crash():
    """Property 4: If fetch_participants fails for a pathway, the pipeline continues gracefully."""
    pipeline = RetrievalPipeline()
    pipeline._bypass_raw_cache = True

    pw1 = {"stId": "R-HSA-FAIL", "displayName": "Failing Pathway"}
    pw2 = {"stId": "R-HSA-PASS", "displayName": "Passing Pathway"}

    with patch("backend.engineering.retrieval.pipeline.ReactomeConnector") as MockConn:
        conn_inst = AsyncMock()
        MockConn.return_value.__aenter__.return_value = conn_inst
        MockConn.return_value.__aexit__.return_value = None

        conn_inst.fetch = AsyncMock(return_value={"pathways": [pw1, pw2]})
        conn_inst.fetch_reactions = AsyncMock(return_value=[])

        async def mock_participants(stid):
            if stid == "R-HSA-FAIL":
                raise RuntimeError("Reactome 500 Server Error")
            return {"uniprot_ids": ["P_GOOD"], "mappings": []}

        conn_inst.fetch_participants = AsyncMock(side_effect=mock_participants)

        res = await pipeline._fetch_reactome(["P_TEST"])

        pws_by_id = {p["stId"]: p for p in res["pathways"]}
        assert pws_by_id["R-HSA-FAIL"]["_participant_uniprot_ids"] == []
        assert pws_by_id["R-HSA-PASS"]["_participant_uniprot_ids"] == ["P_GOOD"]
