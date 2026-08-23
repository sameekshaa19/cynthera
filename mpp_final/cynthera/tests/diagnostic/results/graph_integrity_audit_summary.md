============================================================
CYNTHERA GRAPH INTEGRITY AUDIT
============================================================

PACKAGE
    Drug: Sildenafil
    Disease: Pulmonary Arterial Hypertension

------------------------------------------------------------
1. RETRIEVAL INVENTORY
------------------------------------------------------------
Targets: 1
Proteins: 1
Pathways: 3
Disease genes: 1205
Evidence: 56

------------------------------------------------------------
2. CANONICALIZATION
------------------------------------------------------------
Identifiers audited: 1290
Resolved: 1290 (100.0%)
Unresolved: 0
Duplicate raw IDs: 8
Canonical entities: 1232

Raw matching: 4
Canonical matching: 4
New matches: 0

------------------------------------------------------------
3. ACTUAL GRAPH
------------------------------------------------------------
Nodes:
    Drug: 1
    Target: 1
    Protein: 0
    Pathway: 3
    Gene: 4
    Disease: 1

Edges:
    SOURCE        RELATIONSHIP                        DIRECTION    TARGET       COUNT
    ---------------------------------------------------------------------------
    DRUG          MODULATES                           UNKNOWN      TARGET          1
    GENE          ASSOCIATED_WITH                     UNKNOWN      DISEASE         4
    PATHWAY       CONTAINS_ASSOCIATED_GENE            UNKNOWN      GENE            6
    TARGET        ENCODED_BY_DISEASE_ASSOCIATED_GENE  UNKNOWN      GENE            1
    TARGET        PARTICIPATES_IN                     UNKNOWN      PATHWAY         3

------------------------------------------------------------
4. EDGE EVIDENCE COVERAGE
------------------------------------------------------------
Total edges: 15
With source: 15 (100.0%)
With source ID: 15
With evidence type: 15
With context: 15

------------------------------------------------------------
5. CONNECTIVITY
------------------------------------------------------------
Drug -> Target: 1 edges (candidates: 1)
Target -> Pathway: 3 edges (candidates: 3)
Pathway -> Gene: 6 edges (candidates: 83)
Gene -> Disease: 4 edges (candidates: 50)

------------------------------------------------------------
6. PATH TRAVERSAL
------------------------------------------------------------
Depth 1: 1
Depth 2: 4
Depth 3: 7
Depth 4: 4
Complete Drug -> Disease paths: 7
Shortest path length: 4
Longest path length: 5

------------------------------------------------------------
7. ISOLATED NODES
------------------------------------------------------------
Targets: 0 (None)
Pathways: 0 (None)
Genes: 0 (None)
Other: 0

------------------------------------------------------------
8. ROOT-CAUSE DIAGNOSIS
------------------------------------------------------------
Classification: NO_GRAPH_GAP_DETECTED

Evidence: Complete hop-by-hop paths successfully traced from Drug to Disease.

Affected layer: NONE

Recommended NEXT INVESTIGATION: Proceed to direction-of-effect and mechanistic scoring validation.

============================================================

============================================================
CYNTHERA GRAPH INTEGRITY AUDIT
============================================================

PACKAGE
    Drug: Metformin
    Disease: Type 2 Diabetes

------------------------------------------------------------
1. RETRIEVAL INVENTORY
------------------------------------------------------------
Targets: 1
Proteins: 1
Pathways: 2
Disease genes: 1335
Evidence: 56

------------------------------------------------------------
2. CANONICALIZATION
------------------------------------------------------------
Identifiers audited: 1371
Resolved: 1371 (100.0%)
Unresolved: 0
Duplicate raw IDs: 14
Canonical entities: 1307

Raw matching: 2
Canonical matching: 2
New matches: 0

------------------------------------------------------------
3. ACTUAL GRAPH
------------------------------------------------------------
Nodes:
    Drug: 1
    Target: 1
    Protein: 0
    Pathway: 2
    Gene: 2
    Disease: 1

Edges:
    SOURCE        RELATIONSHIP                        DIRECTION    TARGET       COUNT
    ---------------------------------------------------------------------------
    DRUG          MODULATES                           UNKNOWN      TARGET          1
    GENE          ASSOCIATED_WITH                     UNKNOWN      DISEASE         2
    PATHWAY       CONTAINS_ASSOCIATED_GENE            UNKNOWN      GENE            3
    TARGET        ENCODED_BY_DISEASE_ASSOCIATED_GENE  UNKNOWN      GENE            1
    TARGET        PARTICIPATES_IN                     UNKNOWN      PATHWAY         2

------------------------------------------------------------
4. EDGE EVIDENCE COVERAGE
------------------------------------------------------------
Total edges: 9
With source: 9 (100.0%)
With source ID: 9
With evidence type: 9
With context: 9

------------------------------------------------------------
5. CONNECTIVITY
------------------------------------------------------------
Drug -> Target: 1 edges (candidates: 1)
Target -> Pathway: 2 edges (candidates: 2)
Pathway -> Gene: 3 edges (candidates: 34)
Gene -> Disease: 2 edges (candidates: 50)

