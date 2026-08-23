---
name: cynthera-engineering-constitution
description: Immutable engineering constitution governing every architectural and implementation decision within the CYNTHERA scientific drug repurposing platform.
---

# CYNTHERA Engineering Constitution

> **This document defines the immutable architectural, scientific, and engineering principles of CYNTHERA.**
>
> Every implementation, refactor, bug fix, optimization, and new feature must preserve these guarantees.
>
> If a requested change violates any principle in this document, the implementation must be rejected and a compliant alternative proposed.

---

# Mission

CYNTHERA is a **research-grade scientific reasoning platform** for drug repurposing.

Its purpose is to:

1. Retrieve biomedical evidence from authoritative sources.
2. Normalize heterogeneous biomedical information.
3. Construct canonical scientific knowledge.
4. Reason over evidence using deterministic scientific logic.
5. Produce transparent and reproducible recommendations.
6. Explain every conclusion with traceable evidence.

The objective is **scientific correctness**, not producing expected outputs.

---

# Fundamental Philosophy

The system does **not** exist to make a report look correct.

The system exists to discover what the evidence supports.

Whenever appearance conflicts with scientific correctness,

scientific correctness always wins.

---

# Architectural Invariants

These invariants are permanent.

Breaking any invariant is considered an architectural regression.

---

## 1. Single Source of Truth

Every biomedical fact must exist exactly once.

Correct

```
Retrieval
      ↓
Canonical Models
      ↓
Entire System
```

Incorrect

```
Drug.approved_indications

KnowledgeStore.approved_indications

RuleEngine.approved_list
```

Biomedical knowledge must never be duplicated across components.

---

## 2. Layer Responsibility

Every architectural layer has exactly one responsibility.

### Retrieval

Responsible for

- API communication
- data acquisition

Never

- score evidence
- classify drugs
- infer biology

---

### Parser

Responsible for

- transforming raw payloads
- validation
- normalization

Never

- infer mechanisms
- determine recommendations

---

### Canonical Models

Responsible for

- representing biomedical entities

Never

- perform reasoning
- mutate themselves

---

### Scientific Reasoning

Responsible for

- evaluating biological evidence

Never

- call APIs
- perform retrieval
- modify canonical data

---

### Rule Engine

Responsible for

- deterministic policy
- recommendation classification

Never

- invent evidence
- override biology
- query databases

---

### Frontend

Responsible for

- visualization

Never

- calculate scores
- perform reasoning
- reconstruct biology

---

## 3. Immutable Canonical Models

Once canonical models are created they become read-only.

Reasoning may consume them.

Reasoning may never rewrite them.

Example

```
Drug

Protein

Target

Pathway

Disease

Evidence
```

must remain immutable after normalization.

---

## 4. No Hidden State

Scientific outputs must never depend upon

- previous executions
- hidden caches
- global variables
- execution ordering
- random iteration
- undocumented configuration

Unless explicitly documented and reproducible.

---

## 5. Evolution Without Rewrites

Adding

- DrugBank
- PharmGKB
- DisGeNET
- OMIM
- TCGA
- LINCS
- FAERS

must not require modifying the reasoning engine.

If a new connector requires reasoning changes,

the architecture has become tightly coupled.

---

# Data Integrity Principles

---

## Retrieval First

Scientific reasoning begins only after validated retrieval.

Always

```
Retrieve

↓

Validate

↓

Parse

↓

Normalize

↓

Canonical Models

↓

Reason
```

Never

```
Retrieve

↓

Reason

↓

Notice missing data

↓

Guess
```

---

## Evidence Completeness

Every reasoning step assumes retrieval has been validated.

Evidence completeness must be known before scientific reasoning begins.

Missing evidence is an explicit system state.

---

## API Quality Contracts

Every connector must define

- expected schema
- required fields
- optional fields
- retry behaviour
- timeout behaviour
- validation rules
- parser completeness

Connector quality must be measurable.

---

## Silent Failures Are Forbidden

Forbidden

```python
try:
    ...
except:
    return []
```

Every failure must be

- logged
- classified
- propagated

Examples

- API timeout
- parser failure
- malformed payload
- rate limit
- identifier resolution failure

The system must always know why information is missing.

---

## Information Preservation

Parsers must preserve retrieved information.

No retrieved field may disappear without explicit justification.

Every discarded field must record

- stage
- reason
- responsible component

---

# Scientific Reasoning Principles

---

## Evidence Before Reasoning

Reasoning only consumes validated canonical evidence.

Evidence is never inferred from missing information.

---

