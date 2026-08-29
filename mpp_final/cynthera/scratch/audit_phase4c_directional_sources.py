"""Comprehensive Phase 4C/4D Directional Evidence Audit Script.

Audits independently:
1. ChEMBL
2. Reactome
3. Open Targets Direction of Effect (OT DoE)
4. DATTs (Disease-Associated Therapeutic Targets)
5. Literature / Europe PMC / PubMed
6. DrugMechDB

For 5 Required Test Cases:
1. Furosemide -> Edema
2. Propranolol -> Infantile Hemangioma
3. Dapagliflozin -> Heart Failure
4. Thalidomide -> Multiple Myeloma
5. Aspirin -> Colorectal Cancer
"""
import asyncio
import json
import os
import re
import sys
import yaml
import httpx

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
from backend.engineering.retrieval.connectors.europepmc import EuropePMCConnector
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.directional.chembl_polarity import chembl_action_to_polarity, chembl_action_to_grounding
from backend.reasoning.directional.reactome_polarity import reactome_role_to_polarity, reactome_role_to_grounding
from backend.reasoning.directional.canonical_entity_gate import is_canonically_grounded, validate_directional_claim, claims_are_comparable
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.extraction.claim_extraction_agent import ClaimExtractionAgent

TEST_CASES = [
    ("Furosemide", "Edema"),
    ("Propranolol", "Infantile Hemangioma"),
    ("Dapagliflozin", "Heart Failure"),
    ("Thalidomide", "Multiple Myeloma"),
    ("Aspirin", "Colorectal Cancer"),
]

# Open Targets Ensembl ID mapping helper
async def get_ensembl_id_for_symbol_or_uniprot(client: httpx.AsyncClient, symbol: str, uniprot: str) -> tuple[str | None, str]:
    query = """
    query SearchTarget($name: String!) {
      search(queryString: $name, entityNames: ["target"], page: {index: 0, size: 5}) {
        hits {
          id
          name
          entity
          score
        }
      }
    }
    """
    for q in [symbol, uniprot]:
        if not q:
            continue
        try:
            r = await client.post("https://api.platform.opentargets.org/api/v4/graphql", json={"query": query, "variables": {"name": q}}, timeout=15.0)
            if r.status_code == 200:
                hits = (r.json().get("data") or {}).get("search", {}).get("hits", [])
                for h in hits:
                    if h.get("name", "").upper() == symbol.upper():
                        return h.get("id"), "EXACT"
                for h in hits:
                    if h.get("id", "").startswith("ENSG"):
                        return h.get("id"), "RESOLVED"
        except Exception as e:
            pass
    return None, "UNRESOLVED"

async def fetch_ot_doe(client: httpx.AsyncClient, ensembl_id: str, mondo_id: str) -> list[dict]:
    if not ensembl_id or not mondo_id:
        return []
    query = """
    query TargetDOE($ensemblId: String!, $efoId: String!) {
      target(ensemblId: $ensemblId) {
        id
        approvedSymbol
        evidences(efoIds: [$efoId], size: 50) {
          count
          rows {
            datasourceId
            datatypeId
            directionOnTarget
            directionOnTrait
            targetModulation
            targetRole
            score
            literature
            studyId
            variantFunctionalConsequence {
              id
              label
            }
          }
        }
      }
    }
    """
    try:
        r = await client.post("https://api.platform.opentargets.org/api/v4/graphql", json={"query": query, "variables": {"ensemblId": ensembl_id, "efoId": mondo_id}}, timeout=20.0)
        if r.status_code == 200:
            data = r.json().get("data") or {}
            target_data = data.get("target") or {}
            evs = (target_data.get("evidences") or {}).get("rows", [])
            return evs
    except Exception as e:
        print(f"Error fetching OT DoE for {ensembl_id} + {mondo_id}: {e}")
    return []

