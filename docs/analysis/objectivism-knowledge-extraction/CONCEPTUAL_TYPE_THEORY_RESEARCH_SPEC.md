# Conceptual Type Theory (CTT)
## A Formalization of the Algebra of Cognition

*Initiated: 2026-02-21*
*Status: Research specification — theoretical foundation established, formalization not yet begun*
*Companion documents: DISCOVERY_DETECTION_FRAMEWORK.md, FUTURE_WORK_AND_POTENTIALITIES.md*

---

## The Research Claim

Ayn Rand's statement in *Introduction to Objectivist Epistemology*:

> *"The relationship of concepts to their constituent particulars is the same as the relationship of algebraic symbols to numbers... conceptual awareness is the algebra of cognition."*

This is not a metaphor. It is a precise structural claim that can be formalized into a rigorous mathematical system — **Conceptual Type Theory (CTT)** — which would serve as:

1. The formal foundation for the DDF framework
2. A new architecture for AI systems that generalize by concept rather than by pattern
3. A unifying theory connecting Objectivist epistemology to existing formal mathematics
4. The theoretical basis for the OPE project's concept store (FlameEvent infrastructure)

---

## Core Motivation: What Algebra Actually Is

Algebra works because variables stand for *any* value in a domain — an algebraic statement is true for all instances of the variable simultaneously, not just specific observed ones. You derive `x + y = y + x` once; it holds for all numbers.

Rand's claim is that concepts have the same structure:
- A concept stands for *any* instance in its class
- A principle stated over concepts holds for all instances
- The specific instances are the "numbers"; the concept is the "variable"; measurement omission is the abstraction step that moves from numbers to variables

Formalizing this means writing down the rules precisely enough to compute with them.

---

## The Formal Objects

### Definition 1: A Concept

A concept **K** is a triple **(C, M, ∅)** where:

- **C** — the CCD (Conceptual Common Denominator): the retained characteristic, the axis all instances share
- **M** — the measurement space: the valid range of variation along C (the domain of the variable)
- **∅** — omitted measurements: the specific values deliberately dropped by measurement omission

A particular **p** is an *instance* of K (written **p : K**) if and only if p possesses characteristic C at some measurement m ∈ M.

**Reading:** K = (C, M, ∅) means "the concept of anything that has characteristic C at any measurement within M, regardless of its specific measurement."

---

### Definition 2: Concept Formation (Measurement Omission)

Given a set of particulars {p₁, p₂, ..., pₙ} each possessing characteristic C at measurement mᵢ:

> **Form({p₁...pₙ}) = K = (C, range(m₁...mₙ), ∅)**

The specific measurements mᵢ are dropped (∅). The range is retained as the valid scope. The axis C is retained as the defining characteristic.

This is the formal statement of measurement omission: retain the axis, allow the range as the variable's domain, omit the specific values.

**Validity condition (Flood Criterion):** A concept K is valid only if it can generate instances on demand — given K, one can produce diverse particular pᵢ : K that were not in the original formation set. A concept that cannot pass the Flood test is a floating abstraction: the word exists, the CCD does not.

---

### Definition 3: A Principle

A principle is a universally quantified statement over a concept:

> **∀x : K . R(x)**

where R is a causal or structural relation. The principle holds for any instance of K — not just the observed ones. This is why principles generalize: they are stated over the variable (the concept), not the values (the particulars).

**Example:** "Irreversible actions require human confirmation" is formally:
∀x : IrreversibleAction . requires_confirmation(x)

Any new action that is an instance of IrreversibleAction — regardless of surface form — falls under this principle. The key is whether the new action's axis falls within the concept's CCD.

---

### Definition 4: Genus-Species Relation

Concept K is a *species* of genus G (written **K ⊆ G**) if and only if:
1. K's CCD is a specification of G's CCD (C_K is a restriction of C_G)
2. K's measurement space is a subspace of G's (M_K ⊆ M_G)
3. Every instance of K is an instance of G (∀p : K . p : G)

The genus-species hierarchy is not conventional or arbitrary — it is determined by CCD subsumption. This makes the hierarchy objectively derivable from the concept definitions.

**Proximal genus:** The proximal genus of K is the smallest G such that K ⊆ G. Finding the proximal genus algorithmically is a core CTT operation ("get the genus").

---

### Definition 5: Floating Abstraction

A concept K is a floating abstraction if:
1. K lacks traceable formation history (no particular pᵢ from which it was formed), OR
2. K fails the Flood Criterion (cannot generate instances on demand), OR
3. K's CCD is incoherent (C is not a genuine measurable axis)

Floating abstractions are formally invalid. Principles stated over floating abstractions do not generalize — they appear to hold but are not grounded in any real measurement axis.

---

### Definition 6: Conceptual Common Denominator (CCD) Coherence

