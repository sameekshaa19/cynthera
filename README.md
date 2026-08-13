# 🧬 CYNTHERA — An evidence-traceable, mechanism-grounded AI research assistant for drug repurposing

CYNTHERA investigates a **Drug + Disease** hypothesis and produces a scientifically defensible **mechanistic plausibility assessment** with the underlying biological reasoning and the actual sources that support it exposed for direct inspection.

The system is built on two principles:

1. **Mechanism-first, evidence-grounded reasoning.** Biological relationships (Drug → Target → Pathway → Disease-associated gene → Disease) are traced from retrieved data, not invented by an LLM. LLMs may interpret or summarize retrieved evidence; they do not fabricate it.
2. **Traceability.** Every important conclusion is linked back through claims and evidence to the actual papers, databases, and trials used — with direct access links where a source is publicly available.

---

## ✨ What CYNTHERA does

**Input:** a drug name and a disease name.

```
Drug: Sildenafil          →          Disease: Pulmonary Arterial Hypertension
```

**Output:** a structured assessment containing:

| Output component | Description |
| :--- | :--- |
| **Mechanistic Plausibility** | `HIGH / MEDIUM / LOW / INSUFFICIENT EVIDENCE` + a numerical score. |
| **Mechanistic chain** | The multi-hop biological chain `Drug → Target → Pathway → Disease gene → Disease`. |
| **Why?** | Per-hop explanation with the evidence supporting each step. |
| **Supporting / contradicting evidence** | Papers and trials for and against the hypothesis. |
| **Sources accessed** | Exactly which databases and papers were used. |
| **Direct links** | Clickable access to the underlying resource (paper, database, trial). |

**What CYNTHERA does not do:** it does not autonomously "discover" or clinically recommend drugs. It is a research-support tool: it assembles, scores, and explains the mechanistic evidence for a hypothesis so a domain expert can evaluate it.

---

## ✨ Features

- **Mechanism-First Reasoning**: Traces multi-hop biological pathways (Drug → Target → Pathway → Disease Gene) using ChEMBL, Reactome, UniProt, Open Targets, and DisGeNET data. Each hop is grounded in retrieved evidence — relationships are never invented.
- **Evidence-Grounded Scoring**: Deterministic, explainable mechanistic scores computed from actual retrieved biological evidence (target–affinity confidence, pathway participation, disease-gene validation, per-hop confidence). The system can explain exactly why a score was produced.
- **Anti-Inflation Scoring**: Multiple weak paths are not naively combined into one strong conclusion. Scores are conservative and reproducible.
- **Per-Hop Mechanistic Reasoning**: Every hop in `Drug → Target → Pathway → Disease gene → Disease` is supported by direction-consistent retrieved evidence and validated by disease-gene associations.
- **Claim → Evidence → Source → URL Traceability**: Every important conclusion is linked back through its claim and evidence to the actual PMID / DOI / database identifier, with direct source URLs.
- **Direct Source Access**: Papers expose title, authors, year, PMID, DOI, and direct access buttons distinguishing `[Open PubMed]`, `[Open Europe PMC]`, `[Open DOI]`, and `[Open Full Text / PDF]`. PDF/full-text links are shown only when actually and legally publicly available — never fabricated. When the same paper is retrieved from multiple sources, it is deduplicated into one paper with multiple access options.
- **Source Transparency**: Reports show a `SOURCES ACCESSED` section listing every database and paper used, each with a direct link to the exact resource/entity/paper.
- **Evidence Separation**: Mechanistic evidence, clinical evidence, and safety/risk evidence are kept clearly separate and never mixed.
- **Contextual Clinical Trial Analysis**: Inspects `whyStopped` trial logs to distinguish true safety/efficacy failures from administrative friction (low enrollment, COVID-19 delays, funding limits).
- **Contradiction Detection**: Conflicting evidence is detected, reported, and shown with its sources.
- **Honest Failure Handling**: Retrieval failures are never silently converted into scientific conclusions. The system distinguishes `DATA NOT FOUND`, `SOURCE UNAVAILABLE`, `IDENTITY RESOLUTION FAILED`, `INSUFFICIENT EVIDENCE`, `CONTRADICTORY EVIDENCE`, `MECHANISTICALLY UNSUPPORTED`, and `MECHANISTICALLY PLAUSIBLE`. A ChEMBL API outage produces `INSUFFICIENT EVIDENCE`, not "not plausible".
- **Identity Resolution Hard Gate**: Short-circuits invalid queries gracefully when canonical database IDs cannot be resolved.
- **LLM Claim Extraction with Fallback**: Extracts claims from retrieved literature via Groq/Gemini with an automatic rule-based fallback when the LLM is unavailable.
- **Raw-Response SQLite Cache**: Tiered TTL caching (structural, associations, literature, clinical trials) with a `--no-cache` bypass for fresh live data.
- **100% Free Open Biomedical Data**: Built entirely on free, open biomedical APIs.
- **Interactive Streamlit Web UI, FastAPI, & CLI**: Rich visual dashboard, REST API, and command-line interfaces.

