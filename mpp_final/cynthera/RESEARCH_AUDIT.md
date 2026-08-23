# CYNTHERA Research Audit
## Evidence-Traceable Mechanistic Assessment — Full Audit, Literature Review, and Minimal-Change Implementation Design

---

## Phase 1 — Live State Validation (Probe Results)

### Probe: Thalidomide → Fatty Liver (MASLD)

**Command executed:**
```
python main.py --drug "Thalidomide" --disease "Fatty Liver" --no-cache --output probe_thalidomide_MASLD.json
```

### Runtime Scores
| Score | Value | Level |
|---|---|---|
| Support Score (SS) | 0.902 | HIGH |
| Mechanistic Score (MS) | **0.000** | **NONE** |
| Risk Score (RS) | 0.213 | LOW |
| Recommendation | UNCERTAIN | — |

### Data Coverage
| Source | Status |
|---|---|
| ChEMBL (drug-target resolution) | ❌ FAILED — chembl_resolve_failed, no ChEMBL ID assigned |
| ChEMBL (bioactivity API) | ❌ FAILED — request_error (network error) |
| Semantic Scholar | ❌ FAILED — HTTP 403 (API gating) |
| PubMed | ✅ 11 claims extracted (LLM-based) |
| MeSH disease resolution | ✅ D005234 (Fatty Liver) resolved |

### Confirmed Bugs at Runtime

#### Bug P1 — UnicodeEncodeError on JSON export (Windows cp1252)
- **Location:** main.py:109 — `f.write(result.model_dump_json(indent=2))`
- **Root cause:** Safety Agent uses checkmark/warning symbols; Windows default encoding (cp1252) cannot encode them.
- **Fix:** `open(args.output, 'w', encoding='utf-8')`

#### Bug P2 — ChEMBL Resolution Failure → MS=0.0 cascade
- ChEMBL name lookup fails for "Thalidomide" → targets=[] → no multi-hop paths → MS=0.0
- Suggest synonym retry on resolution failure (CHEMBL267, lowercase, etc.)

#### Bug P3 — literature_evidence silently excludes LITERATURE-typed evidence
- retrieval_package.py:97-107 only returns META_ANALYSIS|RCT|OBSERVATIONAL types
- OpenAlex, EuropePMC, Semantic Scholar all produce EvidenceType.LITERATURE — never feeds claim extraction

#### Bug P4 — DOI prefix check misses doi:10. format
- _extract_citations() at line 1297 checks startswith("10.") but OpenAlex produces "doi:10.xxx" keys
- DOI citations format as raw "doi:10.xxx" instead of "DOI:10.xxx"

#### Bug P5 — ClaimGraph has zero edges, never used
- _build_claim_graph() only calls add_claim(), never add_relation()
- Direction-consistent hop gating (spec §8.3) not implemented

#### Bug P6 — pathways[:4] insertion-order slice ignores relevance
- calculate_pathway_relevance_score exists but is never called from the mechanistic reasoner

#### Bug P7 — Union-inflation formula in compute_mechanistic_score
- score = 1 - prod(1 - p_i): three paths at 0.40 → 0.784 (HIGH) — unjustified
- Per DeepRoot (arXiv 2606.15931): weakest-link scoring is more conservative and accurate

#### Bug P8 — Fail-open membership guard
- Guard only fires when participant_ids is non-empty; empty list passes any target through
- Should be fail-closed: no participant data → reject, not pass

---

## Phase 2 — Literature Research & Comparative Analysis

### Systems Compared

