---
phase: 14-live-session-governance-research
plan: 04
subsystem: governance
tags: [spike, validation, bus-transport, ddf, memory-ingestion, hooks]

# Dependency graph
requires:
  - phase: 14-01
    provides: "CCD constraint architecture, hook design, GovernanceSignal boundary_dependency"
  - phase: 14-02
    provides: "Bus API routes, governing daemon design, DDF co-pilot intervention types"
provides:
  - "Empirical validation that OPE extract pipeline IS the post-task memory ingestion layer"
  - "DDF signal density comparison: full-session wins over per-prompt heuristic (10-20% precision)"
  - "Hook stdout visibility resolution: only SessionStart.additionalContext is user-visible"
  - "Bus transport latency validation: 1.6ms p99 (30x under 50ms target)"
  - "Phase 15 wave ordering with deposit-first mandate and load-bearing vs scaffolding classification"
affects: [phase-15, phase-16, memory-candidates, governing-daemon, ddf-co-pilot]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-tier fidelity model: fidelity=1 (real-time heuristic stub) + fidelity=2 (post-task OPE enrichment)"
    - "Post-task memory ingestion via existing CLI: subprocess.run python -m src.pipeline.cli extract"
    - "DDF delivery: write-on-detect to memory_candidates (terminal) + next-session SessionStart (scaffolding)"

key-files:
  created:
    - ".planning/phases/14-live-session-governance-research/14-04-SPIKE-RESULTS.md"
  modified: []

key-decisions:
  - "OPE extract pipeline IS the post-task memory ingestion layer (no new component needed)"
  - "Real-time path = write-on-detect stubs (fidelity=1); post-task path = OPE enrichment (fidelity=2)"
  - "DDF co-pilot user delivery = next-session SessionStart only; within-session = context injection only"
  - "Bus transport LOCKED: Unix socket + uvicorn/starlette (1.6ms p99, 30x under target)"
  - "Phase 15 Wave 1 = deposit-first (flame_events + write-on-detect), no scaffolding"

patterns-established:
  - "Spike validation pattern: run existing tools against real data, measure, document findings"
  - "Two-tier fidelity model for memory_candidates (real-time stubs enriched by post-task pipeline)"

# Metrics
duration: 6min
completed: 2026-02-24
---

# Phase 14 Plan 04: OpenClaw Bus Spike Summary

**Validation spike confirming OPE pipeline as post-task memory layer (3.3s/session), bus transport at 1.6ms p99, and DDF delivery via SessionStart-only channel**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-02-24T01:29:55Z
- **Completed:** 2026-02-24T01:35:27Z
- **Tasks:** 4
- **Files created:** 1 (14-04-SPIKE-RESULTS.md)

## Accomplishments

- Validated OPE extract pipeline processes real session JSONL (498 events, 3.9MB) in 3.3s, producing 15 episodes with reaction labels, 131 constraint evaluations, and 38 amnesia events
- Compared per-prompt heuristic scan (49 flagged events, ~10-20% precision) vs full OPE pipeline (15 structured episodes with reaction labels) -- full-session context wins decisively
- Confirmed hook stdout visibility: PreToolUse stdout is protocol JSON (context injection, not user-visible), SessionStart additionalContext is the only user-visible channel
- Measured PolicyViolationChecker.check() at 0.082ms per call (332 constraints), yielding bus mode p99 of ~1.6ms -- 30x under the 50ms target
- Documented Phase 15 wave ordering with deposit-first mandate (5 waves, 4 load-bearing + 1 scaffolding)

## Task Commits

Each task was committed atomically:

1. **Task 1: Validate OPE pipeline as post-task memory layer** - `735d915` (docs)
2. **Task 2: DDF signal density comparison** - `2459699` (docs)
3. **Task 3: Hook stdout visibility and bus transport validation** - `e111177` (docs)
4. **Task 4: Spike synthesis and architectural decisions** - `384a566` (docs)

## Files Created/Modified

- `.planning/phases/14-live-session-governance-research/14-04-SPIKE-RESULTS.md` - Complete spike results with 5 sections: OPE validation, DDF signal density, hook visibility, bus transport, synthesis

## Decisions Made

1. **OPE pipeline IS the post-task memory ingestion layer** -- No new "memory ingestion component" needed. The governing orchestrator runs `python -m src.pipeline.cli extract` at CONFIRMED_END. Evidence: 15 episodes with reaction labels, 131 constraint evaluations, 38 amnesia events from a single 498-event session in 3.3s.

2. **Real-time path = stubs, post-task path = enrichment** -- Per-prompt heuristic scan produces 49 events at ~10-20% precision (keyword mentions, not violations). Full OPE produces 15 structured episodes. The two-tier fidelity model (fidelity=1 real-time + fidelity=2 post-task UPDATE) is validated.

3. **DDF delivery = SessionStart only for user-visible** -- PreToolUse stdout is protocol JSON (`hookSpecificOutput.additionalContext` = context injection for assistant, not TUI display). PostToolUse stdout is unspecified. SessionStart `additionalContext` is the only confirmed user-visible channel. Design option: PreToolUse can inject assistant-facing DDF hints (PAG hook demonstrates this).

4. **Bus transport LOCKED** -- PolicyViolationChecker.check() at 0.082ms, total bus p99 at ~1.6ms, direct mode fallback at ~70-95ms. All within budget. uvicorn 0.40.0 + starlette 0.52.1 + httpx 0.28.1 already installed.

## Deviations from Plan

None - plan executed exactly as written. All four spike questions were answered with empirical evidence.

**Note:** The OPE pipeline validation (Task 1) revealed a schema drift bug: `parent_episode_id` (added in Phase 14.1-01) is not in `orchestrator-episode.schema.json`, causing all 15 populated episodes to fail JSON Schema validation. This is a pre-existing bug (Rule 1), documented as a pre-Phase 15 fix requirement in the spike results. The pipeline functionality itself is confirmed working.

## Issues Encountered

- Episode validation failure due to `parent_episode_id` schema drift -- all 15 populated episodes failed JSON Schema validation but were fully populated with observation, action, outcome, reaction_label, scope. Escalation episodes (which bypass JSON Schema validation) stored successfully. Documented in SPIKE-RESULTS.md as pre-Phase 15 fix required.

## User Setup Required

None - no external service configuration required. This was a documentation-only spike.

## Next Phase Readiness

- Plan 14-05 (Phase 15+16 implementation blueprint) has unambiguous inputs from all 4 spike findings
- Pre-Phase 15 fix needed: update `orchestrator-episode.schema.json` to include `parent_episode_id` (optional string)
- Phase 15 Wave 1 must be deposit-first: flame_events schema + heuristic DDF detectors + write-on-detect to memory_candidates
- All architectural decisions for the governing daemon, bus transport, DDF co-pilot delivery, and memory ingestion are resolved

## Self-Check: PASSED

- FOUND: `.planning/phases/14-live-session-governance-research/14-04-SPIKE-RESULTS.md`
- FOUND: `.planning/phases/14-live-session-governance-research/14-04-SUMMARY.md`
- FOUND: `735d915` (Task 1 commit)
- FOUND: `2459699` (Task 2 commit)
- FOUND: `e111177` (Task 3 commit)
- FOUND: `384a566` (Task 4 commit)
- SPIKE-RESULTS.md contains 5 sections (verified)

---
*Phase: 14-live-session-governance-research*
*Completed: 2026-02-24*
