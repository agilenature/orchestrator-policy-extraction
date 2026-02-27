# CONTEXT.md — Phase 17: Candidate Assessment System

**Generated:** 2026-02-24
**Phase Goal:** Use the full IntelligenceProfile (FlameEvents + TransportEfficiency) to assess the epistemological quality of candidates for collaborating with AI. Phase 17 is simultaneously the highest-fidelity AI self-improvement mechanism: calibrated DDF Levels 5-7 scenarios force ai_flame_events at depth that routine sessions cannot generate.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-5.2, Gemini Pro w/ high thinking, Perplexity Sonar Deep Research)

---

## Overview

Phase 17 is structurally different from all prior OPE phases. Prior phases built infrastructure; Phase 17 uses that infrastructure to do two things at once: (1) assess human candidates on epistemological quality, and (2) deposit the richest ai_flame_events the system has ever produced to memory_candidates. The dual-purpose design creates seven distinct gray areas requiring decisions before planning.

The governing axis is **deposit-not-detect**: every component is evaluated by whether it deposits to `memory_candidates`. The Assessment Report is the terminal deposit. The FlameEvent timeline, TE scores, AI contribution profile are all instrumental — they exist to make the Report's deposit CCD-quality.

**Confidence markers:**
- ✅ **Consensus** — All 3 providers identified this as critical
- ⚠️ **Recommended** — 2 providers identified this as important
- 🔍 **Needs Clarification** — 1 provider identified, but OPE-specific analysis confirms importance

---

## Gray Areas Identified

### ✅ 1. Scenario Materialization — What the Scenario IS

**What needs to be decided:**
`project_wisdom` and the episode DB contain *text descriptions* of insights, dead ends, and breakthroughs — not runnable code repositories. The generator must bridge from a wisdom entry ("Dependency injection caused circular logic when the factory also implements the interface") to a *functional environment state* that presents the problem without revealing the answer.

**Why it's ambiguous:**
Three options exist: (A) generate a full mock repository (expensive/fragile), (B) generate a text-only problem description (too easy — no real code to interact with), (C) generate a minimal broken artifact (briefing + a broken script that hides the root cause). The requirements don't specify what "pile problem" means concretely.

**Provider synthesis:**
- **OpenAI:** Treated assessment as generic Q&A; not OPE-specific
- **Gemini:** Named this the core problem: **seed-based synthesis** — scenario_context.md (briefing) + repro_script.py (breaks in the intended way, hides root cause behind an abstraction layer)
- **Perplexity:** Confirmed scenario generation tiers by DDF level (L1-L2: parameter substitution, L3-L4: pattern-matched from episode DB, L5-L7: adaptive based on candidate profile)

**Proposed implementation decision:**
Generate two artifacts per scenario:
1. `scenario_context.md` — problem briefing (no solution hints)
2. A minimal broken implementation file (Python/TypeScript appropriate to the episode) that *demonstrates the failure symptom* but hides the root cause behind an abstraction. For L5-L7, the AI's `CLAUDE.md` is pre-seeded with a plausible-but-wrong framing that the candidate must reject.

The `project_wisdom` table needs a new column: `scenario_seed` (nullable TEXT — a code snippet or structural description that seeds the generator). Scenarios without a seed use text-prompt fallback (L1-L2 only).

**Open questions:**
- Does the generated repro_script need automated validation (run it, confirm it fails in the intended way) before deployment?
- Do L5-L7 scenarios require a human-authored "golden solution TE baseline" or can it be computed from the AI solving it clean?
- Which wisdom entity types (dead_end, breakthrough, scope_decision) are appropriate seed sources for each DDF level?

---

### ✅ 2. Actor-Observer Architecture — Two Roles for the AI System

**What needs to be decided:**
The AI must simultaneously be:
1. **Actor (Claude Code instance):** Calibrated collaborator, potentially "handicapped" at a specific DDF level (e.g., Level 3 — surface pattern matching only) to force the candidate to operate independently at Level 5+
2. **Observer (OPE pipeline):** Reads the live session transcript, generates flame_events, writes to DuckDB

If both roles share the same Claude Code instance, the AI will "break character" to log events, or hallucinate helpfulness when it should be testing the candidate. These must be structurally separated.

**Why it's ambiguous:**
The Actor's persona is deliberately constrained. If the Actor also generates its own `ai_flame_events`, those events may be "performance art" (the AI pretending to reason at Level 3) rather than genuine reasoning — which would pollute the AI's IntelligenceProfile with fake data.