| System | Mechanism Weighting | Evidence Handling | Traceability | Adopt/Adapt/Avoid |
|---|---|---|---|---|
| RepurAgent (bioRxiv 2026.04.20.719538) | Disease-specific KG; 4 subagents (Research/Prediction/Data/Report) + planner + supervisor; mechanistic paths grounded in KG edges | Human-supervised loop; SOPs from REMEDi4ALL; assertions trace to KG nodes | Full execution trace per step; human-reviewable | ADAPT — adopt KG-grounded hop gating; avoid LLM loop cost |
| DeepRoot (arXiv 2606.15931) | KG-coordinated; separates grounding from reasoning; graph-only = 0% hallucination; KG+LLM = 7-10% hallucination | Verified KG as constraint layer over LLM; 87% hallucination in raw LLMs | Full KG provenance per claim | ADOPT — weakest-link path scoring; 87% stat validates CYNTHERA thesis |
| DrugAgent (arXiv 2408.13378) | Coordinator + AI/ML + KG + Search/RAG agents; conflict mediation across sources; CoT + ReAct | Multi-source synthesis; agreement/conflict summarization | Per-source attribution; Chain-of-Thought rationales | ADAPT — multi-source conflict mediation; per-source claim attribution |
| Open Targets | Tiered evidence: genetics > clinical candidate > text-mining; human genetics weighted highest | Data type harmonization; provenance per association | Full source provenance; evidence browsable by type | ADOPT — OT score as pathway quality weight |
| DisGeNET | Gene-disease associations from NLP + curated; scored by evidence strength | NLP + manual curation; cumulative publication evidence | PMID/DOI per association | ADOPT — use gene-disease score as continuous base_conf modifier |
| Hetionet | DWPC path count across 29 databases; guilt-by-association inference | Network propagation ensemble | Path enumeration | ADAPT — reference for hop confidence decay (HOP_DECAY=0.72 already good) |

### Key Literature Conclusions for CYNTHERA
1. DeepRoot 87% hallucination rate directly validates CYNTHERA deterministic-grounding thesis — cite in paper
2. RepurAgent KG grounding = ClaimGraph should carry ChEMBL mechanism edges for direction-consistent gating
3. Open Targets tiered weighting = calculate_pathway_relevance_score should drive pathway ranking
4. DisGeNET scores retrieved but used as membership boolean only — extend to continuous base_conf modifier
5. DrugAgent multi-source conflict mediation validates AdvancedConflictResolver design; gap = direction-gating

---

## Phase 3 — Minimal-Change Technical Design

### Root-Cause Priority Matrix

| Bug | File | Impact | Fix Effort |
|---|---|---|---|
| P1 UnicodeEncodeError | main.py:108 | JSON export crash | Trivial |
| P3 LITERATURE evidence excluded | retrieval_package.py:97-107 | OpenAlex/EuropePMC claims never extracted | Trivial |
| P4 DOI prefix mismatch | reasoning_orchestrator.py:1297 | DOI citations malformatted | Trivial |
| P8 Fail-open membership guard | multi_hop_reasoner.py:332-341 | Spurious pathway membership | Low |
| P6 Insertion-order pathway slice | multi_hop_reasoner.py:325 | Low-relevance pathways selected | Low |
| P7 Union-inflation MS formula | multi_hop_reasoner.py:446-469 | MS artificially high | Low |
| P2 ChEMBL synonym retry | resolution_service.py | MS=0.0 on resolvable drugs | Medium |
| P5 ClaimGraph zero edges | reasoning_orchestrator.py:386-393 | Direction gating unimplemented | Medium |

### 3.1 Weakest-Link Formula (replaces union-inflation)

**Current (union-inflation):**
```python
prob_none = prod(1 - p.confidence for p in top[:3])
score = 1 - prob_none
# [0.40, 0.40, 0.40] → 1 - 0.216 = 0.784 (HIGH) — unjustified
```

**Proposed (weakest-link with diminishing returns):**
```python
top = paths[:3]
best_conf = top[0].confidence  # sorted descending
n = len(top)
# Best path drives score; additional paths add diminishing returns
score = round(best_conf * (1 - math.exp(-0.5 * n)), 4)
# [0.40, 0.40, 0.40] → 0.40 × 0.777 = 0.311 (LOW-MEDIUM) — correct
```

