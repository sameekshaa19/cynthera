# CYNTHERA: Engineering Specification
## Contradiction-Aware Mechanistic Reasoning for Explainable Drug Repurposing

---

## 1 Executive Summary

### 1.1 Document Purpose
This document serves as the foundational engineering specification and single source of truth for the design, development, and evaluation of **CYNTHERA** (Contradiction-Aware Mechanistic Reasoning for Explainable Drug Repurposing). It establishes the high-level vision, core requirements, scientific principles, and operational constraints for the system, guiding software engineers, computational biologists, and researchers throughout the system's lifecycle.

### 1.2 System Concept
CYNTHERA is a mechanism-grounded, contradiction-aware, multi-agent AI system designed to scientifically evaluate drug repurposing hypotheses. Unlike traditional computational approaches that focus primarily on candidate generation and evidence aggregation, CYNTHERA operates on a principle of falsification. It actively searches for, models, and scores conflicting biological evidence, failed clinical trials, compensatory biological pathways, and epistemic uncertainty.

### 1.3 Strategic Rationale
De novo drug discovery is notoriously slow, costly, and prone to late-stage failures. While drug repurposing—identifying new therapeutic indications for existing approved compounds—offers an accelerated pathway to clinical use, contemporary computational repurposing tools suffer from a critical flaw: they are built to confirm rather than challenge. These systems aggregate literature and database references, averaging out contradictions and masking critical failures. A system that averages conflicting target-binding assays or overlooks a terminated Phase II trial presents an overconfident and potentially hazardous recommendation.

CYNTHERA exists to address this gap. Rather than acting as a discovery engine that generates novel chemical entities, CYNTHERA functions as a rigorous, automated validation layer. By treating cross-source scientific disagreement as a first-class decision variable rather than noise, CYNTHERA provides an honest, auditable, and mathematically calibrated assessment of whether a drug's proposed mechanism of action is viable for a target disease.

---

## 2 Vision

The long-term vision of CYNTHERA is to transform the role of artificial intelligence in biomedical research from a generative "oracle" into a critical, explainable scientific collaborator. This vision is built upon five pillars:

```
                  ┌─────────────────────────────────────┐
                  │        EXPLAINABLE BIOMEDICAL AI    │
                  │   Causal chains over correlations   │
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │      CONTRADICTION-AWARE REASONING  │
                  │   Disagreement as a primary signal  │
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │         EVIDENCE TRACEABILITY       │
                  │  GRADE-inspired provenance mapping  │
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │         REPRODUCIBLE SCIENCE        │
                  │  Deterministic mathematical scoring │
                  └──────────────────┬──────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │        HUMAN-AI COLLABORATION       │
                  │ Adversarial validation for research │
                  └─────────────────────────────────────┘
```

*   **Explainable Biomedical AI**: Machine learning in biomedicine must move past black-box predictions. CYNTHERA envisions an AI that communicates its reasoning through explicit, human-interpretable biological pathways and causal chains, enabling researchers to inspect and challenge every step.
*   **Contradiction-Aware Reasoning**: Disagreement between experimental studies, literature, and curated databases represents critical biological and translational information. CYNTHERA envisions reasoning frameworks that explicitly represent, propagate, and penalize conflict, preventing overconfident recommendations.
*   **Evidence Traceability**: Every claim made by the system must be linked to its underlying source. The system envisions a zero-trust model of clinical claims where every assertion of target binding, pathway activation, or clinical efficacy is traceable to specific publications or database records.
*   **Reproducible Science**: Computational evaluations must be deterministic and auditable. Given the same state of external biological knowledge, CYNTHERA's reasoning and scoring models must yield identical, reproducible results, eliminating the stochastic variability common in generative AI pipelines.
*   **Human-AI Collaboration**: Rather than replacing human judgment, CYNTHERA is designed to enhance it. It provides computational biologists and clinical researchers with a tireless, objective "devil's advocate" that systematically stress-tests hypothesis translatability before resource-intensive wet-lab or clinical trials begin.

---

## 3 Mission

CYNTHERA’s mission is to build a robust, production-grade, and scientifically rigorous software platform that evaluates drug repurposing hypotheses by attempting to falsify them. 

The system achieves this mission through five core operational capabilities:

| Capability | Description | Core Focus |
| :--- | :--- | :--- |
| **Dynamic Evidence Retrieval** | Query, normalize, and ingest heterogeneous, open-access biomedical data sources covering chemical bioactivity, pathways, clinical trials, and literature. | Heterogeneous Data ingestion & Entity Resolution |
| **Mechanistic Hypothesis Evaluation** | Map and trace the causal biological pathways linking a drug's target profile to the pathophysiology of a target disease. | Causal Pathway Alignment & Target Mapping |
| **Cross-Source Contradiction Detection** | Detect and score directionally inconsistent claims (e.g., target activation vs. inhibition, efficacy vs. failed clinical outcome) across sources. | Contradiction Scoring & Directional Conflicts |
| **Epistemic Uncertainty Quantification** | Synthesize supporting evidence, database reliability, and detected contradictions into a unified, mathematically calibrated plausibility score. | Plausibility Calibration & Evidence Weighting |
| **Auditable Report Generation** | Produce comprehensive, traceable, and human-readable audit reports detailing the exact provenance of every biological claim. | Scientific Audit Trails & Provenance Mapping |

---

## 4 Problem Statement

Computational drug repurposing currently struggles with a set of systemic issues that limit its utility and safety in clinical translation:

*   **Confirmation Bias in Evidence Aggregation**: Most current systems search for and combine supporting evidence to validate a drug-disease relationship. If a drug has 10 papers supporting an effect and 2 high-quality studies showing no effect, typical aggregation systems average the conflict away or ignore the negative findings entirely, presenting an artificially high confidence score.
*   **Lack of Contradiction Modeling**: Databases and literature frequently report conflicting findings due to differences in experimental conditions, assay technologies, tissue types, or species. Current AI models lack the formal mathematical and logical architecture to represent "disagreement" as a distinct state, treating it instead as random noise.
*   **Neglect of Translational and Safety Falsification**: A drug may show strong target binding in vitro but fail in vivo due to compensatory biological pathways, resistance mechanisms, or pharmacokinetic limitations. AI systems rarely scan for failed or terminated clinical trials for the target indication or related mechanisms, leading to the selection of candidates that have already failed in human trials.
*   **Overconfident and Opaque Predictions**: Machine learning models, particularly graph neural network (GNN) embeddings and deep learning classifiers, output probability scores without explaining the biological rationale. When these models make incorrect, overconfident predictions, researchers cannot inspect the underlying network weights to understand *why* the prediction was made.
*   **Asymmetric Evidence Treatment**: Current systems often treat all citations equally. An in vitro cell line binding assay is weighted similarly to a Phase III double-blind randomized controlled trial (RCT). The lack of a formal hierarchy of evidence quality leads to skewed assessments.

---

## 5 Goals

CYNTHERA's objectives are divided into four core categories to ensure alignment across development, scientific validation, system engineering, and research publication.

### 5.1 Functional Goals
*   **Targeted Hypothesis Assessment**: Accept a single drug and a single disease query and return a complete mechanistic evaluation.
*   **Source Provenance Tracking**: Resolve and trace every database entry, paper citation, and clinical trial identifier to a persistent URI.
*   **Automated Conflict Flagging**: Highlight claims where bioactivity, pathway directionality, or trial results conflict.
*   **Hierarchical Reporting**: Output reports categorized into distinct tiers: Promising, Uncertain, and Not Recommended based on evidence quality and conflict penalties.

### 5.2 Scientific Goals
*   **Formulate an Evidence Hierarchy**: Define a rigid weighting system based on clinical evidence frameworks (such as GRADE) to differentiate clinical, in vivo, in vitro, and computational data.
*   **Develop a Contradiction Scoring Formula**: Design a mathematical representation of cross-source conflict that penalizes overall hypothesis confidence rather than averaging it.
*   **Incorporate Translational Falsification**: Formulate a mechanism to detect and score clinical failures (e.g., terminated trials due to lack of efficacy) and biological feedback loops.
*   **Calibrate Plausibility Scores**: Ensure that final plausibility ratings reflect the actual reproducibility and translatability of the drug-disease mechanism.

### 5.3 Engineering Goals
*   **Modular Multi-Agent Architecture**: Separate logical concerns into specialized, autonomous agents (e.g., retrieval, target enumeration, disease mapping, conflict analysis) coordinated by a central orchestrator.
*   **Deterministic Reasoning Layer**: Implement the scoring, conflict evaluation, and path-tracing logic as deterministic algorithms, ensuring that the system's core metrics are reproducible.
*   **Robust Cache and Rate-Limiting Layer**: Design a centralized caching system to minimize external API requests, optimize query speeds, and adhere strictly to external server rate limits.
*   **Strict Type-Safety and Schemas**: Implement rigorous data validation schemas to ensure that noisy data from external biological sources is normalized and validated before reasoning occurs.

