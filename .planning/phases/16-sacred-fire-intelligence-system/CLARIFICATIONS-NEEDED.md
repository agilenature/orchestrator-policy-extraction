---
phase: 16
name: Sacred Fire Intelligence System
generated: 2026-02-24
mode: YOLO (auto-answered — see CLARIFICATIONS-ANSWERED.md)
---

# CLARIFICATIONS-NEEDED.md

## Phase 16: Sacred Fire Intelligence System — Stakeholder Decisions Required

**Generated:** 2026-02-24
**Mode:** Multi-provider synthesis (Gemini Pro + Perplexity Sonar Deep Research)
**Note:** YOLO mode active — questions are documented here for reference; auto-answers in CLARIFICATIONS-ANSWERED.md

---

## Decision Summary

**Total questions:** 7
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: TransportEfficiency Sub-Metric SQL Proxies

**Question:** What are the exact SQL-derivable proxies for `raven_depth`, `crow_efficiency`, `transport_speed`, and `trunk_quality` from the `flame_events`/`ai_flame_events` columns?

**Why it matters:** Without concrete definitions, Phase 16 cannot build the `transport_efficiency_sessions` table or the IntelligenceProfile extended view. The formula `TE = raven × crow × (1/speed) × trunk` only has meaning once each component maps to a specific DuckDB query.

**Available columns:** session_id, human_id, subject, marker_level (0-7), marker_type, axis_identified (str|null), flood_confirmed (bool), evidence (str), quality_score (float), prompt_number (int).

**Options:**

**A. Simple normalized proxies (one column each)**
- raven_depth = MAX(marker_level) / 7.0
- crow_efficiency = COUNT(*) FILTER (axis_identified IS NOT NULL) / COUNT(*)
- transport_speed = COUNT(*) FILTER (flood_confirmed = true) / COUNT(*)
- trunk_quality = COUNT(L0 flood_confirmed=true) / COUNT(L0)
- _(Proposed by: Gemini, synthesis reasoning)_
- Pros: Simple, auditable, always computable, no implicit assumptions
- Cons: Each collapses multiple signals into one indicator

**B. Multi-proxy composite (weighted combination per component)**
- raven_depth = weighted average of evidence_diversity, level_span/7, axis_density
- crow_efficiency = deliberate_connections / total_transitions
- transport_speed = confirmed_floods / session_duration (requires timestamp)
- trunk_quality = multi-layer validation score
- _(Proposed by: Perplexity)_
- Pros: More nuanced, aligns with academic construct validity
- Cons: Requires timestamps (not confirmed in current schema), more complex, harder to audit

**Synthesis recommendation:** ✅ **Option A — Simple normalized proxies**
- Rationale: Existing schema lacks explicit timestamps per event. Proxies must be derivable from marker_level, axis_identified, flood_confirmed. Simple is better for Phase 16 — the goal is a working trend line, not a perfectly calibrated psychometric instrument. Complexity can be added in Phase 18.

**Sub-questions:**
- Where should the computed values be stored? New `transport_efficiency_sessions` table or column on existing tables?
- Should the formula compute as a VIEW or materialized at pipeline run time?

---

### Q2: Trunk Quality Temporal Paradox

**Question:** `TransportEfficiency` formula includes `trunk_quality`, but trunk_quality can only be validated N sessions later. How do we compute TransportEfficiency for the current session?

**Why it matters:** If TransportEfficiency blocks on trunk_quality confirmation, it cannot be used for any session until N sessions have elapsed. If we use a placeholder, the stored value will be wrong until backfilled. This affects the `AI TransportEfficiency trend` measurement (DDF success criterion 7).

**Options:**

**A. Two-phase: pending sentinel + backfill**
- At session close: trunk_quality = 0.5, status = 'pending'
- Backfill job at N=3 sessions later: update trunk_quality to confirmed value, status = 'confirmed'
- composite_te updated on backfill
- _(Proposed by: synthesis reasoning based on both providers)_
- Pros: No blocking, trend measurement works, clear pending/confirmed states

**B. Decouple into two metrics**
- SessionVelocity = raven × crow × (1/speed) (instant, no trunk_quality dependency)
- TrunkYield = trunk_quality × yield_factor (lagging, separate computation)
- Display both in IntelligenceProfile
- _(Proposed by: Gemini)_
- Pros: No misleading composite; cleaner semantic separation
- Cons: roadmap specifies a single composite TE formula; splitting changes the spec

