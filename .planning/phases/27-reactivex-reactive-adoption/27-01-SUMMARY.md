---
phase: 27-reactivex-reactive-adoption
plan: 01
subsystem: testing
tags: [reactivex, rxpy, spike, observable, threadpool, duckdb]

# Dependency graph
requires:
  - phase: 25-genus-protocol-propagation
    provides: "Stable codebase for reactive adoption"
provides:
  - "reactivex>=4.0 dependency in requirements.txt"
  - "Validated external operator pattern for StreamProcessor shape"
  - "Validated map+merge fan-out with sync DuckDB writes"
  - "Validated ThreadPoolScheduler for CPU-bound work from sync context"
  - "Go/no-go gate: GO for all three adoption patterns"
affects: [27-02-embedder-adoption, 27-03-runner-adoption, 27-04-stream-processor-adoption]

# Tech tracking
tech-stack:
  added: [reactivex v4.1.0]
  patterns: [external-operator-pattern, map-merge-fanout, threadpool-scheduler-offload]

key-files:
  created: [tests/test_rx_spike.py]
  modified: [requirements.txt]

key-decisions:
  - "ThreadPoolScheduler.executor.shutdown() for cleanup -- dispose() does not exist in reactivex v4"
  - "subscribe_on(scheduler) on inner observables for thread offload -- not observe_on"
  - "Go/no-go verdict: GO -- all three patterns validated in OPE-compatible shapes"

patterns-established:
  - "External operator: rx.create(subscribe) wrapping stateful processor with cold semantics"
  - "Fan-out: ops.map(factory).pipe(ops.merge(max_concurrent=N)) for concurrent session processing"
  - "Thread offload: rx.create(subscribe).pipe(ops.subscribe_on(ThreadPoolScheduler)) for CPU-bound work"

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 27 Plan 01: ReactiveX Spike Summary

**Validated reactivex v4.1.0 external operator, map+merge fan-out, and ThreadPoolScheduler patterns against OPE's actual data shapes -- go/no-go gate: GO**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T15:21:46Z
- **Completed:** 2026-02-28T15:24:14Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added `reactivex>=4.0` to `requirements.txt` (project uses requirements.txt, not pyproject.toml)
- External operator pattern produces IDENTICAL GovernanceSignal sequence as direct `process_event()` calls, with verified cold semantics (independent state per subscription)
- map+merge fan-out with sync DuckDB writes produces identical row state at both `max_concurrent=1` and `max_concurrent=3`
- ThreadPoolScheduler offloads CPU-bound work to worker threads from sync-only context (no asyncio event loop required), producing identical results to sequential execution
- All 7 spike tests pass in 0.20s

## Task Commits

Each task was committed atomically:

1. **Task 1: Add reactivex dependency + spike test file** - `9be0907` (feat)

## Files Created/Modified
- `requirements.txt` - Added `reactivex>=4.0` under core dependencies
- `tests/test_rx_spike.py` - 468-line spike test file with 7 tests across 3 test classes

## Decisions Made
- **ThreadPoolScheduler cleanup:** `scheduler.executor.shutdown(wait=False)` is the correct cleanup method. `scheduler.dispose()` does not exist in reactivex v4. This is a new discovery not documented in Phase 18 axioms (Phase 18 used AsyncIOScheduler, not ThreadPoolScheduler).
- **subscribe_on for inner observables:** `ops.subscribe_on(scheduler)` applied to each inner observable (not `observe_on`) ensures the subscribe function runs on the thread pool.
- **Go/no-go: GO.** All three adoption patterns validated. Phase 27 plans 02-04 are unblocked.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ThreadPoolScheduler cleanup method**
- **Found during:** Task 1 (initial test run)
- **Issue:** Tests used `scheduler.dispose()` which does not exist on `ThreadPoolScheduler` in reactivex v4
- **Fix:** Changed to `scheduler.executor.shutdown(wait=False)` -- the underlying `ThreadPoolExecutor` exposes `shutdown()` via the `executor` attribute
- **Files modified:** `tests/test_rx_spike.py`
- **Verification:** All 7 tests pass after fix
- **Committed in:** `9be0907` (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minimal -- cleanup API discovery that will inform Plan 27-02 (embedder adoption).

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three adoption patterns validated -- Plans 27-02, 27-03, and 27-04 are unblocked
- Key pattern for Plan 27-02 (embedder): `rx.create(subscribe).pipe(ops.subscribe_on(ThreadPoolScheduler))` with `ops.merge(max_concurrent=N)`
- Key pattern for Plan 27-03 (runner): `ops.map(factory).pipe(ops.merge(max_concurrent=N))` with sync DuckDB writes inside observable
- Key pattern for Plan 27-04 (stream processor): External operator via `rx.create(subscribe)` with cold semantics
- No blockers

## Self-Check: PASSED

- FOUND: tests/test_rx_spike.py
- FOUND: requirements.txt with reactivex>=4.0
- FOUND: commit 9be0907
- FOUND: 27-01-SUMMARY.md

---
*Phase: 27-reactivex-reactive-adoption*
*Completed: 2026-02-28*