### 5.4 Research Goals
*   **Establish a Calibration Benchmark**: Curate a standard benchmark dataset consisting of known successful repurposings, documented clinical failures, and controversial/contested therapeutic claims.
*   **Evaluate False-Positive Reduction**: Measure the reduction of false-positive recommendations when using contradiction-aware scoring compared to baseline evidence-aggregation systems.

---

## 6 Non-Goals

To maintain a sharp engineering focus and avoid scope creep, the following areas are explicitly excluded from CYNTHERA’s scope:

*   **No Generative De Novo Drug Design**: The system will not generate, predict, or design novel chemical structures, peptides, or biologics. It only evaluates existing, approved, or clinically cataloged compounds.
*   **No Unsupervised Global Screening**: The system will not perform all-to-all screenings of thousands of drugs against thousands of diseases to find novel associations. It is designed to perform deep, targeted evaluations of user-defined hypotheses.
*   **No Replacement of Human Clinicians**: CYNTHERA is not a clinical decision support tool for prescribing drugs to individual patients. It is a research tool for evaluating repurposing feasibility.
*   **No Wet-Lab Validation**: The software does not automate, control, or integrate with laboratory robotics, assays, or physical experimental setups.
*   **No Primary Literature Writing or Fact Creation**: The system will not generate new biological facts or write synthetic scientific literature. It relies strictly on external databases and published literature to retrieve and evaluate existing knowledge.

---

## 7 Target Users