---

## 🏗️ Architecture

CYNTHERA uses a **sealed two-tier architecture**: a deterministic engineering retrieval layer feeds a structured `RetrievalPackage` into an agentic + rule-based reasoning layer.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ENGINEERING LAYER (Deterministic)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Master Orchestrator → Identity Resolver (ChEMBL, MeSH, MONDO, UniProt)   │
│                       ↓                                                 │
│ Async Parallel Retrieval Pipeline (PubMed, Europe PMC, Open Targets,    │
│                     Reactome, ClinicalTrials.gov, DisGeNET, OpenAlex)   │
│                       ↓                                                 │
│ SQLite Raw-Response Cache Layer (`data/cynthera.db`)                    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                        Sealed `RetrievalPackage`
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│                      REASONING LAYER (Agentic + Rules)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Claim Extraction Agent (Groq / Gemini LLM, rule-based fallback)         │
│                       ↓                                                 │
│ 6 Parallel Expert Agents:                                                │
│   • Support Assessment Agent     • Mechanistic Expert Agent             │
│   • Clinical & Safety Agent      • Risk Assessment Agent                │
│   • Disease Biology Expert       • Contradiction Analysis Agent         │
│                       ↓                                                 │
│ Deterministic Consensus & Rule Engine (Evidence-First Rules)            │
│                       ↓                                                 │
│ Scientific Audit Report & Recommendation Status                        │
└─────────────────────────────────────────────────────────────────────────┘
```

- The **engineering layer** is deterministic: it resolves canonical IDs and retrieves structured data from open biomedical APIs.
- The **reasoning layer** extracts claims from retrieved literature, traces and scores the biological evidence chain, detects contradictions, and applies a deterministic rule engine to produce a recommendation. The mechanistic score is computed from retrieved biological evidence — it is not an arbitrary LLM-generated number.

---

## 🌐 Data Sources (100% Free & Open)

| Data Source | Domain / Information | Direct access |
| :--- | :--- | :--- |
| **ChEMBL** | Drug bioactivities, targets, mechanisms | https://www.ebi.ac.uk/chembl/ |
| **UniProt** | Human protein accessions, canonical mapping | https://www.uniprot.org/ |
| **Reactome** | Human biological pathways & participants | https://reactome.org/ |
| **Europe PMC** | Open-access literature & abstracts | https://europepmc.org/ |
| **PubMed** | MEDLINE citations & abstracts | https://pubmed.ncbi.nlm.nih.gov/ |
| **Open Targets** | Disease–gene associations & UniProt mapping | https://platform.opentargets.org/ |
| **DisGeNET** | Gene–disease association scores | https://www.disgenet.org/ |
| **ClinicalTrials.gov** | Human trial status & termination logs | https://clinicaltrials.gov/ |
| **OpenAlex** | Open scholarly literature metadata | https://openalex.org/ |
| **Semantic Scholar** | Citation-weighted literature evidence | https://www.semanticscholar.org/ |

---

## 🚀 Quick Start

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/sameekshaa19/cynthera.git
   cd cynthera
   ```

