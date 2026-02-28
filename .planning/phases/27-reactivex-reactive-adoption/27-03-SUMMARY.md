---
phase: 27-reactivex-reactive-adoption
plan: 03
subsystem: pipeline
tags: [reactivex, rxpy, concurrency, batch-processing, observable]

# Dependency graph
requires:
  - phase: 27-01
    provides: "Spike validation of RxPY v4 patterns (ops.map+merge, cold observables)"
provides:
  - "RxPY-adopted run_batch() with configurable session-level fan-out"
  - "PipelineConfig.batch_max_concurrent field with validation"
  - "Behavioral parity tests for run_batch() observable pipeline"
affects: [27-04, pipeline-performance-tuning]

# Tech tracking
tech-stack:
  added: [reactivex (ops.merge in runner.py)]
  patterns: ["ops.map(cold_observable_factory).pipe(ops.merge(max_concurrent=N)) for configurable fan-out"]

key-files:
  created: []
  modified:
    - src/pipeline/runner.py
    - src/pipeline/models/config.py
    - tests/test_runner.py

key-decisions:
  - "Default max_concurrent=1 preserves sequential behavior -- parallelism is opt-in via config"
  - "Errors collected in batch_errors list via on_completed (not on_error) -- preserves existing error-collection contract"
  - "tqdm progress bar updates via on_next callback -- per-session granularity preserved"
  - "Mutable holders (list[int]) for total_events/total_episodes accumulation in closures"

patterns-established:
  - "Cold observable factory pattern: wrap synchronous function in rx.create(subscribe) with Disposable() return"
  - "Error resilience in observables: catch exceptions in subscribe, append to error list, call on_completed (not on_error)"

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 27 Plan 03: run_batch() RxPY Adoption Summary

**RxPY observable fan-out in run_batch() with ops.map+merge(max_concurrent=N), default sequential, config-controlled parallelism**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T15:29:16Z
- **Completed:** 2026-02-28T15:32:38Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Replaced sequential for-loop in run_batch() with RxPY observable pipeline using ops.map(factory).pipe(ops.merge(max_concurrent=N))
- Added PipelineConfig.batch_max_concurrent field with default=1 and positive integer validation
- All 16 existing runner tests pass unchanged -- behavioral parity confirmed
- Added 4 new behavioral parity tests (multi-session, empty dir, config wiring, error collection)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add batch_max_concurrent to PipelineConfig** - `ad1925e` (feat)
2. **Task 2: Adopt RxPY in run_batch()** - `d70f960` (feat)
3. **Task 3: Add runner behavioral parity test** - `f40043f` (test)

## Files Created/Modified
- `src/pipeline/models/config.py` - Added batch_max_concurrent field with Field(default=1) and field_validator
- `src/pipeline/runner.py` - Replaced for-loop with RxPY observable pipeline (reactivex imports, cold observable factory, ops.map+merge pattern)
- `tests/test_runner.py` - Added TestRunBatchRxBehavioralParity class with 4 tests

## Decisions Made
- Default max_concurrent=1 preserves sequential behavior exactly -- no config.yaml change needed, parallelism is opt-in
- Errors collected via on_completed (not on_error) to preserve existing error-collection contract where batch_errors accumulates without aborting
- tqdm progress bar moved from for-loop wrapper to on_next callback for per-session update granularity
- Used mutable list holders ([0]) for total_events/total_episodes accumulation in closure callbacks (Python closure rebinding limitation)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- run_batch() is now RxPY-adopted with configurable concurrency
- When profiling determines optimal max_concurrent value, it becomes a config.yaml change (not a code change)
- Ready for Phase 27 Plan 04 (remaining Tier 2/3 adoptions)

## Self-Check: PASSED

All files exist, all commits verified (ad1925e, d70f960, f40043f).

---
*Phase: 27-reactivex-reactive-adoption*
*Completed: 2026-02-28*