**Provider synthesis:**
- **Gemini:** Named this the hardest architectural decision — process isolation required. Actor = standard Claude Code instance with SessionStart hook setting persona/handicap. Observer = OPE pipeline in background, consuming transcript.
- **Perplexity:** Confirmed: detection pipeline operates independently from session state. Observer must not have write-access to Actor's session context.
- **OpenAI:** Did not model this OPE-specific constraint.

**Proposed implementation decision:**
Strict process isolation:
- **Actor:** Claude Code instance launched with a custom `CLAUDE.md` (assessment persona) + SessionStart hook injecting the handicap level. This instance's job is to be a calibrated collaborator.
- **Observer:** `python -m src.pipeline.cli extract <session_file>` running in tail mode (or post-session batch). The Observer writes flame_events and ai_flame_events from transcript analysis — NOT from the Actor's real-time internal state.
- **ai_flame_events from assessment:** Generated by Observer from transcript *after* the Actor has spoken. The Actor's actual reasoning chain (its tool calls, PREMISE declarations, internal Chain-of-Thought in extended thinking) is the raw material. If the Actor was handicapped to Level 3, the ai_flame_events will genuinely show Level 3 reasoning (not fake).
- The "golden solution" is pre-computed by running the Actor WITHOUT handicap on the same scenario; that run's TE score becomes the `baseline_te` for the scenario.

**Open questions:**
- How is the handicap encoded? A custom `CLAUDE.md` override per assessment session? Or a SessionStart hook that pre-populates a specific incorrect framing?
- Does the Actor know it's in an assessment? (The candidate knows; does the AI know?)
- For L5-L7 scenarios, the AI must hold a wrong framing actively. How do we prevent the Actor from self-correcting before the candidate reaches the contradiction?

---

### ✅ 3. Session Isolation Architecture — How Isolated Must Environments Be?

**What needs to be decided:**
ASSESS-02 requires "isolated Claude Code environments." The isolation options range from: (A) Docker/Firecracker microVMs (true isolation, full sandboxing), (B) filesystem-level isolation with a UUID working directory + PAG hook blocking dangerous commands, (C) process-level isolation with separate `.claude` directories.

**Why it's ambiguous:**
Docker adds provisioning latency and complexity. Filesystem isolation is simpler but shares OS resources. The right choice depends on whether candidates run adversarial code (security concern) vs. whether they just need separate working directories (data isolation concern).

**Provider synthesis:**
- **Gemini:** Filesystem-level isolation is sufficient: `/tmp/ope_assess_{uuid}/`. Rely on PAG hook (Phase 14) to block dangerous shell commands. **Deposit-critical:** zip final state to `transport_efficiency_sessions` before cleanup.
- **Perplexity:** Recommends Docker or Firecracker for true isolation; defines 4GB memory limit, 2 CPU quota, 50GB disk limit per session.
- **OpenAI:** Noted isolation as a concern but not OPE-specific.

**Proposed implementation decision:**
Filesystem-level isolation for MVP, with upgrade path:
- Create `/tmp/ope_assess_{session_id}/` as the isolated working directory
- Launch Claude Code with `--project-dir /tmp/ope_assess_{session_id}/` (or equivalent config override)
- PAG hook (already built in Phase 14) blocks dangerous mutating commands outside the assessment dir
- Session cleanup: zip the final directory state → store path in `transport_efficiency_sessions.session_artifact_path`; then `rm -rf /tmp/ope_assess_{session_id}/`
- Docker container isolation is the upgrade path for production deployment; not required for MVP

**Open questions:**
- Does Claude Code support `--project-dir` or equivalent CLI flag to override the working directory? (Needs spike.)
- What is the maximum assessment duration? (Determines whether `/tmp` cleanup is a concern.)
- Should the `.claude/MEMORY.md` for the assessment session be a fresh blank file, or pre-seeded with the AI's current IntelligenceProfile?

---

### ✅ 4. Memory Deposit Contamination — Assessment vs. Production Candidates

**What needs to be decided:**
Assessment sessions with a deliberately "handicapped" AI produce reasoning at Level 3 (surface patterns, wrong framings). If the raw transcript feeds into `memory_candidates` the same way as production sessions, the AI's IntelligenceProfile will be polluted with sub-optimal reasoning as if it were genuine L3 work.

**Why it's ambiguous:**
Phase 17's secondary goal is *increasing* ai_flame_events quality. But the Actor's handicap generates deliberately low-quality reasoning. The Observer's analysis of the candidate's response to that reasoning generates high-quality signal. These must be separated.

