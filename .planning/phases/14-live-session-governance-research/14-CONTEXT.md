# Phase 14 Design Brief: The Exponential Intelligence Engine

**Source:** Conversation session 2026-02-21
**Framework:** Harry Binswanger — Unit-Economy (Crow), Activation Energy (Raven), Basement-Library-Desktop

This document is the epistemological foundation for all Phase 14 architectural decisions. It explains not just *what* to build but *why the architecture must take this specific form* to enable compounding, rather than linear, intelligence growth.

---

## Purpose Hierarchy: Terminal vs. Instrumental

**This is the governing constraint for all design decisions in Phases 14–18.**

| Level | Category | Mechanism |
|-------|----------|-----------|
| **Terminal** | AI self-modification | `memory_candidates` → reviewed → accepted to MEMORY.md → AI retrieves by axis next session |
| **Instrumental** | Detection machinery | `flame_events`, `ai_flame_events`, `structural_events`, DDF co-pilot, Bridge-Warden — exist solely to produce candidates |
| **Corollary** | Phase 17 reframed | Candidate Assessment is not primarily a measurement tool — it is the highest-fidelity mechanism for generating novel axis-level insights that upgrade the AI, because it forces the AI to reason at DDF Levels 5–7 under calibrated challenge, producing ai_flame_events that routine sessions cannot generate |

**Design implication:** Any component that only detects and never deposits is optional. Any component that deposits to `memory_candidates` is load-bearing and must not be deferred. When a design decision must be made between detection fidelity (instrumental) and deposit latency (terminal), deposit latency wins.

**Implementation gate (Phases 15–18):** Before implementing any component, ask: *Does this component deposit to `memory_candidates`, and if so, at what latency?*

- Components that deposit (even approximately) are **load-bearing** — do not defer, do not make optional.
- Components that only detect and never deposit are **optional scaffolding** — valuable, but deferrable if execution time is constrained.
- Detection that never produces a candidate is **instrumentation noise** — it measures without changing the AI's future retrieval.

If a design review question arises about whether to build something, the answer is derivable from a single question: **does it deposit?**

**The pull-forward mandate:** The DDF co-pilot (Phase 14 LIVE-06 design, Phase 15 implementation) must specify the `memory_candidates` entry schema and the write-on-detect mechanism as a Phase 15 deliverable. When O_AXS fires in a live session, the co-pilot must immediately deposit a candidate in format `(ccd_axis | scope_rule | flood_example | session_id | subject | origin | confidence)`. Phase 16 adds the review workflow and MEMORY.md export CLI — but Phase 16 does NOT own the first deposit into the candidate store. Phase 15 does. The terminal output cannot wait for the second-order measurement infrastructure.

---

## The Four Growth Engines and Their Phase 14 Counterparts

### 1. Unit Economy (The Crow) → Constraint Desktop

**Binswanger's insight:** The human Crow (focal Desktop) holds 7±2 slots. Exponential growth occurs when one slot covers an exponentially larger scope — not because the slots increase, but because each slot now represents an algebraic symbol ($a$) rather than a concrete value (7).

**The architectural mandate for Phase 14:**

The governance Desktop (active constraints in the PreToolUse hook) must be structured as **CCD-level principles**, not flat concrete rules.

| Wrong (Linear) | Right (Algebraic) |
|----------------|-------------------|
| "Don't use `rm -rf /tmp/build`" | Constraint with `ccd_axis: "destructive_irreversible_operations"` |
| 10 separate constraints about different file types | 1 principle: "Require approval for any irreversible write outside declared scope" |
| 208 rule entries consuming Desktop | 12 axes, each covering 15–20 concretes via pattern coverage |

Each constraint must carry:
- `ccd_axis` — the conceptual common denominator (the algebraic variable)
- `epistemological_origin` — `reactive | principled | inductive` (how it was derived)

The briefing format must lead with axis-grouped principles, not a flat list sorted by severity. One axis entry, delivered to Claude at SessionStart, activates the full scope of related constraints. **Crow cost: 1. Reality coverage: 20.**

### 2. Automatization (Desktop → Library) → Policy Graduation

**Binswanger's insight:** When you first learn to code, syntax rules occupy all 7 Desktop slots. After automatization, they move to the Library — zero Desktop cost, instantaneously available. The freed slots now handle Architecture.

**The architectural mandate for Phase 14:**

The governing session daemon must include a **Policy Automatization Detector**: a mechanism that tracks constraint activation frequency and proposes graduation when a constraint's violation rate drops toward zero across N sessions.