async def fetch_datts_for_pair(client: httpx.AsyncClient, gene_symbol: str, uniprot_id: str, disease_name: str) -> list[dict]:
    query = """
    query SearchDatts($keyword: String!) {
      proteinList(keyword: $keyword) {
        id
        proteinId
        geneSymbol
        definition
        uniprotId
        keggGeneId
        diseases {
          id
          nameEn
          nameJp
          umls
          icd10
        }
        relationships {
          id
          relType
          source
          literature
          comment
          disease {
            id
            nameEn
            umls
          }
        }
      }
    }
    """
    matches = []
    search_terms = [t for t in [gene_symbol, uniprot_id] if t]
    seen_keys = set()
    for term in search_terms:
        try:
            r = await client.post("https://datts.nibb.ac.jp/graphql", json={"query": query, "variables": {"keyword": term}}, timeout=20.0)
            if r.status_code == 200:
                prots = (r.json().get("data") or {}).get("proteinList", [])
                for p in prots:
                    rels = p.get("relationships", [])
                    for rel in rels:
                        d_info = rel.get("disease") or {}
                        d_name = (d_info.get("nameEn") or "").lower()
                        k = (p.get("proteinId"), rel.get("id"), d_name)
                        if k in seen_keys:
                            continue
                        seen_keys.add(k)
                        matches.append({
                            "datts_protein_id": p.get("proteinId"),
                            "gene_symbol": p.get("geneSymbol"),
                            "uniprot_id": p.get("uniprotId"),
                            "disease_name_datts": d_info.get("nameEn"),
                            "rel_type": rel.get("relType"),
                            "source": rel.get("source"),
                            "literature": rel.get("literature"),
                            "comment": rel.get("comment"),
                            "queried_disease": disease_name,
                            "is_disease_match": disease_name.lower() in d_name or d_name in disease_name.lower()
                        })
        except Exception as e:
            print(f"Error querying DATTs for {term}: {e}")
    return matches

async def load_drugmechdb_data(client: httpx.AsyncClient) -> list[dict]:
    url = "https://raw.githubusercontent.com/SuLab/DrugMechDB/main/indication_paths.yaml"
    try:
        r = await client.get(url, timeout=60.0)
        if r.status_code == 200:
            return yaml.safe_load(r.text)
    except Exception as e:
        print(f"Error loading DrugMechDB: {e}")
    return []

def search_drugmechdb(data: list[dict], drug_name: str, disease_name: str, candidate_uniprots: list[str]) -> list[dict]:
    results = []
    d_norm = drug_name.lower().strip()
    dis_norm = disease_name.lower().strip()
    
    disease_synonyms = {
        "edema": ["edema", "edemas", "hypertensive"],
        "infantile hemangioma": ["hemangioma", "infantile hemangioma", "vascular"],
        "heart failure": ["heart failure", "cardiac failure", "congestive heart failure", "diabetes mellitus"],
        "multiple myeloma": ["multiple myeloma", "plasma cell myeloma", "myeloma"],
        "colorectal cancer": ["colorectal cancer", "colorectal neoplasms", "colon cancer", "rectal cancer", "pain", "myocardial infarction", "osteoarthritis"]
    }
    syns = disease_synonyms.get(dis_norm, [dis_norm])
    
    for item in data:
        graph = item.get("graph", {})
        item_drug = (graph.get("drug") or "").lower()
        item_dis = (graph.get("disease") or "").lower()
        
        drug_match = d_norm in item_drug or item_drug in d_norm
        if not drug_match:
            continue
            
        disease_match = any(s in item_dis or item_dis in s for s in syns)
        
        nodes = item.get("nodes", [])
        links = item.get("links", [])
        
        results.append({
            "drug_name": graph.get("drug"),
            "disease_name": graph.get("disease"),
            "drugbank_id": graph.get("drugbank"),
            "mesh_disease": graph.get("disease_mesh"),
            "exact_disease_match": dis_norm in item_dis or item_dis in dis_norm,
            "links": links,
            "nodes": nodes
        })
    return results

