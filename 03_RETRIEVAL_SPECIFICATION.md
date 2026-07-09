# CYNTHERA: Retrieval Subsystem Specification
## Reference Identifier: 03_RETRIEVAL_SPECIFICATION.md

---

## 1. Retrieval Philosophy

The Retrieval Layer is the foundation upon which all scientific reasoning in CYNTHERA rests. Its quality determines the quality of every upstream output — scores, contradictions, and recommendations are only as trustworthy as the evidence they are built upon.

The retrieval layer is governed by the following core principles:

*   **Completeness Over Speed**: The layer must prioritize retrieving all relevant, available evidence for a hypothesis before returning. An incomplete retrieval that misses a failed clinical trial or a contradictory bioactivity record is more dangerous than a slow one.
*   **Traceability as a First-Class Requirement**: Every piece of evidence produced by the retrieval layer must carry its full provenance metadata — origin source, version, timestamp, retrieval URL, and license. Evidence without provenance is not evidence; it is data noise.
*   **Identifier Consistency**: All entities retrieved across disparate sources must be mapped to standardized canonical identifiers before they leave the retrieval boundary. Downstream components operate exclusively on canonical keys; they never see raw API-specific identifiers.
*   **Reproducibility**: Given the same canonical input identifiers and a fixed external database version, the retrieval layer must produce an identical set of canonical evidence objects. This requires deterministic query construction, structured cache keys, and database version recording.
*   **Source Authority Respect**: Each external database is recognized as the authoritative record for its domain. ChEMBL is authoritative for small-molecule bioactivity; UniProt is authoritative for protein biology; Reactome is authoritative for pathway topology. Data from one source is never used to override authoritative fields of another.
*   **Hard Separation from Reasoning**: The retrieval layer does not score, rank, reason, or interpret. It collects, validates, normalizes, and packages. Every act of scientific judgment is deferred to the Reasoning Layer.

---

## 2. Retrieval Architecture

The retrieval subsystem operates as a self-contained pipeline. It accepts a fully resolved `Hypothesis` entity and returns a `RetrievalPackage` containing all canonical domain objects required by downstream reasoning engines.

```mermaid
graph TD
    A([Resolved Hypothesis]) --> B[Retrieval Planner]
    B --> C[Retrieval Plan]

    C --> D{Dependency\nScheduler}
    D --> E1[Phase 1: Sequential ID Fetch]
    E1 --> F[Phase 2: Parallel Evidence Fetch]
    F --> F1[PubMed Client]
    F --> F2[ChEMBL Client]
    F --> F3[UniProt Client]
    F --> F4[Reactome Client]
    F --> F5[ClinicalTrials Client]
    F --> F6[DisGeNET Client]
    F --> F7[DrugBank Open Client]

    F1 & F2 & F3 & F4 & F5 & F6 & F7 --> G[Response Validator]
    G --> H[Normalization Layer]
    H --> I[Canonical Domain Model Factory]
    I --> J[Evidence Store]
    J --> K([RetrievalPackage])
```

---

## 3. Canonical Retrieval Pipeline

The execution sequence from raw user query to a validated, packaged `RetrievalPackage` follows these ordered steps:

```mermaid
flowchart TD
    A[Raw Query: Drug Name + Disease Name] --> B[Name Normalization]
    B --> C[Identifier Resolution Service]
    C --> D[Retrieval Planner]
    D --> E[Build Dependency Graph]
    E --> F[Execute Phase 1: Sequential Retrieval]
    F --> G[Execute Phase 2: Parallel Retrieval]
    G --> H[Collect Raw Responses]
    H --> I[Schema Validation]
    I --> J{Valid?}
    J -- No --> K[Log Rejection + Continue]
    J -- Yes --> L[Field Normalization]
    L --> M[Canonical Domain Object Factory]
    M --> N[Deduplication Check]
    N --> O[Evidence Store Population]
    O --> P[Provenance Metadata Injection]
    P --> Q[RetrievalPackage Assembly]
    Q --> R([Return RetrievalPackage])
```

### Step Descriptions