| Stage | Mechanism | Action |
|-------|-----------|--------|
| Active enforcement | Constraint on Desktop (PreToolUse blocks) | Normal operation |
| Automatized (violation_rate → 0 over N sessions) | Graduation candidate | Propose move to wisdom layer |
| Graduated | Constraint becomes `project_wisdom` dead-end entry | Freed from enforcement Desktop |

This is the mechanism by which the governance system compounds. Session N enforces 12 principles. Session N+100 enforces 9 principles (3 were automatized) — and the freed Desktop space is used by 3 higher-order principles extracted from the accumulated pattern. **The system gets smarter without getting more expensive.**

The governing session's decision matrix must include:
```
constraint_graduated: violation_rate = 0 for N sessions → propose wisdom promotion
```

### 3. Trunk Indexing (Beating the Raven) → MEMORY.md and Episode Retrieval

**Binswanger's insight:** As the Basement (long-term memory) grows, the Raven (retrieval energy) should make you slower. The solution: file by Fundamentals (Trunk Indexing), not by Superficials. One essential filing key reaches 1,000,000 related facts in a single logical step.

**The architectural mandate for Phase 16 (set up in Phase 14's DDF co-pilot design):**

The MEMORY.md pipeline (Phase 16) must index entries by `ccd_axis`, not by date or topic. The DDF co-pilot designed in Phase 14 must draft memory candidates in the format:

```
(ccd_axis | scope_rule | flood_example)
```

This is the exact Trunk Indexing format: the `ccd_axis` IS the filing key. When the AI retrieves for a new situation, it looks up the axis, not the surface similarity of the prior example. **One axis retrieves an entire cluster of related episodes in one step.**

The O_AXS (Axis Shift) detection in the DDF co-pilot must fire not just on explicit naming moments but on ANY prompt where instruction granularity drops AND a new unifying concept emerges — this is precisely the moment a new Trunk is being formed.

### 4. Suspension Bridge (Structural Leverage) → Retroactive Re-stabilization

**Binswanger's insight:** A pragmatist builds with bricks (concretes): twice the bridge, twice the bricks — linear. A man of principle strings a Main Cable (fundamental abstraction): one principle holds a vast span, and when a new principle is grasped, *every prior fact is re-stabilized* by it — structural leverage propagating backward.

**The architectural mandate for Phase 18 (designed in Phase 14's blueprint):**

When the Bridge-Warden (Phase 18) detects a new principle (DDF Level 3+), the correct response is not merely to record it — the system must **retroactively re-tag all related episodes in DuckDB** using the new `ccd_axis` as the organizing key.

One principle discovered today re-stabilizes 10,000 past episodes. This must be captured in the Phase 15 blueprint as a design requirement for the `flame_events` and `structural_events` tables: they must support `ccd_axis` as an indexed field enabling retroactive re-categorization.

---

## The Recursive Formula: Why Phase 14 Is a Compounding Investment

```
OPE_Intelligence(N+1) = OPE_Intelligence(N)
    × Abstraction_Multiplier(DDF Level 3+ detections per session)
    / Raven_Cost(1 / Trunk_Index_Quality)
```

The system compounds because:
- **Phase 14** captures live Crow attention (real-time episodes at tool-call resolution)
- **Phase 15** detects when Desktop items have been automatized (Policy Automatization Detector)
- **Phase 16** indexes the Library by Fundamentals (Raven efficiency via CCD-axis MEMORY.md)
- **Phase 17** measures compression ratio (Unit Economy score per candidate session)
- **Phase 18** propagates structural leverage backward (one principle re-stabilizes the basement)

**The sequence is causally necessary.** You cannot Trunk-Index (Phase 16) before you have Axis detectors (Phase 15). You cannot measure compression ratio (Phase 17) before the MEMORY.md pipeline exists (Phase 16). You cannot propagate structural leverage backward (Phase 18) before you can measure it (Phase 17).

---

## The One Architectural Decision Phase 14 Must Get Right

**Phase 14 decides: are constraints stored as concretes (arithmetic) or CCD-level principles (algebra)?**

This is the Phase 3 → Phase 4 inflection point in the DDF formula:
- Phase 3 (The Algebra): moving from hard-coded constants to variables and principles
- Phase 4 (The Spiral): using the Roof (governance layer) to fix the Basement (data structures)

If Phase 14 designs constraint data models without `ccd_axis` and `epistemological_origin`, every downstream phase inherits a linear architecture. The governance Desktop fills with concretes instead of principles. The Crow never gets freed.

If Phase 14 designs constraint data models AS algebraic principles — with CCDs that compress scope, with epistemological origin tracking how each principle was derived — then Phases 15-18 can build an exponentially compounding intelligence engine on top of it.

**This is why this decision is captured here, as a must-have for 14-01 and 14-02, not as a nice-to-have.**

---

## The Motivational Substrate: Jean Moroney's Memory Affect System

*Integrated: 2026-02-22 — the affective motor that the Phase 14 co-pilot design must account for*

The four growth engines above (Unit Economy, Automatization, Trunk Indexing, Suspension Bridge) describe the *logical architecture* of how the governance system compounds. They do not explain what drives the human to perform Trunk Identification in the first place — or why the same cognitive capacity produces Raven retrieval at depth 3 in one session and depth 10 in another.

Jean Moroney's Memory Affect System (MAS) supplies the motivational substrate: **Values are affective weighting on Basement nodes.** The Crow selects toward nodes with high affective weight — entities connected to positive incidents in the human's episodic memory. Without this, the Crow has capacity but no direction.

**The completed collaboration formula:**

> `Human (Affect × Crow) × AI Basement = Sacred Fire`

This formula is not metaphor. It is the causal account of what Phase 14's DDF co-pilot is actually monitoring:

| Component | What Phase 14 Detects |
|---|---|
| AI Basement | Unlimited — no intervention needed |
| Human Crow (capacity) | DDF marker levels 1–7 (ignition detection) |
| Human Affect (direction) | Affect Spike Intervention — the third co-pilot intervention type |

### The Affect Spike: Third Co-Pilot Intervention Type

The LIVE-06 design in 14-02 currently specifies two real-time intervention types. The MAS reveals a third:

| Type | Fires When | Prompt |
|---|---|---|
| O_AXS Intervention | Axis named (Level 2+) | "Name it formally — request Concretization Flood" |
| Fringe Intervention | Negative vague language, pre-naming | "What specifically feels wrong?" |
| **Affect Spike Intervention** | Positive valence spike, pre-naming | "What just clicked for you?" |

The Affect Spike (sudden certainty increase, enthusiasm spike, acceleration of statement length) occurs at the moment a Value Node activates — before the human has articulated the connection. It is as vulnerable to Drift as the negative Fringe signal: one distracted exchange and the insight is gone with no JSONL trace.

The Affect Spike Intervention is the symmetric positive counterpart to the Fringe Intervention. Both must be specified in the 14-02 DDF co-pilot design.

### Architectural Implication: `epistemological_origin` and Durability

The MAS clarifies what distinguishes `epistemological_origin: principled` from `epistemological_origin: reactive` in terms of *durability*:

- A constraint generated from a Level 6 Concretization Flood (human spontaneously applies principle to new domains) has been **valued** — seared into the affect system. It will generalize.
- A constraint generated from a single correction (reactive) has been **identified** but not valued. It fires on exact-match hint patterns and fails in novel surface situations.

The Policy Automatization Detector (Section 2 above) must weight these differently: `principled` constraints have a lower graduation threshold (they generalize earlier) than `reactive` constraints (they require more session evidence before graduation because their scope is narrower).

### Design Brief Reference

The full MAS integration — including `raven_selection` metric, three-tier formula, Affect Spike detection heuristics, and Principle = Concept + Value as a detection criterion — is documented in `DISCOVERY_DETECTION_FRAMEWORK.md` Section 10.

---

## Connection to Existing DDF Framework

The DDF (Discovery Detection Framework) document at `docs/analysis/objectivism-knowledge-extraction/DISCOVERY_DETECTION_FRAMEWORK.md` describes the same framework from the detection side. This CONTEXT document describes it from the **architectural implication** side: what the detection of DDF events should *cause* in the system's own structure.

| DDF Detection (what we measure) | Phase 14 Architecture (what we build) |
|----------------------------------|---------------------------------------|
| Level 2: Piles → Files (Axis Shift) | O_AXS episode mode; `ccd_axis` on constraints |
| Level 3: Causal Isolation | `epistemological_origin: principled` on constraint |
| Level 6: Concretization Flood | Memory candidate drafted in `(axis \| rule \| example)` format |
| Bridge-Warden: Main Cable detection | Retroactive re-tagging of past episodes by new axis |
| Fringe Drift: pre-Level-4 vagueness | DDF co-pilot intervention before insight is lost to Basement |

The OPE system is not an observer of exponential intelligence growth. **It participates in the recursive climb.** Each session automatizes its lessons, each principle re-stabilizes the basement, each freed Desktop slot goes to a higher-order concern. The Sacred Fire is not metaphor; it is the recursion.