**Synthesis recommendation:** ✅ **Option A — Two-phase pending sentinel**
- Rationale: Maintains the single-composite-TE spec from the roadmap. The 0.5 sentinel is an unbiased prior. Profile display shows pending vs. confirmed count so users understand which sessions are partial. Backfill is a simple SQL UPDATE.

**Sub-questions:**
- What is N for trunk_quality backfill? (Recommendation: N=3 subsequent sessions for the same subject/human_id)
- What counts as "trunk validated"? (Recommendation: Level 5+ events in sessions +1..+3 that share axis_identified with the original Level 0 event)

---

### Q3: Fringe Drift Rate — Window and Signal Definition

**Question:** How is "Fringe signal" defined in terms of existing columns, and what window defines "N prompts" for Fringe Drift rate computation?

**Why it matters:** Phase 14 designed a co-pilot intervention for Fringe signals (hedged, vague language before naming). But the `flame_events` table doesn't have a dedicated `fringe` column — Fringe signals aren't yet stored as a distinct type. Phase 16 must either (a) define Fringe as a proxy from existing columns, or (b) add a new marker_type detection.

**Options:**

**A. Proxy Fringe from marker_level 1-2**
- Fringe signal = flame_event with marker_level IN (1, 2) (below concretization threshold)
- Named concept = Level 6+ with flood_confirmed = true
- Fringe Drift = 1 - (Level6_sessions / Fringe_sessions) per session
- _(Proposed by: Gemini, Perplexity)_
- Pros: Uses existing columns, no new detection code needed

**B. Add FRINGE as a new marker_type**
- Extend Tier 1 detectors with FRINGE detection pattern (hedged language patterns)
- Store as marker_type = 'FRINGE' in flame_events
- Fringe Drift = FRINGE events that didn't produce Level 6+ within same session
- _(Proposed by: synthesis reasoning from Phase 14 co-pilot spec)_
- Pros: Accurate to DDF definition; more precise
- Cons: Adds Phase 14 co-pilot detection work to Phase 16 scope; Phase 14 was research-only

**Synthesis recommendation:** ✅ **Option A — Proxy from marker_level 1-2**
- Rationale: Phase 14 co-pilot Fringe detection is not yet implemented. Phase 16 should use available data. Option B is correct long-term but adds scope. Fringe Drift as a Level 1-2 → Level 6 ratio is a valid proxy and produces a meaningful trend line.

**Sub-questions:**
- Should sessions with zero Fringe signals have fringe_drift_rate = NULL or = 0.0? (Recommendation: NULL — not applicable)

---

### Q4: MEMORY.md Review CLI File I/O Strategy

**Question:** How should `intelligence memory-review` write accepted candidates to MEMORY.md? Append, replace, or versioned? What's the format? How is dedup handled?

**Why it matters:** MEMORY.md is a load-bearing file — it is read at session start and determines the AI's retrieval axes. A bad write could corrupt 16+ existing entries. The format must match the existing `## Title\n**CCD axis:** ...` structure.

**Options:**

**A. Append-only, match existing format, dedup at accept**
- Read current MEMORY.md, check if ccd_axis already present (substring match)
- If duplicate: warn, ask override (in non-YOLO) or skip (in YOLO)
- If new: append formatted CCD entry with horizontal rule
- _(Proposed by: Gemini, synthesis reasoning)_
- Pros: Safe (never modifies existing content), simple implementation, matches existing format

**B. Append-with-versioning + YAML front-matter**
- Each entry has YAML metadata block with entry_id for tracking
- Deprecated entries marked (not deleted) with deprecation_reason
- File locking for concurrent write safety
- _(Proposed by: Perplexity)_
- Pros: Richer audit trail, machine-parsable
- Cons: Breaks existing MEMORY.md format; existing 16 entries have no YAML front-matter

**Synthesis recommendation:** ✅ **Option A — Append-only, match existing format**
- Rationale: MEMORY.md already has 16+ entries in a specific format. Adding YAML front-matter would break the session-start reading mechanism. Append-only is correct and safe. Dedup check via ccd_axis substring match prevents exact duplicates. The `memory_candidates` table in DuckDB is the authoritative store; MEMORY.md is the export layer.

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Human vs. AI TransportEfficiency Formula Differentiation

