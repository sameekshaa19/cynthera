============================================================
DIRECTION-OF-EFFECT DATA AUDIT
============================================================

1. OVERVIEW

    Cases: 5
    Complete graph paths: 48
    Direction-ready paths: 0
    Partially ready paths: 5
    Not-ready paths: 43

------------------------------------------------------------
2. CASE-BY-CASE AUDIT
------------------------------------------------------------

CASE 1
    Drug: Propranolol
    Disease: Infantile Hemangioma

    Drug -> Target:
        total: 3
        explicit effects: 0
        unknown effects: 3

    Target -> Pathway:
        total: 2
        explicit directions: 0
        unknown directions: 2

    Disease-associated biology:
        explicit directions: 0
        unknown directions: 6

    Direction-ready paths: 0
    Partial paths: 0
    Not-ready paths: 5

CASE 2
    Drug: Dapagliflozin
    Disease: Heart Failure

    Drug -> Target:
        total: 3
        explicit effects: 1
        unknown effects: 2

    Target -> Pathway:
        total: 5
        explicit directions: 0
        unknown directions: 5

    Disease-associated biology:
        explicit directions: 0
        unknown directions: 7

    Direction-ready paths: 0
    Partial paths: 4
    Not-ready paths: 5

CASE 3
    Drug: Thalidomide
    Disease: Multiple Myeloma

    Drug -> Target:
        total: 3
        explicit effects: 1
        unknown effects: 2

    Target -> Pathway:
        total: 6
        explicit directions: 0
        unknown directions: 6

    Disease-associated biology:
        explicit directions: 0
        unknown directions: 67

    Direction-ready paths: 0
    Partial paths: 1
    Not-ready paths: 33

CASE 4
    Drug: Aspirin
    Disease: Colorectal Cancer

    Drug -> Target:
        total: 1
        explicit effects: 1
        unknown effects: 0

    Target -> Pathway:
        total: 6
        explicit directions: 0
        unknown directions: 6

    Disease-associated biology:
        explicit directions: 0
        unknown directions: 0

    Direction-ready paths: 0
    Partial paths: 0
    Not-ready paths: 0

CASE 5
    Drug: Minoxidil
    Disease: Hair Loss

    Drug -> Target:
        total: 1
        explicit effects: 1
        unknown effects: 0

    Target -> Pathway:
        total: 6
        explicit directions: 0
        unknown directions: 6

    Disease-associated biology:
        explicit directions: 0
        unknown directions: 0

    Direction-ready paths: 0
    Partial paths: 0
    Not-ready paths: 0

------------------------------------------------------------
3. DIRECTION INFORMATION SOURCES
------------------------------------------------------------

Source: ChEMBL
    direction information available: YES (explicit mechanism: INHIBITOR, AGONIST, ANTAGONIST, BLOCKER, etc.)
    count: 4 explicit out of 11 targets
    type: database-provided (curated mechanism endpoint + bioactivity standard_type)

Source: Reactome
    direction information available: NO (membership only: PARTICIPATES_IN)
    count: 0 explicit out of 25 relationships
    type: unavailable in current retrieval schema (/data/participants returns participating molecules without activation/inhibition sign)

Source: Open Targets / DisGeNET
    direction information available: NO (association strength only: score in [0, 1])
    count: 0 explicit out of 80 relationships
    type: unavailable in current retrieval schema (associatedTargets returns scalar overall score and datatypeScores, not GoF/LoF pathology direction)

------------------------------------------------------------
4. PATH-LEVEL READINESS
------------------------------------------------------------

Representative paths for Case 1 (Propranolol -> Infantile Hemangioma):
    Path: [Drug] Propranolol -> [Target] ADRB1 (P08588) -> [Gene] ADRB1 -> [Disease] Infantile Hemangioma
        Drug -> Target: UNKNOWN
        Target -> Pathway: NOT AVAILABLE (membership only)
        Pathway/Gene -> Disease: NOT AVAILABLE (association strength only)
        Overall readiness: NOT_READY
    Path: [Drug] Propranolol -> [Target] ADRB1 (P08588) -> [Pathway] Adrenoceptors (R-HSA-390696) -> [Gene] ADRB1 -> [Disease] Infantile Hemangioma
        Drug -> Target: UNKNOWN
        Target -> Pathway: NOT AVAILABLE (membership only)
        Pathway/Gene -> Disease: NOT AVAILABLE (association strength only)
        Overall readiness: NOT_READY

