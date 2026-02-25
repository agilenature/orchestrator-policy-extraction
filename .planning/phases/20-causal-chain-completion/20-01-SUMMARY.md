---
phase: 20-causal-chain-completion
plan: 01
subsystem: database, api
tags: [duckdb, starlette, pydantic, push-links, causal-chain, bus-schema]

# Dependency graph
requires:
  - phase: 19-control-plane-integration
    provides: "Bus foundation (schema.py, models.py, server.py with 3 routes)"
provides:
  - "bus_sessions extended with repo, project_dir, transcript_path, event_count, outcome columns"
  - "push_links table with 7-column schema for cross-repo causal chain links"
  - "PushLink Pydantic model for push link validation"
  - "CheckResponse.epistemological_signals stub field (Gap 6 foundation)"
  - "/api/push-link stub route (returns 200, full handler in Plan 20-03)"
  - "/api/register stores repo metadata; /api/deregister stores event_count + outcome"
affects: [20-02-causal-chain-completion, 20-03-causal-chain-completion, 20-04-causal-chain-completion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ALTER TABLE ADD COLUMN IF NOT EXISTS for idempotent schema extension"
    - "File-based DuckDB + second connection (not read_only) for test verification"

key-files:
  created:
    - tests/test_bus_schema_extension.py
  modified:
    - src/pipeline/live/bus/schema.py
    - src/pipeline/live/bus/models.py
    - src/pipeline/live/bus/server.py
    - tests/test_bus_foundation.py

key-decisions:
  - "Used ALTER TABLE ADD COLUMN IF NOT EXISTS instead of try/except for DuckDB idempotency"
  - "DuckDB verification connections in tests use same-process read-write (not read_only) to avoid config mismatch"
  - "epistemological_signals field added to CheckResponse as empty list stub for Gap 6"

patterns-established:
  - "Schema extension via _alter_bus_sessions() called from create_bus_schema()"
  - "Stub routes inside create_app() closure with fail-open try/except"

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 20 Plan 01: Bus Schema Extension Summary

**DuckDB bus_sessions extended with 5 cross-repo attribution columns, push_links table created with 7-column causal link schema, PushLink model and /api/push-link stub route added**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T20:57:36Z
- **Completed:** 2026-02-25T21:01:15Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Extended bus_sessions from 5 to 10 columns with repo, project_dir, transcript_path, event_count, outcome
- Created push_links table with 7-column schema for cross-repo causal chain attribution (link_id PK, parent/child decision IDs, transition_trigger, repo_boundary, migration_run_id, captured_at)
- Added PushLink frozen Pydantic model and CheckResponse.epistemological_signals stub field
- Updated /api/register to store repo metadata and /api/deregister to store event_count + outcome
- Added /api/push-link stub route returning 200 (full handler deferred to Plan 20-03)
- 13 new tests covering schema, endpoints, and models; all 27 bus tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend DuckDB schema + Pydantic models** - `69afbdf` (feat)
2. **Task 2: Update server register/deregister + add push-link stub route** - `5867fe1` (feat)
3. **Task 3: Tests for schema extension and endpoint changes** - `7c41628` (test)

## Files Created/Modified
- `src/pipeline/live/bus/schema.py` - Added _BUS_SESSIONS_EXTENSIONS (5 ALTER TABLE statements), PUSH_LINKS_DDL, _alter_bus_sessions(), updated create_bus_schema()
- `src/pipeline/live/bus/models.py` - Added PushLink frozen model, added epistemological_signals field to CheckResponse
- `src/pipeline/live/bus/server.py` - Updated register (repo/project_dir/transcript_path), deregister (event_count/outcome), check (epistemological_signals), added push_link stub route
- `tests/test_bus_schema_extension.py` - 13 tests covering schema columns, push_links table, idempotency, register/deregister with new fields, push-link stub, model validation
- `tests/test_bus_foundation.py` - Updated test_bus_sessions_table_exists to expect 10 columns

## Decisions Made
- Used `ALTER TABLE ADD COLUMN IF NOT EXISTS` (DuckDB native) instead of try/except -- cleaner, does not mask real DDL failures
- DuckDB test verification connections use `duckdb.connect(db_path)` (same-process read-write) rather than `read_only=True` -- DuckDB disallows mixing read_only and read_write connections to the same file
- epistemological_signals added as `list[dict[str, Any]] = []` -- existing consumers unaffected, field ready for post-OpenClaw activation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DuckDB read_only connection conflict in tests**
- **Found during:** Task 3 (test creation)
- **Issue:** `duckdb.connect(db_path, read_only=True)` fails when create_app() already holds a read-write connection to the same file -- DuckDB does not allow mixed access modes
- **Fix:** Changed verification connections to `duckdb.connect(db_path)` (same-process read-write) which DuckDB allows
- **Files modified:** tests/test_bus_schema_extension.py
- **Verification:** All 13 tests pass
- **Committed in:** 7c41628 (Task 3 commit)

**2. [Rule 1 - Bug] Foundation test expected 5 columns, now 10**
- **Found during:** Task 3 (verification of existing tests)
- **Issue:** test_bus_sessions_table_exists in test_bus_foundation.py asserted exactly 5 columns, but create_bus_schema() now adds 5 extension columns via ALTER TABLE
- **Fix:** Updated assertion to expect all 10 columns with explanatory comment
- **Files modified:** tests/test_bus_foundation.py
- **Verification:** All 14 foundation tests pass
- **Committed in:** 7c41628 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Schema foundation complete for Plans 20-02 through 20-05
- push_links table ready for Plan 20-03 (full handler implementation)
- bus_sessions repo/project_dir/transcript_path columns ready for Plan 20-02 (cross-repo grouping)
- epistemological_signals stub ready for Plan 20-04 (Gap 6 activation)

---
*Phase: 20-causal-chain-completion*
*Completed: 2026-02-25*
