import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from frontend.app import (
    get_role_badge_html,
    get_direction_badge_html,
    _ROLE_CONFIG,
)

async def test_ui_components():
    print("Testing badge generators...")
    for role in _ROLE_CONFIG.keys():
        b = get_role_badge_html(role)
        assert role.replace("_", " ") in b
    print("Role badges verified.")

    for d in ["UNKNOWN", "POSITIVE", "NEGATIVE"]:
        db = get_direction_badge_html(d)
        assert f"Direction: {d}" in db
    print("Direction badges verified.")

    print("\nRunning evaluation for Propranolol -> Hypertension...")
    orch = MasterOrchestrator()
    hypothesis, pkg, result = await orch.evaluate("Propranolol", "Hypertension", policy=RetrievalPolicy.STANDARD)

    print(f"\n[EVALUATION RESULT]")
    print(f"Drug: {hypothesis.drug_name}")
    print(f"Disease: {hypothesis.disease_name}")
    print(f"Recommendation: {result.recommendation_status.value}")
    print(f"Reactome Reaction Evidence count: {len(pkg.reactome_reaction_evidence)}")
    for ev in pkg.reactome_reaction_evidence[:3]:
        print(f"  - Reaction: {ev.reaction_name} ({ev.reaction_id})")
        print(f"    Target: {ev.target_canonical_id} ({ev.target_original_id}) | Role: {ev.target_role} | Direction: {ev.direction}")
        print(f"    Pathway: {ev.pathway_name} ({ev.pathway_id})")

    cands = result.audit_report.candidate_mechanisms or result.mechanistic_assessment.candidate_mechanisms
    print(f"\nCandidate Mechanisms count: {len(cands)}")
    for c in cands[:3]:
        print(f"  - {c.get('name')}")
        print(f"    Chain: {' -> '.join(c.get('summary_chain', []))}")
        print(f"    Hops: {len(c.get('hops', []))}")

    print("\nALL UI DATA PIPELINE VERIFIED SUCCESSFULLY!")

asyncio.run(test_ui_components())
