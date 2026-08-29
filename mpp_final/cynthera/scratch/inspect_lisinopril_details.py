import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraphBuilder,
    _MAX_PATHWAYS_PER_TARGET,
    _MAX_TARGETS,
    _MAX_HOPS,
    clean_uniprot,
    target_in_pathway,
    pathway_gene_symbols,
    pathway_relevance_score,
    build_validated_gene_scores,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver

async def inspect_details():
    drug = "Lisinopril"
    disease = "Hypertension"
    orch = MasterOrchestrator()
    hypothesis, pkg, result = await orch.evaluate(drug, disease, policy=RetrievalPolicy.STANDARD)

    resolver = BiologicalIdentifierResolver(
        proteins=pkg.proteins,
        genes=pkg.genes,
        mappings=getattr(pkg, "identifier_mappings", []),
    )
    gene_scores = build_validated_gene_scores(pkg, resolver=resolver)
    disease_gene_syms = set(gene_scores.keys())
    drug_target_syms = {p.gene_symbol.upper() for p in pkg.proteins if getattr(p, "gene_symbol", None)}

    print(f"Disease Gene Symbols ({len(disease_gene_syms)}): {disease_gene_syms}")
    print(f"Drug Target Symbols ({len(drug_target_syms)}): {drug_target_syms}")

    # Check pathway R-HSA-2022377 (Angiotensinogen)
    angio_pw = next((p for p in pkg.pathways if p.reactome_id == "R-HSA-2022377"), None)
    print(f"\nPathway R-HSA-2022377 in pkg.pathways? {angio_pw is not None}")
    if angio_pw:
        syms = pathway_gene_symbols(angio_pw, resolver)
        rel = pathway_relevance_score(syms, disease_gene_syms, drug_target_syms)
        in_pw = target_in_pathway("P12821", angio_pw)
        print(f"  Name: {angio_pw.name}")
        print(f"  Participants ({len(angio_pw.participant_uniprot_ids)}): {angio_pw.participant_uniprot_ids}")
        print(f"  Gene Symbols ({len(syms)}): {syms}")
        print(f"  Relevance Score: {rel}")
        print(f"  Is P12821 in pathway? {in_pw}")
        print(f"  Overlap with disease genes: {syms & disease_gene_syms}")

    # Rank all pathways
    ranked = sorted(
        pkg.pathways,
        key=lambda pw: pathway_relevance_score(
            pathway_gene_symbols(pw, resolver),
            disease_gene_syms,
            drug_target_syms,
        ),
        reverse=True,
    )
    print(f"\nRank of ALL {len(ranked)} pathways:")
    for idx, pw in enumerate(ranked):
        syms = pathway_gene_symbols(pw, resolver)
        rel = pathway_relevance_score(syms, disease_gene_syms, drug_target_syms)
        in_ace = target_in_pathway("P12821", pw)
        overlap_dis = syms & disease_gene_syms
        overlap_drug = syms & drug_target_syms
        print(f"  [{idx+1}] {pw.reactome_id} ({pw.name[:50]}...) -> rel={rel:.4f} | in_ACE={in_ace} | dis_overlap={overlap_dis} | drug_overlap={overlap_drug}")

    # Inspect targets and their edges in graph
    builder = EvidenceGraphBuilder()
    graph, resolver = builder.build(pkg)
    print(f"\nGraph Edges involving ACE (P12821) or Target nodes:")
    for e in graph.edges:
        if "P12821" in e.source_id or "P12821" in e.target_id:
            print(f"  {e.source_id} --[{e.predicate}]--> {e.target_id} (src={e.source}, quality={e.data_quality})")

    print(f"\nAll REACTION nodes in graph ({len([n for n in graph.nodes.values() if n.label == 'REACTION'])}):")
    for n in graph.nodes.values():
        if n.label == "REACTION":
            print(f"  {n.id}: {n.name}")
            out_e = graph.out_edges(n.id)
            for e in out_e:
                print(f"    -> out_edge: --[{e.predicate}]--> {e.target_id}")

asyncio.run(inspect_details())
