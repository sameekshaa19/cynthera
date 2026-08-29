import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.reporting.pdf_exporter import PDFReporter

async def test_browser_flow():
    drug = "Furosemide"
    disease = "Edema"
    policy_str = "STANDARD"
    policy = RetrievalPolicy.STANDARD

    print("=" * 70)
    print("STEP-BY-STEP SIMULATION OF BROWSER EVALUATION")
    print("=" * 70)

    # 1. Check cache state before evaluation
    cache = EvaluationCache(db_path="data/cynthera.db")
    key = cache._make_key(drug, disease, policy_str)
    print(f"\n[CACHE CHECK]")
    print(f"Cache key: {key}")
    print(f"Cache version: {cache._CACHE_VERSION}")
    cached = cache.get(drug, disease, policy_str)
    print(f"Cached result exists? {cached is not None}")
    if cached:
        print(f"  Cached rec: {cached.recommendation_status.value}")
        print(f"  Cached MS: {cached.mechanistic_assessment.score}")
        print(f"  Cached MA cands: {len(cached.mechanistic_assessment.candidate_mechanisms)}")
        print(f"  Cached AR cands: {len(cached.audit_report.candidate_mechanisms)}")
        print(f"  Cached chain: {cached.mechanistic_assessment.mechanistic_chain}")

    # 2. Run orchestrator evaluate exactly as app.py does (with bypass_cache=False)
    print(f"\n[UI EVALUATION INVOCATION - bypass_cache=False]")
    orch = MasterOrchestrator()
    hyp, pkg, res = await orch.evaluate(drug, disease, policy=policy, bypass_cache=False)
    
    print(f"UI Result recommendation: {res.recommendation_status.value}")
    print(f"UI Result mechanistic_score: {res.mechanistic_assessment.score}")
    print(f"UI Result mechanistic_assessment.level: {res.mechanistic_assessment.level}")
    print(f"UI Result mechanistic_assessment.mechanistic_chain: {res.mechanistic_assessment.mechanistic_chain}")
    print(f"UI Result mechanistic_assessment.candidate_mechanisms count: {len(res.mechanistic_assessment.candidate_mechanisms)}")
    print(f"UI Result audit_report.candidate_mechanisms count: {len(res.audit_report.candidate_mechanisms)}")

    # 3. Test serialization boundary (model_dump_json & model_validate_json)
    print(f"\n[SERIALIZATION BOUNDARY CHECK]")
    json_str = res.model_dump_json()
    from backend.core.domain.reasoning_result import ReasoningResult
    res_deserialized = ReasoningResult.model_validate_json(json_str)
    print(f"Deserialized MS: {res_deserialized.mechanistic_assessment.score}")
    print(f"Deserialized MA cands: {len(res_deserialized.mechanistic_assessment.candidate_mechanisms)}")
    print(f"Deserialized AR cands: {len(res_deserialized.audit_report.candidate_mechanisms)}")

    # 4. Check UI data binding logic from app.py lines 760-850
    print(f"\n[UI DATA BINDING CHECK]")
    cands = getattr(res.audit_report, "candidate_mechanisms", []) or getattr(res.mechanistic_assessment, "candidate_mechanisms", []) or []
    print(f"cands count: {len(cands)}")
    for i, c in enumerate(cands):
        print(f"  Candidate {i+1} type: {type(c)}")
        if isinstance(c, dict):
            print(f"    name: {c.get('name')}")
            print(f"    hops count: {len(c.get('hops', []))}")
            for h in c.get('hops', []):
                print(f"      hop: {h.get('from_node')} -> {h.get('to_node')} ({h.get('predicate')})")
        else:
            print(f"    name (attr): {getattr(c, 'name', None)}")

    # 5. Check PDF generation
    print(f"\n[PDF GENERATION CHECK]")
    reporter = PDFReporter(drug_name=drug, disease_name=disease)
    pdf_bytes = reporter.generate(res)
    print(f"PDF bytes generated: {len(pdf_bytes)}")
    print(f"PDF starts with %PDF: {pdf_bytes[:4] == b'%PDF'}")

asyncio.run(test_browser_flow())
