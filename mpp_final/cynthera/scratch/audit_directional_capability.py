import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
from backend.engineering.retrieval.connectors.disgenet import DisGeNETConnector
from backend.engineering.retrieval.connectors.europepmc import EuropePMCConnector
from backend.engineering.retrieval.connectors.pubmed import PubMedConnector
from backend.engineering.retrieval.connectors.openalex import OpenAlexConnector
from backend.engineering.retrieval.connectors.semantic_scholar import SemanticScholarConnector
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

TEST_CASES = [
    ("Furosemide", "Edema"),
    ("Propranolol", "Infantile Hemangioma"),
    ("Dapagliflozin", "Heart Failure"),
    ("Thalidomide", "Multiple Myeloma"),
    ("Aspirin", "Colorectal Cancer"),
]

async def audit_sources_for_case(drug_name: str, disease_name: str):
    print("=" * 80)
    print(f"AUDITING: {drug_name} -> {disease_name}")
    print("=" * 80)

    async with ChEMBLConnector() as chembl, \
               ReactomeConnector() as reactome, \
               OpenTargetsConnector() as ot, \
               DisGeNETConnector() as disgenet, \
               EuropePMCConnector() as epmc:

        # 1. ChEMBL
        chembl_search = await chembl.search_molecule(drug_name)
        mols = chembl_search.get("molecules", [])
        chembl_id = mols[0].get("molecule_chembl_id") if mols else None
        print(f"\n[1. ChEMBL] chembl_id={chembl_id}")
        mechs = []
        if chembl_id:
            targets_raw = await chembl.fetch_targets(chembl_id)
            mechs = targets_raw.get("mechanisms", [])
            print(f"  Mechanisms count: {len(mechs)}")
            for m in mechs[:5]:
                print(f"    - Action Type: {m.get('action_type')} | Mech: {m.get('mechanism_of_action')} | Target: {m.get('target_chembl_id')}")
            inds = await chembl.fetch_indications(chembl_id)
            print(f"  Indications count: {len(inds.get('indications', []))}")
            for ind in inds.get('indications', [])[:3]:
                print(f"    - EFO: {ind.get('efo_term')} | Max Phase: {ind.get('max_phase_for_ind')}")

        # 2. Open Targets (Disease -> Target)
        mondo_id = await ot.resolve_mondo_id(disease_name)
        print(f"\n[2. Open Targets] mondo_id={mondo_id}")
        if mondo_id:
            scores, mappings = await ot.fetch_association_mappings(mondo_id, page_size=10)
            print(f"  Top Gene Associations (score only, no direction):")
            for sym, sc in list(scores.items())[:5]:
                print(f"    - {sym}: score={sc}")

        # 3. DisGeNET
        print(f"\n[3. DisGeNET]")
        print(f"  Endpoint: GET /gda/disease/{{disease_id}} -> provides statistical GDA score / Evidence Index (EI).")
        print(f"  Direction: Disease association magnitude only (0.0-1.0), NO therapeutic directionality.")

        # 4. Reactome (Target -> Reaction / Pathway)
        print(f"\n[4. Reactome]")
        target_map = {
            "furosemide": "Q13621",
            "propranolol": "P08588",
            "dapagliflozin": "P31946",
            "thalidomide": "Q96SW2",
            "aspirin": "P23219"
        }
        sample_uniprot = target_map.get(drug_name.lower(), "Q13621")
        rxns = await reactome.fetch_reactions(sample_uniprot)
        print(f"  Reactions for primary target {sample_uniprot}: {len(rxns)}")
        for r in rxns[:3]:
            stid = r.get("stId")
            print(f"    - Reaction: {r.get('displayName')} ({stid})")
            details = await reactome.fetch_reaction_details(stid)
            cat = details.get("catalystActivity", [])
            inp = details.get("input", [])
            out = details.get("output", [])
            reg = details.get("positivelyRegulates", []) + details.get("negativelyRegulates", []) + details.get("regulatedBy", [])
            print(f"      Role indicators: catalyst={len(cat)}, input={len(inp)}, output={len(out)}, regulators={len(reg)}")

        # 5. Pipeline Execution for Case
        print(f"\n[5. Pipeline Output]")
        orch = MasterOrchestrator()
        hyp, pkg, res = await orch.evaluate(drug_name, disease_name, policy=RetrievalPolicy.STANDARD, bypass_cache=True)
        print(f"  Recommendation: {res.recommendation_status.value}")
        print(f"  Support Score: {res.support_assessment.score}")
        print(f"  Mechanistic Score: {res.mechanistic_assessment.score} ({res.mechanistic_assessment.level})")
        print(f"  Risk Score: {res.risk_assessment.score}")
        print(f"  Contradictions count: {len(res.contradictions)}")
        for c in res.contradictions:
            print(f"    - Contradiction: {c.claim_id_a} vs {c.claim_id_b} (score: {c.contradiction_score}) | {c.explanation}")
        cands = res.audit_report.candidate_mechanisms
        print(f"  Candidate Mechanisms count: {len(cands)}")
        for cand in cands[:2]:
            print(f"    - Name: {cand.get('name')} | Level: {cand.get('support_level')} | Conf: {cand.get('confidence_score')}")
            print(f"      Chain: {' -> '.join(cand.get('summary_chain', []))}")
        
        # Check claims extracted for this drug-disease
        print(f"  Claims extracted count: {len(pkg.evidence_records)}")

async def run_all():
    for drug, disease in TEST_CASES:
        try:
            await audit_sources_for_case(drug, disease)
        except Exception as e:
            print(f"Error auditing {drug} -> {disease}: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(run_all())
