# CYNTHERA: Domain Model Dictionary
## Reference Identifier: 02_DOMAIN_MODEL.md

---

## 1. Domain Model Philosophy

The domain model represents the core vocabulary and semantic language of the CYNTHERA system. It defines the logical entities, relationships, constraints, and validation rules that govern the evaluation of drug repurposing hypotheses.

This model is strictly logical: it does not define database tables, SQL schemas, or programming language implementation details. Instead, it models real-world scientific entities and their relationships.

All downstream layers—including retrieval connectors, normalization modules, reasoning engines, and recommendation rule-sets—must conform to these canonical definitions.

---

## 2. Controlled Vocabularies (Enums)

To ensure semantic consistency across all layers, the following controlled vocabularies are defined as first-class domain enums:

### 2.1 PredicateType
Represents the directional mechanism of a claims triplet:
*   `ACTIVATES`: Increases the target protein's functional activity.
*   `INHIBITS`: Decreases or blocks the target protein's functional activity.
*   `BINDS`: Physically associates with the target without specified functional direction.
*   `UPREGULATES`: Increases the expression level (transcription/translation) of a gene or protein.
*   `DOWNREGULATES`: Decreases the expression level of a gene or protein.
*   `CAUSES`: Induces a downstream pathological state or process.
*   `PREVENTS`: Halts or reverses a downstream pathological state or process.
*   `ASSOCIATED_WITH`: Statistically correlates with, but without implied direct physical causality.
*   `NO_EFFECT`: Explicitly shown to have no directional, regulatory, or binding impact.

### 2.2 EvidenceType
Categorizes the empirical origin of retrieved evidence:
*   `META_ANALYSIS`: Statistical synthesis of multiple clinical trials (highest clinical rank).
*   `RCT`: Double-blind, randomized controlled clinical trial.
*   `OBSERVATIONAL`: Human clinical cohort, case-control, or epidemiological study.
*   `IN_VIVO`: Animal model experiment (e.g., mouse, rat preclinical trial).
*   `IN_VITRO`: Cell line, membrane binding, or molecular assay experiment.
*   `COMPUTATIONAL`: Machine learning binding predictions, graph network proximity scoring, or homology modeling.

### 2.3 RecommendationStatus
The indication classification output by the recommendation engine:
*   `PROMISING`: High-quality supporting evidence with plausible biological pathways and low safety/failure risks.
*   `UNCERTAIN`: Conflicting or sparse evidence, or incomplete pathway connectivity.
*   `NOT_RECOMMENDED`: Strong contradictory evidence, failed clinical trials, or high biological risks.

### 2.4 TrialOutcomeStatus
The clinical status of a human clinical study:
*   `COMPLETED_SUCCESS`: Trial finished, meeting primary clinical endpoints.
*   `COMPLETED_FAILURE`: Trial finished, failing to meet primary endpoints.
*   `TERMINATED_LACK_OF_EFFICACY`: Trial stopped early due to insufficient therapeutic effect.
*   `TERMINATED_SAFETY`: Trial stopped early due to unacceptable toxicity or adverse events.
*   `ACTIVE`: Trial currently recruiting or running.

---

## 3. Entity Dictionary Index

The system's biological and analytical reasoning is governed by the following core canonical entities:

```
                            ┌────────────────────────┐
                            │    RetrievalSession    │
                            └───────────┬────────────┘
                                        │
                            ┌───────────▼────────────┐
                            │       Hypothesis       │
                            └───────────┬────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│      Drug       │            │     Disease     │            │    Clinical     │
│                 │            │                 │            │     Trial       │
└────────┬────────┘            └────────┬────────┘            └────────┬────────┘
         │                              │                              │
         ▼                              │                              │
┌─────────────────┐                     │                              │
│     Target      │                     │                              │
└────────┬────────┘                     │                              │
         │                              │                              │
         ▼                              ▼                              │
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│     Protein     │───────────►│Pathway / Chain  │◄───────────│     Source      │
└─────────────────┘            └─────────────────┘            └────────┬────────┘
                                                                       │
         ┌──────────────────────────────┬──────────────────────────────┘
         ▼                              ▼
┌─────────────────┐            ┌─────────────────┐
│    Evidence     │            │      Claim      │
└────────┬────────┘            └────────┬────────┘
         │                              │
         └──────────────┬───────────────┘
                        ▼
              ┌──────────────────┐
              │  Contradiction   │
              └──────────────────┘
```

---

## 4. Detailed Entity Specifications

### 4.1 RetrievalSession

