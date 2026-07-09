# 🧬 CYNTHERA - Agentic AI for Drug Repurposing

**Mechanism-grounded drug repurposing through multi-agent AI reasoning**

> [!NOTE]
> For the comprehensive, research-grade architectural blueprint and engineering design guidelines, see the [Foundational Engineering Specification](file:///c:/Users/User/Desktop/cynthera/SPECIFICATION.md).

CYNTHERA is an agentic AI system that evaluates drug-disease pairs through mechanism-driven reasoning, cross-verification, and uncertainty modeling. Unlike similarity-based approaches, it prioritizes biological plausibility and produces explainable outputs with uncertainty as a first-class citizen.

## ✨ Features

- **Mechanism-First Reasoning**: Prioritizes biological plausibility over similarity matching
- **Multi-Agent Architecture**: Specialized agents across engineering and reasoning layers working in coordination
- **Uncertainty Quantification**: Treats conflicts and uncertainty as first-class outputs
- **Explainable Results**: Full citation tracking and provenance for all claims
- **100% Free Resources**: Uses only free/open-source databases and tools
- **Interactive Web UI**: Modern Streamlit interface with visualizations
- **CLI Support**: Command-line interface for batch processing

## 🏗️ Architecture

CYNTHERA follows a **hybrid architecture** with a deterministic engineering layer and an agentic reasoning layer separated by a sealed `RetrievalPackage` boundary.

### Engineering Layer (Deterministic)

Orchestrates data acquisition, identifier resolution, and retrieval from external biomedical APIs. All operations are deterministic with no LLM involvement.

- **Master Orchestrator**: Coordinates the full pipeline lifecycle
- **Identifier Resolution Service**: Maps drug/disease names to standardized database keys (ChEMBL, PubChem, MeSH, UMLS)
- **Retrieval Planner & Query Optimizer**: Plans and optimizes API call schedules
- **Retrieval Pipeline**: Executes async parallel queries to external data sources
- **Canonical Mapping Registry**: Normalizes raw API payloads into canonical domain objects
- **Quality Gate**: Validates and seals the `RetrievalPackage` before passing to reasoning

### Reasoning Layer (Agentic + Deterministic)

Transforms structured evidence into reproducible scientific conclusions. LLMs are used strictly for claim extraction; all scoring and decision-making is deterministic.

- **Claim Extraction Agent** (LLM-assisted): Extracts structured (subject, predicate, object) triplets from literature
- **Claim Validation Agent** (deterministic): Validates and assigns Evidence Reliability Weights to claims
- **Claim Graph**: Sealed immutable graph of validated claims — the central reasoning artifact

Six parallel Expert Agents evaluate the hypothesis independently:

1. **Mechanistic Expert Agent**: Constructs and validates biological pathway chains from drug to disease
2. **Disease Biology Expert Agent**: Evaluates drug mechanism relevance to disease pathophysiology
3. **Clinical Evidence Expert Agent**: Assesses human clinical trial evidence
4. **Support Assessment Agent**: Aggregates evidence favoring the hypothesis
5. **Risk Assessment Agent**: Evaluates harm, inefficacy, and contraindication signals
6. **Contradiction Analysis Agent**: Detects and scores conflicting claims

Synthesis and decision-making:

- **Consensus Engine**: Integrates all six assessments into a unified consensus
- **Rule Engine**: Applies deterministic, versioned rules to produce a `RecommendationStatus`
- **Scientific Audit Agent**: Generates the fully traceable audit report

### Data Sources (All Free)

- **Drug Data**: PubChem, ChEMBL, DrugBank Open Data
- **Literature**: PubMed E-utilities
- **Pathways**: Reactome, WikiPathways
- **Gene-Disease**: DisGeNET
- **Proteins**: UniProt

## 🚀 Quick Start

### Installation

1. **Clone or navigate to the project directory**:
```bash
cd c:\Users\User\Desktop\cynthera
```

2. **Create a virtual environment** (recommended):
```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Optional: Set up API keys** (for higher rate limits):
```bash
copy .env.example .env
# Edit .env and add your API keys
```

### Running the Web Interface

```bash
streamlit run frontend/app.py
```

Then open your browser to `http://localhost:8502`

### Using the CLI

```bash
python main.py --drug "Sildenafil" --disease "Pulmonary Arterial Hypertension" --policy STANDARD
```

With JSON output:
```bash
python main.py --drug "Sildenafil" --disease "Pulmonary Arterial Hypertension" --output report.json
```

## 📖 Usage Examples

### Example: Async Programmatic Execution

```python
import asyncio
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

async def run_evaluation():
    orchestrator = MasterOrchestrator()
    hypothesis, package, result = await orchestrator.evaluate(
        drug_name="Sildenafil",
        disease_name="Pulmonary Arterial Hypertension",
        policy=RetrievalPolicy.STANDARD
    )
    
    print(f"Recommendation: {result.recommendation_status.value}")
    print(f"Support Score: {result.support_assessment.score:.3f}")
    print(f"Mechanistic Score: {result.mechanistic_assessment.score:.3f}")
    print(f"Risk Score: {result.risk_assessment.score:.3f}")

asyncio.run(run_evaluation())
```

> [!NOTE]
> The Python API examples above use direct library calls for development and testing. Production deployments route through the FastAPI HTTP layer as documented in the [API Contracts specification](07_API_CONTRACTS.md).

## 📁 Project Structure

```
cynthera/
├── backend/                 # Server-side application code
│   ├── api/                 # FastAPI application layer
│   │   ├── v1/routes/       # API route handlers (evaluate, hypotheses, system)
│   │   ├── dependencies.py  # Dependency injection providers
│   │   └── middleware.py    # Auth, rate limiting, trace injection
│   │   └── main.py          # FastAPI app factory
│   ├── core/                # Domain layer (no external dependencies)
│   │   ├── domain/          #   Canonical entities (Drug, Disease, Claim, etc.)
│   │   ├── enums/           #   Controlled vocabularies (PredicateType, EvidenceType, etc.)
│   │   └── value_objects/   #   Immutable value types (ERW, Provenance, Identifiers)
│   ├── engineering/         # Deterministic retrieval infrastructure
│   │   ├── orchestrator/    #   Master Orchestrator
│   │   ├── identity/        #   Identifier Resolution Service
│   │   ├── retrieval/       #   Planner, Optimizer, Pipeline, Connectors, Parsers
│   │   └── quality_gate/    #   Quality Gate
│   ├── reasoning/           # Agentic + deterministic reasoning
│   │   ├── extraction/      #   Claim Extraction Agent (LLM-assisted)
│   │   ├── validation/      #   Claim Validation Agent (deterministic)
│   │   ├── graph/           #   Claim Graph construction + sealing
│   │   ├── agents/          #   6 Expert Agents (Mechanistic, Disease, Clinical, etc.)
│   │   ├── consensus/       #   Consensus Engine + Uncertainty Model
│   │   ├── rules/           #   Rule Engine + versioned rule sets
│   │   └── audit/           #   Scientific Audit Agent
│   ├── infrastructure/      # Cross-cutting services (LLM, cache, config, logging, metrics)
│   ├── database/            # SQLAlchemy models, repositories, Alembic migrations
│   └── schemas/             # Pydantic request/response models
├── frontend/               # Streamlit MVP frontend
│   ├── app.py
│   ├── pages/              #   evaluate, results, audit, history
│   └── components/         #   score_cards, chain_viz, contradiction_table
├── tests/                  # Unit, integration, and scientific validation tests
├── config/                 # Configuration files (settings, sources, rules)
├── docker/                 # Dockerfiles + docker-compose
├── scripts/                # Operational scripts
├── pyproject.toml          # Poetry project definition
└── .env.example            # Environment variable template
```

## 🔧 Configuration

Edit `config/config.yaml` to customize:

- API endpoints and timeouts
- Confidence thresholds
- LLM settings (if using)
- Caching behavior
- Logging levels

## 🧪 Testing

Run tests (when implemented):
```bash
pytest tests/ -v
```

## 📊 Output Format

Cynthera generates comprehensive `HypothesisReport` objects containing:

- **Executive Summary**: High-level findings and recommendation
- **Mechanisms of Action**: Identified drug targets and pathways
- **Disease Relevance**: Alignment score and biological rationale
- **Confidence Assessment**: Overall confidence with detailed breakdown
- **Uncertainties**: Key limitations and conflicting evidence
- **Supporting Evidence**: All citations with provenance
- **Next Steps**: Recommended experimental validation steps

## 🛣️ Roadmap

### Phase 1: Foundation (Current)
- ✅ Deterministic engineering layer (retrieval, normalization, quality gate)
- ✅ Agentic reasoning layer (claim extraction, 6 expert agents, consensus, rules)
- ✅ Free data source integration (ChEMBL, UniProt, PubMed, Reactome, ClinicalTrials, DisGeNET)
- ✅ Streamlit UI
- ✅ Structured confidence scoring with ERW hierarchy

### Phase 2: Enhanced Capabilities
- [ ] Clinical & Safety Agent enhancements
- [ ] Literature Scan expansions
- [ ] Prior Knowledge Agent (vector DB)
- [ ] Multi-hop mechanistic reasoning
- [ ] Advanced conflict resolution
- [ ] Batch evaluation API

### Phase 3: Production Features
- [ ] Comprehensive test suite
- [ ] API deployment
- [ ] Batch processing
- [ ] Result caching and history
- [ ] User authentication
- [ ] Export to PDF reports

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- Additional data source integrations
- Enhanced confidence scoring algorithms
- Better directionality determination
- LLM-powered reasoning
- UI/UX improvements
- Test coverage

## 📝 License

This project is for educational and research purposes.

## 🙏 Acknowledgments

Built using free and open-source resources:
- PubChem (NCBI)
- ChEMBL (EMBL-EBI)
- Reactome
- PubMed
- DisGeNET
- UniProt

## 📧 Contact

For questions or feedback, please open an issue on the repository.

---

**Note**: This is an MVP implementation. Results should be validated by domain experts before any clinical or research decisions.
