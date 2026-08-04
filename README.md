# 🧬 CYNTHERA - Agentic AI for Drug Repurposing

**Mechanism-grounded drug repurposing through multi-agent AI reasoning**

CYNTHERA is an agentic AI system that evaluates drug-disease repurposing hypotheses through mechanism-driven reasoning, cross-verification, and uncertainty modeling. Unlike pure similarity-based approaches, it prioritizes biological plausibility and produces fully explainable outputs with uncertainty as a first-class citizen.

---

## ✨ Features

- **Mechanism-First Reasoning**: Traces multi-hop biological pathways (Drug → Target → Pathway → Disease Gene) using Reactome and UniProt data.
- **Multi-Agent Architecture**: Coordinates deterministic engineering pipeline components with specialized reasoning agents.
- **Flexible LLM Provider Engine**: Native support for **Groq API** (`llama-3.3-70b-versatile`) and **Google Gemini** (`gemini-2.0-flash`) with automatic, weighted rule-based fallback.
- **Per-Source Claims Breakdown**: Full citation and provenance tracking per data source (PubMed, Europe PMC, Open Targets, ClinicalTrials.gov).
- **Contextual Clinical Trial Analysis**: Inspects `whyStopped` trial logs to distinguish true safety/efficacy failures from administrative friction (low enrollment, COVID-19 delays, funding limits).
- **Raw-Response SQLite Cache Layer**: Tiered TTL caching (30-day structural, 14-day associations, 7-day literature, 1-day clinical trials) with `--no-cache` bypass.
- **Identity Resolution Hard Gate**: Short-circuits invalid queries gracefully with `RESOLUTION_FAILED` status when canonical database IDs cannot be resolved.
- **100% Free Open Biomedical Data**: Built entirely on free, open biomedical APIs.
- **Interactive Streamlit Web UI & CLI**: Rich visual dashboard and command-line interfaces.

---

## 🏗️ Architecture

CYNTHERA uses a **sealed two-tier architecture**: a deterministic engineering retrieval layer feeds a structured `RetrievalPackage` into an agentic reasoning layer.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ENGINEERING LAYER (Deterministic)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Master Orchestrator → Identity Resolver (ChEMBL, MeSH, MONDO, UniProt)   │
│                       ↓                                                 │
│ Async Parallel Retrieval Pipeline (PubMed, Europe PMC, Open Targets,    │
│                     Reactome, ClinicalTrials.gov, DisGeNET)            │
│                       ↓                                                 │
│ SQLite Raw-Response Cache Layer (`data/cynthera.db`)                    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                        Sealed `RetrievalPackage`
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│                      REASONING LAYER (Agentic + Rules)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Claim Extraction Agent (Groq / Gemini LLM with discounted Fallback)    │
│                       ↓                                                 │
│ 6 Parallel Expert Agents:                                                │
│   • Support Assessment Agent     • Mechanistic Expert Agent             │
│   • Clinical & Safety Agent      • Risk Assessment Agent                │
│   • Disease Biology Expert       • Contradiction Analysis Agent         │
│                       ↓                                                 │
│ Deterministic Consensus & Rule Engine (v3.1 Evidence-First Rules)       │
│                       ↓                                                 │
│ Scientific Audit Report & Recommendation Status                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🌐 Data Sources (100% Free & Open)

| Data Source | Domain / Information | Connector / Protocol |
| :--- | :--- | :--- |
| **ChEMBL** | Drug bioactivities, mechanisms, indication data | REST (`httpx`) |
| **UniProt** | Human protein accessions, Swiss-Prot canonical mapping | REST (`httpx`) |
| **Reactome** | Human biological pathways & participant mapping | REST (`httpx`) |
| **Europe PMC** | Open-access biomedical literature & abstracts | REST (`httpx`) |
| **PubMed** | NCBI literature & MEDLINE citations | E-utilities REST (`httpx`) |
| **Open Targets** | MONDO disease-gene associations & UniProt mapping | GraphQL (`_post_with_retry`) |
| **ClinicalTrials.gov** | Human trial status & `whyStopped` termination logs | REST API v2 (`httpx`) |
| **DisGeNET** | Gene-disease association scores | REST (`httpx`) |

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