1.  **Name Normalization**: Input strings are sanitized. Unicode characters are normalized, case is folded to lowercase, common synonyms are expanded (e.g., "aspirin" → "acetylsalicylic acid"), and abbreviations are resolved using a static synonym map.
2.  **Identifier Resolution**: The Identifier Resolution Service translates normalized names to canonical cross-reference ID sets.
3.  **Retrieval Planning**: The Retrieval Planner inspects the resolved IDs and determines exactly which sources must be queried, in which order, and which can be parallelized.
4.  **Dependency Graph Construction**: A directed acyclic graph of API call dependencies is built. Calls that require outputs from prior calls are placed in subsequent phases.
5.  **Phase 1 Execution (Sequential)**: Source-of-truth identifier fetches that other clients depend upon are executed sequentially first (e.g., ChEMBL target IDs before UniProt can be called).
6.  **Phase 2 Execution (Parallel)**: All independent evidence sources are queried concurrently using async HTTP sessions.
7.  **Response Collection**: Raw payloads are aggregated into a source-keyed memory structure.
8.  **Schema Validation**: Each payload is validated against the source-specific expected schema. Records failing validation are dropped and logged.
9.  **Field Normalization**: Numeric values are standardized (units, precision), strings are trimmed, and date formats are unified to ISO-8601.
10. **Canonical Object Factory**: Normalized fields are projected onto the canonical domain model definitions from `02_DOMAIN_MODEL.md`.
11. **Deduplication**: Records with identical canonical identifiers are merged, preserving the highest-authority source and collecting all reference URLs.
12. **Provenance Injection**: Source metadata, retrieval timestamps, database versions, and API endpoint URLs are attached to every canonical object.
13. **Package Assembly**: All canonical objects are assembled into a single `RetrievalPackage` entity.

---

## 4. Identifier Resolution

Identifier resolution is the most critical prerequisite step in the pipeline. No retrieval client is called until stable, standardized identifiers are established for both the drug and disease entities.

### 4.1 Drug Identifier Resolution

```mermaid
flowchart LR
    A[Drug Name String] --> B[Synonym Expansion]
    B --> C[PubChem Name Lookup]
    C --> D[PubChem CID]
    D --> E[ChEMBL Cross-Reference]
    E --> F[ChEMBL ID]
    F --> G[DrugBank Cross-Reference]
    G --> H[DrugBank ID]
    D & F & H --> I[Canonical Drug Object]
```

**Resolution Sequence**:
1.  Query PubChem Name-to-CID service using the normalized string.
2.  Use the PubChem CID to retrieve cross-reference IDs from the PubChem CID-Property endpoint.
3.  Use the ChEMBL molecule search endpoint to confirm the ChEMBL compound ID.
4.  Use ChEMBL's cross-reference data to confirm the DrugBank ID.
5.  Assemble the `Drug` canonical object carrying `pubchem_cid`, `chembl_id`, and `drugbank_id`.

### 4.2 Disease Identifier Resolution

```mermaid
flowchart LR
    A[Disease Name String] --> B[Synonym Normalization]
    B --> C[NCBI MeSH Lookup]
    C --> D[MeSH ID]
    D --> E[UMLS Metathesaurus Lookup]
    E --> F[UMLS CUI]
    F --> G[MONDO Ontology Mapping]
    G --> H[MONDO ID]
    D & F & H --> I[Canonical Disease Object]
```

**Resolution Sequence**:
1.  Query NCBI MeSH via E-utilities to retrieve the primary MeSH Descriptor ID.
2.  Use the MeSH ID to query the UMLS REST API for the UMLS Concept Unique Identifier (CUI).
3.  Map the CUI to a MONDO disease ontology identifier.
4.  Assemble the `Disease` canonical object carrying `mesh_id`, `umls_cui`, and `mondo_id`.

### 4.3 Protein Identifier Resolution

```mermaid
flowchart LR
    A[Gene Symbol / Protein Name] --> B[HGNC Approved Symbol Lookup]
    B --> C[HGNC Gene ID]
    C --> D[UniProt ID Mapping Service]
    D --> E[UniProt Accession]
    E --> F[Canonical Protein Object]
```

**Resolution Sequence**:
1.  Validate and normalize gene symbols against the HGNC approved symbol list.
2.  Use the UniProt ID Mapping API to convert HGNC symbols to UniProt accessions.
3.  Assemble the `Protein` canonical object.

### 4.4 Ambiguity Handling

| Scenario | Handling |
| :--- | :--- |
| Input matches multiple identifiers | Select the highest-ranked match by source priority score; log all alternatives. |
| Input matches no identifiers | Terminate pipeline with an `ENTITY_NOT_FOUND` error and return a structured error payload. |
| Input contains a deprecated synonym | Map to the current preferred term via synonym expansion table before querying. |
| Input is an abbreviation | Expand using a curated biomedical abbreviation dictionary before querying. |
| Identifier mismatch across sources | Prefer the authoritative source (e.g., UniProt over ChEMBL for protein accession). |

---

## 5. Retrieval Planner

The Retrieval Planner is a dedicated subsystem responsible for determining what evidence is needed, from which sources, and in what order. It separates retrieval decision-making from retrieval execution.

### 5.1 Responsibilities

*   Inspect the resolved `Drug`, `Disease`, and `Protein` canonical IDs.
*   Determine which sources are required given the current hypothesis.
*   Build a dependency graph defining which source calls must precede others.
*   Produce a `RetrievalPlan` consumed by the Dependency Scheduler.
*   Avoid calling sources that have already been served from cache.

### 5.2 Planning Logic