2. **Set up a Python virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and set your preferred LLM provider:
   ```bash
   copy .env.example .env  # Windows
   # or: cp .env.example .env
   ```

   In `.env`:
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_groq_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
   Optional keys (PubMed rate limits, DisGeNET, Semantic Scholar) are documented in `.env.example`.

### Running via CLI

Evaluate a drug-disease pair from the command line:

```bash
python main.py --drug "Sildenafil" --disease "Pulmonary Arterial Hypertension"
```

Bypass the raw-response cache for fresh live API data:
```bash
python main.py --drug "Duloxetine" --disease "Diabetic Neuropathy" --no-cache
```

Save the full JSON report to file:
```bash
python main.py --drug "Thalidomide" --disease "Multiple Myeloma" --output report.json
```

### Running the Web Interface

```bash
streamlit run app.py
```
Then open `http://localhost:8501`.

### Running the API Server

```bash
python -m uvicorn backend.api.main:app --reload --port 8000
```
Interactive Swagger docs at `http://localhost:8000/docs`.

---

## 📊 Sample Output

CYNTHERA reports the assessment as a research narrative: verdict → why → per-hop mechanism → evidence → sources → direct links.

```text
==================================================
CYNTHERA — DRUG REPURPOSING ASSESSMENT
==================================================

Drug:     Sildenafil
Disease:  Pulmonary Arterial Hypertension

--------------------------------------------------
OVERALL ASSESSMENT
--------------------------------------------------
Mechanistic Plausibility : HIGH
Score                    : 0.82
Evidence Status          : WELL SUPPORTED

--------------------------------------------------
WHY?
--------------------------------------------------

1. Drug → Target
   Sildenafil → PDE5
   Evidence: ChEMBL, PubMed, Europe PMC
   [Open ChEMBL] [Open Paper] [Open DOI]

2. Target → Pathway
   PDE5 → cGMP signaling
   Evidence: Reactome, PubMed
   [Open Reactome] [Open Paper]

3. Pathway → Disease
   cGMP signaling → pulmonary vasodilation → PAH
   Evidence: Open Targets, PubMed
   [Open Open Targets] [Open Paper]

--------------------------------------------------
SUPPORTING EVIDENCE
--------------------------------------------------
Paper 1
  Title:  ...
  Authors: ...
  Year:   ...
  PMID:   ...
  DOI:    ...
  [Open PubMed] [Open DOI] [Open Full Text / PDF]

--------------------------------------------------
CONTRADICTING / LIMITING EVIDENCE
--------------------------------------------------
Paper 3
  [Open Source]

--------------------------------------------------
CLINICAL EVIDENCE
--------------------------------------------------
Trial:        NCT...
Status:       Completed
Why stopped:  ...
  [Open ClinicalTrials.gov]

--------------------------------------------------
SOURCES ACCESSED
--------------------------------------------------
ChEMBL · UniProt · Reactome · Open Targets · DisGeNET ·
PubMed · Europe PMC · ClinicalTrials.gov
```

---

## 🔗 Evidence & Traceability Model

Every important conclusion is traceable:

```
Conclusion
    ↓
Claim ID
    ↓
Evidence IDs
    ↓
PMID / DOI / database identifier
    ↓
Direct source URL
```

For literature sources, CYNTHERA exposes — whenever available — paper title, authors, year, PMID, DOI, and direct access buttons that distinguish:

- `[Open PubMed]`
- `[Open Europe PMC]`
- `[Open DOI]`
- `[Open Full Text / PDF]` — **only** when a full text/PDF is actually and legally publicly available. CYNTHERA never invents or fabricates PDF links; if a PDF is not public, the most authoritative accessible source is shown instead.

When the same paper is retrieved from multiple sources (e.g., a PubMed PMID and a Europe PMC PMC ID), it is **deduplicated** into a single paper with multiple legitimate access options.

---

## 🛑 Failure-State Handling

A retrieval failure is **never** silently converted into a scientific conclusion. These states are distinct and are never conflated:

| State | Meaning |
| :--- | :--- |
| `DATA NOT FOUND` | The query succeeded but no data exists for this entity. |
| `SOURCE UNAVAILABLE` | A source API failed or was unreachable (e.g., ChEMBL returned HTTP 500). |
| `IDENTITY RESOLUTION FAILED` | The drug/disease name could not be resolved to a canonical database ID. |
| `INSUFFICIENT EVIDENCE` | Not enough retrieved evidence to assess mechanism — not a claim of implausibility. |
| `CONTRADICTORY EVIDENCE` | Retrieved evidence conflicts; the disagreement is shown. |
| `MECHANISTICALLY UNSUPPORTED` | The evidence was retrieved but does not support the hypothesized mechanism. |
| `MECHANISTICALLY PLAUSIBLE` | Retrieved evidence supports the mechanism. |

**Example.** If ChEMBL is unavailable:

- ❌ **Bad:** `Mechanistic score = 0 → LOW` ("not plausible").
- ✅ **Good:** `Mechanistic assessment = INSUFFICIENT EVIDENCE`, reason = *target evidence could not be retrieved*.

---

## 📐 Scoring

Scores are **deterministic, evidence-grounded, and explainable**. The system can explain exactly why a score was produced, from the retrieved biological evidence:

- **Support Score (SS)** — strength of retrieved literature evidence.
- **Mechanistic Score (MS)** — plausibility of the traced biological chain (Drug → Target → Pathway → Disease gene → Disease), built from target–affinity confidence, pathway relevance (disease-gene overlap), pathway participation, and per-hop confidence.
- **Risk Score (RS)** — clinical safety signals from trials and adverse-event evidence.

The score design optimizes **correctness over completeness over confidence**: if evidence is insufficient the system says `INSUFFICIENT EVIDENCE` rather than guessing, shows disagreement when sources conflict, and never inflates confidence by combining multiple weak paths into one strong conclusion.

---

## ✅ Validation

The system is validated against known drug-disease relationships:

| Pair | Expectation |
| :--- | :--- |
| **Sildenafil → Pulmonary Arterial Hypertension** | Strong, evidence-gated mechanistic chain. |
| **Metformin → Type 2 Diabetes** | Strong mechanistic evidence. |
| **Negative / weak example** | Must **not** artificially produce HIGH. |

Edge cases exercised: invalid drug, invalid disease, missing API key, missing literature, duplicate papers across sources, paper without DOI, DOI without PDF, PubMed-only paper, Europe PMC-only paper, API failure, empty pathway participants, missing target mapping.

---

## 📁 Project Structure

```
cynthera/
├── backend/                 # Server-side application code
│   ├── api/                 # FastAPI application layer & routes
│   ├── core/                # Domain models, value objects, enums
│   │   ├── domain/          #   Drug, Disease, Claim, Evidence, Hypothesis...
│   │   ├── enums/           #   RecommendationStatus, EvidenceType, ...
│   │   └── value_objects/   #   ERW, ProvenanceReference, CanonicalIdentifier
│   ├── engineering/         # Deterministic retrieval infrastructure
│   │   ├── orchestrator/    #   Master Orchestrator
│   │   ├── identity/        #   Identity Resolution Service
│   │   └── retrieval/       #   Pipeline & connectors (ChEMBL, Reactome, ...)
│   ├── infrastructure/      # SQLite cache, logging, knowledge store
│   ├── reasoning/           # Claim extraction, expert agents, multi-hop
│   │                        # reasoner, rule engine, conflict resolution
│   └── reporting/           # Report & PDF export
├── frontend/               # Streamlit web app (`app.py`)
├── tests/                  # Unit + integration test suite (`pytest`)
├── main.py                 # CLI entry point
├── .env.example            # Environment template
└── requirements.txt        # Python dependencies
```

---

## 🧪 Running Tests

```bash
python -m pytest tests/unit/ -v
```

---

## 📝 License & Disclaimer

This project is built for research and educational purposes. Hypotheses and scores output by CYNTHERA should be evaluated by domain experts prior to clinical or experimental decisions.