CYNTHERA is engineered for professionals and institutions involved in translational medicine, pharmacology, and computational biology:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             TARGET USERS                                 │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   COMPUTATIONAL  │       │  DRUG DISCOVERY  │       │     ACADEMIC     │
│    BIOLOGISTS    │       │    SCIENTISTS    │       │   RESEARCHERS    │
│                  │       │                  │       │   & STUDENTS     │
│  Validate high-  │       │  Stress-test pipeline│       │  Audit claims,   │
│  throughput hits │       │  candidates, prevent │       │  explore pathways│
│  & trace pathways│       │  translational loss  │       │  & literature    │
└──────────────────┘       └──────────────────┘       └──────────────────┘
```

*   **Computational Biologists**: Need to validate candidate hits from high-throughput screening or genomics pipelines. They require access to detailed biological pathways, evidence weights, and API-accessible reasoning chains to integrate into their larger workflows.
*   **Drug Discovery Scientists (Biotech/Pharma)**: Focus on pipeline safety and clinical translatability. They use the system to identify potential showstoppers—such as hidden clinical failures or compensatory pathway loops—before dedicating capital to wet-lab validation.
*   **Academic Researchers and Graduate Students**: Require a transparent tool to audit scientific literature. They use the system's structured reports to explore biological mechanisms, identify gaps in current literature, and verify citations.

---

## 8 Guiding Principles

The development, maintenance, and execution of CYNTHERA must adhere to the following principles:

1.  **Mechanism Over Similarity**: Biological plausibility must be evaluated through causal pathway interactions rather than relying solely on chemical similarity or shared disease signatures. A drug is only considered a viable candidate if a logical chain of mechanistic interactions can be traced from its target to the disease pathophysiology.
2.  **Evidence Over Opinion**: Assertions must be weighted based on a strict hierarchy of empirical evidence. A clinical trial result is fundamentally more reliable than an in vitro binding assay, which is more reliable than a computational prediction.
3.  **Deterministic Scoring Integrity**: All scores—including target relevance, pathway overlap, contradiction penalties, and final plausibility metrics—must be calculated using clear, deterministic mathematical formulas. Stochastic processes (such as free-form LLM scoring) are forbidden in the scoring pipeline.
4.  **LLMs as Information Extractors, Not Decision Makers**: Large Language Models are used strictly as natural language parsing assistants—extracting relationships, entity names, and claim stances from unstructured text. They are never permitted to make the final determination of a drug’s viability or assign numerical confidence scores.
5.  **Absolute Provenance and Traceability**: Every claim, edge, node, or score presented in the final report must link back to its exact source database, publication DOI, or trial ID. Speculative claims without verifiable provenance are rejected.
6.  **Contradiction Penalization**: Contradictory evidence is not averaged out. When sources disagree on a drug’s mechanism of action or efficacy, the overall plausibility score must be penalized. In science, high contradiction does not equal average confidence; it equals high uncertainty.
7.  **Epistemic Honesty**: If the system cannot find sufficient evidence to support or falsify a mechanism, it must report low confidence due to data sparsity rather than projecting a speculative score.

---

## 9 Success Criteria

CYNTHERA's success is measured across five distinct dimensions:

### 9.1 Scientific Success
*   **Falsification Accuracy**: The system must successfully identify and downgrade known failed drug repurposing cases (e.g., drugs that failed Phase II or Phase III trials for the target disease) on the benchmark dataset, achieving a falsification rate of $>90\%$.
*   **False-Positive Reduction**: When compared to baseline evidence-aggregation systems, CYNTHERA must reduce false-positive recommendations by at least $30\%$ on the evaluation benchmark by actively detecting contradictions.

### 9.2 Engineering Success
*   **Reasoning Determinism**: Given identical database snapshots and input parameters, the system must produce identical numerical scores (Contradiction Score, Falsification Penalty, and Mechanistic Plausibility Score) across repeated runs.
*   **Resource Cache Efficiency**: Cache hit rate should exceed $70\%$ for common target-disease queries, significantly reducing API load and query latency.

### 9.3 Software Success
*   **Interface Clarity**: The user interface must present the evidence hierarchy, detected contradictions, and causal pathways in a clear, scannable format, minimizing cognitive load for clinical reviewers.
*   **Schema Conformity**: $100\%$ validation rates for extracted evidence against internal Pydantic/dataclass schemas, with clean error handling for malformed external data.

### 9.4 Performance Success
*   **Query Latency**: Deep evaluation queries must complete within 120 seconds for standard drug-disease pairs under normal API rate-limit conditions.
*   **Graceful Degradation**: If an external API is down, the system must degrade gracefully, using cached data or executing other agents while clearly indicating the missing source in the final report.

### 9.5 Explainability Success
*   **Zero-Gap Provenance**: $100\%$ of claims in the generated audit report must be accompanied by an active reference (URL, DOI, or NCT Identifier).
*   **Scoring Transparency**: The report must display the mathematical breakdown of the Mechanistic Plausibility Score, showing the exact impact of the target relevance, pathway overlap, contradiction score, and falsification penalty.

---

## 10 Constraints

The system architecture and operational environment are bounded by the following constraints:

*   **Strictly Open-Access Data**: CYNTHERA must rely exclusively on free, public, and open-access biomedical APIs (e.g., NCBI PubMed E-utilities, EMBL-EBI ChEMBL API, Reactome Analysis Service, UniProt REST API, and ClinicalTrials.gov API). The integration of proprietary databases or APIs requiring paid licenses is prohibited.
*   **Deterministic Evaluation Logic**: The final scoring layer must execute strictly within deterministic code. No stochastic elements, random seeds, or LLM-generated scores may influence the final Mechanistic Plausibility Score.
*   **Stateless Execution**: The core reasoning pipeline must remain stateless. A query for Drug D and Disease T must not be influenced by prior queries, except via static caching mechanisms.
*   **No Structural Modeling at Runtime**: The system does not perform heavy molecular docking or structural protein simulations (e.g., running AlphaFold or AutoDock) during runtime. It relies on pre-calculated structural annotations and affinity data available in database endpoints.
*   **API Rate-Limit Compliance**: The system must strictly respect the rate limits of public endpoints (e.g., NCBI limits of 3 requests/second without an API key, 10 requests/second with a key). Rate limiters and back-off mechanisms must be built-in.
*   **Correctness Prioritized Over Speed**: Accuracy and deep validation of literature claims are more important than response times. The system is allowed to take up to several minutes to perform deep literature extraction and contradiction mapping rather than returning a fast, shallow result.

---

## 11 Assumptions

The design of CYNTHERA is based on the following assumptions:

*   **Public API Stability**: The external biomedical database APIs (NCBI, EMBL-EBI, Reactome, UniProt, ClinicalTrials.gov) will remain operational, maintain backward-compatible endpoints, and provide public access.
*   **Biomedical Identifier Mapping Feasibility**: Heterogeneous identifiers (ChEMBL IDs, PubChem CIDs, UniProt Accession Numbers, MeSH IDs, and Gene Symbols) can be normalized and mapped using cross-references available in UniProt and ChEMBL.
*   **Sufficient Literature Coverage**: There is a critical mass of peer-reviewed biomedical literature and clinical trial metadata available through PubMed and Europe PMC to perform meaningful stance detection and contradiction mapping.
*   **LLM API Availability**: High-performance LLM APIs (such as Gemini, GPT, or local open-source models via Ollama) are available for unstructured text information extraction tasks, and their performance is sufficient for identifying claims and stances.
*   **Parametric Memory Boundaries**: The LLM’s internal parametric memory is treated as untrusted. The system assumes the LLM will only be used to process retrieved context, never to generate biological facts from its own weights.

---

## 12 Risks

The CYNTHERA project must mitigate several critical risks:

| Risk Category | Risk Description | Mitigation Strategy |
| :--- | :--- | :--- |
| **Scientific** | **Publication Bias**: Negative results or failed laboratory experiments are rarely published, which could limit the volume of contradictory evidence available to the system. | Actively mine ClinicalTrials.gov for terminated/failed trials, and search Europe PMC for preprints and negative-results journals. |
| **Engineering** | **API Instability & Deprecation**: Public databases frequently modify their API endpoints, schemas, or rate-limiting policies, which can break data retrieval pipelines. | Implement abstraction layers for database connectors, establish strict schema validation, and maintain local fallback caches. |
| **API** | **Rate Limiting & IP Blocking**: High-frequency queries during parallel execution could trigger IP blocking or severe rate-limiting by federal database servers (e.g., NCBI). | Implement queue-based rate-limiting, thread-safe sleep intervals, and require user API keys for higher rate-limit tiers. |
| **LLM** | **Hallucination & Non-Determinism**: LLM agents may extract false relationships or misinterpret claims from literature abstracts. | Use strictly defined JSON schemas for LLM outputs, run verification loops on extracted terms, and keep scoring deterministic. |
| **Data Quality** | **Noisy/Incomplete Databases**: Curated databases may contain outdated annotations, incorrect protein targets, or mismatched identifiers. | Cross-verify claims across multiple databases (e.g., verify ChEMBL target binding using UniProt target details and literature). |
| **Scalability** | **Literature Ingestion Latency**: Broad drug-disease queries returning thousands of PubMed articles can cause request times to exceed timeouts. | Use multi-stage filtering (e.g., first filter by abstract relevancy before downloading full text or running LLM extraction). |

---

## 13 Future Scope

The architecture of CYNTHERA is designed to allow modular expansion. Future iterations of the system are planned to incorporate the following capabilities:

*   **Offline Graph Database Integration**: Migrate from live API traversal to a locally hosted graph database (e.g., Neo4j) populated with multimodal precision medicine knowledge graphs like PrimeKG or Hetionet. This will reduce query latencies from minutes to milliseconds and enable complex graph path-finding algorithms.
*   **Persistent Reasoning Memory**: Implement vector database-backed long-term memory for reasoning agents, allowing them to store validated biological claims, target mappings, and resolved contradictions across user queries.
*   **Clinical Guideline and Real-World Evidence (RWE) Ingestion**: Integrate the system with databases containing clinical guidelines, electronic health records (EHR) metadata, and post-market surveillance databases (such as FDA FAERS) to capture real-world drug efficacy and adverse events.
*   **Genomics and Patient-Specific Repurposing**: Extend the Disease Relevance Agent to ingest individual patient genomic sequencing data (VCF files). This will enable personalized drug repurposing evaluations based on the specific mutations and dysregulated pathways present in a single patient.
*   **Structural Biology Reasoning**: Integrate programmatic access to protein structure repositories (such as AlphaFold DB and PDB) to evaluate the structural binding viability of drugs against target proteins, providing a physics-based verification of ChEMBL bioactivity data.
*   **Language-Agnostic Processing**: Expand the retrieval layer to ingest and translate non-English biomedical literature, capturing a broader set of international trials and clinical findings.
*   **Automatic Hypothesis Refinement**: If a hypothesis is rejected due to a specific contradiction or falsification (e.g., "Drug A cannot treat Disease B because it is a promoter of Pathway C, which exacerbates the disease"), the system could automatically search for and propose structural analogs or related drugs that inhibit Pathway C.