```mermaid
flowchart TD
    A[Resolved Drug + Disease] --> B{Drug targets known?}
    B -- No --> C[Schedule ChEMBL Target Fetch]
    B -- Yes --> D{Protein accessions resolved?}
    C --> D
    D -- No --> E[Schedule UniProt Fetch]
    D -- Yes --> F{Pathways required?}
    E --> F
    F -- Yes --> G[Schedule Reactome Fetch]
    F --> H{Gene-disease links required?}
    H -- Yes --> I[Schedule DisGeNET Fetch]
    H --> J{Clinical trials required?}
    J -- Yes --> K[Schedule ClinicalTrials Fetch]
    J --> L{Literature required?}
    L -- Yes --> M[Schedule PubMed Fetch]
    C & E & G & I & K & M --> N[Compile RetrievalPlan]
    N --> O([RetrievalPlan Object])
```

### 5.3 RetrievalPlan Object

The `RetrievalPlan` is an ordered, structured manifest defining:

*   **Phase 1 tasks**: Sequential calls (e.g., ChEMBL target IDs → UniProt accessions).
*   **Phase 2 tasks**: Parallel calls that have no inter-dependencies (e.g., PubMed literature + ClinicalTrials + DisGeNET).
*   **Cache bypass flags**: Per-source flags specifying whether the planner detected stale cache records.
*   **Source priority order**: In the event of a timeout, which sources are non-negotiable vs. optional.

---

## 6. Source Inventory

The following subsections define every external data source integrated into the Retrieval Layer.

---

### 6.1 PubMed (NCBI E-utilities)

| Property | Value |
| :--- | :--- |
| **Authority** | National Center for Biotechnology Information (NCBI / NIH) |
| **Purpose** | Scientific literature retrieval for claim extraction and evidence grounding. |
| **Unique Contribution** | Provides published experimental results, human clinical study findings, and observational research. |
| **Canonical Output** | `LiteratureRecord` → `Evidence` (type: `META_ANALYSIS`, `RCT`, `OBSERVATIONAL`) |
| **Consumed By** | Claim Extraction Agent, Support Engine |
| **Priority** | High — literature is the primary source of human-level evidence |
| **Input Required** | Normalized drug name, disease MeSH ID, gene symbols |
| **Dependencies** | None (independent call in Phase 2) |
| **Rate Limit** | 3 req/sec (unauthenticated), 10 req/sec (with NCBI API key) |
| **Timeout** | 15 seconds per request |
| **Retry Policy** | 3 retries with exponential backoff starting at 2 seconds |
| **Cache TTL** | 24 hours |
| **Failure Policy** | Non-critical. Flag literature claims as `Unavailable`; degrade Support Score accordingly. |

---

### 6.2 ChEMBL (EMBL-EBI)

| Property | Value |
| :--- | :--- |
| **Authority** | European Molecular Biology Laboratory – European Bioinformatics Institute (EMBL-EBI) |
| **Purpose** | Drug-target bioactivity data and binding affinity records. |
| **Unique Contribution** | Provides Ki, IC50, Kd, and percentage inhibition values with assay metadata, and maps drugs to their protein targets. |
| **Canonical Output** | `BioActivity` → `Target`, `Evidence` (type: `IN_VITRO`) |
| **Consumed By** | MoA Enumerator, Mechanistic Engine, Support Engine |
| **Priority** | Critical — required to identify drug protein targets |
| **Input Required** | ChEMBL compound ID |
| **Dependencies** | Identifier Resolution must provide ChEMBL ID before this call executes |
| **Rate Limit** | No hard limit documented; practical limit is ~5 req/sec to avoid server 429 responses |
| **Timeout** | 20 seconds per request |
| **Retry Policy** | 3 retries with exponential backoff starting at 3 seconds |
| **Cache TTL** | 30 days |
| **Failure Policy** | Critical. If ChEMBL is unavailable, the pipeline halts with `CORE_SOURCE_FAILURE`. |

---

### 6.3 UniProt (UniProt Consortium)

| Property | Value |
| :--- | :--- |
| **Authority** | UniProt Consortium (EMBL-EBI, SIB, PIR) |
| **Purpose** | Protein biological function, sequence, and gene mapping data. |
| **Unique Contribution** | Authoritative source for protein accession numbers, subcellular locations, functional annotations, and cross-reference mapping across databases. |
| **Canonical Output** | UniProt Entry → `Protein` |
| **Consumed By** | Mechanistic Engine, Disease Relevance Agent, Causal Path Agent |
| **Priority** | Critical — required for pathway-level reasoning |
| **Input Required** | Gene symbols or ChEMBL target UniProt cross-references |
| **Dependencies** | ChEMBL must execute first (provides initial gene symbols for lookup) |
| **Rate Limit** | No hard documented rate limit; practical limit is ~5 req/sec |
| **Timeout** | 15 seconds per request |
| **Retry Policy** | 3 retries with exponential backoff starting at 2 seconds |
| **Cache TTL** | 30 days |
| **Failure Policy** | Critical. If UniProt is unavailable, Reactome and Mechanistic Engine cannot execute. Pipeline halts with `CORE_SOURCE_FAILURE`. |