*   **Definition**: A record documenting the details, performance, and configurations of a data retrieval operation.
*   **Purpose**: Ensure trace auditability for cache hits, API latency logs, connection errors, and third-party database versions.
*   **Created by**: Master Orchestrator.
*   **Consumed by**: Log Aggregator, Performance Dashboard, System Administrator.
*   **Mutability**: **Immutable** once compiled.
*   **Lifecycle**: Formed at the start of a query execution, populated with connection and cache metrics, and archived with the final report.
*   **Relationships**:
    *   Linked to exactly one **Hypothesis** instance (1:1).
    *   Contains metadata for all queried **Source** entities.
*   **Validation Rules**:
    *   Must record API timestamp, total duration (ms), total cache hits, and count of API retries.
*   **Business Rules**:
    *   Every evaluation query must initialize a new retrieval session to audit database versions.
*   **Example**: `RetrievalSession(timestamp="2026-07-09T15:39:37Z", duration_ms=4520, cache_hit_count=12, retry_count=0)`.

---

### 4.2 Hypothesis

*   **Definition**: The primary parent entity representing the drug-disease repurposing query. It holds all retrieved, parsed, and calculated context.
*   **Purpose**: Manage lifecycle states and group all evaluation metrics.
*   **Created by**: Master Orchestrator.
*   **Consumed by**: All reasoning engines, Recommendation Engine, Report Generator.
*   **Mutability**: **Mutable**.
*   **Lifecycle States**:
    *   `Initialized`: Created with validated input strings.
    *   `ID_Resolved`: Standard biological taxonomies have successfully mapped the names.
    *   `Data_Retrieved`: External raw responses have been collected and cached.
    *   `Normalized`: Raw data has been converted to Canonical Domain Models.
    *   `Reasoned`: Stances have been mapped and target pathway traces are complete.
    *   `Evaluated`: Three-dimensional scores (SS, MS, RS) have been computed.
    *   `Completed`: Recommendation rules have run, and the report has been written.
*   **Relationships**:
    *   Has exactly one **Drug** instance (1:1).
    *   Has exactly one **Disease** instance (1:1).
    *   Has exactly one **RetrievalSession** (1:1).
    *   Owns zero or many **Evidence** objects (1:N).
    *   Owns zero or many **Claim** objects (1:N).
    *   Owns zero or many **Contradiction** objects (1:N).
    *   Owns zero or many **MechanisticChain** paths (1:N).
    *   Owns exactly one **SupportScore**, one **MechanisticScore**, and one **RiskScore** (1:1 each).
    *   Owns exactly one **Recommendation** decision object (1:1).
*   **Validation Rules**:
    *   Cannot exist without valid references to both a Drug and a Disease entity.
*   **Business Rules**:
    *   Duplicate concurrent queries for the same drug-disease key are blocked at the Orchestrator level.

---

### 4.3 Drug

*   **Definition**: The canonical representation of an active chemical compound or biological agent evaluated for therapeutic utility.
*   **Purpose**: Uniquely identify the therapeutic compound and hold its standardized keys.
*   **Created by**: Identifier Resolution Service.
*   **Consumed by**: Retrieval Clients, Target Enumeration, ClinicalTrials Connector, Recommendation Engine.
*   **Mutability**: **Immutable**.
*   **Lifecycle**: Resolved during the lookup phase; discarded when the query ends.
*   **Relationships**:
    *   Linked to one or more active **Hypothesis** instances.
    *   Connects to one or more **Target** entities (1:N).
    *   References zero or many **ClinicalTrial** records (1:N).
*   **Validation Rules**:
    *   Must contain a non-empty name string.
    *   Must resolve to at least one of the following standardized keys: `ChEMBL ID`, `PubChem CID`, or `DrugBank ID`.

---

### 4.4 Target

*   **Definition**: A relationship entity documenting a drug's interaction with a specific protein.
*   **Purpose**: Decouple the compound-target affinity and interaction metadata from the physical protein properties.
*   **Created by**: Normalization Layer (mapping ChEMBL bioactivity and target records).
*   **Consumed by**: MoA Enumerator, Disease Relevance Agent, Mechanistic Engine.
*   **Mutability**: **Immutable**.
*   **Lifecycle**: Parsed during normalization, stored in the active `EvidenceStore`.
*   **Relationships**:
    *   Belongs to exactly one **Drug** (N:1).
    *   Connects to exactly one **Protein** target node (N:1).
    *   Linked to one or more supporting **Evidence** records.
*   **Validation Rules**:
    *   Must contain a measured interaction metric (e.g., Ki, IC50, Kd, or percentage inhibition).
    *   Must reference an interaction mechanism classification (e.g., inhibitor, agonist, antagonist).
*   **Business Rules**:
    *   A Target relationship is ignored if its measured binding affinity value falls below a reliability threshold defined in the configuration.
*   **Example**: `Target(drug_id="CHEMBL941", protein_id="O76074", affinity_nm=4.0, mechanism="INHIBITOR")`.

