"""
Concurrent Deep Reactome Capability Audit Script
"""
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REACTOME_BASE = "https://reactome.org/ContentService"

CASES_TARGETS_PATHWAYS = [
    {
        "case": "Propranolol -> Infantile Hemangioma",
        "drug": "Propranolol",
        "disease": "Infantile Hemangioma",
        "relationships": [
            {
                "target_symbol": "ADRB1",
                "uniprot": "P08588",
                "pathway_stId": "R-HSA-390696",
                "pathway_name": "Adrenoceptors"
            },
            {
                "target_symbol": "ADRB1",
                "uniprot": "P08588",
                "pathway_stId": "R-HSA-418555",
                "pathway_name": "G alpha (s) signalling events"
            }
        ]
    },
    {
        "case": "Dapagliflozin -> Heart Failure",
        "drug": "Dapagliflozin",
        "disease": "Heart Failure",
        "relationships": [
            {
                "target_symbol": "SLC5A2",
                "uniprot": "P31639",
                "pathway_stId": "R-HSA-5658208",
                "pathway_name": "Defective SLC5A2 causes renal glucosuria (GLYS1)"
            },
            {
                "target_symbol": "SLC5A2",
                "uniprot": "P31639",
                "pathway_stId": "R-HSA-189200",
                "pathway_name": "Cellular hexose transport"
            },
            {
                "target_symbol": "SLC5A1",
                "uniprot": "P13866",
                "pathway_stId": "R-HSA-5656364",
                "pathway_name": "Defective SLC5A1 causes congenital glucose/galactose malabsorption (GGM)"
            },
            {
                "target_symbol": "SLC5A1",
                "uniprot": "P13866",
                "pathway_stId": "R-HSA-8981373",
                "pathway_name": "Intestinal hexose absorption"
            },
            {
                "target_symbol": "SLC5A1",
                "uniprot": "P13866",
                "pathway_stId": "R-HSA-189200",
                "pathway_name": "Cellular hexose transport"
            }
        ]
    },
    {
        "case": "Thalidomide -> Multiple Myeloma",
        "drug": "Thalidomide",
        "disease": "Multiple Myeloma",
        "relationships": [
            {
                "target_symbol": "TNF",
                "uniprot": "P01375",
                "pathway_stId": "R-HSA-5668541",
                "pathway_name": "TNFR2 non-canonical NF-kB pathway"
            },
            {
                "target_symbol": "TNF",
                "uniprot": "P01375",
                "pathway_stId": "R-HSA-5626978",
                "pathway_name": "TNFR1-mediated ceramide production"
            },
            {
                "target_symbol": "TNF",
                "uniprot": "P01375",
                "pathway_stId": "R-HSA-9942503",
                "pathway_name": "Differentiation of naive CD4+ T cells to T helper 1 cells (Th1 cells)"
            },
            {
                "target_symbol": "TNF",
                "uniprot": "P01375",
                "pathway_stId": "R-HSA-5357786",
                "pathway_name": "TNFR1-induced proapoptotic signaling"
            },
            {
                "target_symbol": "TNF",
                "uniprot": "P01375",
                "pathway_stId": "R-HSA-5357956",
                "pathway_name": "TNFR1-induced NF-kappa-B signaling pathway"
            },
            {
                "target_symbol": "TNF",
                "uniprot": "P01375",
                "pathway_stId": "R-HSA-6783783",
                "pathway_name": "Interleukin-10 signaling"
            }
        ]
    },
    {
        "case": "Aspirin -> Colorectal Cancer",
        "drug": "Aspirin",
        "disease": "Colorectal Cancer",
        "relationships": [
            {
                "target_symbol": "PTGS2",
                "uniprot": "P35354",
                "pathway_stId": "R-HSA-9027604",
                "pathway_name": "Biosynthesis of electrophilic omega-3 PUFA oxo-derivatives"
            },
            {
                "target_symbol": "PTGS2",
                "uniprot": "P35354",
                "pathway_stId": "R-HSA-9025094",
                "pathway_name": "Biosynthesis of DPAn-3 SPMs"
            },
            {
                "target_symbol": "PTGS2",
                "uniprot": "P35354",
                "pathway_stId": "R-HSA-2142770",
                "pathway_name": "Synthesis of 15-eicosatetraenoic acid derivatives"
            },
            {
                "target_symbol": "PTGS2",
                "uniprot": "P35354",
                "pathway_stId": "R-HSA-9018679",
                "pathway_name": "Biosynthesis of EPA-derived SPMs"
            },
            {
                "target_symbol": "PTGS2",
                "uniprot": "P35354",
                "pathway_stId": "R-HSA-2162123",
                "pathway_name": "Synthesis of Prostaglandins (PG) and Thromboxanes (TX)"
            },
            {
                "target_symbol": "PTGS2",
                "uniprot": "P35354",
                "pathway_stId": "R-HSA-9018677",
                "pathway_name": "Biosynthesis of DHA-derived SPMs"
            }
        ]
    },
    {
        "case": "Minoxidil -> Hair Loss",
        "drug": "Minoxidil",
        "disease": "Hair Loss",
        "relationships": [
            {
                "target_symbol": "KCNJ11",
                "uniprot": "Q14654",
                "pathway_stId": "R-HSA-5678420",
                "pathway_name": "Defective ABCC9 causes CMD10, ATFB12 and Cantu syndrome"
            },
            {
                "target_symbol": "KCNJ11",
                "uniprot": "Q14654",
                "pathway_stId": "R-HSA-5683177",
                "pathway_name": "Defective ABCC8 can cause hypo- and hyper-glycemias"
            },
            {
                "target_symbol": "KCNJ11",
                "uniprot": "Q14654",
                "pathway_stId": "R-HSA-1296025",
                "pathway_name": "ATP sensitive Potassium channels"
            },
            {
                "target_symbol": "KCNJ11",
                "uniprot": "Q14654",
                "pathway_stId": "R-HSA-5578775",
                "pathway_name": "Ion homeostasis"
            },
            {
                "target_symbol": "KCNJ11",
                "uniprot": "Q14654",
                "pathway_stId": "R-HSA-422356",
                "pathway_name": "Regulation of insulin secretion"
            },
            {
                "target_symbol": "KCNJ11",
                "uniprot": "Q14654",
                "pathway_stId": "R-HSA-382556",
                "pathway_name": "ABC-family protein mediated transport"
            }
        ]
    }
]

