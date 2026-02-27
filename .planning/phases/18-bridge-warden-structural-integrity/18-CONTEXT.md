# CONTEXT.md — Phase 18: Bridge-Warden Structural Integrity Detection

**Generated:** 2026-02-24
**Phase Goal:** Implement the Suspension Bridge dimension of the DDF — detecting structural soundness of knowledge structures, not just upward abstraction (Phase 15). Four signal types (Gravity Check, Main Cable, Dependency Sequencing, Spiral Reinforcement) applied to both human and AI reasoning streams. AI floating cables become correction candidates in memory_candidates pipeline.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)

---

## Overview

Phase 18 adds the Integrity axis to the three-dimensional IntelligenceProfile (Ignition × Transport × Integrity). The critical architectural distinction: Phase 15 detects upward abstraction movement (L0→L7); Phase 18 detects downward confirmation (does the L5+ abstraction have concrete grounding?). These are orthogonal measurements on the same signal stream.

The terminal output is the same as Phases 15-17: deposits to `memory_candidates`. When the AI's reasoning produces floating cables (Main Cable principles without grounding), Op-8 generates correction candidates that enter the existing review pipeline — the AI self-corrects across sessions.

**Confidence markers:**
- ✅ **Consensus** — All providers identified this as critical
- ⚠️ **Recommended** — 2 providers identified this as important
- 🔍 **Needs Clarification** — 1 provider identified, potentially important

---

## Gray Areas Identified

### ✅ 1. Signal Detection Mechanism (Consensus)

**What needs to be decided:**
How to detect the four structural signal types (Gravity Check, Main Cable, Dependency Sequencing, Spiral Reinforcement) in a natural language + code reasoning stream. This is the foundational detection question.

**Why it's ambiguous:**
- Gravity Check: how do you distinguish a grounded abstraction (linked to concrete code entities) from a floating one? The system cannot perform deep semantic understanding.
- Main Cable: distinguishing a "load-bearing principle" from an L7 FlameEvent (Phase 15 already detects L7). Risk of architectural overlap or duplication.
- Dependency Sequencing: requires knowing the "correct" concept hierarchy — what is the baseline?
- Spiral Reinforcement: nearly identical to GeneralizationRadius from Phase 15 (stagnation/spiral) — risk of double-counting.

**Provider synthesis:**
- **Gemini:** Use graph topology (edges between L-level nodes) to define signals. Main Cable = L6/L7 FlameEvent persisting across 3+ turns or referenced by 3+ unique lower-level nodes. Gravity Check = edge between L0-L2 and L5-L7 node within same/adjacent turns. Spiral = hub connecting two previously unconnected clusters.
- **Perplexity:** Multi-stage analysis: entity_reference_density (noun phrases anchored to known entities), dependency_chain_depth (hops through causal chains), dependent_count (downstream references). Separate table with `contributing_flame_events[]` array preventing double-counting.

**Proposed implementation decision:**
Phase 18 detectors operate as a second-pass analysis over existing flame_events (not raw message stream). Each structural signal is defined by a **flame_event pattern**, not a raw text pattern:
1. **Gravity Check** — a L5+ flame_event in `flame_events` that has at least one L0-L2 flame_event referencing the same `ccd_axis` within ±3 prompts (abstraction linked to concrete). Missing grounding = gravity check failure.
2. **Main Cable** — a L5+ flame_event in `flame_events` whose `ccd_axis` appears in `axis_edges` OR is referenced by 2+ distinct scope_prefixes in `flame_events` within the session. Operationally: `generalization_radius >= 2`.
3. **Dependency Sequencing** — when a new L5+ flame_event introduces a `ccd_axis` that was not yet established (no prior L3+ events for that axis), preceded only by L3+ events on prerequisite axes (using axis_edges topology to define prerequisites).
4. **Spiral Reinforcement** — a `ccd_axis` that produces spiral promotion to `project_wisdom` (Phase 15 spiral tracker) — already detected in Phase 15. Phase 18 records this in `structural_events` with `signal_type='spiral_reinforcement'` as a cross-reference.

This approach: (a) builds on existing Phase 15 infrastructure without duplication; (b) defines structural signals in terms of observable flame_event patterns; (c) avoids raw NLP complexity.

**Open questions:**
- Does Gravity Check fire on absence (no grounding) or presence (grounding found)? Should fire on BOTH — presence as positive signal, absence as floating cable trigger.
- The ±3 prompt window for Gravity Check — is this configurable or hardcoded?