---

### Running via CLI

Evaluate a drug-disease pair from the command line:

```bash
python main.py --drug "Aspirin" --disease "Multiple Myeloma"
```

Bypass raw response cache for fresh live API data:
```bash
python main.py --drug "Duloxetine" --disease "Diabetic Neuropathy" --no-cache
```

Save full JSON report to file:
```bash
python main.py --drug "Thalidomide" --disease "Multiple Myeloma" --output report.json
```

---

### Running the Web Interface

Launch the interactive Streamlit dashboard:

```bash
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

---

### Running the API Server

Launch the FastAPI backend server:

```bash
python -m uvicorn backend.api.main:app --reload --port 8000
```

Open interactive Swagger documentation at `http://localhost:8000/docs`.

---

## 📊 Sample Output & Report Structure

CYNTHERA generates a comprehensive `ScientificAuditReport` containing:

```text
============================================================
CYNTHERA HYPOTHESIS REPORT
============================================================
Drug: Duloxetine (ChEMBL ID: CHEMBL1175)
Disease: Diabetic Neuropathy (MeSH ID: D003929, MONDO ID: MONDO_0001583)
Recommendation: PROMISING
Support Score (SS): 0.984 (HIGH)
Mechanistic Score (MS): 0.793 (HIGH)
Risk Score (RS): 0.000 (NONE)

Summary:
CYNTHERA v2.0 analysis of Duloxetine → Diabetic Neuropathy produced a recommendation of 'PROMISING'.
Evidence Strength: 98.4% (HIGH) | Mechanistic Plausibility: 79.3% (HIGH) | Risk Level: 0.0% (NONE).
4 claim(s) extracted from literature (4 from pubmed), 0 contradiction(s) detected. Safety grade: A. 9 mechanistic path(s) traced.

Claims Breakdown by Source:
  • PUBMED: 4 claim(s)
============================================================
```

---

## 📁 Project Structure

```
cynthera/
├── backend/                 # Server-side application code
│   ├── api/                 # FastAPI application layer & routes
│   ├── core/                # Domain models, value objects, and enums
│   │   ├── domain/          #   Drug, Disease, Claim, Evidence, ApprovalSignal
│   │   ├── enums/           #   RecommendationStatus, TrialOutcomeStatus, etc.
│   │   └── value_objects/   #   ERW, ProvenanceReference, CanonicalIdentifier
│   ├── engineering/         # Deterministic retrieval infrastructure
│   │   ├── orchestrator/    #   Master Orchestrator
│   │   ├── identity/        #   Identity Resolution Service (ChEMBL, MeSH, MONDO)
│   │   └── retrieval/       #   Pipeline, Connectors (Europe PMC, Open Targets, etc.)
│   ├── infrastructure/      # SQLite RawResponseCache (`data/cynthera.db`), logging
│   └── reasoning/           # Agentic reasoning & rule engine
│       ├── extraction/      #   ClaimExtractionAgent (Groq/Gemini + Fallback)
│       ├── agents/          #   6 Expert Agents (Mechanistic, Clinical, Risk, etc.)
│       └── rules/           #   Deterministic v3.1 Rule Engine
├── frontend/               # Streamlit MVP web app (`app.py`)
├── tests/                  # Unit and integration test suite (`pytest`)
├── main.py                 # CLI entry point
├── .env.example            # Environment template
└── requirements.txt        # Python dependencies
```

---

## 🧪 Running Tests

Run unit tests:
```bash
python -m pytest tests/unit/ -v
```

---

## 📝 License & Disclaimer

This project is built for research and educational purposes. Hypotheses and scores output by CYNTHERA should be evaluated by domain experts prior to clinical or experimental decisions.
