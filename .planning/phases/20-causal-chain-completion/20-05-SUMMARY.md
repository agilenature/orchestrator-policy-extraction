---
phase: 20-causal-chain-completion
plan: 05
subsystem: testing
tags: [integration-tests, duckdb, starlette, httpx, pytest-asyncio, governance-bus]

# Dependency graph
requires:
  - phase: 20-01
    provides: bus_sessions schema extension + push_links table
  - phase: 20-02
    provides: BUS_REGISTRATION_FAILED emission + openclaw_unavailable flag
  - phase: 20-03
    provides: /api/push-link handler with DuckDB persistence
  - phase: 20-04
    provides: GovernorDaemon repo scope filter + /api/check wiring
provides:
  - 14 integration tests validating all 6 Phase 20 structural gaps end-to-end
  - Full regression verification (1843 passing, 2 pre-existing failures)
affects: [phase-20-completion, causal-chain-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [gap-numbered test classes, file-based DuckDB integration with httpx AsyncClient]

key-files:
  created:
    - tests/test_causal_chain_integration.py
  modified: []

key-decisions:
  - "Used duckdb.connect(db_path) without read_only=True for verification reads, matching proven Plan 01/03 pattern"
  - "Moved sync test_check_response_model_has_field out of @pytest.mark.asyncio class to eliminate pytest warning"

patterns-established:
  - "Integration test pattern: create_app per test method with tmp_path DuckDB, AsyncClient context manager, then separate verification connection after context exit"

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 20 Plan 05: Integration Tests Summary

**14 integration tests across 6 gap-numbered classes validating all Phase 20 causal chain structural gaps end-to-end**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T21:11:45Z
- **Completed:** 2026-02-25T21:16:55Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- 14 integration tests organized into 6 test classes (TestGap1 through TestGap6) mapping 1:1 to Phase 20 structural gaps
- Full end-to-end coverage: actual Starlette app, actual DuckDB writes, actual session_start behavior via mocks
- Full regression check: 1843 tests passing, 2 pre-existing segmenter failures (unchanged), zero new failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Integration tests for all 6 gaps** - `0744223` (test)
2. **Task 2: Full regression check** - no commit (verification only, no code changes)

## Files Created/Modified
- `tests/test_causal_chain_integration.py` - 14 integration tests: Gap 1 bus schema (3), Gap 2 push links (3), Gap 3 registration failed (2), Gap 4 repo scope (2), Gap 5 openclaw flag (2), Gap 6 epistemological signals (2)

## Decisions Made
- Used `duckdb.connect(db_path)` without `read_only=True` for verification connections, matching the pattern established in Plans 01 and 03 (DuckDB disallows mixed read_only/read_write connections to the same file)
- Moved the sync `test_check_response_model_has_field` out of the `@pytest.mark.asyncio` TestGap6 class to eliminate a pytest warning about sync functions in async-marked classes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Moved sync test out of async-marked class**
- **Found during:** Task 1
- **Issue:** `test_check_response_model_has_field` is a sync function but was inside `@pytest.mark.asyncio` class TestGap6, producing a pytest warning
- **Fix:** Moved to module-level as `test_gap6_check_response_model_has_field()`
- **Files modified:** tests/test_causal_chain_integration.py
- **Verification:** All 14 tests pass with zero warnings
- **Committed in:** 0744223

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Minor cleanup to eliminate warning. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 20 is now complete: all 5 plans delivered, all 6 structural gaps closed
- All Phase 20 success criteria verified by integration tests:
  1. bus_sessions stores repo/project_dir/transcript_path; deregister stores event_count/outcome
  2. push_links table with T1 round-trip verified
  3. BUS_REGISTRATION_FAILED emitted when bus unavailable
  4. openclaw_unavailable flag in register payload when OPE_RUN_ID absent
  5. GovernorDaemon filters constraints by repo scope
  6. /api/check includes epistemological_signals: []
- Total test count: 1845 (1843 passing + 2 pre-existing segmenter failures)
- Ready for post-OpenClaw activation phases

## Self-Check: PASSED

- FOUND: tests/test_causal_chain_integration.py
- FOUND: commit 0744223

---
*Phase: 20-causal-chain-completion*
*Completed: 2026-02-25*