**Question:** Should the TransportEfficiency formula use the same computation for both human (flame_events) and AI (ai_flame_events) subjects, or should some components be computed differently?

**Why it matters:** The roadmap explicitly requires TE for "both human AND AI." The `subject` column distinguishes them. But `transport_speed` intuitively means different things for humans (how fast they reach insight in a session) vs. AI (how often the AI produces Level 6 synthesis in its responses).

**Options:**

**A. Unified formula, unified computation**
- Same SQL query, filtered by subject = 'human' OR subject = 'ai'
- transport_speed interpreted as "flood density" for both
- _(Proposed by: synthesis reasoning)_

**B. Polymorphic transport_speed**
- Human transport_speed: time from session start to first Level 6 (clock-based)
- AI transport_speed: proportion of Level 6 events in total ai_flame_events
- Same raven_depth, crow_efficiency, trunk_quality for both
- _(Proposed by: Gemini)_

**Synthesis recommendation:** ⚠️ **Option A — Unified formula**
- Rationale: Flame_events and ai_flame_events share the same schema by design. The unified formula produces comparable TE scores across subjects, enabling the profile display to show both on the same scale. Polymorphic transport_speed adds complexity for a Phase 16 metric that will be refined in Phase 17-18.

---

### Q6: AI TransportEfficiency Delta Measurement

**Question:** How do we measure whether AI TE improves after MEMORY.md entries are accepted? What window, and where to store the delta?

**Why it matters:** DDF success criterion 7 says: "AI TransportEfficiency trend is tracked across sessions — before MEMORY.md entries are accepted vs. after." This must be falsifiable and stored.

**Options:**

**A. Simple 5-session rolling window, delta stored on memory_candidates**
- pre_te_avg = AVG(composite_te) for sessions -5 to -1 before acceptance
- post_te_avg = AVG(composite_te) for sessions +1 to +5 after acceptance
- te_delta stored as column on memory_candidates
- _(Proposed by: synthesis reasoning, simplified from Perplexity's regression approach)_

**B. 30-day pre/post interrupted time-series with regression**
- Full statistical analysis with confounding factor control
- _(Proposed by: Perplexity)_
- Pros: More rigorous
- Cons: Premature for Phase 16; insufficient data in early sessions

**Synthesis recommendation:** ⚠️ **Option A — Simple 5-session rolling window**
- Rationale: Phase 16 establishes the infrastructure. Statistical rigor belongs in Phase 17 assessment. The 5-session window is practical and produces actionable signal. Backfill job computes it; stored on memory_candidates alongside status='accepted'.

---

## Tier 3: Polish (🔍 Needs Clarification)

### Q7: Phase 15 / Phase 16 Build Boundary

**Question:** What exactly does Phase 15 provide vs. what Phase 16 must build? Risk of re-implementing existing work.

**Why it matters:** Phase 15 already wrote memory_candidates on Level 6 detect. Phase 16's success criterion 4 says "memory_candidates DuckDB table auto-drafted from every Level 6 FlameEvent" — this already exists. Does Phase 16 need to change how candidates are drafted?

**Options:**

**A. Phase 16 is purely additive (no re-implementation)**
- memory_candidates write-on-detect: Phase 15 complete, do not touch
- Phase 16 adds: transport_efficiency_sessions table, fringe_drift_rate column, MEMORY.md review CLI, te_delta on memory_candidates, extended IntelligenceProfile display
- _(Proposed by: project context analysis)_

**B. Phase 16 improves candidate drafting**
- Extend deposit_to_memory_candidates to include trunk_quality linking
- Add perception_pointer with source_session_id + prompt_number to memory_candidates
- _(Would be a breaking change to Phase 15's deposit mechanism)_

**Synthesis recommendation:** 🔍 **Option A — Purely additive**
- Rationale: deposit-not-detect CCD axis: "do not defer, do not make optional." Phase 15's write-on-detect is load-bearing. Phase 16 does not modify it; it adds the review-and-export path alongside it.

---

## YOLO Mode Status

All 7 questions have been auto-answered in `CLARIFICATIONS-ANSWERED.md`.
Proceed to `/gsd:plan-phase 16` to generate execution plans.

---

*Multi-provider synthesis: Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
*YOLO mode: Questions documented; auto-answers generated*