---

### 4.5 Protein

*   **Definition**: A physiological polypeptide that performs cellular biological functions.
*   **Purpose**: Define the physical gene products participating in pathways.
*   **Created by**: Normalization Layer (mapping UniProt target details).
*   **Consumed by**: Disease Relevance Agent, Causal Path Agent, Mechanistic Engine.
*   **Mutability**: **Immutable**.
*   **Lifecycle**: Loaded into memory during target mapping; remains read-only.
*   **Relationships**:
    *   Acts as the protein entity in one or more **Target** interactions.
    *   Participates in one or more **Pathway** cascades (N:N).
*   **Validation Rules**:
    *   Must contain a valid `UniProt Accession` key (e.g., `O76074`).
    *   Must contain an uppercase HGNC gene symbol (e.g., `PDE5A`).
*   **Example**: `Protein(uniprot_acc="O76074", gene_symbol="PDE5A", name="cGMP-specific phosphodiesterase 5A")`.

---

### 4.6 Disease

*   **Definition**: The canonical disease entity mapped to standard biological taxonomies.
*   **Purpose**: Uniquely identify the disease state and locate its corresponding pathophysiology markers.
*   **Created by**: Identifier Resolution Service.
*   **Consumed by**: Retrieval Clients, Disease Relevance Agent, Causal Path Agent, Recommendation Engine.
*   **Mutability**: **Immutable**.
*   **Lifecycle**: Instantiated during entity resolution.
*   **Relationships**:
    *   Linked to one or more active **Hypothesis** instances.
    *   Linked to one or more implicated **Protein** biomarkers (1:N).
    *   Linked to one or more dysregulated **Pathway** entities (1:N).
    *   Linked to zero or many **ClinicalTrial** records (1:N).
*   **Validation Rules**:
    *   Must contain a standard vocabulary identifier: `MeSH ID` or `UMLS CUI`.

---

### 4.7 Pathway

*   **Definition**: A curated sequence of molecular interactions and reactions in a cell.
*   **Purpose**: Provide structural pathways for causal mechanistic tracing.
*   **Created by**: Normalization Layer (Reactome Analysis connector).
*   **Consumed by**: Causal Path Agent, Mechanistic Engine.
*   **Mutability**: **Immutable**.
*   **Relationships**:
    *   Contains one or more participating **Protein** target elements.
*   **Validation Rules**:
    *   Must contain a valid `Reactome ID` (e.g., `R-HSA-202127`).

---

### 4.8 Source

*   **Definition**: A meta-entity defining the source database or publication registry where evidence originates.
*   **Purpose**: Store API versions, licensing, citation rules, and reliability weights.
*   **Created by**: Retrieval Layer / Configuration Manager.
*   **Consumed by**: Normalization Layer, Evidence Store, Report Generator.
*   **Mutability**: **Immutable**.
*   **Lifecycle**: Loaded from static system configuration.
*   **Relationships**:
    *   References one or more **Evidence** objects.
    *   References one or more **ClinicalTrial** objects.
*   **Validation Rules**:
    *   Must specify name, API base endpoint URL, database version, and access timestamp.
*   **Example**: `Source(name="ChEMBL", version="v33", url="https://www.ebi.ac.uk/chembl/api/data/")`.

---

### 4.9 Evidence

*   **Definition**: An empirical observation, assay data, or literature record retrieved from a Source.
*   **Purpose**: Ground every claim in an auditable external reference.
*   **Created by**: Normalization Layer.
*   **Consumed by**: Claim Extractor, Support Engine, Mechanistic Engine, Risk Engine.
*   **Mutability**: **Immutable**.
*   **Relationships**:
    *   Belongs to one **Hypothesis** query.
    *   Belongs to exactly one **Source** (N:1).
    *   Spawns one or more structured **Claim** objects.
*   **Validation Rules**:
    *   Type must match an `EvidenceType` enum value.
    *   Must contain an Evidence Reliability Weight (ERW) float value between `0.15` and `1.00`.
    *   Must contain a valid citation key (e.g., DOI, PMID, or NCT ID).

---

### 4.10 Claim

*   **Definition**: A structured semantic statement extracted from text, representing a biological relationship as a triple.
*   **Purpose**: Convert unstructured literature or assay text into standardized directional mechanisms.
*   **Created by**: Claim Extraction Agent.
*   **Consumed by**: Contradiction Engine, Support Engine, Mechanistic Engine, Risk Engine.
*   **Mutability**: **Immutable**.
*   **Relationships**:
    *   Belongs to one **Hypothesis** query.
    *   Supported by one or more parent **Evidence** objects.
    *   May participate in one or more **Contradiction** instances.