async def run_audit():
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=20)
    sem = asyncio.Semaphore(10)
    
    async with httpx.AsyncClient(base_url=REACTOME_BASE, timeout=15.0, limits=limits) as client:
        unique_targets = {}
        for c in CASES_TARGETS_PATHWAYS:
            for r in c["relationships"]:
                unique_targets[r["uniprot"]] = r["target_symbol"]

        print(f"Target count: {len(unique_targets)}", flush=True)

        async def fetch_target(uniprot, sym):
            async with sem:
                r_rxn = await client.get(f"/data/mapping/UniProt/{uniprot}/reactions")
                rxns = r_rxn.json() if r_rxn.status_code == 200 else []
                r_pw = await client.get(f"/data/mapping/UniProt/{uniprot}/pathways")
                pws = r_pw.json() if r_pw.status_code == 200 else []
                return uniprot, sym, rxns, pws

        tasks = [fetch_target(u, s) for u, s in unique_targets.items()]
        target_results = await asyncio.gather(*tasks)

        target_data = {}
        all_rxn_stIds = set()
        for uniprot, sym, rxns, pws in target_results:
            target_data[uniprot] = {
                "symbol": sym,
                "uniprot": uniprot,
                "reactions": rxns,
                "pathways": pws,
            }
            for rxn in rxns:
                all_rxn_stIds.add(rxn["stId"])

        print(f"Discovered {len(all_rxn_stIds)} unique reactions.", flush=True)

        rxn_details = {}
        rxn_ancestors = {}
        rxn_participants = {}

        async def fetch_rxn_info(stId):
            async with sem:
                # enhanced
                try:
                    r1 = await client.get(f"/data/query/enhanced/{stId}")
                    det = r1.json() if r1.status_code == 200 else {}
                except Exception:
                    det = {}
                # ancestors
                try:
                    r2 = await client.get(f"/data/event/{stId}/ancestors")
                    anc = r2.json() if r2.status_code == 200 else []
                except Exception:
                    anc = []
                # participants
                try:
                    r3 = await client.get(f"/data/participants/{stId}/participatingPhysicalEntities")
                    part = r3.json() if r3.status_code == 200 else []
                except Exception:
                    part = []
                return stId, det, anc, part

        rxn_tasks = [fetch_rxn_info(stId) for stId in all_rxn_stIds]
        rxn_res = await asyncio.gather(*rxn_tasks)

        for stId, det, anc, part in rxn_res:
            rxn_details[stId] = det
            rxn_ancestors[stId] = anc
            rxn_participants[stId] = part

        print(f"All reaction details fetched successfully.", flush=True)

        output_results = {
            "target_data": target_data,
            "rxn_details": rxn_details,
            "rxn_ancestors": rxn_ancestors,
            "rxn_participants": rxn_participants,
            "cases": CASES_TARGETS_PATHWAYS
        }

        with open("scratch/deep_reactome_raw_results.json", "w", encoding="utf-8") as f:
            json.dump(output_results, f, indent=2, default=str)

        print("Saved results to scratch/deep_reactome_raw_results.json", flush=True)

if __name__ == "__main__":
    asyncio.run(run_audit())