---

### 6.4 Reactome

| Property | Value |
| :--- | :--- |
| **Authority** | Reactome Consortium (EMBL-EBI, ORCID, Ontario Institute for Cancer Research) |
| **Purpose** | Biological pathway topology and reaction cascade data. |
| **Unique Contribution** | Provides curated, peer-reviewed hierarchical pathway networks that enable mechanistic path tracing from drug target to disease biology. |
| **Canonical Output** | Reactome Pathway Event → `Pathway`, `MechanisticChain` edges |
| **Consumed By** | Causal Path Agent, Mechanistic Engine |
| **Priority** | High — essential for mechanistic scoring |
| **Input Required** | UniProt accession numbers |
| **Dependencies** | UniProt must execute first (provides accessions for pathway mapping) |
| **Rate Limit** | No documented hard limit; conservative practice is ~3 req/sec |
| **Timeout** | 20 seconds per request |
| **Retry Policy** | 3 retries with exponential backoff starting at 3 seconds |
| **Cache TTL** | 30 days |
| **Failure Policy** | Non-critical. Mechanistic Score pathway component is set to `0`; report warns of pathway data unavailability. |

---

### 6.5 ClinicalTrials.gov (NLM)

| Property | Value |
| :--- | :--- |
| **Authority** | National Library of Medicine (NLM / NIH) |
| **Purpose** | Human clinical trial records including phase, outcome, and trial status. |
| **Unique Contribution** | The sole authoritative registry for discovering terminated, failed, and safety-halted clinical trials involving the drug-disease pair. |
| **Canonical Output** | ClinicalTrials Study → `ClinicalTrial` |
| **Consumed By** | Risk / Falsification Engine, Recommendation Engine |
| **Priority** | High — critical safety source |
| **Input Required** | Drug name/synonyms, Disease MeSH ID |
| **Dependencies** | None (independent Phase 2 call) |
| **Rate Limit** | Formally undocumented; practical limit is ~5 req/sec |
| **Timeout** | 20 seconds per request |
| **Retry Policy** | 3 retries with exponential backoff starting at 3 seconds |
| **Cache TTL** | 7 days (trial statuses change more frequently than biological data) |
| **Failure Policy** | Safety-critical. If unavailable, clinical trial component of Risk Score is marked `Unverified`; Recommendation Engine vetoes `PROMISING` output. |

---

### 6.6 DisGeNET

| Property | Value |
| :--- | :--- |
| **Authority** | Research Programme on Biomedical Informatics (GRIB), Hospital del Mar Research Institute |
| **Purpose** | Gene-disease association records linking specific genes to clinical phenotypes. |
| **Unique Contribution** | Provides score-ranked gene-disease association data sourced from curated databases and text mining, enabling disease pathway mapping when structured disease gene lists are unavailable. |
| **Canonical Output** | GDA (Gene-Disease Association) → `GeneAssociation` → `Evidence` (type: `COMPUTATIONAL`) |
| **Consumed By** | Disease Relevance Agent, Mechanistic Engine |
| **Priority** | Medium — primary mechanism for identifying disease-implicated proteins |
| **Input Required** | Disease UMLS CUI |
| **Dependencies** | Disease entity must be fully resolved before this call executes |
| **Rate Limit** | API key required for higher access; rate limited at 1 req/sec (free tier) |
| **Timeout** | 15 seconds per request |
| **Retry Policy** | 2 retries with fixed 5-second backoff |
| **Cache TTL** | 14 days |
| **Failure Policy** | Non-critical. If unavailable, disease gene mapping falls back to MeSH-annotated pathway data. Report notes DisGeNET as unavailable. |

---

### 6.7 DrugBank Open Data

| Property | Value |
| :--- | :--- |
| **Authority** | DrugBank (OMx Personal Health Analytics, University of Alberta) |
| **Purpose** | Drug mechanism of action (MoA) descriptions, pharmacology annotations, and target lists. |
| **Unique Contribution** | Provides human-curated, text-level mechanism of action descriptions enabling LLM claim extraction of known pharmacological effects. |
| **Canonical Output** | DrugBank Entry → supplementary field in `Drug` canonical object |
| **Consumed By** | Claim Extraction Agent (MoA text), MoA Enumerator |
| **Priority** | Medium — enriches drug canonical object |
| **Input Required** | DrugBank ID |
| **Dependencies** | DrugBank ID must be resolved in Identifier Resolution phase |
| **Rate Limit** | Open data downloads; no real-time API rate limit formally documented |
| **Timeout** | 10 seconds |
| **Retry Policy** | 2 retries with exponential backoff starting at 2 seconds |
| **Cache TTL** | 30 days |
| **Failure Policy** | Non-critical. MoA text field is left empty in `Drug` canonical object if unavailable. |

---