**Provider synthesis:**
- **Gemini:** Named this "Memory Pollution vs. High-Fidelity Training." Proposed: save the **Assessment Report** (not raw transcript) as the primary deposit artifact. Introduce `simulation_review` as a memory type distinct from `production` work.
- **Perplexity:** Proposed `source_type` classification per session: `assessment_only` vs. `improvement_eligible` vs. `improvement_prioritized`. Deposits require explicit validation gates before entering `memory_candidates`.
- **OpenAI:** Did not model this OPE-specific contamination concern.

**Proposed implementation decision:**
Add `source_type VARCHAR CHECK IN ('production', 'assessment', 'simulation_review')` column to `memory_candidates`.
- Actor transcript → ai_flame_events tagged with `source_type='assessment'` and `assessment_session_id`
- **Assessment-source ai_flame_events do NOT flow to the main IntelligenceProfile** — they feed a separate `assessment_intelligence_profile` query
- The **Assessment Report** (ASSESS-03 artifact) is the terminal deposit: it captures the candidate-AI interaction dynamics as a CCD-quality entry (what framing did the AI use? at what level did the candidate operate? what was the TE delta?). This is deposited to `memory_candidates` with `source_type='simulation_review'` and `fidelity=3` (highest fidelity, forced DDF L5-7 reasoning)
- Assessment-source entries are explicitly excluded from `IntelligenceProfile` CLI by default; accessible via `--include-assessments` flag

**Open questions:**
- Should `assessment_intelligence_profile` be a separate DuckDB table or a view with a filter on `source_type`?
- Do `simulation_review` deposits go through the same MEMORY.md review CLI (Phase 16), or do they have a separate review pathway?
- At what trust level do `simulation_review` deposits start? (Higher confidence than production, since they were forced to L5-7 reasoning?)

---

### ⚠️ 5. Level 5-7 Rejection Detection — Semantic vs. Preference Rejection

**What needs to be decided:**
For a rejection to count as a Level 5+ FlameEvent (independent epistemological judgment), the candidate must reject the AI's *framing* — the underlying causal model — not just its surface output (a specific variable name, a code style preference). Automated detection of semantic vs. preference rejection is ambiguous.

**Why it's ambiguous:**
A candidate might say "I don't like this approach" and implement something worse. Is that Level 5 (independent thought) or Level 0 (stubbornness)? Without grounding rejection quality to outcome, the metric fires on false positives.

**Provider synthesis:**
- **Gemini:** **Outcome-gated epistemology**: a rejection counts as Level 5-7 ONLY if the candidate's solution TE > the AI's proposed-path baseline TE. If Candidate Rejects AND Candidate TE > Baseline TE → Level 5 FlameEvent. If Candidate Rejects AND Candidate TE < Baseline TE → Level 1 (Stubbornness flag, not a Level 5).
- **Perplexity:** Did not specifically address this; covered rejection as part of contribution profiling.

