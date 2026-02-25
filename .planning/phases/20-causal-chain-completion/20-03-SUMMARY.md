---
phase: 20-causal-chain-completion
plan: 03
subsystem: api, database
tags: [duckdb, starlette, push-links, causal-chain, sha256]

# Dependency graph
requires:
  - phase: 20-causal-chain-completion/01
    provides: push_links DuckDB table (7-col) and /api/push-link stub route
provides:
  - Full /api/push-link handler with DuckDB write, validation, deterministic ID generation
  - 10 tests covering T1 round-trip, validation, idempotency, auto-ID generation
affects: [20-04, 20-05, causal-chain-traversal]

# Tech tracking
tech-stack:
  added: [hashlib (stdlib)]
  patterns: [deterministic-id-via-sha256, fail-open-with-warning, timestamptz-utc-comparison]

key-files:
  created:
    - tests/test_push_links.py
  modified:
    - src/pipeline/live/bus/server.py

key-decisions:
  - "DuckDB TIMESTAMPTZ returns datetime objects converted to local TZ; tests compare via UTC conversion"
  - "Deterministic link_id: SHA-256[:16] of 'link:{parent}:{child}:{trigger}' ensures idempotent re-pushes"
  - "Fail open on DuckDB write errors: 200 with warning field, never 500"

patterns-established:
  - "Push link ID generation: hashlib.sha256(f'link:{parent}:{child}:{trigger}'.encode()).hexdigest()[:16]"
  - "TIMESTAMPTZ test pattern: row[N].astimezone(timezone.utc) for cross-timezone comparison"
  - "Validation pattern: 400 with detail listing missing fields, not fail-open"

# Metrics
duration: 3min
completed: 2026-02-25
---

# Phase 20 Plan 03: Push Link Handler Summary

**Full /api/push-link handler with DuckDB persistence, SHA-256 deterministic IDs, field validation, and T1 round-trip verification**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-25T21:04:24Z
- **Completed:** 2026-02-25T21:07:01Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Full /api/push-link handler replaces Plan 01 stub: validates 4 required fields, auto-generates deterministic link_id, writes to DuckDB push_links table, fails open on write errors
- T1 round-trip test: POST full payload, SELECT from DuckDB, all 7 fields match (including UTC-converted TIMESTAMPTZ)
- 10 tests covering validation, idempotency, auto-generated IDs, optional fields, custom timestamps, malformed JSON

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement full /api/push-link handler** - `8a10f69` (feat)
2. **Task 2: Push link tests including T1 round-trip** - `7ebabe8` (test)

## Files Created/Modified
- `src/pipeline/live/bus/server.py` - Full push_link handler: validates required fields, generates SHA-256[:16] link_id, writes to DuckDB push_links table via INSERT OR REPLACE, fails open on DuckDB errors
- `tests/test_push_links.py` - 10 tests: T1 round-trip, auto-generated IDs, deterministic ID generation, required field validation, multiple missing fields, malformed JSON, optional repo_boundary, idempotent insert, server-time default, custom captured_at

## Decisions Made
- DuckDB returns `datetime.datetime` objects for TIMESTAMPTZ columns, converted to local timezone. Tests compare by converting to UTC with `astimezone(timezone.utc)` rather than string comparison. This is a reusable pattern for all TIMESTAMPTZ verification.
- Used `duckdb.connect(db_path)` (not `read_only=True`) for verification connections, following the pattern established in test_bus_schema_extension.py -- DuckDB disallows mixed read_only/read_write connections to the same file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TIMESTAMPTZ comparison in T1 round-trip and custom timestamp tests**
- **Found during:** Task 2 (Push link tests)
- **Issue:** DuckDB returns `datetime.datetime` objects for TIMESTAMPTZ columns, not ISO strings. Tests comparing raw row values to strings failed.
- **Fix:** Convert DuckDB datetime to UTC via `astimezone(timezone.utc)` and compare year/month/day/hour components.
- **Files modified:** tests/test_push_links.py
- **Verification:** All 10 tests pass
- **Committed in:** 7ebabe8 (Task 2 commit)

**2. [Rule 1 - Bug] Used duckdb.connect(db_path) instead of read_only=True for verification**
- **Found during:** Task 2 (test fixture design)
- **Issue:** Plan specified `read_only=True` but existing test_bus_schema_extension.py documents that DuckDB disallows mixed read_only/read_write to same file
- **Fix:** Followed established pattern: `duckdb.connect(db_path)` without read_only flag
- **Files modified:** tests/test_push_links.py
- **Verification:** All 10 tests pass, no write-lock conflicts
- **Committed in:** 7ebabe8 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- /api/push-link is now fully functional: validates, generates IDs, writes to DuckDB, fails open
- Plan 04 (causal chain query endpoint) can proceed -- push_links table is populated via this handler
- Plan 05 (backward traversal) has the foundation it needs: push links are persistable and queryable
- No blockers

---
*Phase: 20-causal-chain-completion*
*Completed: 2026-02-25*