### 6.8 Europe PMC

| Property | Value |
| :--- | :--- |
| **Authority** | European Molecular Biology Laboratory – European Bioinformatics Institute (EMBL-EBI) |
| **Purpose** | Supplemental scientific literature source capturing preprints, full-text papers, and non-English studies not indexed in PubMed. |
| **Unique Contribution** | Covers preprint servers (bioRxiv, medRxiv), open-access full-text articles, and international clinical findings missing from PubMed's index. |
| **Canonical Output** | Europe PMC Article → `LiteratureRecord` → `Evidence` |
| **Consumed By** | Claim Extraction Agent |
| **Priority** | Low — supplemental to PubMed |
| **Input Required** | Drug name, disease name, gene symbols |
| **Dependencies** | None (optional Phase 2 call) |
| **Rate Limit** | No formally documented hard limit |
| **Timeout** | 15 seconds |
| **Retry Policy** | 2 retries with exponential backoff starting at 2 seconds |
| **Cache TTL** | 24 hours |
| **Failure Policy** | Non-critical. If unavailable, PubMed covers the primary literature corpus. |

---

## 7. Source Dependency Graph

API calls are not independent. Some sources require outputs from prior calls. This dependency graph determines the execution phases and prevents race conditions:

```mermaid
graph TD
    A[Identifier Resolution Service] --> B[ChEMBL Bioactivity Fetch]
    A --> C[PubMed Literature Fetch]
    A --> D[ClinicalTrials Fetch]
    A --> E[DisGeNET Gene-Disease Fetch]
    A --> F[DrugBank MoA Fetch]

    B --> G[UniProt Protein Fetch]
    G --> H[Reactome Pathway Fetch]
    G --> E

    subgraph Phase 1 - Sequential
        A
        B
        G
    end

    subgraph Phase 2 - Parallel
        C
        D
        E
        F
        H
    end
```

**Rationale for ordering**:
*   ChEMBL must precede UniProt because ChEMBL target records contain the initial UniProt accession cross-references.
*   UniProt must precede Reactome because Reactome's pathway analysis service requires UniProt accessions as inputs.
*   PubMed, ClinicalTrials, DisGeNET, DrugBank, and Europe PMC operate independently and can execute concurrently.

---

## 8. Parallel vs Sequential Execution

```mermaid
sequenceDiagram
    autonumber
    participant RP as Retrieval Planner
    participant Sched as Dependency Scheduler
    participant ChEMBL
    participant UniProt
    participant Reactome
    participant PubMed
    participant ClinTrials as ClinicalTrials
    participant DisGeNET
    participant DrugBank

    RP->>Sched: Issue RetrievalPlan

    Note over Sched,ChEMBL: Phase 1 — Sequential
    Sched->>ChEMBL: Fetch bioactivity + target IDs
    ChEMBL-->>Sched: BioActivity records + UniProt IDs

    Sched->>UniProt: Fetch protein annotations
    UniProt-->>Sched: Protein canonical objects

    Note over Sched,DrugBank: Phase 2 — Parallel (asyncio.gather)
    par
        Sched->>Reactome: Fetch pathway events
    and
        Sched->>PubMed: Fetch literature abstracts
    and
        Sched->>ClinTrials: Fetch trial records
    and
        Sched->>DisGeNET: Fetch gene-disease associations
    and
        Sched->>DrugBank: Fetch MoA annotations
    end

    Reactome-->>Sched: Pathway events
    PubMed-->>Sched: Literature records
    ClinTrials-->>Sched: Trial records
    DisGeNET-->>Sched: GDA records
    DrugBank-->>Sched: MoA text

    Note over Sched: Merge + Validate + Normalize
    Sched->>RP: Return RetrievalPackage
```

### Execution Rules Summary

| Phase | Tasks | Execution Mode |
| :--- | :--- | :--- |
| Phase 0 | Identifier Resolution | Sequential — must precede all retrieval |
| Phase 1a | ChEMBL bioactivity + target fetch | Sequential |
| Phase 1b | UniProt protein annotation fetch | Sequential (depends on ChEMBL output) |
| Phase 2 | Reactome, PubMed, ClinicalTrials, DisGeNET, DrugBank, Europe PMC | Parallel (asyncio.gather) |
| Phase 3 | Validation, normalization, canonical mapping, deduplication | Sequential |

---

## 9. Response Validation

The Retrieval Layer applies a structured validation protocol to every API response before it enters the normalization pipeline. Invalid records are never silently discarded — they are logged with a reason code and excluded from the Evidence Store.

### 9.1 Validation Checks

