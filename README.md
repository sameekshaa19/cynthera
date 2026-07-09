# 🧬 Cynthera - Agentic AI for Drug Repurposing

**Mechanism-grounded drug repurposing through multi-agent AI reasoning**

> [!NOTE]
> For the comprehensive, research-grade architectural blueprint and engineering design guidelines, see the [Foundational Engineering Specification](file:///c:/Users/User/Desktop/cynthera/SPECIFICATION.md).

Cynthera is an agentic AI system that evaluates drug-disease pairs through mechanism-driven reasoning, cross-verification, and uncertainty modeling. Unlike similarity-based approaches, it prioritizes biological plausibility and produces explainable outputs with uncertainty as a first-class citizen.

## ✨ Features

- **Mechanism-First Reasoning**: Prioritizes biological plausibility over similarity matching
- **Multi-Agent Architecture**: 4 specialized agents working in coordination
- **Uncertainty Quantification**: Treats conflicts and uncertainty as first-class outputs
- **Explainable Results**: Full citation tracking and provenance for all claims
- **100% Free Resources**: Uses only free/open-source databases and tools
- **Interactive Web UI**: Modern Streamlit interface with visualizations
- **CLI Support**: Command-line interface for batch processing

## 🏗️ Architecture

### MVP Agents (Phase 1)

1. **MoA Enumeration Agent**: Identifies drug targets and mechanisms from PubChem, ChEMBL, Reactome
2. **MoA Cross-Verification Agent**: Validates targets, scores strengths, and detects conflicts
3. **Disease Relevance Agent**: Evaluates mechanism-disease alignment using gene-disease associations
4. **Synthesis Agent**: Generates comprehensive hypothesis reports with confidence scores
5. **Master Orchestrator**: Coordinates all agents and manages workflow

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
streamlit run ui/streamlit_app.py
```

Then open your browser to `http://localhost:8501`

### Using the CLI

```bash
python main.py --drug "Metformin" --disease "Alzheimer's disease"
```

With JSON output:
```bash
python main.py --drug "Sildenafil" --disease "Pulmonary Hypertension" --output report.json
```

## 📖 Usage Examples

### Example 1: Known Repurposing (Sildenafil → Pulmonary Hypertension)

```python
from models.data_models import DrugInput, DiseaseInput
from orchestrator.orchestrator import MasterOrchestrator

drug = DrugInput(name="Sildenafil")
disease = DiseaseInput(name="Pulmonary Hypertension")

orchestrator = MasterOrchestrator()
report = orchestrator.process(drug, disease)

print(f"Recommendation: {report.recommendation}")
print(f"Confidence: {report.overall_confidence.value:.2f}")
```

### Example 2: Controversial Case (Metformin → Alzheimer's)

```python
drug = DrugInput(name="Metformin", pubchem_cid=4091)
disease = DiseaseInput(name="Alzheimer's disease")

orchestrator = MasterOrchestrator()
report = orchestrator.process(drug, disease)

# Access detailed results
for chain in report.moa_chains:
    print(f"Mechanism: {chain.mechanism_description}")
    print(f"Confidence: {chain.confidence.value:.2f}")

for uncertainty in report.uncertainties:
    print(f"Uncertainty: {uncertainty}")
```

## 📁 Project Structure

```
cynthera/
├── agents/                 # Individual agent implementations
│   ├── moa_enumeration_agent.py
│   ├── moa_cross_verification_agent.py
│   ├── disease_relevance_agent.py
│   └── synthesis_agent.py
├── orchestrator/          # Master orchestrator
│   └── orchestrator.py
├── data/                  # Data access layer
│   ├── database_connectors.py
│   └── cache_manager.py
├── models/                # Data models and schemas
│   └── data_models.py
├── utils/                 # Shared utilities
│   ├── logger.py
│   └── confidence_scoring.py
├── ui/                    # User interface
│   └── streamlit_app.py
├── config/                # Configuration
│   └── config.yaml
├── main.py               # CLI entry point
└── requirements.txt      # Dependencies
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

### Phase 1: MVP (Current)
- ✅ Core 4 agents
- ✅ Free data source integration
- ✅ Streamlit UI
- ✅ Basic confidence scoring

### Phase 2: Enhanced Capabilities
- [x] MoA Cross-Verification Agent
- [ ] Clinical & Safety Agent
- [ ] Literature Scan Agent
- [ ] Prior Knowledge Agent (vector DB)
- [ ] LLM integration for reasoning
- [ ] Advanced conflict resolution

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
