import asyncio
import os
import sys
import json

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
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner, PathFinder, PathScorer
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver

async def run_diagnostic():
    drug = "Lisinopril"
    disease = "Hypertension"
    print("=" * 80)
    print(f"CYNTHERA BACKEND DIAGNOSTIC: {drug} -> {disease}")
    print("=" * 80)

    orch = MasterOrchestrator()
    hypothesis, pkg, result = await orch.evaluate(drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=True)

    # ─────────────────────────────────────────────────────────────
    # STAGE 1: REACTOME RETRIEVAL
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 40)
    print("STAGE 1: REACTOME RETRIEVAL")
    print("=" * 40)
    rxn_ev = getattr(pkg, "reactome_reaction_evidence", []) or []
    print(f"Total reactome_reaction_evidence in RetrievalPackage: {len(rxn_ev)}")
    
    # Group by target
    rxn_by_target = {}
    for r in rxn_ev:
        tgt_key = f"{r.target_canonical_id} ({r.target_original_id})"
        rxn_by_target.setdefault(tgt_key, []).append(r)

    print(f"Targets with Reactome reaction evidence ({len(rxn_by_target)}):")
    for tgt_key, rev_list in rxn_by_target.items():
        print(f"  Target: {tgt_key} -> {len(rev_list)} reaction records")
        roles = set(r.target_role for r in rev_list)
        directions = set(r.direction for r in rev_list)
        pw_ids = set(r.pathway_id for r in rev_list)
        print(f"    Roles: {roles}")
        print(f"    Directions: {directions}")
        print(f"    Linked Pathway IDs ({len(pw_ids)}): {list(pw_ids)[:5]}")
        for r in rev_list[:3]:
            print(f"      [Sample Rxn] ID={r.reaction_id} | Name={r.reaction_name} | Role={r.target_role} | Pathway={r.pathway_id}")

    # Check targets in package
    print(f"\nTargets in RetrievalPackage ({len(pkg.targets)}):")
    for t in pkg.targets:
        print(f"  Target: UniProt={t.protein_uniprot} | Mech={t.mechanism} | Affinity={t.affinity_nm} nM")

    # Check pathways in package
    print(f"\nPathways in RetrievalPackage ({len(pkg.pathways)}):")
    pkg_pw_ids = set(p.reactome_id for p in pkg.pathways)
    for p in pkg.pathways[:5]:
        print(f"  Pathway: {p.reactome_id} | {p.name} | participants={len(p.participant_uniprot_ids)}")

    # Check pathway ID overlap
    rxn_pw_ids_all = set(r.pathway_id for r in rxn_ev if r.pathway_id)
    overlap = rxn_pw_ids_all & pkg_pw_ids
    print(f"\nPathway ID Overlap: {len(overlap)} of {len(rxn_pw_ids_all)} reaction pathways exist in pkg.pathways")

    # ─────────────────────────────────────────────────────────────
    # STAGE 2: EVIDENCE NORMALIZATION / GRAPH CONSTRUCTION
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 40)
    print("STAGE 2: GRAPH CONSTRUCTION")
    print("=" * 40)
    builder = EvidenceGraphBuilder()
    graph, resolver = builder.build(pkg)

    rxn_nodes = [n for n in graph.nodes.values() if n.label == "REACTION"]
    target_rxn_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("REACTION:")]
    rxn_pw_edges = [e for e in graph.edges if e.source_id.startswith("REACTION:") and e.target_id.startswith("PATHWAY:")]
    target_pw_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("PATHWAY:")]
    pw_gene_edges = [e for e in graph.edges if e.source_id.startswith("PATHWAY:") and e.target_id.startswith("GENE:")]
    gene_dis_edges = [e for e in graph.edges if e.source_id.startswith("GENE:") and e.target_id.startswith("DISEASE:")]

    print(f"Total graph nodes: {len(graph.nodes)}")
    print(f"  DRUG nodes: {sum(1 for n in graph.nodes.values() if n.label == 'DRUG')}")
    print(f"  TARGET nodes: {sum(1 for n in graph.nodes.values() if n.label == 'TARGET')}")
    print(f"  REACTION nodes: {len(rxn_nodes)}")
    print(f"  PATHWAY nodes: {sum(1 for n in graph.nodes.values() if n.label == 'PATHWAY')}")
    print(f"  GENE nodes: {sum(1 for n in graph.nodes.values() if n.label == 'GENE')}")
    print(f"  DISEASE nodes: {sum(1 for n in graph.nodes.values() if n.label == 'DISEASE')}")

    print(f"\nTotal graph edges: {len(graph.edges)}")
    print(f"  Target -> Reaction edges: {len(target_rxn_edges)}")
    print(f"  Reaction -> Pathway edges: {len(rxn_pw_edges)}")
    print(f"  Target -> Pathway edges: {len(target_pw_edges)}")
    print(f"  Pathway -> Gene edges: {len(pw_gene_edges)}")
    print(f"  Gene -> Disease edges: {len(gene_dis_edges)}")

    if rxn_nodes:
        print("\nSample Reaction Nodes in Graph:")
        for rn in rxn_nodes[:3]:
            print(f"  Node: {rn.id} ({rn.name})")
    else:
        print("\n[ALERT] NO REACTION NODES IN GRAPH!")
        # Deep inspection of why reaction nodes weren't created
        gene_scores = build_validated_gene_scores(pkg, resolver=resolver)
        protein_by_uniprot = {p.uniprot_accession: p for p in pkg.proteins if getattr(p, "uniprot_accession", None)}
        drug_target_syms = {p.gene_symbol.upper() for p in pkg.proteins if getattr(p, "gene_symbol", None)}
        disease_gene_syms = set(gene_scores.keys())

        ranked_pathways = sorted(
            pkg.pathways,
            key=lambda pw: pathway_relevance_score(
                pathway_gene_symbols(pw, resolver),
                disease_gene_syms,
                drug_target_syms,
            ),
            reverse=True,
        )
        print(f"  Ranked pathways total: {len(ranked_pathways)}")
        print(f"  Top {_MAX_PATHWAYS_PER_TARGET} ranked pathways evaluated:")
        for idx, pw in enumerate(ranked_pathways[:_MAX_PATHWAYS_PER_TARGET]):
            pw_gene_syms = pathway_gene_symbols(pw, resolver)
            rel = pathway_relevance_score(pw_gene_syms, disease_gene_syms, drug_target_syms)
            print(f"    [{idx+1}] {pw.reactome_id} ({pw.name}) -> rel={rel:.4f}, pw_gene_syms_len={len(pw_gene_syms)}, overlap_with_dis_genes={len(pw_gene_syms & disease_gene_syms)}")

        for target in list(pkg.targets)[:_MAX_TARGETS]:
            uniprot_id = getattr(target, "protein_uniprot", None)
            norm_uniprot = clean_uniprot(uniprot_id)
            print(f"\n  Checking Target {uniprot_id} (norm={norm_uniprot}):")
            matching_rxns_total = [r for r in rxn_ev if clean_uniprot(r.target_original_id) == norm_uniprot or (r.target_canonical_id and r.target_canonical_id.upper() == str(getattr(target, 'protein_uniprot', '')).upper())]
            print(f"    Matching reaction records in rxn_ev: {len(matching_rxns_total)}")
            rxn_pw_ids_for_target = set(r.pathway_id for r in matching_rxns_total)
            print(f"    Reaction pathway IDs for this target: {rxn_pw_ids_for_target}")
            
            top_pw_ids = set(pw.reactome_id for pw in ranked_pathways[:_MAX_PATHWAYS_PER_TARGET])
            print(f"    Top {_MAX_PATHWAYS_PER_TARGET} pathway IDs: {top_pw_ids}")
            print(f"    Intersection: {rxn_pw_ids_for_target & top_pw_ids}")
            for pw in ranked_pathways[:_MAX_PATHWAYS_PER_TARGET]:
                in_pw = target_in_pathway(norm_uniprot, pw)
                print(f"      Target in pathway {pw.reactome_id}? {in_pw}")

    # ─────────────────────────────────────────────────────────────
    # STAGE 3: MULTI-HOP REASONER / PATHFINDER
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 40)
    print("STAGE 3: MULTI-HOP REASONER & PATHFINDER")
    print("=" * 40)
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(pkg)
    print(f"Total paths returned by reasoner.trace_paths(): {len(paths)}")

    # Let's also inspect raw paths from PathFinder
    drug_id = f"DRUG:{pkg.drug.name}"
    disease_id = f"DISEASE:{pkg.disease.name}"
    raw_paths = list(graph.find_simple_paths(drug_id, disease_id, max_hops=_MAX_HOPS))
    print(f"Raw graph simple paths (<= {_MAX_HOPS} hops): {len(raw_paths)}")

    paths_with_reaction = []
    paths_without_reaction = []
    for edge_chain in raw_paths:
        has_rxn = any(e.source_id.startswith("REACTION:") or e.target_id.startswith("REACTION:") for e in edge_chain)
        if has_rxn:
            paths_with_reaction.append(edge_chain)
        else:
            paths_without_reaction.append(edge_chain)

    print(f"  Raw paths WITH Reaction node: {len(paths_with_reaction)}")
    print(f"  Raw paths WITHOUT Reaction node: {len(paths_without_reaction)}")

    scorer = PathScorer()
    print("\nPaths evaluated:")
    for idx, p in enumerate(paths):
        has_rxn = any("Reaction" in h.label for h in p.hops)
        print(f"  [{idx+1}] Hops={len(p.hops)-1} | Conf={p.confidence:.4f} | HasReaction={has_rxn}")
        print(f"      Chain: {' -> '.join(h.label + ': ' + h.name for h in p.hops)}")

    # ─────────────────────────────────────────────────────────────
    # STAGE 4: CANDIDATE MECHANISMS & REACTION ENRICHMENT
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 40)
    print("STAGE 4: CANDIDATE MECHANISMS & REACTION-ENRICHMENT")
    print("=" * 40)
    cands = reasoner.discover_candidate_mechanisms(pkg, paths)
    print(f"Candidate mechanisms created: {len(cands)}")
    for idx, c in enumerate(cands):
        # Test frontend condition
        has_rxn_frontend = any(
            "REACTION" in str(h.from_node).upper() or "REACTION" in str(h.to_node).upper()
            for h in c.hops
        ) or any("REACTION" in str(node).upper() for node in c.summary_chain)
        print(f"  Candidate {idx+1}: {c.name}")
        print(f"    support_level: {c.support_level}")
        print(f"    confidence_score: {c.confidence_score}")
        print(f"    summary_chain: {c.summary_chain}")
        print(f"    directional_polarity: {c.directional_polarity}")
        print(f"    causal_grounding_level: {c.causal_grounding_level}")
        print(f"    grounded_edge_count: {c.grounded_edge_count}")
        print(f"    therapeutic_direction: {c.therapeutic_direction}")
        print(f"    has_reaction_hop (Reaction-Enriched condition): {has_rxn_frontend}")
        print("    Hops:")
        for h in c.hops:
            print(f"      - {h.from_node} -> {h.to_node} [pred={h.predicate}, pol={h.polarity}, grounding={h.causal_grounding}]")

    # ─────────────────────────────────────────────────────────────
    # STAGE 5: FINAL SERIALIZATION / PAYLOAD
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 40)
    print("STAGE 5: FINAL SERIALIZATION / PAYLOAD")
    print("=" * 40)
    ma_cands = result.mechanistic_assessment.candidate_mechanisms
    print(f"result.mechanistic_assessment.candidate_mechanisms count: {len(ma_cands)}")
    if ma_cands:
        print("Serialized CandidateMechanism 0 JSON:")
        print(json.dumps(ma_cands[0], indent=2))
    else:
        print("ma_cands is EMPTY!")

asyncio.run(run_diagnostic())
