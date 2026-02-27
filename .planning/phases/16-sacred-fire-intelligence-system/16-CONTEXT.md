---
phase: 16
name: Sacred Fire Intelligence System
generated: 2026-02-24
synthesis_source: Gemini Pro + Perplexity Sonar Deep Research (OpenAI response truncated, 2-provider synthesis)
yolo: true
---

# CONTEXT.md — Phase 16: Sacred Fire Intelligence System

**Generated:** 2026-02-24
**Phase Goal:** Build the second-order intelligence layer on top of Phase 15's detection substrate. Measures the quality of the transport system that produces FlameEvents — for both human and AI — and closes the review-and-export loop that Phase 15's write-on-detect mechanism opened. The MEMORY.md pipeline is the concrete mechanism by which the AI self-modifies across sessions.
**Synthesis Source:** Gemini Pro (thinking=high) + Perplexity Sonar Deep Research

---

## Overview

Phase 16 implements 4 requirements (DDF-06 through DDF-09) that transform Phase 15's raw detection output into a measured, bidirectionally-improving intelligence system. The abstract DDF metaphors (raven_depth, crow_efficiency, transport_speed, trunk_quality) require concrete SQL/Python operationalizations. The primary structural challenge is a **temporal paradox** in trunk_quality: TransportEfficiency depends on trunk_quality, but trunk_quality is a lagging metric validated N sessions *after* the current session. The secondary challenge is the **MEMORY.md closed loop**: the file I/O strategy, dedup logic, and CLI interaction pattern determine whether the AI's concept store actually improves across sessions.

**All providers agreed**: these 4 items are the blocking decisions before planning.

**Confidence markers:**
- ✅ **Consensus** — Both providers identified this as critical/blocking
- ⚠️ **Recommended** — One provider identified, well-aligned with project architecture
- 🔍 **Needs Clarification** — Identified by synthesis reasoning against project constraints

---

## Gray Areas Identified

### ✅ 1. TransportEfficiency Sub-Metric SQL Proxies (Consensus)

**What needs to be decided:**
Concrete SQL-derivable definitions for `raven_depth`, `crow_efficiency`, `transport_speed`, and `trunk_quality` from the existing `flame_events` and `ai_flame_events` DuckDB tables.

**Why it's ambiguous:**
The formula `raven_depth × crow_efficiency × (1/transport_speed) × trunk_quality` uses cognitive metaphors. The columns available are: `session_id`, `human_id`, `subject`, `marker_level` (0-7), `marker_type`, `axis_identified`, `flood_confirmed`, `evidence`, `quality_score`. No explicit timestamps in the current schema — temporal ordering comes from marker_level and prompt_number.

**Provider synthesis:**
- **Gemini:** raven_depth = MAX(marker_level)/7.0; crow_efficiency = SUM(marker_level)/COUNT(prompts); transport_speed = time from session start to first Level 6 event. Prefers DuckDB Views over Python computation.
- **Perplexity:** Multi-proxy approach with normalization. raven_depth = f(evidence_diversity, level_span, axis_density); crow_efficiency = deliberate_connections/total_transitions; transport_speed = confirmed_floods/session_duration_minutes (normalized). Recommends proxy correlation validation (>0.7 inter-proxy correlation for construct validity).

**Proposed implementation decision (YOLO):**
Simple, auditable SQL proxies — one primary proxy per component, computed per session per subject:
- `raven_depth` = MAX(marker_level) / 7.0 (normalized 0–1)
- `crow_efficiency` = COUNT(*) FILTER (WHERE axis_identified IS NOT NULL) / NULLIF(COUNT(*), 0) (axis identification rate)
- `transport_speed` = COUNT(*) FILTER (WHERE flood_confirmed = true) / NULLIF(COUNT(*), 0) (flood density)
- `trunk_quality` = 0.5 sentinel until backfilled (see Gray Area 2); then COUNT(Level 0 with flood_confirmed=true) / NULLIF(COUNT(Level 0), 0)