------------------------------------------------------------
6. PATH TRAVERSAL
------------------------------------------------------------
Depth 1: 1
Depth 2: 3
Depth 3: 4
Depth 4: 2
Complete Drug -> Disease paths: 4
Shortest path length: 4
Longest path length: 5

------------------------------------------------------------
7. ISOLATED NODES
------------------------------------------------------------
Targets: 0 (None)
Pathways: 0 (None)
Genes: 0 (None)
Other: 0

------------------------------------------------------------
8. ROOT-CAUSE DIAGNOSIS
------------------------------------------------------------
Classification: NO_GRAPH_GAP_DETECTED

Evidence: Complete hop-by-hop paths successfully traced from Drug to Disease.

Affected layer: NONE

Recommended NEXT INVESTIGATION: Proceed to direction-of-effect and mechanistic scoring validation.

============================================================

============================================================
CYNTHERA GRAPH INTEGRITY AUDIT
============================================================

PACKAGE
    Drug: Propranolol
    Disease: Infantile Hemangioma

------------------------------------------------------------
1. RETRIEVAL INVENTORY
------------------------------------------------------------
Targets: 3
Proteins: 3
Pathways: 2
Disease genes: 555
Evidence: 58

------------------------------------------------------------
2. CANONICALIZATION
------------------------------------------------------------
Identifiers audited: 730
Resolved: 730 (100.0%)
Unresolved: 0
Duplicate raw IDs: 8
Canonical entities: 698

Raw matching: 2
Canonical matching: 2
New matches: 0

------------------------------------------------------------
3. ACTUAL GRAPH
------------------------------------------------------------
Nodes:
    Drug: 1
    Target: 2
    Protein: 0
    Pathway: 2
    Gene: 2
    Disease: 1

Edges:
    SOURCE        RELATIONSHIP                        DIRECTION    TARGET       COUNT
    ---------------------------------------------------------------------------
    DRUG          MODULATES                           UNKNOWN      TARGET          2
    GENE          ASSOCIATED_WITH                     UNKNOWN      DISEASE         2
    PATHWAY       CONTAINS_ASSOCIATED_GENE            UNKNOWN      GENE            4
    TARGET        ENCODED_BY_DISEASE_ASSOCIATED_GENE  UNKNOWN      GENE            1
    TARGET        PARTICIPATES_IN                     UNKNOWN      PATHWAY         2

------------------------------------------------------------
4. EDGE EVIDENCE COVERAGE
------------------------------------------------------------
Total edges: 11
With source: 11 (100.0%)
With source ID: 11
With evidence type: 11
With context: 11

------------------------------------------------------------
5. CONNECTIVITY
------------------------------------------------------------
Drug -> Target: 2 edges (candidates: 3)
Target -> Pathway: 2 edges (candidates: 6)
Pathway -> Gene: 4 edges (candidates: 169)
Gene -> Disease: 2 edges (candidates: 23)

------------------------------------------------------------
6. PATH TRAVERSAL
------------------------------------------------------------
Depth 1: 2
Depth 2: 3
Depth 3: 5
Depth 4: 2
Complete Drug -> Disease paths: 5
Shortest path length: 4
Longest path length: 5

------------------------------------------------------------
7. ISOLATED NODES
------------------------------------------------------------
Targets: 1 (UNKNOWN (B0FL73))
Pathways: 0 (None)
Genes: 0 (None)
Other: 0

------------------------------------------------------------
8. ROOT-CAUSE DIAGNOSIS
------------------------------------------------------------
Classification: NO_GRAPH_GAP_DETECTED

Evidence: Complete hop-by-hop paths successfully traced from Drug to Disease.

Affected layer: NONE

Recommended NEXT INVESTIGATION: Proceed to direction-of-effect and mechanistic scoring validation.

============================================================

============================================================
CYNTHERA GRAPH INTEGRITY AUDIT
============================================================

PACKAGE
    Drug: Dapagliflozin
    Disease: Heart Failure

------------------------------------------------------------
1. RETRIEVAL INVENTORY
------------------------------------------------------------
Targets: 3
Proteins: 3
Pathways: 4
Disease genes: 1180
Evidence: 70

------------------------------------------------------------
2. CANONICALIZATION
------------------------------------------------------------
Identifiers audited: 1213
Resolved: 1213 (100.0%)
Unresolved: 0
Duplicate raw IDs: 11
Canonical entities: 1152

Raw matching: 2
Canonical matching: 2
New matches: 0

------------------------------------------------------------
3. ACTUAL GRAPH
------------------------------------------------------------
Nodes:
    Drug: 1
    Target: 2
    Protein: 0
    Pathway: 4
    Gene: 2
    Disease: 1