| Check | Description | Action on Failure |
| :--- | :--- | :--- |
| **HTTP Status Code** | Verify response is `200`. | Trigger retry policy; log if all retries fail. |
| **Non-Empty Body** | Verify response body is not null or empty. | Log `EMPTY_RESPONSE`; mark source as partial. |
| **Content-Type** | Verify response is `application/json`. | Log `UNEXPECTED_CONTENT_TYPE`; discard payload. |
| **JSON Parse Validity** | Verify payload parses without error. | Log `MALFORMED_JSON`; discard payload. |
| **Required Fields Presence** | Verify mandatory fields for the source type exist. | Log `MISSING_REQUIRED_FIELD`; drop individual record. |
| **Identifier Format** | Verify identifiers conform to expected regex patterns. | Log `INVALID_IDENTIFIER_FORMAT`; drop record. |
| **Numeric Range Plausibility** | Verify assay values (e.g., IC50, Ki) fall within physically plausible ranges. | Log `IMPLAUSIBLE_VALUE`; drop record and flag for review. |
| **Duplicate Detection** | Verify same-key records are not duplicated across source pages. | Merge duplicates; keep highest-quality source copy. |

### 9.2 Validation Error Severity Levels

*   **`CRITICAL`**: A core source is completely unreachable or returns a structurally invalid response. Triggers pipeline halt.
*   **`WARNING`**: Individual records fail validation but the source returned sufficient valid data.
*   **`INFO`**: Edge cases flagged for observability (e.g., deprecated identifiers automatically remapped).

---

## 10. Canonical Domain Object Mapping

Every raw API payload must be projected onto a canonical domain object before leaving the retrieval boundary. No raw JSON ever reaches a reasoning engine or scoring component.

| External Source | Raw Object Type | Canonical Domain Object | Notes |
| :--- | :--- | :--- | :--- |
| PubMed | `Article` JSON | `Evidence` (type: `RCT`, `OBSERVATIONAL`, `META_ANALYSIS`) | Abstract text preserved for Claim Extraction Agent |
| Europe PMC | `ResultList.result` | `Evidence` (type: `OBSERVATIONAL`) | Includes preprints; lower default ERW |
| ChEMBL | `Activity` record | `Target` + `Evidence` (type: `IN_VITRO`) | Affinity values mapped to `Target.affinity_nm` |
| UniProt | `UniProtKB entry` | `Protein` | Cross-references used for Reactome IDs |
| Reactome | `Pathway` event | `Pathway` + `MechanisticChain` edge | Hierarchical pathway merged into graph nodes |
| ClinicalTrials.gov | `StudyDocument` | `ClinicalTrial` | Status mapped to `TrialOutcomeStatus` enum |
| DisGeNET | `GDA` record | `Evidence` (type: `COMPUTATIONAL`) | Score mapped to ERW via linear scale |
| DrugBank Open | `Drug` entry fields | Supplementary fields on `Drug` canonical object | MoA text appended to `Drug.moa_description` |

---

## 11. Retrieval Package Specification

Upon completion, the Retrieval Layer returns a single structured object — the `RetrievalPackage` — to the Master Orchestrator. Downstream agents consume only this package and never call retrieval connectors directly.

### 11.1 RetrievalPackage Composition

```
RetrievalPackage
│
├── hypothesis_id             (UUID — links package to parent Hypothesis)
│
├── drug                      (Canonical Drug object)
│
├── disease                   (Canonical Disease object)
│
├── targets                   (List of canonical Target objects)
│
├── proteins                  (List of canonical Protein objects)
│
├── pathways                  (List of canonical Pathway objects)
│
├── clinical_trials           (List of canonical ClinicalTrial objects)
│
├── evidence                  (List of canonical Evidence objects, all types)
│
├── retrieval_session         (RetrievalSession metadata object)
│   ├── session_id
│   ├── started_at
│   ├── completed_at
│   ├── duration_ms
│   ├── sources_queried       (List of Source names)
│   ├── sources_failed        (List of Source names + error codes)
│   ├── cache_hits            (Per-source cache hit count)
│   ├── total_records         (Total evidence records collected)
│   └── api_versions          (Dict of Source name → database version string)
│
└── completeness_flags        (Per-source availability status)
    ├── pubmed_available      (boolean)
    ├── chembl_available      (boolean)
    ├── uniprot_available     (boolean)
    ├── reactome_available    (boolean)
    ├── clintrials_available  (boolean)
    ├── disgenet_available    (boolean)
    └── drugbank_available    (boolean)
```

### 11.2 Package Completeness Rules

*   **Minimum Viable Package**: A package is considered `Minimum Viable` if ChEMBL and UniProt data are present (targets and proteins resolved).
*   **Partial Package**: A package where one or more non-critical sources failed. Downstream engines receive completeness flags and adjust their scoring accordingly.
*   **Failed Package**: A package where ChEMBL or UniProt data is completely absent. The pipeline terminates and returns an error.

---

## 12. Failure Handling

Every distinct HTTP and application failure type receives a specific, documented handling behavior.