Store computed values in a new `transport_efficiency_sessions` DuckDB table: (te_id, session_id, subject, human_id, raven_depth, crow_efficiency, transport_speed, trunk_quality, composite_te, trunk_quality_status IN ('pending', 'confirmed'), created_at).

**Open questions (resolved by YOLO):**
- Formula: Multiplicative composite with 0.5 sentinel for trunk_quality until confirmed → acceptable approximation for pending sessions.
- Normalization: Each component normalized 0–1 before multiplication to prevent scale collapse.

**Confidence:** ✅ Both providers agreed this is blocking.

---

### ✅ 2. Trunk Quality Temporal Paradox (Consensus)

**What needs to be decided:**
`trunk_quality` is defined as downstream validation — N sessions later, did the named trunk explain derivative facts? This means `TransportEfficiency` for session S cannot be fully computed at session close. How to handle this structural gap?

**Why it's ambiguous:**
If TransportEfficiency requires trunk_quality and trunk_quality requires future sessions, then either:
(a) TransportEfficiency is a lagging metric (computed retroactively), or
(b) TransportEfficiency is split into an immediate partial metric + a lagging backfill.

The roadmap says `AI TransportEfficiency trend is tracked across sessions — before MEMORY.md entries are accepted vs. after`, implying it IS tracked over time, not just at session close.

**Provider synthesis:**
- **Gemini:** Split the metric. `SessionVelocity` = raven × crow × speed (instantaneous). `TrunkYield` = lagging. trunk_quality = 1 if memory_candidate referenced in sessions +1 to +5, else 0.
- **Perplexity:** Three-layer validation: immediate consistency (blocking contradictions), temporal generalization (scope rule alignment across subsequent sessions), contradiction emergence detection. Storage: `trunk_quality_status` column on transport_efficiency_sessions.

**Proposed implementation decision (YOLO):**
Two-phase approach:
1. **At session close:** store te with `trunk_quality=0.5` (uninformed prior) and `trunk_quality_status='pending'`.
2. **Backfill job** (runs during `intelligence profile` queries or as a CLI command): for sessions >= 3 older, compute trunk_quality as: `COUNT(subsequent Level 5+ events in sessions +1..+5 that share the same axis_identified) / 5.0`, capped at 1.0. Update `trunk_quality_status='confirmed'`.

The `composite_te` column stores the current best estimate (updated on backfill). The `--ai` flag profile shows pending vs. confirmed breakdown.

**Confidence:** ✅ Both providers agreed this is the #1 structural blocker.

---

### ✅ 3. Fringe Drift Rate Computation Window (Consensus)

**What needs to be decided:**
Fringe Drift rate = proportion of Fringe signals that failed to produce a named concept within N prompts. What is N, and how do we define "Fringe signal" and "named concept" in terms of existing columns?

**Why it's ambiguous:**
- "Fringe signal" has no direct column in flame_events — it would be detected by the co-pilot (Phase 14), not yet stored as a flag.
- "N prompts" is undefined — could be session-scoped, sliding window, or fixed count.
- "Named concept" could mean: axis_identified IS NOT NULL, OR flood_confirmed=true, OR Level 6+ event.

**Provider synthesis:**
- **Gemini:** Simplify to session-batch ratio: `1 - (Count(Level 6) / Count(Level 1|2))`. Session is the natural window. Abandon causal lineage tracing per-signal.
- **Perplexity:** Session-windowed with Level 6 as graduation threshold. N = empirical (average prompts per session). Temporal decay for longitudinal monitoring.

**Proposed implementation decision (YOLO):**
Phase 16 definition for Fringe signal: `marker_level IN (1, 2)` in flame_events/ai_flame_events (low-level detection below concretization threshold). Named concept: `marker_level >= 6 AND flood_confirmed = true` in the same session.

Fringe Drift rate per session = `1 - (COUNT(*) FILTER (WHERE marker_level >= 6 AND flood_confirmed = true) / NULLIF(COUNT(*) FILTER (WHERE marker_level IN (1,2)), 0))`. NULL if no Fringe signals in session.

Session-windowed (not per-signal trace): treating the session as a "batch reactor" as Gemini describes. This is a practical proxy; per-signal causal linking deferred to Phase 18 (Bridge-Warden structural integrity detection).

