---
phase: 27-reactivex-reactive-adoption
plan: 02
subsystem: pipeline
tags: [reactivex, rxpy, embedder, threadpool, observable, sentence-transformers, duckdb]

# Dependency graph
requires:
  - phase: 27-01-spike
    provides: "Validated ThreadPoolScheduler pattern, create_work_observable shape, merge(max_concurrent) fan-out"
provides:
  - "src/pipeline/rx_operators.py shared RxPY utility module with create_work_observable"
  - "RxPY-adopted embed_episodes() with ThreadPoolScheduler(max_workers=4) parallelism"
  - "Behavioral parity test validating contract preservation post-adoption"
affects: [27-03-runner-adoption, 27-04-stream-processor-adoption]

# Tech tracking
tech-stack:
  added: []
  patterns: [create-work-observable-factory, map-subscribe_on-merge-pattern, do_action-sequential-writes]

key-files:
  created: [src/pipeline/rx_operators.py]
  modified: [src/pipeline/rag/embedder.py, tests/test_embedder.py]

key-decisions:
  - "ThreadPoolScheduler(max_workers=4) for sync CLI context -- supersedes CONTEXT.md run_in_executor direction for embedder"
  - "DuckDB writes in do_action(on_next=) callback for sequential write safety after merge serializes emissions"
  - "scheduler.executor.shutdown(wait=True) for cleanup -- wait=True ensures all threads complete before returning stats"
  - "Early return when rows empty (before creating scheduler) to avoid unnecessary thread pool allocation"

patterns-established:
  - "create_work_observable(fn, *args, **kwargs) factory: cold observable wrapping sync work, reusable across pipeline"
  - "map(lambda x: create_work_observable(fn, x).pipe(ops.subscribe_on(scheduler))).pipe(ops.merge(max_concurrent=N)): standard parallelism pattern"
  - "do_action(on_next=write_fn): sequential side-effects after merge serialization"

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 27 Plan 02: Embedder RxPY Adoption Summary

**RxPY-parallelized embed_episodes() with ThreadPoolScheduler(max_workers=4) for concurrent model.encode() calls, shared rx_operators.py utility, all 19 tests passing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T15:28:32Z
- **Completed:** 2026-02-28T15:31:53Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created `src/pipeline/rx_operators.py` with `create_work_observable` factory -- reusable across runner and stream processor adoptions
- Replaced sequential for-loop in `embed_episodes()` with RxPY observable pipeline: `map -> subscribe_on(ThreadPoolScheduler) -> merge(max_concurrent=4) -> do_action(write)`
- DuckDB writes remain sequential on subscriber thread via `do_action(on_next=)` after merge serializes emissions
- All 18 existing embedder tests pass without any modification to test assertions -- behavioral parity confirmed
- Added new `test_embed_episodes_rx_behavioral_parity` test validating full contract (return values, row counts, id presence, idempotency)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create shared rx_operators.py + adopt embedder** - `e801f16` (feat)
2. **Task 2: Add embedder-specific RxPY behavioral parity test** - `3706fad` (test)

## Files Created/Modified
- `src/pipeline/rx_operators.py` - Shared RxPY utility with `create_work_observable` cold observable factory
- `src/pipeline/rag/embedder.py` - RxPY-adopted `embed_episodes()` with ThreadPoolScheduler parallelism
- `tests/test_embedder.py` - Added `test_embed_episodes_rx_behavioral_parity` (N=3 episodes, both tables, idempotency)

## Decisions Made
- **ThreadPoolScheduler over run_in_executor:** `embed_episodes()` is called from sync CLI with no asyncio event loop. `run_in_executor` requires an event loop. ThreadPoolScheduler is the correct sync-compatible pattern. Supersedes CONTEXT.md direction for embedder only (per spike finding).
- **wait=True for shutdown:** Changed from spike's `wait=False` to `wait=True` to ensure all thread pool work completes before counting embedded_ids and returning stats. This prevents a race where stats could be incomplete.
- **Early return before scheduler creation:** When `rows` is empty, return immediately without creating a ThreadPoolScheduler. Avoids unnecessary thread pool allocation for the common idempotent-rerun case.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `src/pipeline/rx_operators.py` is ready for import by Plan 27-03 (runner adoption) and Plan 27-04 (stream processor adoption)
- The `create_work_observable` + `subscribe_on(scheduler)` + `merge(max_concurrent=N)` pattern is validated in production code
- Runner adoption (Plan 27-03) is the next target -- more complex due to stateful session processing

## Self-Check: PASSED

- FOUND: src/pipeline/rx_operators.py
- FOUND: src/pipeline/rag/embedder.py
- FOUND: tests/test_embedder.py
- FOUND: 27-02-SUMMARY.md
- FOUND: commit e801f16
- FOUND: commit 3706fad

---
*Phase: 27-reactivex-reactive-adoption*
*Completed: 2026-02-28*