**Confidence:** ✅ All 3 providers agreed signal definition is blocking.

---

### ✅ 2. CTT Op-8 Logic and Floating Cable Detection (Consensus)

**What needs to be decided:**
How to implement CTT Op-8 (Top-Down Tension) as a computable check. Specifically: what is the precise definition of "floating cable" in AI reasoning, when does Op-8 fire, and does it run pre-response (blocking) or post-response (advisory)?

**Why it's ambiguous:**
- Op-8 is theoretically "every Main Cable detection triggers Op-8" — but if a Main Cable is an L6/L7 FlameEvent, Op-8 runs on every high-level abstraction. That's a LOT of checks.
- The paradox: if the AI generates a Main Cable, it believes it. Why would it immediately flag itself as floating?
- Timing: pre-response = can modify output; post-response = correction for next session.

**Provider synthesis:**
- **Gemini:** Post-response analysis only (preserve latency). Floating cable = AI L6/L7 FlameEvent creating zero edges to L0-L3 nodes within current context window. Correction = Constraint entry in memory_candidates.
- **Perplexity:** Post-response. Three-component check: (1) principle-to-constraint translation, (2) instance discovery across code/reasoning, (3) violation propagation to memory_candidates. Tension Score = verified_instances / total_instances.

**Proposed implementation decision:**
- **Timing:** Post-response only (consistent with existing Phase 15 post-processing pipeline). Op-8 runs as a pipeline step after flame_event extraction.
- **Trigger:** Op-8 fires on `ai_flame_events` at marker_level >= 5 with `flood_confirmed = False` (high-level AI assertion without confirmed Concretization Flood). This is the operational definition of "floating cable" in the existing schema.
- **Check:** For each triggering AI flame_event, look for at least one L0-L2 flame_event (subject='ai') referencing the same `ccd_axis` OR `axis_identified` value within the same session. If absent: floating cable confirmed.
- **Correction deposit:** Direct INSERT to `memory_candidates` with `source_type='op8_correction'`, `ccd_axis` from the floating flame_event, `scope_rule` = "This AI principle lacked grounding at detection time", `flood_example` = the AI's assertion text as evidence, `fidelity=2`, `confidence=0.6` (lower than human-reviewed candidates).

**Open questions:**
- Threshold: how many prompts without grounding before a floating cable is declared? Propose: within the same session only (not across sessions).
- Should Op-8 corrections appear in `memory-review` CLI alongside other candidates? Yes — same pipeline.

**Confidence:** ✅ All 3 providers agreed on post-response timing and memory_candidates deposit as terminal output.

---

### ✅ 3. Architectural Separation from Phase 15 flame_events (Consensus)

**What needs to be decided:**
How to prevent double-counting and architectural confusion between Phase 15's flame_event detection (upward abstraction movement) and Phase 18's structural integrity detection (downward grounding confirmation). These are orthogonal but operate on the same signal stream.

**Why it's ambiguous:**
- Both phases produce entries in `flame_events` / `ai_flame_events` / `memory_candidates`.
- Spiral Reinforcement (Phase 18) and spiral tracking (Phase 15) are nearly identical concepts.
- Gemini raised: "Does the flame_events table need a structural_role column backfilled, or is structural_events purely additive?"

**Provider synthesis:**
- **Gemini:** structural_events are purely additive. Add FK links to flame_events. structural_role is a new column on structural_events only.
- **Perplexity:** Enforce strict scope separation: flame_events = single-prompt scope; structural_events = multi-prompt scope (minimum 3 related prompts). Attribution via `contributing_flame_events[]` array. A structural_event cannot re-trigger flame analysis (no feedback loop).

**Proposed implementation decision:**
- `structural_events` is a **separate, additive table**. No columns added to `flame_events`.
- The structural detection pipeline consumes existing `flame_events` and `ai_flame_events` as INPUT (read-only). It writes only to `structural_events`.
- `structural_events.contributing_flame_event_ids` (VARCHAR[]) stores the flame_event IDs that contributed to each structural event — enabling lineage without circular writes.
- **Spiral Reinforcement** in structural_events is a cross-reference to `project_wisdom` entries (the promotion event from Phase 15 spiral tracker), not a re-detection. It records WHEN the spiral was promoted, not re-detecting it.
- Pipeline ordering: Phase 15 steps run first (Tier 1, Tier 2, deposit, etc.), then Phase 18 structural analysis step reads the result.