Store in `transport_efficiency_sessions` as `fringe_drift_rate FLOAT` column alongside TransportEfficiency.

**Confidence:** ✅ Both providers agreed on session-windowed approach.

---

### ✅ 4. MEMORY.md Review CLI File I/O Strategy (Consensus)

**What needs to be decided:**
How does `intelligence memory-review` interact with the MEMORY.md file? Append vs. replace, dedup at what stage, how to handle the existing file format, and how to prevent concurrent write corruption.

**Why it's ambiguous:**
- MEMORY.md already has 16+ entries in a specific format (`## Title\n\n**CCD axis:** ...\n**Scope rule:** ...\n**Flood example:** ...`).
- A candidate could duplicate an existing entry (same ccd_axis).
- The CLI must not corrupt existing content — the MEMORY.md is load-bearing.
- "Edit" option in the review implies in-place modification of a candidate before writing.

**Provider synthesis:**
- **Gemini:** Append-only from CLI. Dedup at candidate generation stage (Phase 15 write-on-detect already soft-dedups on ccd_axis + scope_rule). No YAML front-matter.
- **Perplexity:** Append-with-versioning, YAML front-matter, frozen Pydantic models for entries, file locking. More complex than needed for current project.

**Proposed implementation decision (YOLO):**
**Append-only, no YAML front-matter, match existing MEMORY.md format:**

Format for exported entry:
```
## [ccd_axis title from candidate]

**CCD axis:** [ccd_axis]
**Scope rule:** [scope_rule]
**Flood example:** [flood_example]

---
```

CLI flow:
1. List pending `memory_candidates` (status='pending') ordered by confidence DESC.
2. For each: show full CCD triple, confidence, subject, origin, source_flame_event_id.
3. User: `a`=accept, `r`=reject, `e`=edit (opens $EDITOR on the triple), `s`=skip.
4. Accept: (a) check if ccd_axis already exists in MEMORY.md (case-insensitive substring match on existing content), (b) if duplicate → warn but allow override, (c) append to MEMORY.md, (d) update memory_candidates status='accepted'.
5. Reject: update status='rejected'.
6. Edit: write candidate fields to a temp file, open $EDITOR, re-read on save, update candidate in DB before accepting.

No file locking needed: CLI is single-process, not concurrent. MEMORY.md is < 500 lines; full read for dedup check is fast.

**Confidence:** ✅ Both providers agreed append-only is the correct strategy.

---

### ⚠️ 5. Human vs. AI TransportEfficiency Formula Differentiation

**What needs to be decided:**
Are the 4 sub-metric formulas identical for human and AI subjects, or are they polymorphic? The `subject` column distinguishes them; the columns are the same (`flame_events` for human, `ai_flame_events` for AI).

**Why it's ambiguous:**
`transport_speed` has different semantics: for the human, speed is meaningful (how quickly they achieve insights); for the AI, all events in a session are co-generated — "speed" within a single session may not be meaningful in the same way.

**Provider synthesis (Gemini only — consensus not reached):**
Gemini proposes unified formula with polymorphic transport_speed interpretation:
- Human: time to first Level 6 from session start.
- AI: time from first ai_flame_event to first Level 6 ai_flame_event.

**Proposed implementation decision (YOLO):**
Use **unified formula** for both subjects. The `transport_efficiency_sessions` table has a `subject` column ('human' or 'ai'). The computation logic is identical — both draw from flame_events filtered by subject. transport_speed for AI is computed identically (flood density: confirmed_floods / total_events); interpreting this as "how often does the AI produce breakthrough-level synthesis when it reasons?" — a valid quality indicator regardless of session timing.

The difference appears at the *IntelligenceProfile* display layer: human profile shows trend over time (improving sessions); AI profile shows trend across MEMORY.md iterations (does the AI produce better quality synthesis after new entries are accepted?).

**Confidence:** ⚠️ One provider, but well-aligned with existing subject-column design.

---

### ⚠️ 6. AI TransportEfficiency Delta Measurement (Pre vs. Post MEMORY.md Acceptance)