### 3.2 Fail-Closed Membership Guard

```python
# OLD (fail-open):
participant_ids = pathway.participant_uniprot_ids or []
clean_participants = {_clean_uniprot(pid) for pid in participant_ids if pid}
if (clean_participants and norm_uniprot not in clean_participants ...):
    continue  # only skips when list is non-empty

# NEW (fail-closed):
participant_ids = pathway.participant_uniprot_ids or []
if not participant_ids:
    logger.debug("pathway_membership_data_absent_skip", extra={...})
    continue  # no participant data → cannot assert membership → reject
clean_participants = {_clean_uniprot(pid) for pid in participant_ids if pid}
if clean_participants and norm_uniprot not in clean_participants ...:
    continue
```

### 3.3 Pathway Relevance Ranking

```python
from utils.confidence_scoring import calculate_pathway_relevance_score

drug_target_genes = [p.gene_symbol for p in package.proteins if p.gene_symbol]
disease_genes = list((package.validated_disease_genes or {}).keys())

def _score_pathway(pw) -> float:
    return calculate_pathway_relevance_score(
        pathway_genes=pw.participant_uniprot_ids or [],
        disease_genes=disease_genes,
        drug_targets=drug_target_genes,
    )

ranked_pathways = sorted(pathways, key=_score_pathway, reverse=True)
# Use ranked_pathways[:4] instead of pathways[:4]
```

### 3.4 LITERATURE Evidence Inclusion

```python
# retrieval_package.py — literature_evidence property
return [
    e for e in self.evidence_records
    if e.evidence_type in (
        EvidenceType.META_ANALYSIS,
        EvidenceType.RCT,
        EvidenceType.OBSERVATIONAL,
        EvidenceType.LITERATURE,  # ADD THIS — enables OpenAlex/EuropePMC claim extraction
    ) and e.abstract
]
```

### 3.5 DOI Citation Formatting Fix

```python
# reasoning_orchestrator.py _extract_citations()
if key.startswith("PMID:") or key.isdigit():
    pmid = key.replace("PMID:", "").strip()
    citations.append(f"PMID:{pmid} [{ev_type}, ERW:{erw:.2f}] — {title_short}")
elif key.startswith("doi:") or key.startswith("10."):  # FIX: catch doi:10. prefix
    doi_clean = key.replace("doi:", "").strip()
    citations.append(f"DOI:{doi_clean} [{ev_type}, ERW:{erw:.2f}] — {title_short}")
else:
    citations.append(f"{key} [{ev_type}, ERW:{erw:.2f}] — {title_short}")
```

### 3.6 Citation Traceability on Chain Nodes

**No new storage needed** — uses already-available `Claim.evidence_ids` → `Evidence.citation_key` mapping.

**Report assembly step** (reasoning_orchestrator.py `_generate_audit_report`):
```python
# Build evidence lookup at report time
evidence_by_id = {str(ev.id): ev for ev in package.evidence_records}

# For each chain node, collect supporting claim citations
claim_citations: dict[str, list[str]] = {}
for claim in all_claims:
    keys = [
        evidence_by_id[str(eid)].citation_key
        for eid in claim.evidence_ids
        if str(eid) in evidence_by_id
    ]
    claim_citations[str(claim.id)] = [k for k in keys if k]

# Add to ScientificAuditReport
```

---

## Phase 4 — Research Contribution Framing

### NOT Claimed
- Generic agentic drug repurposing (RepurAgent, DrugAgent, DeepRoot all precede this)
- LLM-based hypothesis generation (explicitly avoided by design)
- Clinical recommendation

### Defensible Claims (with citations)

