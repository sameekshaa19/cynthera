============================================================
REACTOME REGULATORY DIRECTION AUDIT
============================================================

1. CURRENT REACTOME INTEGRATION

    Current endpoint(s):
        1. GET https://reactome.org/ContentService/data/mapping/UniProt/{uniprotId}/pathways
        2. GET https://reactome.org/ContentService/data/participants/{stId}

    Current fields extracted:
        - Pathway: stId, displayName (parsed to name, reactome_id)
        - Participants: refEntities[].identifier (UniProt accession), refEntities[].geneName, displayName (Gene symbols)

    Relevant fields currently discarded:
        - schemaClass (Complex, EntitySet, GenomeEncodedEntity, etc.)
        - hasDiagram, isInDisease, species
        - reaction roles and child event hierarchy in participant responses

    Current Target -> Pathway representation:
        - Undirected participant edge: Target --[PARTICIPATES_IN]--> Pathway
        - Strength: 0.30 + 0.50 * disease_gene_relevance (purely structural overlap)

------------------------------------------------------------
2. REACTOME DATA CAPABILITY

    Directional information available:
        NO (in current endpoints /data/mapping and /data/participants)

    Available relationship/event types:
        - PARTICIPATES_IN (undirected PhysicalEntity membership in pathway container)
        - ReferenceGeneProduct / PhysicalEntity mapping

    Regulatory polarity available:
        NO (no positive vs negative regulation flag, activation vs inhibition, or catalyst role is provided by the /data/participants endpoint)

    Causal/event information available:
        NO (the current integration operates at Level C: Target participates in pathway container, without reaction-level input/output/catalyst resolution)

------------------------------------------------------------
3. TARGET -> PATHWAY COVERAGE

    Total relationships: 25
    Participation only: 25 (100.0%)
    Explicitly directional: 0 (0.0%)
    Causal/event-based: 0 (0.0%)
    Ambiguous: 0 (0.0%)
    No usable direction: 25 (100.0%)

    Directional coverage: 0.0%

------------------------------------------------------------
4. CASE-BY-CASE RESULTS
------------------------------------------------------------

CASE 1
    Drug: Propranolol
    Disease: Infantile Hemangioma
    Target -> Pathway relationships: 2
    Directional relationships: 0
    Participation-only relationships: 2
    Causal/event relationships: 0
    Ambiguous relationships: 0

CASE 2
    Drug: Dapagliflozin
    Disease: Heart Failure
    Target -> Pathway relationships: 5
    Directional relationships: 0
    Participation-only relationships: 5
    Causal/event relationships: 0
    Ambiguous relationships: 0

CASE 3
    Drug: Thalidomide
    Disease: Multiple Myeloma
    Target -> Pathway relationships: 6
    Directional relationships: 0
    Participation-only relationships: 6
    Causal/event relationships: 0
    Ambiguous relationships: 0

CASE 4
    Drug: Aspirin
    Disease: Colorectal Cancer
    Target -> Pathway relationships: 6
    Directional relationships: 0
    Participation-only relationships: 6
    Causal/event relationships: 0
    Ambiguous relationships: 0

CASE 5
    Drug: Minoxidil
    Disease: Hair Loss
    Target -> Pathway relationships: 6
    Directional relationships: 0
    Participation-only relationships: 6
    Causal/event relationships: 0
    Ambiguous relationships: 0

------------------------------------------------------------
5. REPRESENTATIVE ACTUAL RELATIONSHIPS
------------------------------------------------------------

Relationship 1:
    Target: ADRB1 (P08588)
    Pathway: Adrenoceptors (R-HSA-390696)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-390696
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 2:
    Target: ADRB1 (P08588)
    Pathway: G alpha (s) signalling events (R-HSA-418555)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-418555
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 3:
    Target: SLC5A2 (P31639)
    Pathway: Defective SLC5A2 causes renal glucosuria (GLYS1) (R-HSA-5658208)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-5658208
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 4:
    Target: SLC5A2 (P31639)
    Pathway: Cellular hexose transport (R-HSA-189200)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-189200
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 5:
    Target: SLC5A1 (P13866)
    Pathway: Defective SLC5A1 causes congenital glucose/galactose malabsorption (GGM) (R-HSA-5656364)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-5656364
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 6:
    Target: SLC5A1 (P13866)
    Pathway: Intestinal hexose absorption (R-HSA-8981373)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-8981373
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 7:
    Target: SLC5A1 (P13866)
    Pathway: Cellular hexose transport (R-HSA-189200)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-189200
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 8:
    Target: TNF (P01375)
    Pathway: TNFR2 non-canonical NF-kB pathway (R-HSA-5668541)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-5668541
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 9:
    Target: TNF (P01375)
    Pathway: TNFR1-mediated ceramide production (R-HSA-5626978)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-5626978
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