**Proposed implementation decision:**
Implement outcome-gated rejection scoring in the Observer:
1. Pre-compute `baseline_te` for each scenario by running the Actor WITHOUT handicap
2. After session end, compute `candidate_te` from the candidate's actual work FlameEvents
3. If `rejection_detected=True` (heuristic: candidate explicitly declined the AI's suggestion AND pursued a different path) AND `candidate_te > baseline_te * 0.9` → upgrade to Level 5 FlameEvent
4. If `rejection_detected=True` AND `candidate_te < baseline_te * 0.9` → flag as `stubbornness_indicator=True` in ai_flame_events (not a Level 5)
5. Rejection detection heuristic: candidate's next tool call diverges from AI's suggested tool call AND candidate issued a correction or question event

**Open questions:**
- What is the `baseline_te` computation method for a scenario the AI solves clean? (One run, or averaged over N runs?)
- Should Fringe-signal rejections (candidate says "something feels off" before naming the alternative) count as Level 5 immediately, or require the same outcome gate?

---

### ⚠️ 6. TE Score Normalization for Assessment Context

**What needs to be decided:**
Production TE scores (Phase 16) are computed over full work sessions (hours, hundreds of events). Assessment TE scores are computed over 30-90 minute contrived scenarios. The time scales are different; the problem sizes are different. ASSESS-03 requires comparison against IntelligenceProfile population baseline — but which baseline?

**Why it's ambiguous:**
If assessment TE feeds directly into the production TE baseline, a candidate who is slow on a tiny contrived problem will look worse than their real IntelligenceProfile suggests. The metrics are not dimensionally compatible.

**Provider synthesis:**
- **Gemini:** Scenario-specific `complexity_modifier` scalar: `Assessment_TE = Raw_TE × complexity_modifier`. Calibration run (AI alone, no handicap) sets the normalization baseline.
- **Perplexity:** Z-score normalization against historical assessment population: `TE_normalized = (Score - Mean_Assessment_Historical) / StdDev_Assessment_Historical`.

**Proposed implementation decision:**
Two-layer normalization:
1. **Within-scenario normalization:** Each scenario has a `scenario_baseline_te` (AI clean-run TE) stored in the `project_wisdom.scenario_seed` metadata. Candidate TE is expressed as `ratio = candidate_te / scenario_baseline_te` (values > 1.0 mean the candidate outperformed the AI clean-run)
2. **Cross-scenario population baseline:** Maintain a `assessment_baselines` DuckDB table. After N>=10 assessments on the same scenario, compute mean/stddev of the ratio. Report candidate performance as percentile within that distribution.
3. **Assessment TE does NOT update the production `transport_efficiency_sessions` table.** It writes to a separate `assessment_te_sessions` table with `scenario_id` as a grouping key.

**Open questions:**
- What if a scenario has never been run before (no population baseline)? Report raw ratio only, flag as `population_baseline_pending=True`.
- Should `transport_speed` sub-metric be excluded from assessment TE? (Gemini suggested this; assessment problem contexts are too small for meaningful transport speed measurement.)

---

### 🔍 7. Scenario DDF-Level Calibration — Annotating the Wisdom DB

**What needs to be decided:**
`project_wisdom` entries don't have DDF-level annotations. The scenario generator needs to know which wisdom entries produce L1-2 problems (one abstraction unlocks the solution) vs. L5-7 problems (AI's framing must be rejected). Without this metadata, the generator can't calibrate.

**Why it's ambiguous:**
DDF level is a property of the *challenge context*, not just the wisdom content. A dead-end entry about circular dependency could be L2 (just import the right module) or L5 (the entire architectural assumption was wrong). The level depends on how the scenario is framed, not on the wisdom entry alone.

**Provider synthesis:**
- **Perplexity:** Described a calibration table mapping scenario characteristics to DDF levels; suggested the calibration learns from prior assessment outcomes.
- **Gemini:** Mentioned that project_wisdom needs a `code_snippet_seed` column to facilitate generation; DDF level emerges from the seed structure.

**Proposed implementation decision:**
Add two columns to `project_wisdom`:
1. `scenario_seed TEXT` — optional code snippet or structural description enabling scenario generation
2. `ddf_target_level INTEGER` — the DDF level this wisdom entry is intended to challenge at (1-7; NULL = not yet calibrated)

Retrospective annotation CLI: `python -m src.pipeline.cli intelligence assess annotate-scenarios` — presents each wisdom entry with a DDF level picker (1-7) and optional seed text. This must be run before the first assessment session.

For auto-calibration: after 10 assessments on a scenario, if the median candidate DDF level achieved consistently matches or exceeds `ddf_target_level`, downgrade `ddf_target_level` by 1 (scenario too easy). If fewer than 30% of candidates reach the target level, upgrade by 1 (too hard).

**Open questions:**
- Should `ddf_target_level` be an integer or a range (e.g., target L4-L5)?
- Who has authority to override auto-calibration? (Human reviewer via CLI only?)

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking — must decide before coding):**
- [ ] Scenario materialization format (seed-based: context.md + repro file?)
- [ ] Actor-Observer process separation (separate Claude Code + OPE pipeline observer?)
- [ ] Session isolation level (filesystem-only vs. Docker?)
- [ ] Memory deposit contamination control (source_type column + assessment exclusion from IntelligenceProfile?)

**Tier 2 (Important — impacts scoring quality):**
- [ ] Level 5-7 rejection detection mechanism (outcome-gated via baseline TE?)
- [ ] TE normalization for assessment context (separate assessment_te_sessions table + within-scenario ratio?)

**Tier 3 (Polish — can decide during implementation):**
- [ ] Scenario DDF-level annotation mechanism (CLI annotation + auto-calibration threshold?)

---

*Multi-provider synthesis by: OpenAI gpt-5.2, Gemini Pro (high thinking), Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
*YOLO mode: Auto-answers generated in CLARIFICATIONS-ANSWERED.md*