| Claim | Differentiator | Cite |
|---|---|---|
| 100% open/free data stack | ChEMBL, Reactome, OT, DisGeNET free tier, PubMed, EuropePMC, OpenAlex — zero paid DB | — |
| Deterministic, evidence-gated MS with weakest-link transparency | Weakest-link formula; fail-closed membership; direction-consistent gating | DeepRoot arXiv 2606.15931 |
| Per-conclusion citation traceability to PMID/DOI | claim.evidence_ids → citation_key; chain nodes carry citation lists | — |
| End-to-end auditable artifacts | ReasoningResult.model_dump_json(); Streamlit audit page; PDF export | — |
| Hallucination resistance by design | Only ClaimExtractionAgent calls LLM; all scoring deterministic | DeepRoot 87% finding |
| Cost efficiency vs LLM-loop agents | Full evaluation seconds at near-zero cost vs RepurAgent human-supervisor loop | RepurAgent bioRxiv 2026.04.20.719538 |

---

## Phase 5 — File-by-File Implementation Matrix

| File | Status | Changes | Priority |
|---|---|---|---|
| main.py | MODIFY | encoding='utf-8' on output file open | P0 trivial |
| backend/core/domain/retrieval_package.py | MODIFY | Add LITERATURE to literature_evidence filter | P0 trivial |
| backend/reasoning/mechanistic/multi_hop_reasoner.py | MODIFY | Weakest-link formula, fail-closed guard, relevance-sorted pathways | P1 medium |
| backend/reasoning/orchestrator/reasoning_orchestrator.py | MODIFY | DOI prefix fix, cross-source dedup, citation map on chain nodes | P1 medium |
| backend/core/domain/reasoning_result.py | MODIFY | Add mechanistic_citation_map, claim_citations fields | P1 low |
| backend/engineering/identity/resolution_service.py | MODIFY | ChEMBL synonym retry on name-resolution failure | P2 medium |
| backend/reporting/ (PDF/Text) | MODIFY | Include citation lists in exports, parity with Streamlit | P2 low |
| tests/unit/test_mechanistic_scoring.py | NEW | Golden-value tests, formula regression, guards, dedup | P1 medium |
| RESEARCH_AUDIT.md | NEW | This document | Done |

---

## Phase 6 — Test Plan

### Golden-Value MS Regression Tests
```python
# Sildenafil → PAH: PDE5 → cGMP → pulmonary vasodilation
assert result.mechanistic_assessment.score >= 0.60
assert result.mechanistic_assessment.level in ("MEDIUM", "HIGH")
assert len(result.mechanistic_assessment.mechanistic_chain) >= 3

# Metformin → T2D: AMPK → glucose metabolism
assert result.mechanistic_assessment.score >= 0.55
```

### Formula Regression Tests
```python
# Weakest-link is always <= union-inflation for same inputs
# Three paths at 0.40 must not produce HIGH
assert weakest_link_score([0.40, 0.40, 0.40]) <= 0.50
assert union_inflation_score([0.40, 0.40, 0.40]) > 0.70  # shows old inflation
```

### Fail-Closed Guard Tests
```python
# Empty participant list → always skip
assert pathway_membership_passes(target, pathway_with_empty_participants=True) == False
# Non-member target in non-empty list → skip
assert pathway_membership_passes(target_P33402, pathway_with=[Q9Y6K9]) == False
```

### Citation Tests
```python
# DOI formatting
assert format_citation("doi:10.1016/j.jacc.2022.01.001").startswith("DOI:10.")
# Cross-source dedup (same paper from PubMed + EuropePMC)
assert len(deduplicate(["PMID:12345", "doi:10.1000/182"], pmid_doi_map={"12345": "10.1000/182"})) == 1
```

---

*Probe executed: 2026-08-13, Thalidomide → Fatty Liver (--no-cache)*
*Literature surveyed: RepurAgent bioRxiv 2026.04.20.719538, DeepRoot arXiv 2606.15931, DrugAgent arXiv 2408.13378*
*Open Targets, DisGeNET, Hetionet evidence-weighting frameworks reviewed*