Relationship 10:
    Target: TNF (P01375)
    Pathway: Differentiation of naive CD4+ T cells to T helper 1 cells (Th1 cells) (R-HSA-9942503)
    Reactome event/relationship: PhysicalEntity in Pathway
    Direction: PARTICIPATION_ONLY
    Reactome identifier: R-HSA-9942503
    Source: /data/participants/{stId}
    Explicitly directional: NO
    Target-specific: YES
    Causal/event-based: Level C (Target participates in pathway container)

------------------------------------------------------------
6. CONFLICTS / AMBIGUITIES
------------------------------------------------------------

    Conflicting directions: 0 (no directional annotations exist to conflict)
    Duplicate events: 0 (all 25 Target -> Pathway pairs are distinct stIds)
    Multiple regulatory relationships: 0
    Ambiguous relationships: 25 (all relationships lack activation/inhibition sign)

------------------------------------------------------------
7. DATA FLOW GAP

Current:

    Reactome (/data/participants)
       ↓
    PARTICIPATES_IN
       ↓
    Cynthera (EvidenceGraph)

What Reactome provides that Cynthera currently discards:
    - Complex / EntitySet membership structure
    - Pathway hierarchical container structure (parent/child pathway links)

What is required for directional Target -> Pathway reasoning:
    - Target role resolution (CatalystActivity vs PositiveRegulation vs NegativeRegulation vs Substrate vs Product)
    - Reaction-level event traversal linking target protein to downstream reaction events in pathway

------------------------------------------------------------
8. IMPLEMENTATION READINESS
------------------------------------------------------------

    NOT READY

    Explain the verdict using actual audit results:
    - Out of 25 actual Target -> Pathway relationships across all 5 test cases, 25 (100.0%) are participation-only.
    - The current Reactome integration (/data/mapping and /data/participants) contains 0.0% directional polarity or regulatory event signs.
    - Attempting to implement Target -> Pathway directional reasoning using the currently retrieved Reactome data would require fabricating or guessing direction, violating Cynthera's evidence-backed design principle.

------------------------------------------------------------
9. IF ANOTHER REACTOME RESOURCE IS NEEDED
------------------------------------------------------------

    Resource/endpoint:
        - GET https://reactome.org/ContentService/data/query/{stId} (detailed DatabaseObject query)
        - GET https://reactome.org/ContentService/data/eventsHierarchy/{species} (event cascade hierarchy)
        - Reactome Graph Database (Neo4j dump) / BioPAX export for regulation entities

    Relevant data:
        - CatalystActivity (catalyst for reaction)
        - PositiveRegulation / Requirement (activator / stimulator)
        - NegativeRegulation / Inhibition (inhibitor / repressor)

    Why it could solve the gap:
        - It would provide explicit molecular regulatory roles for targets in specific reactions rather than container-level membership.

    What additional mapping would be required:
        - Target -> Reaction mapping (many-to-many)
        - Reaction -> Pathway aggregation (tracing reaction regulation up to pathway impact)
        - Regulation polarity propagation through reaction cascade chains

    Potential limitations:
        - Substantial increase in API call volume and network latency per target (each pathway contains 10-50 child reactions).
        - Incomplete regulatory annotations: many human reactions in Reactome annotate catalysis but lack formal Positive/NegativeRegulation instances.

------------------------------------------------------------
10. FILES CHANGED
------------------------------------------------------------

    NONE

------------------------------------------------------------
11. TEST STATUS
------------------------------------------------------------

    Existing tests: 168 passed
    Diagnostic cases: 5 cases audited
    Failures: 0
    Errors: 0

============================================================