| Failure Type | Trigger | Handling |
| :--- | :--- | :--- |
| **HTTP 404** | Entity not found at the queried identifier | Log `ENTITY_NOT_FOUND`; skip record; continue. |
| **HTTP 429** | Rate limit exceeded | Pause the specific source client; wait `Retry-After` header duration; retry. |
| **HTTP 500** | Internal server error at source | Log `SOURCE_SERVER_ERROR`; apply retry policy. |
| **HTTP 503** | Service temporarily unavailable | Log `SOURCE_UNAVAILABLE`; apply retry policy; fall back to cache if available. |
| **Connection Timeout** | Connection not established within timeout | Log `CONNECTION_TIMEOUT`; apply retry policy. |
| **Read Timeout** | Connection established but no response body received in time | Log `READ_TIMEOUT`; apply retry policy. |
| **Malformed JSON** | Response body is not valid JSON | Log `MALFORMED_RESPONSE`; discard payload; continue. |
| **Schema Mismatch** | Response JSON is valid but expected fields are absent | Log `SCHEMA_MISMATCH`; discard individual records; continue. |
| **Empty Results** | Response is valid but returns zero records | Log `EMPTY_RESULT_SET`; mark source as returning no evidence for this query. |
| **Identifier Resolution Failure** | Drug or disease name resolves to zero identifiers | Terminate pipeline; return `400 ENTITY_NOT_RESOLVED` to API layer. |

---

## 13. Retry Strategy

### 13.1 Exponential Backoff Policy

All retryable failures follow a standard exponential backoff schedule:

*   **Maximum Retries**: 3 (configurable per source).
*   **Base Delay**: 2 seconds.
*   **Backoff Multiplier**: 2.0 (delay doubles with each attempt).
*   **Maximum Delay Cap**: 30 seconds (delays do not grow beyond this cap).
*   **Jitter**: A random jitter of ±0.5 seconds is added to each delay to prevent synchronized thundering herd patterns.

**Retry Schedule Example**:
| Attempt | Delay Before Attempt |
| :--- | :--- |
| 1 (initial) | 0s |
| 2 (first retry) | ~2s |
| 3 (second retry) | ~4s |
| 4 (third and final) | ~8s |

### 13.2 Retryable vs Non-Retryable Errors

| Error | Retryable |
| :--- | :--- |
| `HTTP 429` (Rate Limit) | Yes |
| `HTTP 500` (Server Error) | Yes |
| `HTTP 503` (Service Unavailable) | Yes |
| Connection Timeout | Yes |
| Read Timeout | Yes |
| `HTTP 400` (Bad Request) | No — query is malformed; retrying will produce the same error |
| `HTTP 404` (Not Found) | No — entity does not exist in this database |
| Malformed JSON | No — indicates a structural change in the source schema |

### 13.3 Circuit Breaker (Future)

A circuit breaker pattern is defined for Phase 2 architecture. When a source generates more than 5 consecutive failures within a 60-second window, the circuit opens and the source is suspended for 120 seconds before reattempting.

---

## 14. Caching Strategy

### 14.1 Cache Architecture

The cache operates as a key-value store interposed between the Retrieval Planner and the API client connectors. Cache reads are attempted before any external network call. Cache writes occur after successful response validation.

### 14.2 Cache Key Structure

Cache keys are deterministic, constructed from the combination of:
*   Source name
*   Query type
*   Normalized canonical identifier(s)

**Example Key Format**: `{source}:{query_type}:{canonical_id}`
*   `pubmed:literature:D006976+CHEMBL941`
*   `reactome:pathways:O76074`
*   `clintrials:trials:CHEMBL941+D006976`

### 14.3 TTL Policy by Source

| Source | TTL | Rationale |
| :--- | :--- | :--- |
| PubMed | 24 hours | New publications appear daily; short TTL ensures recent negative results are captured |
| Europe PMC | 24 hours | Same as PubMed |
| ClinicalTrials.gov | 7 days | Trial statuses update frequently; weekly refresh needed for safety accuracy |
| DisGeNET | 14 days | Gene-disease association scores are recalculated periodically |
| ChEMBL | 30 days | Bioactivity records are stable; new versions release quarterly |
| UniProt | 30 days | Protein annotations are highly stable |
| Reactome | 30 days | Pathway events are stable; major updates are infrequent |
| DrugBank Open | 30 days | MoA annotations are stable |

### 14.4 Cache Invalidation

*   **TTL Expiry**: Standard expiry as defined per source.
*   **Force Refresh**: An `X-Cache-Bypass: true` request header bypasses all cache reads and forces fresh API calls. All new responses overwrite existing cache entries.
*   **Version Mismatch**: If the recorded API version in the cache entry differs from the current configured API version, the cache entry is considered stale and invalidated.

---

## 15. Provenance & Traceability

Every canonical `Evidence` object produced by the Retrieval Layer must carry a complete provenance record. This is non-negotiable for scientific reproducibility.

