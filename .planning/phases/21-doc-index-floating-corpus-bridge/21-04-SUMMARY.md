---
phase: 21-doc-index-floating-corpus-bridge
plan: 04
subsystem: testing
tags: [integration-tests, duckdb, doc-index, governor-daemon, starlette]

# Dependency graph
requires:
  - phase: 21-02
    provides: "doc_indexer.py with 3-tier extraction and reindex_docs()"
  - phase: 21-03
    provides: "GovernorDaemon._query_relevant_docs(), /api/check docs, session_start.py printing"
provides:
  - "13 integration tests validating full doc index pipeline end-to-end"
  - "Pipeline verification: reindex -> doc_index -> daemon query -> /api/check -> session_start"
  - "Idempotency, ordering, deduplication, and no-constraint-axis-join verified"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["pytest.approx for DuckDB FLOAT comparisons", "tmp_path-based DuckDB pipeline testing"]

key-files:
  created:
    - tests/test_doc_integration.py
  modified: []

key-decisions:
  - "Used pytest.approx(abs=1e-6) for DuckDB FLOAT confidence comparisons (0.7 stored as 0.699999988079071)"
  - "Test docs include frontmatter, header, comment, unclassified, and always-show variants"
  - "Test 13 proves no constraint-axis join by using empty constraints.json with populated doc_index"

patterns-established:
  - "DuckDB FLOAT precision: always use pytest.approx for confidence comparisons round-tripping through DuckDB"
  - "Pipeline integration pattern: setup (db + docs + memory), reindex, query, assert"

# Metrics
duration: 4min
completed: 2026-02-27
---

# Phase 21 Plan 04: Doc Index Integration Tests Summary

**13 integration tests verifying full doc index pipeline: reindex -> DuckDB doc_index -> GovernorDaemon query -> /api/check delivery with always-show ordering and no constraint-axis join**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-27T15:38:53Z
- **Completed:** 2026-02-27T15:43:14Z
- **Tasks:** 2
- **Files created:** 1

## Accomplishments
- Full pipeline integration verified: reindex_docs() populates doc_index, GovernorDaemon queries it, /api/check delivers results
- Idempotency confirmed: running reindex twice produces identical row counts
- 3-tier extraction verified: frontmatter (1.0), regex/header (0.7), regex/comment (0.7)
- Unclassified docs stored but excluded from daemon queries
- always-show docs ordered first in results, max 3 docs returned
- No constraint-axis join: docs delivered independently of constraints.json state
- Full regression: 1912 tests total, 1910 passing, 2 pre-existing segmenter failures (X_ASK end-trigger -- unchanged)

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end integration tests** - `6e4d561` (test)
2. **Task 2: Full regression check** - no commit (verification-only task, no files created)

## Files Created/Modified
- `tests/test_doc_integration.py` - 13 integration tests for the full doc index pipeline

## Decisions Made
- Used `pytest.approx(abs=1e-6)` for DuckDB FLOAT confidence comparisons -- DuckDB stores FLOAT as 32-bit, so 0.7 round-trips as 0.699999988079071
- Created temp MEMORY.md files with known CCD axes for test isolation instead of using memory_candidates table

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed DuckDB FLOAT precision in confidence assertions**
- **Found during:** Task 1 (integration tests)
- **Issue:** DuckDB FLOAT column stores 0.7 as 32-bit float (0.699999988079071), causing exact equality assertions to fail
- **Fix:** Changed `assert rows[0][2] == 0.7` to `assert rows[0][2] == pytest.approx(0.7, abs=1e-6)` in tier2 tests
- **Files modified:** tests/test_doc_integration.py
- **Verification:** All 13 tests pass
- **Committed in:** 6e4d561 (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for test correctness. No scope creep.

## Issues Encountered
- pytest-timeout plugin not installed (--timeout=60 flag rejected). Ran tests without timeout. All tests complete within 80 seconds.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 21 is complete: all 4 plans delivered, all 64 Phase 21 tests passing
- Doc index pipeline fully operational: schema, extraction, CLI, daemon query, /api/check delivery, session_start printing
- Ready for production use: `python -m src.pipeline.cli docs reindex` populates doc_index, sessions receive relevant docs at start

## Self-Check: PASSED

- FOUND: tests/test_doc_integration.py
- FOUND: 21-04-SUMMARY.md
- FOUND: commit 6e4d561
- VERIFIED: 13 tests collected

---
*Phase: 21-doc-index-floating-corpus-bridge*
*Completed: 2026-02-27*
