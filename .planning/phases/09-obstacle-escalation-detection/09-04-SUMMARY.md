---
phase: 09-obstacle-escalation-detection
plan: 04
subsystem: pipeline
tags: [escalation, integration, duckdb, shadow-reporter, idempotent]

# Dependency graph
requires:
  - phase: 09-02
    provides: EscalationDetector with sliding window detection
  - phase: 09-03
    provides: EscalationConstraintGenerator with three-tier severity
  - phase: 01-02
    provides: Staging table upsert pattern for DuckDB
  - phase: 05-03
    provides: ShadowReporter with PASS/FAIL gate metrics
provides:
  - End-to-end escalation detection wired into PipelineRunner
  - Escalation episodes written to DuckDB with 6 escalate_* columns
  - write_escalation_episodes() for idempotent MERGE upsert
  - ShadowReporter escalation metrics (3 new metrics)
  - unapproved_escalation_rate headline gate metric with PASS/FAIL
  - 12 integration tests for full pipeline escalation flow
affects: [phase-10-decision-durability, phase-11-wisdom-layer, phase-12-governance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Escalation episode SHA-256 content-derived IDs for idempotent UPSERT"
    - "Separate write_escalation_episodes() for escalate_* column handling"
    - "Approval status mapping: approve->APPROVED, block/correct->REJECTED, else->UNAPPROVED"

key-files:
  created:
    - tests/test_escalation_integration.py
  modified:
    - src/pipeline/runner.py
    - src/pipeline/storage/writer.py
    - src/pipeline/shadow/reporter.py

key-decisions:
  - "Escalation detection runs as Step 13 after constraint extraction (Step 12)"
  - "_determine_approval_status() maps reactions to APPROVED/REJECTED/UNAPPROVED"
  - "write_escalation_episodes() uses separate staging table for clean MERGE with escalate_* columns"
  - "Escalation metrics computed from episodes table, not shadow_mode_results"
  - "unapproved_escalation_rate is headline PASS/FAIL gate (target: 0.0%)"

patterns-established:
  - "Content-derived episode IDs: SHA-256(session_id + block_event_ref + bypass_event_ref + detector_version_major)[:16]"
  - "Approval status three-way: APPROVED, REJECTED, UNAPPROVED"
  - "Escalation metrics as sub-dict in ShadowReporter report"

# Metrics
duration: 8min
completed: 2026-02-20
---

# Phase 9 Plan 4: Pipeline Integration Summary

**End-to-end escalation detection wired into PipelineRunner with DuckDB episode storage, constraint generation, ShadowReporter metrics, and 12 integration tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20T00:58:16Z
- **Completed:** 2026-02-20T01:06:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- PipelineRunner.run_session() now detects escalation sequences via EscalationDetector and writes mode=ESCALATE episodes with all 6 escalate_* columns
- Auto-generated constraints from escalation detections added to ConstraintStore with status=candidate and source=inferred_from_escalation
- ShadowReporter computes and formats 3 escalation metrics with unapproved_escalation_rate as PASS/FAIL headline gate
- 12 integration tests prove correctness, idempotency, read-only exemption, approval status mapping, and reporter metrics
- Full test suite: 529 tests passing (zero regressions from 517 baseline)

## Task Commits

Each task was committed atomically:

1. **Task 1: Pipeline runner escalation step and episode writer extension** - `d436570` (feat)
2. **Task 2: Shadow reporter escalation metrics and integration tests** - `86f5f63` (feat)

## Files Created/Modified
- `src/pipeline/runner.py` - Added Step 13 escalation detection, _determine_approval_status(), escalation stats in result
- `src/pipeline/storage/writer.py` - Added write_escalation_episodes() and _merge_single_escalation_episode() for MERGE upsert
- `src/pipeline/shadow/reporter.py` - Added _compute_escalation_metrics() and "Escalation Metrics:" format section
- `tests/test_escalation_integration.py` - 12 integration tests across 4 test classes

## Decisions Made
- Escalation detection placed as Step 13, after existing constraint extraction (Step 12), because it needs tagged_events and populated_episodes for reaction context
- Approval status mapping is a three-way classification (APPROVED for approve, REJECTED for block/correct, UNAPPROVED for everything else including silence)
- write_escalation_episodes() is a separate function from write_episodes() because escalation episodes have different column requirements (6 escalate_* columns, no observation STRUCT)
- Escalation metrics query the episodes table directly (not shadow_mode_results) since escalation data lives in the episodes table

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 9 is now COMPLETE (4/4 plans delivered)
- Escalation detection is fully integrated into the pipeline
- Running `python -m src.pipeline.cli extract` will detect escalation sequences and store them as episodes
- Ready for Phase 10 (Decision Durability) or Phase 11 (Wisdom Layer)
- All prior phase functionality preserved (529 tests passing)

---
*Phase: 09-obstacle-escalation-detection*
*Completed: 2026-02-20*