**What needs to be decided:**
How to measure whether AI TransportEfficiency improves after a MEMORY.md entry is accepted? What window, what comparison, and where to store the delta?

**Why it's ambiguous:**
- Causal attribution is hard: other factors change between sessions.
- Window size: N sessions before/after acceptance.
- The AI profile must show this trend for the measurement to be "falsifiable and measurable" (per roadmap).

**Provider synthesis (Perplexity only):**
Time-series interrupted design: 30-day pre/post observation windows, confounding factor regression. Lagged analysis for delayed effects.

**Proposed implementation decision (YOLO):**
**Simple rolling comparison**, not regression: for each accepted memory_candidate, compute:
- `pre_te_avg` = AVG(composite_te) for AI subject, sessions in the 5 sessions BEFORE acceptance
- `post_te_avg` = AVG(composite_te) for AI subject, sessions in the 5 sessions AFTER acceptance
- `te_delta` = post_te_avg - pre_te_avg

Store on `memory_candidates` table: add columns `pre_te_avg FLOAT`, `post_te_avg FLOAT`, `te_delta FLOAT`. Populated by backfill job (same job as trunk_quality backfill).

Display in `intelligence profile --ai` as a ranked list: "Which accepted MEMORY.md entries produced the largest TransportEfficiency improvement?"

**Confidence:** ⚠️ One provider; simple implementation avoids premature statistical complexity.

---

### 🔍 7. Phase Boundary: What Phase 15 Already Built vs. What Phase 16 Must Build

**What needs to be decided:**
Phase 15 already wrote memory_candidates on Level 6 detect (write-on-detect). Phase 16 requires a MEMORY.md review CLI and TransportEfficiency metrics. The exact boundary matters for avoiding duplicate effort.

**Provider synthesis (synthesis reasoning):**
Phase 15 built:
- `flame_events` and `ai_flame_events` tables with all columns
- `memory_candidates` table with write-on-detect at Level 6 (`deposit_to_memory_candidates`)
- `IntelligenceProfile` aggregation (flame_frequency, avg_marker_level, spiral_depth, generalization_radius, flood_rate)
- `intelligence profile <human_id>` CLI (basic display)

Phase 16 must build:
- `transport_efficiency_sessions` table + computation
- Fringe drift rate computation
- Level 0 Trunk Identification detection type (not yet implemented — Phase 15 detects L0-L7 but trunk_quality validation is not stored)
- MEMORY.md review CLI (`intelligence memory-review`)
- AI TransportEfficiency trend + te_delta on memory_candidates
- `intelligence profile` extended with TransportEfficiency breakdown

**Proposed implementation decision (YOLO):**
Do NOT re-implement anything Phase 15 built. Phase 16 is purely additive: new table, new CLI subcommand, new columns on existing tables, new aggregation queries. The deposit mechanism (write_on_detect at Level 6) is Phase 15's — Phase 16 only adds the *review-and-export* half of the loop.

**Confidence:** 🔍 Project context analysis; no provider explicitly addressed this boundary.

---

## Summary: Decision Checklist

**Tier 1 (Blocking — must decide before planning):**
- [x] TransportEfficiency sub-metric SQL proxies (raven_depth, crow_efficiency, transport_speed, trunk_quality)
- [x] Trunk quality temporal paradox (2-phase: pending 0.5 sentinel + backfill confirmed)
- [x] Fringe Drift rate window (session-windowed, Level 1/2 = Fringe, Level 6+ = named concept)
- [x] MEMORY.md file I/O strategy (append-only, match existing format, $EDITOR for edits)

**Tier 2 (Important — should decide before planning):**
- [x] Human vs. AI TransportEfficiency formula (unified formula, differentiated at profile display)
- [x] AI TransportEfficiency delta measurement (5-session rolling window, stored on memory_candidates)

**Tier 3 (Can defer to implementation):**
- [x] Phase 15 / Phase 16 boundary (additive only, no re-implementation)

---

*Multi-provider synthesis: Gemini Pro (thinking=high) + Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
*YOLO mode: Auto-answers generated below in CLARIFICATIONS-ANSWERED.md*
