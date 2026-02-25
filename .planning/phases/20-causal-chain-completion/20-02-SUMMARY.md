---
phase: 20-causal-chain-completion
plan: 02
subsystem: pipeline
tags: [session-start, bus-registration, fail-open, jsonl-staging, causal-chain]

# Dependency graph
requires:
  - phase: 19-control-plane-integration
    provides: "session_start.py hook with _post_json and bus registration"
provides:
  - "BUS_REGISTRATION_FAILED event emission to JSONL staging when bus unreachable"
  - "openclaw_unavailable flag distinguishing pre-OpenClaw from post-OpenClaw sessions"
  - "repo/project_dir/transcript_path metadata in register payload"
affects: [20-causal-chain-completion, bus-intelligence-layer]

# Tech tracking
tech-stack:
  added: []
  patterns: ["fail-open JSONL staging write via _append_event_to_staging", "conditional payload field inclusion based on env var presence"]

key-files:
  created:
    - tests/test_bus_registration_failed.py
  modified:
    - src/pipeline/live/hooks/session_start.py

key-decisions:
  - "BUS_REGISTRATION_FAILED written to JSONL staging (not bus) since bus is down when this fires"
  - "openclaw_unavailable is boolean flag, not string, for direct truthiness check"
  - "Register payload omits repo/project_dir/transcript_path when env vars empty (sparse payload)"

patterns-established:
  - "_append_event_to_staging: fail-open JSONL append for governance events during hook execution"
  - "Conditional payload enrichment: include metadata fields only when env vars are non-empty"

# Metrics
duration: 2min
completed: 2026-02-25
---

# Phase 20 Plan 02: BUS_REGISTRATION_FAILED + openclaw_unavailable Summary

**BUS_REGISTRATION_FAILED event emission to JSONL staging when bus unreachable, plus openclaw_unavailable flag distinguishing pre-OpenClaw sessions in register payload**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T20:58:12Z
- **Completed:** 2026-02-25T21:00:34Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- session_start.py emits BUS_REGISTRATION_FAILED to JSONL staging when bus returns empty dict
- Register payload carries `openclaw_unavailable: true` when OPE_RUN_ID env var is absent
- Register payload includes repo, project_dir, transcript_path when corresponding env vars are set
- 10 new tests covering all behaviors; 14 existing tests still pass
- Fail-open preserved: staging write failure silently caught, hook always exits 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Add BUS_REGISTRATION_FAILED emission + openclaw_unavailable flag** - `d4ebeb2` (feat)
2. **Task 2: Tests for BUS_REGISTRATION_FAILED and openclaw_unavailable** - `ce8bcb8` (test)

## Files Created/Modified
- `src/pipeline/live/hooks/session_start.py` - Added _append_event_to_staging helper, BUS_REGISTRATION_FAILED emission on bus failure, openclaw_unavailable flag in register payload, repo/project_dir/transcript_path metadata fields
- `tests/test_bus_registration_failed.py` - 10 tests covering event emission, field completeness, fail-open behavior, openclaw_unavailable flag, payload metadata inclusion/exclusion

## Decisions Made
- BUS_REGISTRATION_FAILED written to local JSONL staging file (not the bus) since the bus is unreachable when this event fires -- the governing orchestrator reads staging files during post-session analysis
- openclaw_unavailable is a boolean flag (not a string) for direct truthiness checks in downstream consumers
- Register payload uses sparse inclusion: repo/project_dir/transcript_path fields only present when their env vars are non-empty, avoiding empty-string noise

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Gaps 3 (BUS_REGISTRATION_FAILED not emitted) and 5 (no openclaw_unavailable flag) are now closed
- Ready for Plan 20-03 (decision artifact linkage) and subsequent plans
- Existing bus connection tests (14) continue to pass alongside new tests (10)

## Self-Check: PASSED

- FOUND: src/pipeline/live/hooks/session_start.py
- FOUND: tests/test_bus_registration_failed.py
- FOUND: 20-02-SUMMARY.md
- FOUND: d4ebeb2 (Task 1 commit)
- FOUND: ce8bcb8 (Task 2 commit)

---
*Phase: 20-causal-chain-completion*
*Completed: 2026-02-25*