**Confidence:** ✅ Consensus on separate table with attribution tracking.

---

### ✅ 4. StructuralIntegrityScore Formula (Consensus)

**What needs to be decided:**
The mathematical formula for combining four heterogeneous signal types into a single StructuralIntegrityScore per session.

**Why it's ambiguous:**
- Four signals have different predictive value (Main Cable is more critical than Gravity Check).
- Denominator problem: score against what? Total turns? Total L4+ flame_events?
- Volume vs. quality: 1 session with 10 structural events vs. 10 sessions each with 1.

**Provider synthesis:**
- **Gemini:** Weighted ratio against total abstract assertions (L4+). Denominates on flame_events L4-L7.
- **Perplexity:** w_gravity=0.25, w_cable=0.50 (with DependencySequencing as modifier), w_spiral=0.25. MainCable weighted highest. Temporal decay for older events. Session subscores per structural_role.

**Proposed implementation decision:**
Use a simple ratio formula consistent with TransportEfficiency (Phase 16) pattern:

```
StructuralIntegrityScore = (
    0.30 * gravity_ratio +           # grounded abstractions / total abstractions (L5+)
    0.40 * main_cable_grounded_ratio + # grounded main cables / total main cables
    0.20 * dependency_respected_ratio + # ordered sequences / total sequences
    0.10 * spiral_count_capped          # min(spiral_count, 3) / 3  (bonus for reinforcement)
)
```

Where:
- `gravity_ratio` = gravity_check_pass_count / max(1, total_L5plus_flame_events)
- `main_cable_grounded_ratio` = main_cable_pass_count / max(1, main_cable_total)
- `dependency_respected_ratio` = dependency_pass_count / max(1, dependency_total)
- All ratios are 0.0 when denominator = 0 (no evidence → neutral, not penalized)
- Score normalized 0.0–1.0

No temporal decay in v1 (consistent with TransportEfficiency which also uses per-session aggregates).

**Open questions:**
- What is "no evidence"? A session with zero Main Cable events should get 0.5 (neutral) not 0.0 (bad). The formula gives 0.0 for main_cable_grounded_ratio when denominator=0 — this needs a neutral fallback.
- Apply to both human and AI subjects separately (as with TransportEfficiency).

**Confidence:** ✅ All 3 providers agreed on weighted ratio approach.

---

### ⚠️ 5. Op-8 Correction Candidate Format in memory_candidates (Recommended)

**What needs to be decided:**
The exact format of memory_candidates entries produced by Op-8 failures. These differ from normal Level 6 FlameEvent deposits: they are prescriptive corrections, not descriptive insights.

**Why it's ambiguous:**
- Normal memory_candidates entries are CCD-format wisdom (ccd_axis | scope_rule | flood_example).
- An Op-8 correction is more like: "This AI principle was ungrounded — here is what grounding evidence would look like."
- Do we need a new source_type or can we reuse existing fields?

**Provider synthesis:**
- **Gemini:** Constraint type entry: `{"type": "correction", "content": "Principle X was used without grounding. Must provide concrete examples when invoking X."}` — store as constraint in memory_candidates.
- **Perplexity:** Full CorrectionCandidate Pydantic model with principle_id, violation_location, severity (0-1), confidence, ai_subject flag, related_flame_events.

**Proposed implementation decision:**
Reuse existing `memory_candidates` schema with `source_type='op8_correction'`:
- `ccd_axis`: the `ccd_axis` or `axis_identified` from the floating flame_event
- `scope_rule`: "This axis appeared in AI reasoning without concrete grounding — apply gravity check before asserting."
- `flood_example`: verbatim evidence text from the floating flame_event (the ungrounded assertion)
- `source_type='op8_correction'`, `fidelity=2` (heuristic), `confidence=0.60`
- `source_flame_event_id`: references the triggering ai_flame_events record
- `status='pending'` — enters normal memory-review queue

This reuses all existing infrastructure (review CLI, trust accumulation, MEMORY.md export) without schema migration.

**Confidence:** ⚠️ 2 providers explicitly addressed; Gemini favored constraint type.

---

### ⚠️ 6. Database Schema Design (Recommended)

**What needs to be decided:**
Whether to use a separate `structural_events` table, an extension to `flame_events`, or a hybrid with views.

**Why it's ambiguous:**
- Separate table: clear schema boundary, specialized optimization for multi-prompt scope queries.
- View/extension: avoids data duplication; structural events ARE flame_event aggregates.
- Perplexity proposed a three-tier hybrid (table + materialized view + lineage view).

