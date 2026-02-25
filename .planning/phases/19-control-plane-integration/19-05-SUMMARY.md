---
phase: 19-control-plane-integration
plan: 05
subsystem: governance-bus
tags: [integration-tests, cli, architecture-docs, duckdb, starlette, httpx, click]

# Dependency graph
requires:
  - phase: 19-01
    provides: Bus foundation (DuckDB schema, Starlette server, session-facing API)
  - phase: 19-02
    provides: Stream processor (JSONL tail, state machine, signal routing)
  - phase: 19-03
    provides: GovernorDaemon + ConstraintBriefing + /api/check wiring
  - phase: 19-04
    provides: PAG hook bus wiring + SessionStart hook
provides:
  - Cross-session run_id grouping integration tests (Phase 19 validation criterion)
  - Builder-Operator Boundary specification (Layer 1 canon)
  - Bus CLI (start + status commands)
  - Updated PROGRAM-SEQUENCE.md with Phase 19 completion
affects: [phase-20, modernizing-tool-platform-core]

# Tech tracking
tech-stack:
  added: []
  patterns: [bus-cli-lifecycle, builder-operator-structural-separation]

key-files:
  created:
    - tests/test_bus_integration.py
    - docs/architecture/BUILDER-OPERATOR-BOUNDARY.md
    - src/pipeline/cli/bus.py
  modified:
    - src/pipeline/cli/__main__.py
    - .planning/PROGRAM-SEQUENCE.md

key-decisions:
  - "DuckDB read_only=True cannot coexist with active read-write connection on same file; use default mode for test verification"
  - "Bus CLI defers to uvicorn for Unix socket serving (no custom socket management)"
  - "Skills Pack authorship protocol documented but deferred to post-OpenClaw-installation"

patterns-established:
  - "Integration tests use httpx ASGITransport with Starlette app for in-process API testing"
  - "Bus CLI follows existing CLI group pattern (click group + add_command in __main__.py)"

# Metrics
duration: 7min
completed: 2026-02-25
---

# Phase 19 Plan 05: Integration + Boundary Documentation Summary

**Cross-session run_id grouping validated by 9 integration tests, builder-operator boundary documented as Layer 1 canon, bus CLI scaffolding complete**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-25T18:40:46Z
- **Completed:** 2026-02-25T18:47:45Z
- **Tasks:** 5
- **Files modified:** 5

## Accomplishments
- THE critical test passes: two sessions with shared run_id both appear in bus_sessions under that run_id in DuckDB
- Cross-session constraint delivery verified: both sessions receive identical constraint briefing via /api/check
- Bus read-channel enforcement confirmed: /api/constraints returns 404 (no write endpoint exists)
- Builder-Operator Boundary specification created as Layer 1 canon artifact grounded in Phase 19 CONTEXT.md
- PROGRAM-SEQUENCE.md updated: Phase 19 marked COMPLETE, Step 7 (MT repo creation) now READY
- Bus CLI operational: `python -m src.pipeline.cli bus start|status`

## Task Commits

Each task was committed atomically:

1. **Task 1: Integration tests** - `43fcc9c` (test) - 7 async integration tests
2. **Task 2: Builder-Operator Boundary doc** - `b782302` (docs) - 174 lines, 5 sections
3. **Task 3: PROGRAM-SEQUENCE.md update** - `db99bc8` (docs) - Phase 19 complete, Step 7 READY
4. **Task 4: Bus CLI** - `103b0ff` (feat) - start + status commands, registered in __main__.py
5. **Task 5: CLI tests** - `b5c0479` (test) - 2 CLI tests (status no-socket, start idempotent guard)

## Files Created/Modified
- `tests/test_bus_integration.py` - 9 tests: cross-session grouping, constraint delivery, fail-open, read-channel, CLI
- `docs/architecture/BUILDER-OPERATOR-BOUNDARY.md` - Layer 1 canon: role separation, OPE_RUN_ID injection, bus enforcement
- `src/pipeline/cli/bus.py` - Click group with start (uvicorn on Unix socket) and status commands
- `src/pipeline/cli/__main__.py` - Added bus_group import and registration
- `.planning/PROGRAM-SEQUENCE.md` - Phase 19 COMPLETE, step headers updated, MT repo creation READY

## Decisions Made
- Used `duckdb.connect(db_path)` without `read_only=True` for test verification queries (DuckDB does not allow read-only connection to same file with active read-write connection)
- Skills Pack authorship protocol documented as deferred (enforcement requires OpenClaw session dispatch infrastructure)
- Bus CLI `start` command exits 1 if socket file already exists (idempotent guard without PID checking)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DuckDB read_only connection conflict**
- **Found during:** Task 1 (integration tests)
- **Issue:** `duckdb.connect(db_path, read_only=True)` raises ConnectionException when server's read-write connection is still open on the same file
- **Fix:** Changed to `duckdb.connect(db_path)` (default read-write mode) for test verification queries
- **Files modified:** tests/test_bus_integration.py
- **Verification:** All 7 integration tests pass after fix
- **Committed in:** 43fcc9c (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor -- DuckDB connection mode incompatibility resolved without changing test semantics.

## Issues Encountered
None beyond the auto-fixed deviation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 19 is complete: all 5 plans delivered across 3 waves
- OPE Governance Bus is operational with 1787 passing tests (3 pre-existing failures in segmenter/premise gate unrelated to Phase 19)
- MT Step 7 (repo creation) is now READY -- human can create the 6 platform repos
- Cross-project dependency satisfied: Phase 19 bus must be operational before MT sessions register OPE_RUN_ID

## Self-Check: PASSED

All 5 created/modified files verified present. All 5 task commit hashes verified in git log.

---
*Phase: 19-control-plane-integration*
*Completed: 2026-02-25*