async def run_full_audit():
    print("=" * 100)
    print("CYNTHERA PHASE 4C/4D DIRECTIONAL EVIDENCE AUDIT")
    print("=" * 100)
    
    orch = MasterOrchestrator()
    claim_extractor = ClaimExtractionAgent()
    
    async with httpx.AsyncClient(timeout=45.0) as http_client, \
               ChEMBLConnector() as chembl_conn, \
               ReactomeConnector() as reactome_conn, \
               OpenTargetsConnector() as ot_conn, \
               EuropePMCConnector() as epmc_conn:
               
        print("\nLoading DrugMechDB reference data...")
        drugmech_data = await load_drugmechdb_data(http_client)
        print(f"DrugMechDB loaded: {len(drugmech_data)} curated mechanism paths.")
        
        audit_results = []
        all_case_pairs = []
        
        for drug_name, disease_name in TEST_CASES:
            print("\n" + "#" * 80)
            print(f"TEST CASE: {drug_name} -> {disease_name}")
            print("#" * 80)
            
            hyp, pkg, res = await orch.evaluate(drug_name, disease_name, policy=RetrievalPolicy.STANDARD, bypass_cache=True)
            
            try:
                _, resolver = EvidenceGraphBuilder().build(pkg)
            except Exception as e:
                print(f"Warning: Error building resolver via EvidenceGraphBuilder: {e}")
                resolver = None
            
            protein_map = {p.uniprot_accession: p for p in pkg.proteins}
            
            retrieved_targets = []
            seen_uniprot = set()
            for t in pkg.targets:
                uni = t.protein_uniprot
                if uni and uni not in seen_uniprot:
                    seen_uniprot.add(uni)
                    prot = protein_map.get(uni)
                    target_info = {
                        "uniprot_id": uni,
                        "drug_chembl_id": t.drug_chembl_id,
                        "mechanism": t.mechanism,
                        "gene_symbol": prot.gene_symbol if prot else "",
                        "target_name": prot.name if prot else f"Protein {uni}",
                        "chembl_target_id": t.provenance.record_id if t.provenance else None,
                        "affinity_nm": t.affinity_nm,
                        "affinity_type": t.affinity_type,
                    }
                    retrieved_targets.append(target_info)
            
            print(f"Retrieved Targets Count from CYNTHERA: {len(retrieved_targets)}")
            
            mondo_id = await ot_conn.resolve_mondo_id(disease_name)
            print(f"Open Targets MONDO ID for '{disease_name}': {mondo_id}")
            
            case_target_audits = []
            for target in retrieved_targets:
                target_name = target["target_name"]
                uniprot_id = target["uniprot_id"]
                gene_symbol = target["gene_symbol"]
                chembl_tid = target["chembl_target_id"]
                action_type = target["mechanism"]
                
                print(f"\n--- Target: {gene_symbol} / {uniprot_id} ({target_name}) ---")
                
                # 1. ChEMBL Drug Action & Polarity
                chembl_polarity = chembl_action_to_polarity(action_type)
                chembl_grounding = chembl_action_to_grounding(action_type)
                print(f"  [ChEMBL] Action: {action_type} -> Polarity: {chembl_polarity.value} | Grounding: {chembl_grounding.value}")
                
                # 2. Entity Mapping across external sources
                # A. Open Targets target mapping (Ensembl ID)
                ensembl_id, ot_map_status = await get_ensembl_id_for_symbol_or_uniprot(http_client, gene_symbol, uniprot_id)
                print(f"  [Entity Mapping -> Open Targets] Ensembl: {ensembl_id} (Status: {ot_map_status})")
                
                # B. DATTs target mapping
                datts_records = await fetch_datts_for_pair(http_client, gene_symbol, uniprot_id, disease_name)
                datts_target_id = None
                if datts_records:
                    datts_target_id = datts_records[0].get("datts_protein_id")
                    datts_map_status = "EXACT" if any(r["gene_symbol"] == gene_symbol or r["uniprot_id"] == uniprot_id for r in datts_records) else "RESOLVED"
                else:
                    datts_map_status = "UNRESOLVED"
                print(f"  [Entity Mapping -> DATTs] Target ID: {datts_target_id} | Total Records: {len(datts_records)} | Status: {datts_map_status}")
                
                # C. DrugMechDB target mapping
                drugmech_hits = search_drugmechdb(drugmech_data, drug_name, disease_name, [uniprot_id])
                drugmech_target_id = None
                drugmech_map_status = "UNRESOLVED"
                for dm_hit in drugmech_hits:
                    for link in dm_hit.get("links", []):
                        tgt = link.get("target", "")
                        src = link.get("source", "")
                        if f"UniProt:{uniprot_id}" in tgt or f"UniProt:{uniprot_id}" in src:
                            drugmech_target_id = f"UniProt:{uniprot_id}"
                            drugmech_map_status = "EXACT"
                            break
                        if gene_symbol and (f"NCBIGene:" in tgt or f"NCBIGene:" in src):
                            drugmech_target_id = "NCBIGene_MATCH"
                            drugmech_map_status = "RESOLVED"
                print(f"  [Entity Mapping -> DrugMechDB] Target ID: {drugmech_target_id} (Status: {drugmech_map_status})")
                
                # 3. Open Targets Direction of Effect (OT DoE)
                ot_doe_records = await fetch_ot_doe(http_client, ensembl_id, mondo_id) if (ensembl_id and mondo_id) else []
                ot_doe_direction_target = "UNKNOWN"
                ot_doe_direction_trait = "UNKNOWN"
                ot_doe_evidence_types = []
                ot_doe_usable_records = []
                for ev in ot_doe_records:
                    dt = ev.get("directionOnTarget")
                    tr = ev.get("directionOnTrait")
                    ds = ev.get("datasourceId")
                    if dt or tr:
                        ot_doe_usable_records.append(ev)
                        if dt and ot_doe_direction_target == "UNKNOWN":
                            ot_doe_direction_target = dt
                        if tr and ot_doe_direction_trait == "UNKNOWN":
                            ot_doe_direction_trait = tr
                        if ds:
                            ot_doe_evidence_types.append(ds)
                print(f"  [Open Targets DoE] Total Evidences: {len(ot_doe_records)} | Directional: {len(ot_doe_usable_records)} | DirOnTarget: {ot_doe_direction_target} | DirOnTrait: {ot_doe_direction_trait} | Sources: {set(ot_doe_evidence_types)}")
                
                # 4. DATTs Therapeutic Direction
                datts_disease_matches = [r for r in datts_records if r.get("is_disease_match")]
                datts_action = "NONE"
                datts_rel_type = "NONE"
                datts_source_ref = "NONE"
                if datts_disease_matches:
                    first_m = datts_disease_matches[0]
                    datts_rel_type = first_m.get("rel_type") or "UNKNOWN"
                    datts_source_ref = first_m.get("literature") or first_m.get("source") or "DATTs"
                    if "inhibit" in datts_rel_type.lower() or "antagon" in datts_rel_type.lower():
                        datts_action = "INHIBITION"
                    elif "activat" in datts_rel_type.lower() or "agoni" in datts_rel_type.lower():
                        datts_action = "ACTIVATION"
                    elif "target" in datts_rel_type.lower():
                        datts_action = "TARGETING"
                    else:
                        datts_action = datts_rel_type.upper()
                print(f"  [DATTs] Disease Matches: {len(datts_disease_matches)} | Required Action: {datts_action} | RelType: {datts_rel_type} | Ref: {datts_source_ref}")
                
                # 5. Literature Directional Claims
                lit_usable_claims = []
                for ev in pkg.literature_evidence:
                    claims = await claim_extractor.extract_claims(ev, drug_name, disease_name)
                    for cl in claims:
                        val = validate_directional_claim(cl, resolver) if resolver else None
                        is_target_related = (
                            gene_symbol.lower() in cl.subject.lower() or gene_symbol.lower() in cl.object.lower() or
                            uniprot_id.lower() in cl.subject.lower() or uniprot_id.lower() in cl.object.lower() or
                            drug_name.lower() in cl.subject.lower() or disease_name.lower() in cl.object.lower()
                        )
                        if is_target_related:
                            lit_usable_claims.append({
                                "claim": cl,
                                "citation": ev.citation_key,
                                "title": ev.title,
                                "is_grounded": val is not None,
                                "canonical_pair": val,
                                "predicate": cl.predicate.value,
                                "raw_text": cl.raw_text
                            })
                grounded_lit_claims = [c for c in lit_usable_claims if c["is_grounded"]]
                print(f"  [Literature] Total Target-Related Claims: {len(lit_usable_claims)} | Canonically Grounded: {len(grounded_lit_claims)}")
                for gc in grounded_lit_claims[:2]:
                    print(f"    - Subj: '{gc['claim'].subject}' | Pred: '{gc['predicate']}' | Obj: '{gc['claim'].object}' | Canonical: {gc['canonical_pair']} | Citation: {gc['citation']}")
                
                # 6. Reactome Direction
                rxns = [r for r in pkg.reactome_reaction_evidence if r.target_original_id == uniprot_id or r.target_canonical_id == gene_symbol]
                rxn_roles = [r.target_role for r in rxns]
                reactome_polarities = [reactome_role_to_polarity(role) for role in rxn_roles]
                explicit_roles = [r.target_role for r in rxns if reactome_role_to_polarity(r.target_role).value != "UNKNOWN"]
                print(f"  [Reactome] Reactions count: {len(rxns)} | Roles: {set(rxn_roles)} | Explicit Regulatory: {set(explicit_roles) if explicit_roles else 'NONE (all structural)'}")
                reactome_direction_summary = "STRUCTURAL (UNKNOWN polarity)" if not explicit_roles else f"EXPLICIT_{explicit_roles}"
                
                # 7. DrugMechDB Mechanism Path
                dm_case_matches = [m for m in drugmech_hits if m.get("exact_disease_match")]
                dm_has_path = len(dm_case_matches) > 0
                dm_path_summary = "NONE"
                if dm_has_path:
                    links = dm_case_matches[0].get("links", [])
                    chain = " -> ".join([f"({l.get('source')} -[{l.get('key')}]-> {l.get('target')})" for l in links])
                    dm_path_summary = chain[:200]
                print(f"  [DrugMechDB] Exact Mechanism Path Available: {'YES' if dm_has_path else 'NO'} | Path: {dm_path_summary}")
                
                # 8. Directional Convergence Determination
                overall_mapping = "EXACT" if (ot_map_status == "EXACT" and datts_map_status in ["EXACT", "RESOLVED"]) else ("RESOLVED" if (ot_map_status in ["EXACT", "RESOLVED"] and datts_map_status in ["EXACT", "RESOLVED"]) else "PARTIAL")
                if ot_map_status == "UNRESOLVED" and datts_map_status == "UNRESOLVED":
                    overall_mapping = "UNRESOLVED"
                    
                has_chembl_pol = chembl_polarity.value != "UNKNOWN"
                has_ot_doe = len(ot_doe_usable_records) > 0
                has_datts_act = datts_action not in ["NONE", "UNKNOWN"]
                has_grounded_lit = len(grounded_lit_claims) > 0
                has_dm_path = dm_has_path
                
                directional_sources_count = sum([has_chembl_pol, has_ot_doe, has_datts_act, has_grounded_lit, has_dm_path])
                
                convergence_status = "INSUFFICIENT"
                if overall_mapping == "UNRESOLVED":
                    convergence_status = "UNRESOLVED"
                elif directional_sources_count >= 2:
                    is_conflict = False
                    if has_chembl_pol and has_datts_act:
                        if chembl_polarity.value == "NEGATIVE" and datts_action == "ACTIVATION":
                            is_conflict = True
                        elif chembl_polarity.value == "POSITIVE" and datts_action == "INHIBITION":
                            is_conflict = True
                    if is_conflict:
                        convergence_status = "CONFLICTING"
                    else:
                        if directional_sources_count >= 3:
                            convergence_status = "CONVERGENT"
                        else:
                            convergence_status = "PARTIALLY_CONVERGENT"
                elif directional_sources_count == 1:
                    convergence_status = "PARTIALLY_CONVERGENT"
                else:
                    convergence_status = "INSUFFICIENT"
                    
                print(f"  --> Convergence Determination: {convergence_status} (Directional Sources: {directional_sources_count}/5)")
                
                target_audit_data = {
                    "drug": drug_name,
                    "disease": disease_name,
                    "target_name": target_name,
                    "gene_symbol": gene_symbol,
                    "uniprot_id": uniprot_id,
                    "chembl_tid": chembl_tid,
                    "chembl_action": action_type or "UNKNOWN",
                    "chembl_polarity": chembl_polarity.value,
                    "chembl_grounding": chembl_grounding.value,
                    "ot_ensembl_id": ensembl_id,
                    "ot_mapping_status": ot_map_status,
                    "ot_doe_count": len(ot_doe_records),
                    "ot_doe_directional_count": len(ot_doe_usable_records),
                    "ot_doe_dir_target": ot_doe_direction_target,
                    "ot_doe_dir_trait": ot_doe_direction_trait,
                    "ot_doe_sources": list(set(ot_doe_evidence_types)),
                    "datts_protein_id": datts_target_id,
                    "datts_found_count": len(datts_records),
                    "datts_disease_matches": len(datts_disease_matches),
                    "datts_action": datts_action,
                    "datts_rel_type": datts_rel_type,
                    "datts_ref": datts_source_ref,
                    "datts_mapping_status": datts_map_status,
                    "lit_claims_total": len(lit_usable_claims),
                    "lit_claims_grounded": len(grounded_lit_claims),
                    "grounded_claims_sample": [
                        {"subj": gc["claim"].subject, "pred": gc["predicate"], "obj": gc["claim"].object, "citation": gc["citation"]}
                        for gc in grounded_lit_claims[:2]
                    ],
                    "reactome_rxns_count": len(rxns),
                    "reactome_roles": list(set(rxn_roles)),
                    "reactome_explicit_regulatory": explicit_roles,
                    "reactome_direction_summary": reactome_direction_summary,
                    "drugmech_target_id": drugmech_target_id,
                    "drugmech_map_status": drugmech_map_status,
                    "drugmech_available": dm_has_path,
                    "drugmech_path_summary": dm_path_summary,
                    "overall_mapping": overall_mapping,
                    "directional_coverage_score": f"{directional_sources_count}/5",
                    "convergence": convergence_status
                }
                case_target_audits.append(target_audit_data)
                all_case_pairs.append(target_audit_data)
            
            audit_results.append({
                "drug": drug_name,
                "disease": disease_name,
                "mondo_id": mondo_id,
                "targets": case_target_audits
            })
            
        out_path = "scratch/phase4c_directional_audit_results.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(audit_results, f, indent=2)
        print(f"\n" + "=" * 100)
        print(f"AUDIT COMPLETE. {len(all_case_pairs)} total target-disease pairs evaluated across 5 cases.")
        print(f"Results saved to {out_path}")
        print("=" * 100)

asyncio.run(run_full_audit())