*   **Validation Rules**:
    *   Predicate must map to a `PredicateType` enum.
    *   Confidence score must be a float value between `0.0` and `1.0`.

---

### 4.11 ClinicalTrial

*   **Definition**: A registered, human-subject clinical study evaluating the therapeutic action of the drug on the disease.
*   **Purpose**: Identify clinical outcomes, efficacy endpoints, and trial safety statuses.
*   **Created by**: Normalization Layer.
*   **Consumed by**: Risk / Falsification Engine, Recommendation Engine.
*   **Mutability**: **Immutable**.
*   **Relationships**:
    *   Belongs to one **Hypothesis** query.
    *   Tied directly to the evaluated **Drug** and **Disease** entities.
    *   Belongs to exactly one **Source** (N:1).
*   **Validation Rules**:
    *   NCT identifier must match the format `NCT\d{8}`.
    *   Status must map to a `TrialOutcomeStatus` enum.
    *   Phase must map to a valid phase string (`Phase I` - `Phase IV`).

---

### 4.12 Contradiction

*   **Definition**: An analytical model documenting a directional conflict between two claims or experimental records.
*   **Purpose**: Prevent the averaging of conflicting results, surfacing it as a safety penalty.
*   **Created by**: Contradiction Engine.
*   **Consumed by**: Risk / Falsification Engine, Recommendation Engine, Report Generator.
*   **Mutability**: **Immutable**.
*   **Relationships**:
    *   Belongs to one **Hypothesis** query.
    *   References two or more conflicting **Claim** or **Evidence** instances.
*   **Validation Rules**:
    *   Target subject and object must be identical.
    *   Contradiction Score must be a float between `0.0` and `1.0`.

---

### 4.13 MechanisticChain

*   **Definition**: The complete traced path linking a drug's target to the target disease pathophysiology.
*   **Purpose**: Provide the visual and semantic explanation of target-pathway-disease cascade.
*   **Created by**: Causal Path Agent.
*   **Consumed by**: Mechanistic Engine, Scientific Report Generator.
*   **Mutability**: **Immutable**.
*   **Lifecycle**: Built during the pathway tracing phase.
*   **Relationships**:
    *   Belongs to one **Hypothesis** query.
    *   Linked to one or more participating **Pathway** and **Protein** objects.
*   **Validation Rules**:
    *   Must contain a list of nodes (entities) and edges (predicates).
    *   Must verify directional consistency from source Drug Target to destination Disease Gene.
*   **Example**: `MechanisticChain(nodes=["CHEMBL941", "PDE5A", "R-HSA-202127", "D006976"], edges=["INHIBITS", "PARTICIPATES_IN", "IMPLICATED_IN"])`.

---

### 4.14 SupportScore, MechanisticScore, RiskScore

*   **Definition**: Values representing the calculated support, mechanistic plausibility, and refutation risk of the hypothesis.
*   **Purpose**: Quantify the three dimensions of hypothesis evaluation.
*   **Created by**: Support Engine, Mechanistic Engine, Risk / Falsification Engine.
*   **Consumed by**: Recommendation Engine, Scientific Report Generator.
*   **Mutability**: **Immutable**.
*   **Validation Rules**:
    *   Values must be float types between `0.0` and `1.0`.

---

### 4.15 Recommendation

*   **Definition**: The final decision object generated by applying rules and vetoes over the three score dimensions.
*   **Purpose**: Provide an actionable, transparent verdict for the researcher.
*   **Created by**: Recommendation Engine.
*   **Consumed by**: Scientific Report Generator, Streamlit UI.
*   **Mutability**: **Immutable**.
*   **Relationships**:
    *   Belongs to one **Hypothesis** query.
*   **Validation Rules**:
    *   Status must map to a `RecommendationStatus` enum value.
    *   Must contain a list of text reasons.

---

## 5. Future Domain Extensions

The following entity stubs are defined as placeholders for future system expansions:

*   **Identifier**: Interface for naming-system mapping (e.g., CAS Registry Numbers, IUPAC names).
*   **CanonicalIdentifier**: Reference identifier system mapping raw source keys to standardized taxonomies.
*   **OntologyTerm**: Maps custom text terms to hierarchical bio-ontologies (e.g., Gene Ontology, Disease Ontology).
*   **BioActivity**: Stores assay details (e.g., standard activity types, units, values, assay configurations) in target mapping.
*   **GeneAssociation**: Logical link connecting a gene or protein variant to a clinical phenotype.
*   **PathwayRelation**: Documents the reaction edges linking separate pathway systems together.
*   **EvidenceWeight**: Metric configuring the impact factor of a given Evidence record.
*   **AuditTrail**: Session-level record verifying the pipeline step durations, user parameters, and environment state variables.