Edges:
    SOURCE        RELATIONSHIP                        DIRECTION    TARGET       COUNT
    ---------------------------------------------------------------------------
    DRUG          INHIBITOR                           NEGATIVE     TARGET          1
    DRUG          MODULATES                           UNKNOWN      TARGET          1
    GENE          ASSOCIATED_WITH                     UNKNOWN      DISEASE         2
    PATHWAY       CONTAINS_ASSOCIATED_GENE            UNKNOWN      GENE            5
    TARGET        ENCODED_BY_DISEASE_ASSOCIATED_GENE  UNKNOWN      GENE            2
    TARGET        PARTICIPATES_IN                     UNKNOWN      PATHWAY         5

------------------------------------------------------------
4. EDGE EVIDENCE COVERAGE
------------------------------------------------------------
Total edges: 16
With source: 16 (100.0%)
With source ID: 16
With evidence type: 16
With context: 16

------------------------------------------------------------
5. CONNECTIVITY
------------------------------------------------------------
Drug -> Target: 2 edges (candidates: 3)
Target -> Pathway: 5 edges (candidates: 12)
Pathway -> Gene: 5 edges (candidates: 27)
Gene -> Disease: 2 edges (candidates: 50)

------------------------------------------------------------
6. PATH TRAVERSAL
------------------------------------------------------------
Depth 1: 2
Depth 2: 7
Depth 3: 7
Depth 4: 2
Complete Drug -> Disease paths: 9
Shortest path length: 4
Longest path length: 5

------------------------------------------------------------
7. ISOLATED NODES
------------------------------------------------------------
Targets: 0 (None)
Pathways: 0 (None)
Genes: 0 (None)
Other: 0

------------------------------------------------------------
8. ROOT-CAUSE DIAGNOSIS
------------------------------------------------------------
Classification: NO_GRAPH_GAP_DETECTED

Evidence: Complete hop-by-hop paths successfully traced from Drug to Disease.

Affected layer: NONE

Recommended NEXT INVESTIGATION: Proceed to direction-of-effect and mechanistic scoring validation.

============================================================

============================================================
CYNTHERA GRAPH INTEGRITY AUDIT
============================================================

PACKAGE
    Drug: Thalidomide
    Disease: Multiple Myeloma

------------------------------------------------------------
1. RETRIEVAL INVENTORY
------------------------------------------------------------
Targets: 3
Proteins: 3
Pathways: 12
Disease genes: 1319
Evidence: 70

------------------------------------------------------------
2. CANONICALIZATION
------------------------------------------------------------
Identifiers audited: 1841
Resolved: 1841 (100.0%)
Unresolved: 0
Duplicate raw IDs: 192
Canonical entities: 1597

Raw matching: 33
Canonical matching: 33
New matches: 0

------------------------------------------------------------
3. ACTUAL GRAPH
------------------------------------------------------------
Nodes:
    Drug: 1
    Target: 3
    Protein: 0
    Pathway: 6
    Gene: 34
    Disease: 1

Edges:
    SOURCE        RELATIONSHIP                        DIRECTION    TARGET       COUNT
    ---------------------------------------------------------------------------
    DRUG          INHIBITOR                           NEGATIVE     TARGET          1
    DRUG          MODULATES                           UNKNOWN      TARGET          2
    GENE          ASSOCIATED_WITH                     UNKNOWN      DISEASE        34
    PATHWAY       CONTAINS_ASSOCIATED_GENE            UNKNOWN      GENE           33
    TARGET        ENCODED_BY_DISEASE_ASSOCIATED_GENE  UNKNOWN      GENE            1
    TARGET        PARTICIPATES_IN                     UNKNOWN      PATHWAY         6

------------------------------------------------------------
4. EDGE EVIDENCE COVERAGE
------------------------------------------------------------
Total edges: 77
With source: 77 (100.0%)
With source ID: 77
With evidence type: 77
With context: 77

------------------------------------------------------------
5. CONNECTIVITY
------------------------------------------------------------
Drug -> Target: 3 edges (candidates: 3)
Target -> Pathway: 6 edges (candidates: 18)
Pathway -> Gene: 33 edges (candidates: 516)
Gene -> Disease: 34 edges (candidates: 50)

------------------------------------------------------------
6. PATH TRAVERSAL
------------------------------------------------------------
Depth 1: 3
Depth 2: 7
Depth 3: 34
Depth 4: 33
Complete Drug -> Disease paths: 34
Shortest path length: 4
Longest path length: 5

------------------------------------------------------------
7. ISOLATED NODES
------------------------------------------------------------
Targets: 1 (PTGS1 (P05979))
Pathways: 5 (TNFR1-mediated ceramide production (R-HSA-5626978), Differentiation of naive CD4+ T cells to T helper 1 cells (Th1 cells) (R-HSA-9942503), TNFR1-induced proapoptotic signaling (R-HSA-5357786))
Genes: 0 (None)
Other: 0

------------------------------------------------------------
8. ROOT-CAUSE DIAGNOSIS
------------------------------------------------------------
Classification: NO_GRAPH_GAP_DETECTED

Evidence: Complete hop-by-hop paths successfully traced from Drug to Disease.

Affected layer: NONE

Recommended NEXT INVESTIGATION: Proceed to direction-of-effect and mechanistic scoring validation.

============================================================