### 15.1 Provenance Metadata Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `source_name` | String | Name of the originating database (e.g., `ChEMBL`, `PubMed`) |
| `source_version` | String | Database version at time of retrieval (e.g., `ChEMBL v33`) |
| `source_url` | URI | Direct URL of the queried API endpoint |
| `original_identifier` | String | The source-native identifier for this record (e.g., `CHEMBL_ACTIVITY_123456`) |
| `canonical_url` | URI | Permanent public URL for the record (e.g., PubMed article page) |
| `doi` | String (optional) | Digital Object Identifier for literature records |
| `nct_id` | String (optional) | ClinicalTrials.gov identifier for trial records |
| `retrieved_at` | ISO-8601 DateTime | Timestamp when this record was fetched |
| `normalized_at` | ISO-8601 DateTime | Timestamp when this record was mapped to its canonical object |
| `cache_hit` | Boolean | Whether this record was served from cache or a live API call |
| `license` | String | Data license statement from the source database |
| `citation` | String | Formatted citation string for the source record |

### 15.2 Provenance Chain Example

```
Evidence (ChEMBL binding record for Sildenafil–PDE5A)
│
├── source_name: "ChEMBL"
├── source_version: "ChEMBL v33"
├── source_url: "https://www.ebi.ac.uk/chembl/api/data/activity?molecule_chembl_id=CHEMBL941"
├── original_identifier: "CHEMBL_ACTIVITY_3189226"
├── canonical_url: "https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL941/"
├── retrieved_at: "2026-07-09T15:39:37Z"
├── cache_hit: false
└── license: "CC BY-SA 3.0"
```

---

## 16. Retrieval Metrics & Observability

The Retrieval Layer emits structured metrics to enable performance monitoring, source quality tracking, and debugging of incomplete evidence retrieval.

### 16.1 Metrics Emitted

| Metric | Unit | Description |
| :--- | :--- | :--- |
| `retrieval.source.latency_ms` | ms (per source) | Elapsed time for each source's HTTP request cycle |
| `retrieval.cache.hit_ratio` | Ratio [0–1] (per source) | Fraction of queries served from cache |
| `retrieval.records.total` | Count | Total canonical Evidence records returned |
| `retrieval.records.dropped` | Count | Records rejected by schema validation |
| `retrieval.records.deduplicated` | Count | Records merged during deduplication |
| `retrieval.sources.failed` | Count | Number of sources that returned no data |
| `retrieval.source.retry_count` | Count (per source) | Number of HTTP retries performed |
| `retrieval.normalization.failures` | Count | Records that passed HTTP validation but failed canonical mapping |
| `retrieval.completeness_score` | Ratio [0–1] | Fraction of planned sources that returned data |
| `retrieval.total_duration_ms` | ms | Full pipeline duration from plan start to package assembly |

### 16.2 Observability Signals

*   **Low Cache Hit Ratio** (`< 0.3`): Signals that many queries are cold-start. May indicate the cache TTL is too short or the query parameter space is highly variable.
*   **High Drop Rate** (`> 0.2`): Signals a schema mismatch, possibly caused by a source API version change. Triggers a `SCHEMA_DRIFT_ALERT`.
*   **Source Failure Clustering**: If multiple sources fail simultaneously, this may indicate a network-level issue rather than a source-specific failure.
*   **Latency Spikes**: P95 latency exceeding 3× the source's historical average signals impending source degradation and should trigger a preemptive cache extension.

---

## 17. Future Retrieval Roadmap

The retrieval architecture is designed to grow without requiring structural rework. The following capabilities are defined for future phases:

*   **Local Source Mirrors**: Deploy local read-only mirrors of ChEMBL, UniProt, and Reactome using their bulk download releases. This eliminates all HTTP round-trip latency for Phase 1 sources and removes rate-limit constraints entirely.
*   **Neo4j Knowledge Graph Integration**: Integrate a locally hosted Neo4j instance populated with PrimeKG or Hetionet. The Retrieval Planner routes protein-pathway-disease traversal queries directly to Neo4j via Cypher, reducing mechanistic chain retrieval from seconds to milliseconds.
*   **Vector Similarity Retrieval**: Index extracted `Claim` objects in a vector database (e.g., ChromaDB or Weaviate). Future queries can retrieve semantically similar claims from prior evaluations without re-running literature extraction.
*   **Hybrid Retrieval**: Combine structured API retrieval with vector-based retrieval for cases where no direct bioactivity record exists but similar experimental findings are available from prior queries.
*   **Incremental Evidence Updates**: Rather than full re-retrieval on cache expiry, implement event-driven update subscriptions (where source APIs support it) to ingest only new or changed records since last retrieval.
*   **Batch Retrieval Mode**: Support retrieval for multiple drug-disease pairs in a single planning session, enabling high-throughput research batch jobs without redundant source calls for shared drugs or diseases.
*   **Source Credentialing**: Introduce a formal source credentialing framework that tracks evidence volume, consistency score, and historical validation rate per database, adjusting Evidence Reliability Weights dynamically based on observed source quality.