A characteristic C is a valid CCD for a set of particulars {p₁...pₙ} if and only if:
1. Every pᵢ possesses C (universality)
2. The pᵢ possess C in different magnitudes (variation — otherwise C is a logical universal, not a CCD)
3. The magnitudes form a coherent measurement space M with a definite ordering or metric (commensurability)

This prevents spurious CCDs — you cannot group a laptop and the concept of justice under "things that exist" as a meaningful CCD, because existence is not a measurable axis with variation.

---

## What Existing Mathematics Contains

Three formal systems already contain pieces of CTT. The synthesis has not been done.

### Type Theory
A concept is a type; a particular is a term inhabiting the type; measurement omission is abstraction from terms to types. **Dependent type theory** gets closest — the type can depend on measurement values. But standard type theory lacks:
- The Flood Criterion (no requirement that a type be demonstrably productive)
- The Spiral structure (types don't deepen over time)
- The Floating Abstraction criterion (no grounding requirement)

### Category Theory
Concepts are objects; concept formation is a functor from the category of particulars to the category of abstractions; the CCD is the functor's defining structure; the genus-species hierarchy is a natural transformation. But category theory lacks:
- Measurement spaces as first-class objects
- Empirical grounding requirements
- Temporal dynamics of concept deepening

### Measurement Theory (Krantz et al.)
Already formalizes what it means for things to share a measurable axis with valid comparisons — representational, ordinal, interval, and ratio scales. This is the formal treatment of CCDs as measurable axes. But measurement theory lacks:
- The concept formation operation
- The genus-species hierarchy
- The principle generalization mechanism

### What CTT Adds to All Three
1. **The Flood Criterion** — empirical constraint on formal objects: a concept must be demonstrably productive
2. **The Spiral Structure** — temporal dynamics: concept K at time t₁ is less determinate than K at t₂ after more instances are integrated
3. **The Floating Abstraction Criterion** — grounding requirement: every concept must be traceable to observed particulars
4. **Measurement spaces as type parameters** — the range of variation is part of the type definition, not a separate concern

---

## CTT Operations and Their Algorithms

### Op-1: Concept Formation
**Input:** Set of particulars {p₁...pₙ} with observed axis C and measurements {m₁...mₙ}
**Output:** Concept K = (C, range(m₁...mₙ), ∅)
**Validation:** Flood test — can K generate pₙ₊₁, pₙ₊₂ outside the formation set?

### Op-2: Genus Computation
**Input:** Concept K = (C_K, M_K, ∅)
**Output:** Proximal genus G = (C_G, M_G, ∅) such that C_K restricts C_G and M_K ⊆ M_G, with G minimal
**Use:** Organizing concepts into valid hierarchies; finding the right "ballpark"

### Op-3: Category Error Detection
**Input:** Two concepts K₁ = (C₁, M₁, ∅) and K₂ = (C₂, M₂, ∅)
**Output:** VALID if C₁ and C₂ have a common superaxis; ERROR if no shared measurement axis exists
**Use:** Detecting Big Divides — preventing subsumption of incommensurable concepts under a common genus

### Op-4: Contextual Transfusion Validation
**Input:** Source concept K_A from domain A, target concept K_B from domain B
**Output:** VALID if there exists a structural isomorphism φ: (C_A, M_A) → (C_B, M_B); INVALID otherwise
**Bidirectionality check:** φ must enrich both domains — applying the analogy must make source domain clearer too
**Use:** Validating cross-domain analogies; detecting galaxy-brained category errors with style

### Op-5: CCD-Level Constraint Matching
**Input:** New situation S with candidate axis C_S, constraint store with concepts K₁...Kₙ
**Output:** Matching constraints: all Kᵢ where C_S is an instance of C_Kᵢ (not text match — structural match)
**Use:** Replacing text-based constraint detection with axis-based detection; the formal solution to amnesia

### Op-6: Floating Abstraction Detection
**Input:** Concept K = (C, M, ∅)
**Output:** GROUNDED if K passes all three criteria (formation trace, Flood test, coherent CCD); FLOATING otherwise
**Use:** Quality gate on the concept store; preventing floating abstraction inflation

### Op-7: Concept Deepening (Spiral Integration)
**Input:** Existing concept K = (C, M_t₁, ∅) at time t₁, new instance set {pₙ₊₁...pₙ₊ₖ}
**Output:** Enriched concept K' = (C, M_t₂, ∅) where M_t₂ ⊇ M_t₁
**Property:** Earlier understanding is enriched, not invalidated (Spiral Theory's non-destructive development)
**Use:** Tracking how concepts deepen across sessions; detecting ascending spirals in the constraint store

### Op-8: Top-Down Tension (Bridge-Warden Validation)
*Added: 2026-02-21 — derived from Binswanger's Suspension Bridge analogy, Chapter 6*

**Input:** Principle P = ∀x : K . R(x) stated over concept K
**Output:** LOAD-BEARING if P satisfies all three criteria; FLOATING CABLE otherwise
**Criteria:**
1. **Elimination:** P removes at least one class of instances that would otherwise be valid members of K — it constrains the membership, it does not merely describe it
2. **Integration:** P connects previously independent instances of K under a common structural requirement — it creates tension between elements, not just a label above them
3. **Independence:** Violations of P are detectable by examining instances directly, without reference to P's wording — the constraint is real, not definitional

**Why this matters:** A principle that fails Op-8 is a floating cable — it appears to be a main cable but bears no structural load. The entire span below it remains unsupported. In code: "every function must be idempotent" passes Op-8 if you can test idempotency without knowing the rule. "Every function should be clean" fails Op-8 — "clean" has no instance-level test independent of the stated preference.

**Connection to DDF Signal B (Main Cable):** Every Main Cable detection event should trigger Op-8. Signal B fires when a principle is stated that appears to hold up many concretes. Op-8 validates that the cable is actually bearing load.

**Connection to amnesia detection:** A constraint that fails Op-8 will reliably produce amnesia — it cannot fire in novel situations because it has no instance-level test. The constraint is a floating abstraction pretending to be a principle.

**Use:** Quality gate for principles entering the concept store; automated detection of floating cables in constraint history; Phase 17 StructuralIntegrityScore computation

---

## The DDF as the Empirical Layer of CTT

Every DDF marker is an observable event in a CTT derivation sequence:

| DDF Level | CTT Operation | What Is Being Observed |
|---|---|---|
| Level 1 — Algebra of Prompt | Variable introduction | Specific m replaced by variable over M |
| Level 2 — CCD/Axis Shift | Op-1: Concept Formation | Form({p₁...pₙ}) = K executed |
| Level 3 — Causal Isolation | Op-2: Genus Computation | Proximal genus G identified |
| Level 4 — Prose Principle Lag | Implicit Op-1 before registration | Concept used before formally named |
| Level 5 — Premise Check Pivot | Contradiction detected | Two concepts found to have incompatible CCDs |
| Level 6 — Concretization Flood | Flood Criterion validated | K → {p₁...pₙ₊ₖ} with k ≥ threshold |
| Level 7 — Spiral Phase Consciousness | C identified, M undetermined | Concept-in-formation: Op-1 incomplete |

The **DDF is the empirical observation layer for CTT derivations**. The FlameEvent store is the empirical record of CTT operations performed by human minds in real sessions.

This gives the research program two mutually validating components:
- **CTT** provides the formal theory that explains why the DDF markers are what they are
- **DDF/FlameEvent data** provides the empirical grounding that calibrates CTT's parameters (flood threshold, formation set minimum, measurement space coherence criteria)

---

## The Architectural Implication: A New AI Architecture

The most radical consequence of CTT formalization is a new AI architecture distinct from current language models.

**Current AI:** Implicit knowledge in weights. Learns statistical patterns over tokens (magnitude learning). Generalizes by interpolation within the training distribution.

**CTT AI:** Explicit concept objects in a concept store. Learns concept structures — (C, M, ∅) triples with scope rules and validation evidence. Generalizes by concept algebra: a new situation is handled by computing its CCD, matching against the concept store, and applying principles stated over matching concepts.

**Why this generalizes better:** A language model trained on 1,000 examples of irreversible actions learns to recognize surface features of those examples. A CTT system with one principle (∀x : IrreversibleAction . requires_confirmation(x)) handles any new instance correctly as long as it correctly identifies x as an IrreversibleAction — which requires only CCD matching, not surface-pattern matching.

**The alignment connection:** RLHF trains on human preference judgments (magnitudes). Fails to generalize to novel situations with different surface features. CTT alignment trains on CCDs extracted from human corrections — the concept that generated the preference, not the preference itself. Generalizes by axis identity, not surface similarity. This is the formal solution to the alignment generalization problem.

---

## Connection to the OPE Project

The OPE project is the empirical apparatus that the CTT research program needs:

| OPE Component | CTT Role |
|---|---|
| FlameEvent store | Record of CTT operations detected in real sessions |
| Constraint `epistemological_origin` | Distinguishes reactive (magnitude) from principled (CCD) constraints |
| Concretization Flood detection | Empirical validation of the Flood Criterion threshold |
| Generalization Radius metric | Empirical measurement of concept deepening (Op-7) |
| AmnesiaDetector | Detects failures of CCD-level constraint matching (Op-5) |
| WisdomStore | Concept store: repository of validated (C, M, ∅) triples |
| GenusValidator | Partial implementation of CTT validation operations |

The OPE project is building the empirical validation apparatus without yet having the formal theory. CTT formalization would give the OPE project:
- A precise specification for what the FlameEvent store should contain
- Formal definitions for what counts as a valid concept (replacing heuristic thresholds)
- A formal deduplication criterion for constraints (CCD identity vs. text similarity)
- A formal amnesia criterion (CCD-level honoring vs. text-match honoring)

---

## Research Phases

### Phase 1: Core Formalism (Theory)
**Goal:** Develop CTT as a complete formal system — syntax, semantics, inference rules
**Deliverables:**
- CTT axioms: concept formation, Flood Criterion, genus-species, floating abstraction
- Proof of basic theorems: concept uniqueness under CCD identity, genus decidability, category error completeness
- Formal comparison to type theory, category theory, measurement theory
- A paper: "Conceptual Type Theory: Formalizing the Algebra of Cognition"

**Key open questions for Phase 1:**
- Is the Flood Criterion decidable in general? (Can a machine always determine if a concept is productive?)
- What is the right formal treatment of M (measurement space) — ordinal? interval? ratio? context-dependent?
- How is the Spiral structure (concept deepening over time) formalized — as indexed types? as a temporal modality?

---

### Phase 2: Computational Implementation
**Goal:** Implement CTT as a working system
**Deliverables:**
- CTT checker: validates proposed concept triples
- Genus computation algorithm: Op-2 implemented and tested
- Category error detector: Op-3 implemented
- CCD-level constraint matcher: Op-5 — replaces text-based constraint detection in OPE
- Floating abstraction detector: Op-6 — quality gate for the concept store

**Integration point:** Wire CTT checker into OPE's GenusValidator as a new validation layer. First empirical test: does CCD-level constraint matching reduce amnesia events compared to text-based matching?

---

### Phase 3: Empirical Grounding and Calibration
**Goal:** Ground CTT parameters in real FlameEvent data
**Deliverables:**
- Flood threshold calibration: what minimum k constitutes a valid Flood? (Empirical from session data)
- Formation set minimum: how many instances are required for valid concept formation?
- Measurement space coherence criteria: what makes M well-defined vs. incoherent?
- IntelligenceProfile as CTT operation frequency record: which operations does a given person perform habitually?
- Validation study: compare CTT-based amnesia detection to text-based; measure false positive/negative rates

---

### Phase 4: CTT-Based AI Architecture
**Goal:** Prototype an AI system with explicit concept store rather than implicit weights
**Deliverables:**
- Concept store architecture: (C, M, ∅) as first-class data structures
- CCD-matching inference engine: replaces token prediction with concept algebra
- Flood-validated learning: new knowledge only committed to concept store after passing Flood Criterion
- Comparison study: CTT AI vs. RAG baseline on out-of-distribution generalization tasks

---

## Open Research Questions

**OQ-CTT-01 — Decidability of the Flood Criterion**
Is there an algorithm that, given a concept triple (C, M, ∅), determines in finite time whether the concept is productive (can generate instances)? Or is this undecidable in general (requiring human judgment)?

**OQ-CTT-02 — Measurement Space Formalization**
What is the right formal treatment of M? Real-valued? Ordinal? Qualitative? Context-dependent? The answer affects what "commensurability" means and what CCDs are valid.

**OQ-CTT-03 — The Temporal Dimension**
How is concept deepening formalized? Options: indexed type theory (K_t₁ ⊆ K_t₂), temporal modal logic, or a special "spiral operator" that describes the enrichment process.

**OQ-CTT-04 — Automatic CCD Extraction**
Given a text description of a situation, can a system extract the candidate CCD without human labeling? This is required for CTT to scale beyond human-in-the-loop annotation.

**OQ-CTT-05 — CTT and Gödel**
Does CTT face incompleteness? Can there be true conceptual statements (valid principles) that CTT cannot prove from its axioms? What are the limits of formal concept validation?

**OQ-CTT-06 — The Alignment Theorem**
Can it be formally proved that CCD-level constraint specification is more robust to distribution shift than magnitude-level specification (RLHF)? What are the formal conditions under which this holds?

---

## Why This Has Not Been Done Before

The people who know Rand's epistemology have not known category theory and type theory. The people who know type theory have not read Rand. The empirical validation apparatus (the DDF FlameEvent store) did not exist before the OPE project.

Three conditions now exist simultaneously for the first time:
1. The formal mathematical tools (type theory, category theory, measurement theory) are mature
2. The philosophical theory (Objectivist epistemology) is fully developed with 60 years of explication
3. The empirical validation apparatus (OPE pipeline + DDF FlameEvent store) is being built

The synthesis is overdue.

---

## Update Log

| Date | Update |
|------|--------|
| 2026-02-21 | Research specification initiated. Core formal objects defined (concept triple, measurement omission, Flood Criterion, genus-species). CTT operations enumerated. DDF-CTT correspondence table established. OPE integration points identified. Four research phases scoped. |