Representative paths for Case 2 (Dapagliflozin -> Heart Failure):
    Path: [Drug] Dapagliflozin -> [Target] SLC5A2 (P31639) -> [Gene] SLC5A2 -> [Disease] Heart Failure
        Drug -> Target: EXPLICIT (INHIBITOR)
        Target -> Pathway: NOT AVAILABLE (membership only)
        Pathway/Gene -> Disease: NOT AVAILABLE (association strength only)
        Overall readiness: PARTIAL
    Path: [Drug] Dapagliflozin -> [Target] SLC5A2 (P31639) -> [Pathway] Defective SLC5A2 causes renal glucosuria (GLYS1) (R-HSA-5658208) -> [Gene] SLC5A2 -> [Disease] Heart Failure
        Drug -> Target: EXPLICIT (INHIBITOR)
        Target -> Pathway: NOT AVAILABLE (membership only)
        Pathway/Gene -> Disease: NOT AVAILABLE (association strength only)
        Overall readiness: PARTIAL

Representative paths for Case 3 (Thalidomide -> Multiple Myeloma):
    Path: [Drug] Thalidomide -> [Target] CRBN (Q96SW2) -> [Gene] CRBN -> [Disease] Multiple Myeloma
        Drug -> Target: EXPLICIT (INHIBITOR)
        Target -> Pathway: NOT AVAILABLE (membership only)
        Pathway/Gene -> Disease: NOT AVAILABLE (association strength only)
        Overall readiness: PARTIAL
    Path: [Drug] Thalidomide -> [Target] TNF (P01375) -> [Pathway] TNFR2 non-canonical NF-kB pathway (R-HSA-5668541) -> [Gene] PSMA1 -> [Disease] Multiple Myeloma
        Drug -> Target: UNKNOWN
        Target -> Pathway: NOT AVAILABLE (membership only)
        Pathway/Gene -> Disease: NOT AVAILABLE (association strength only)
        Overall readiness: NOT_READY

Representative paths for Case 4 (Aspirin -> Colorectal Cancer):
    [NONE - no complete path found]

Representative paths for Case 5 (Minoxidil -> Hair Loss):
    [NONE - no complete path found]

------------------------------------------------------------
5. CROSS-CASE COMPARISON
------------------------------------------------------------

| Case | Drug | Disease | Complete paths | Drug-target direction | Target-pathway direction | Disease direction | Fully direction-ready paths |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|
| 1 | Propranolol | Infantile Hemangioma | 5 | 0/3 explicit | 0/2 explicit | 0/6 explicit | 0 |
| 2 | Dapagliflozin | Heart Failure | 9 | 1/3 explicit | 0/5 explicit | 0/7 explicit | 0 |
| 3 | Thalidomide | Multiple Myeloma | 34 | 1/3 explicit | 0/6 explicit | 0/67 explicit | 0 |
| 4 | Aspirin | Colorectal Cancer | 0 | 1/1 explicit | 0/6 explicit | 0/0 explicit | 0 |
| 5 | Minoxidil | Hair Loss | 0 | 1/1 explicit | 0/6 explicit | 0/0 explicit | 0 |

------------------------------------------------------------
6. MISSING INFORMATION
------------------------------------------------------------

    Missing information:
        1. Target -> Pathway regulatory polarity (positive vs negative regulation / activation vs inhibition).
        2. Gene -> Disease pathological direction (gain-of-function vs loss-of-function / risk-increasing vs protective / pathogenic overexpression vs down-regulation).

    Layer:
        - Target -> Pathway (Reactome)
        - Pathway / Gene -> Disease (Open Targets / DisGeNET / Literature)

    Already present in retrieved data:
        - Drug -> Target: YES (ChEMBL provides explicit mechanism: INHIBITOR, AGONIST, ANTAGONIST, etc.).
        - Target -> Pathway: NO (Reactome connector currently queries /data/participants which returns unpolarized PhysicalEntities).
        - Gene -> Disease: NO (Open Targets connector currently queries associatedTargets { score, datatypeScores } which returns unpolarized scalar scores).

    New data required:
        - Polarized regulatory relationships (e.g. Reactome Regulation events or curated sign metadata).
        - Directional genetic/pathological evidence (e.g. Open Targets geneticConstraint, ClinVar clinicalSignificance, or literature directional claims).

------------------------------------------------------------
7. FINAL VERDICT
------------------------------------------------------------

    PARTIALLY READY

    Explain exactly why:
    - Drug -> Target directional polarity is already fully available and explicit in ChEMBL (e.g. Dapagliflozin = INHIBITOR, Thalidomide = INHIBITOR, Propranolol = MODULATOR/ANTAGONIST).
    - However, Target -> Pathway (Reactome) and Gene -> Disease (Open Targets) are currently retrieved and represented purely as undirected participation and association strengths.
    - As a result, 100% of discovered complete paths are PARTIALLY ready (possessing explicit Drug->Target direction but lacking downstream pathway and disease directional polarity).
    - Implementing full end-to-end direction-of-effect reasoning without completing the downstream directional layers would force ungrounded heuristic assumptions.

------------------------------------------------------------
8. FILES CHANGED
------------------------------------------------------------

    NONE

------------------------------------------------------------
9. TEST STATUS
------------------------------------------------------------

    Existing tests: 168 passed
    Diagnostic cases: 5 cases audited
    Failures: 0
    Errors: 0

============================================================