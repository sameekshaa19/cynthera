import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.reporting.pdf_exporter import PDFReporter

async def trace_pipeline():
    drug = "Furosemide"
    disease = "Edema"
    print("=" * 70)
    print(f"TRACING DATA FLOW FOR: {drug} -> {disease}")
    print("=" * 70)

    orch = MasterOrchestrator()
    hypothesis, pkg, result = await orch.evaluate(drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=True)

    # 1. RetrievalPackage
    rxn_ev = getattr(pkg, "reactome_reaction_evidence", [])
    print(f"\n[STEP 1 — RETRIEVAL PACKAGE]")
    print(f"  Targets retrieved: {len(pkg.targets)}")
    for t in pkg.targets:
        print(f"    - Target: UniProt={t.protein_uniprot} | Mech={t.mechanism} | Affinity={t.affinity_nm} nM")
    print(f"  Pathways retrieved: {len(pkg.pathways)}")
    print(f"  Validated Disease Genes: {len(pkg.validated_disease_genes)}")
    for g in list(pkg.validated_disease_genes.keys())[:5]:
        print(f"    - Disease Gene: {g}")
    print(f"  Reactome reaction evidence count: {len(rxn_ev)}")
    for r in rxn_ev[:5]:
        print(f"    - Target: {r.target_canonical_id} ({r.target_original_id}) | Reaction: {r.reaction_name} ({r.reaction_id}) | Role: {r.target_role} | Dir: {r.direction} | Pathway: {r.pathway_name} ({r.pathway_id})")

    # 2. EvidenceGraph
    print(f"\n[STEP 2 — EVIDENCE GRAPH]")
    builder = EvidenceGraphBuilder()
    graph = builder.build(pkg)
    rxn_nodes = [n for n in graph.nodes.values() if n.label == "REACTION"]
    target_rxn_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("REACTION:")]
    rxn_pw_edges = [e for e in graph.edges if e.source_id.startswith("REACTION:") and e.target_id.startswith("PATHWAY:")]
    target_pw_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("PATHWAY:")]
    pw_gene_edges = [e for e in graph.edges if e.source_id.startswith("PATHWAY:") and e.target_id.startswith("GENE:")]
    gene_dis_edges = [e for e in graph.edges if e.source_id.startswith("GENE:") and e.target_id.startswith("DISEASE:")]

    print(f"  Total graph nodes: {len(graph.nodes)}")
    print(f"  Reaction nodes: {len(rxn_nodes)}")
    for rn in rxn_nodes[:3]:
        print(f"    - Reaction Node: {rn.id} ({rn.name})")
    print(f"  Total graph edges: {len(graph.edges)}")
    print(f"  Target -> Reaction edges: {len(target_rxn_edges)}")
    for e in target_rxn_edges[:3]:
        print(f"    - {e.source_id} --[{e.predicate}]--> {e.target_id} (dir={e.direction})")
    print(f"  Reaction -> Pathway edges: {len(rxn_pw_edges)}")
    for e in rxn_pw_edges[:3]:
        print(f"    - {e.source_id} --[{e.predicate}]--> {e.target_id} (dir={e.direction})")
    print(f"  Target -> Pathway edges (baseline): {len(target_pw_edges)}")
    print(f"  Pathway -> Gene edges: {len(pw_gene_edges)}")
    for e in pw_gene_edges[:3]:
        print(f"    - {e.source_id} --[{e.predicate}]--> {e.target_id}")
    print(f"  Gene -> Disease edges: {len(gene_dis_edges)}")
    for e in gene_dis_edges[:3]:
        print(f"    - {e.source_id} --[{e.predicate}]--> {e.target_id}")

    # 3. MultiHopReasoner
    print(f"\n[STEP 3 — MULTI-HOP REASONER]")
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(pkg)
    print(f"  Total paths traced: {len(paths)}")
    hop_counts = {}
    for p in paths:
        h_len = len(p.hops) - 1
        hop_counts[h_len] = hop_counts.get(h_len, 0) + 1
    print(f"  Hop breakdown: {hop_counts}")
    for p in paths[:5]:
        print(f"    - Path ({len(p.hops)-1} hops): {' -> '.join(h.label + ':' + h.name for h in p.hops)}")

    # 4. CandidateMechanism construction
    print(f"\n[STEP 4 — CANDIDATE MECHANISMS]")
    cands_from_reasoner = reasoner.discover_candidate_mechanisms(pkg, paths)
    print(f"  Candidate mechanisms from reasoner: {len(cands_from_reasoner)}")
    for c in cands_from_reasoner[:3]:
        print(f"    - Candidate: {c.name} ({c.support_level}, conf={c.confidence_score})")
        print(f"      Summary chain: {' -> '.join(c.summary_chain)}")
        print(f"      Hops count: {len(c.hops)}")

    # 5. MechanisticAssessment & ReasoningResult
    print(f"\n[STEP 5 & 6 — MECHANISTIC ASSESSMENT & REASONING RESULT]")
    ma = result.mechanistic_assessment
    print(f"  Mechanistic Score: {ma.score:.3f} ({ma.level})")
    print(f"  Mechanistic chain: {ma.mechanistic_chain}")
    print(f"  Assessment candidate_mechanisms: {len(ma.candidate_mechanisms)}")
    audit_cands = getattr(result.audit_report, "candidate_mechanisms", [])
    print(f"  Audit report candidate_mechanisms: {len(audit_cands)}")

    # 7. PDF Report
    print(f"\n[STEP 8 — PDF REPORTER]")
    pdf_rep = PDFReporter(drug, disease)
    pdf_out = pdf_rep.generate(result)
    print(f"  PDF generated bytes: {len(pdf_out)}")

asyncio.run(trace_pipeline())