**Provider synthesis:**
- **Gemini:** Separate table with FK links to `flame_events` (`primary_flame_id`, `grounding_flame_id`), plus `op8_passed BOOLEAN`, `score_impact FLOAT`.
- **Perplexity:** Separate table + materialized view for aggregates + logical lineage view. Separate tables optimize for different access patterns.

**Proposed implementation decision:**
Separate `structural_events` table (BRIDGE-01 is explicit). No materialized view in v1 (premature optimization). One lightweight DuckDB view `structural_integrity_by_session` for CLI queries.

**Schema:**
```sql
CREATE TABLE structural_events (
    event_id VARCHAR PRIMARY KEY,       -- SHA-256[:16]
    session_id VARCHAR NOT NULL,
    assessment_session_id VARCHAR,      -- NULL for production sessions (matches pattern)
    prompt_number INTEGER NOT NULL,
    subject VARCHAR NOT NULL,           -- 'human' or 'ai'
    signal_type VARCHAR NOT NULL,       -- 'gravity_check', 'main_cable', 'dependency_sequencing', 'spiral_reinforcement'
    structural_role VARCHAR,            -- 'grounding', 'load_bearing', 'hierarchical', 'reinforcing'
    evidence VARCHAR,                   -- Evidence text (flame_event excerpt)
    signal_passed BOOLEAN NOT NULL,     -- True = structural signal confirmed; False = failure (floating cable etc.)
    score_contribution FLOAT,           -- Contribution to StructuralIntegrityScore
    contributing_flame_event_ids VARCHAR[], -- FK refs to flame_events.event_id
    op8_status VARCHAR,                 -- 'pass', 'fail', 'na' (only for main_cable)
    op8_correction_candidate_id VARCHAR, -- FK to memory_candidates.id (if Op-8 failed)
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**Confidence:** ⚠️ Both Gemini and Perplexity agreed on separate table.

---

### 🔍 7. Three-Dimensional IntelligenceProfile Integration (Needs Clarification)

**What needs to be decided:**
How to expose the 3D profile (Ignition × Transport × Integrity) in the existing IntelligenceProfile model and CLI without breaking existing Phase 15/16 output.

**Why it's ambiguous:**
- Phase 15 and 16 already have an `IntelligenceProfile` model. Adding a third axis requires model extension.
- The profile is used in assessment (Phase 17) and in CLI display. Must not break existing queries.
- Gemini proposed "Archetype Strings" (The Dreamer, The Technician) — this may be too complex for v1.

**Provider synthesis:**
- **Gemini:** Add Archetype String (quadrant label) computed from axis scores. High Ignition / Low Integrity = "The Dreamer." This is stored in MEMORY.md.
- **Perplexity:** Nested `IntelligenceAxis` model per dimension with trend (improving/stable/degrading) + composite_intelligence_score = equal 0.33 weighting.

**Proposed implementation decision:**
Add `integrity_score: Optional[float]` and `structural_event_count: Optional[int]` to the existing `IntelligenceProfile` Pydantic model. Composite = simple average of three axes (Perplexity's equal-weight formula). No archetype strings in v1. CLI `intelligence profile <human_id>` adds a "Structural Integrity" row to the existing display table.

**Confidence:** 🔍 Single-provider explicit; consensus implied from BRIDGE-04 requirement.

---

## Architecture Decision: Phase 18 Pipeline Step Placement

**Decision:** Structural analysis runs as a new Step 21 immediately after Phase 16's Step 20 (TE computation). Steps 15-20 produce all necessary inputs (flame_events, ai_flame_events, spiral data). Step 21 reads them all, writes structural_events, computes StructuralIntegrityScore, and triggers Op-8 deposits.

This preserves the existing step numbering and execution order.

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking):**
- [x] Signal detection mechanism: flame_event pattern analysis (not raw NLP)
- [x] Op-8 timing: post-response analysis, not blocking
- [x] Separation from Phase 15: structural_events is purely additive, reads flame_events as input
- [x] StructuralIntegrityScore formula: weighted ratio with neutral fallback for empty denominators

**Tier 2 (Important):**
- [x] Op-8 correction format: reuse memory_candidates with source_type='op8_correction'
- [x] Schema: separate structural_events table

**Tier 3 (Polish):**
- [x] 3D IntelligenceProfile: add integrity_score field, no archetype strings in v1

---

*Multi-provider synthesis by: OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