## Confidence Is Not Recommendation

Confidence answers

> How certain is the available evidence?

Recommendation answers

> Should this therapeutic hypothesis be pursued?

These are independent.

Possible

```
Low Confidence

↓

PROMISING
```

Possible

```
High Confidence

↓

NOT RECOMMENDED
```

Never combine them.

---

## Scores Summarize Reasoning

Scores summarize reasoning.

They do not replace reasoning.

Correct

```
Evidence

↓

Claims

↓

Mechanistic Analysis

↓

Consensus

↓

Scores

↓

Recommendation
```

Incorrect

```
Support Score

↓

Recommendation
```

---

## Cross-Agent Consistency

Scientific outputs must remain logically consistent.

Example

```
Support = HIGH

Mechanism = NONE

Recommendation = PROMISING
```

must trigger consistency validation.

Contradictions must never pass silently.

---

## Scientific Defensibility

Every recommendation must survive repeated questioning.

```
Recommendation

↓

Evidence

↓

Claims

↓

Sources

↓

Publications

↓

Retrieved Records
```

Every level must remain explainable.

If the explanation chain breaks,

the recommendation is invalid.

---

## Contradictory Evidence

Conflicting evidence must never be hidden.

The report must distinguish

- supporting evidence
- contradicting evidence
- uncertain evidence

Scientific disagreement is itself evidence.

---

# Scientific Integrity

The system must never

- fabricate biological mechanisms
- invent citations
- infer regulatory approval
- suppress contradictory evidence
- convert weak evidence into established knowledge
- overstate certainty
- fill missing evidence with assumptions

Whenever uncertainty exists,

the report must explicitly communicate uncertainty.

---

# Root Cause Policy

Before modifying code,

identify

```
Symptom

↓

Immediate Cause

↓

Underlying Cause

↓

Architectural Cause
```

Always solve the lowest practical cause.

Never patch symptoms.

---

# Regression Protection

Every implementation must answer

> What existing behaviour could this change break?

Regression validation is mandatory.

Passing the new test alone is insufficient.

---

# Placeholder Logic

Forbidden in production

```
TODO

pass

return []

return {}

return HIGH

dummy values

temporary heuristics
```

Temporary logic must fail loudly.

---

# Performance Philosophy

Performance improvements must never sacrifice

- validation
- correctness
- traceability
- determinism
- scientific integrity

Correctness always takes priority.

---

# Explainability Requirements

Every transformation must be reconstructable.

Every step must answer

```
Input

↓

Transformation

↓

Output

↓

Reason
```

No behaviour may exist solely because

> helper.py does it.

---

# Recommendation Reconstruction

Every recommendation must be reproducible.

```
Drug

↓

Retrieved Evidence

↓

Canonical Models

↓

Scientific Claims

↓

Mechanistic Analysis

↓

Consensus

↓

Scores

↓

Recommendation
```

Every score must be traceable.

Every recommendation must be reconstructable.

---

# Future-Proof Architecture

Every implementation should satisfy

> If a completely new drug approved in 2035 entered the system tomorrow,

would CYNTHERA retrieve,

reason,

and generate a valid report

without code changes?

If not,

the implementation introduced unnecessary coupling.

---

# Forbidden Behaviours

Reject implementations that

- hardcode biomedical knowledge
- optimize for one report
- duplicate biomedical facts
- merge architectural responsibilities
- ignore parser failures
- suppress contradictory evidence
- infer biology from missing data
- manipulate scores to force outcomes
- introduce hidden state
- add special cases instead of solving root causes

---

# Architectural Exit Criteria

Before completing any implementation,

the following questions must be answered.

1. Which pipeline stage changed?
2. Why was that the correct architectural layer?
3. What root cause was resolved?
4. Which downstream symptoms disappear?
5. What evidence proves the fix works?
6. Which regression tests were executed?
7. Which architectural invariants were verified?
8. Did this introduce coupling or hidden assumptions?
9. Does this generalize to unseen drug–disease pairs?
10. Can every recommendation still be reconstructed from retrieved evidence?
11. Does every biomedical fact still originate from retrieval?
12. Has any architectural responsibility moved into the wrong layer?

If any answer is **No**,

the implementation is incomplete.

---

# Definition of Done

A change is complete only if it

- preserves architectural invariants
- preserves scientific integrity
- preserves determinism
- preserves explainability
- preserves reproducibility
- preserves traceability
- generalizes beyond the current example
- reduces architectural complexity rather than increasing it

The objective is not to make the current report pass.

The objective is to strengthen the scientific architecture for every future report.