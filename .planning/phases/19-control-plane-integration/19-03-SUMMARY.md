---
phase: 19-control-plane-integration
plan: 03
subsystem: governance-bus
tags: [starlette, pydantic, constraints, daemon, json]

# Dependency graph
requires:
  - phase: 19-01
    provides: "Bus server scaffold with /api/check stub and daemon parameter"
  - phase: 19-02
    provides: "Stream processor state machine for signal routing"
  - phase: 03-constraint-management
    provides: "ConstraintStore and data/constraints.json format"
provides:
  - "GovernorDaemon: stateless constraint reader from constraints.json"
  - "ConstraintBriefing: severity-ordered frozen model for wire delivery"
  - "generate_briefing(): sorts constraints by severity (forbidden > requires_approval > warning)"
  - "/api/check endpoint now returns real constraints via daemon"
affects: [19-04, 19-05, LIVE-06-interventions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stateless daemon: reads fresh from JSON on each request, no caching"
    - "Fail-open constraint delivery: missing/malformed JSON returns empty list"
    - "DuckDB single-writer invariant: daemon reads constraints.json, never ope.db"

key-files:
  created:
    - src/pipeline/live/governor/__init__.py
    - src/pipeline/live/governor/briefing.py
    - src/pipeline/live/governor/daemon.py
    - tests/test_governing_daemon.py
  modified:
    - src/pipeline/live/bus/server.py
    - tests/test_bus_foundation.py

key-decisions:
  - "Flat constraint list (not grouped by ccd_axis) matches server.py wire format and CheckResponse model"
  - "Daemon reads constraints.json directly instead of ConstraintStore class to avoid import coupling"
  - "Default GovernorDaemon created when none provided to create_app() -- /api/check always delivers real constraints"
  - "Status filtering: constraints without status field default to active (consistent with ConstraintStore)"

patterns-established:
  - "Governor package pattern: briefing.py (model + generation) + daemon.py (file reader) + __init__.py (exports)"
  - "Test isolation via constraints_path parameter + tmp_path (no monkeypatch.chdir required for daemon tests)"

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 19 Plan 03: Governing Daemon Summary

**GovernorDaemon reads active constraints from constraints.json and delivers severity-ordered ConstraintBriefings via /api/check**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T18:31:28Z
- **Completed:** 2026-02-25T18:36:36Z
- **Tasks:** 5
- **Files modified:** 6

## Accomplishments

- ConstraintBriefing model with severity ordering (forbidden > requires_approval > warning)
- GovernorDaemon stateless reader filtering retired/superseded constraints from JSON
- /api/check endpoint upgraded from stub to real constraint delivery
- 21 tests covering briefing generation, daemon reading, and /api/check integration

## Task Commits

Each task was committed atomically:

1. **Task 1: ConstraintBriefing model + generate_briefing()** - `e21b99c` (feat)
2. **Task 2: GovernorDaemon** - `10d5f5e` (feat)
3. **Task 3: Wire daemon into /api/check** - `4bab5b3` (feat)
4. **Task 4: Package init** - `d84b9f8` (chore)
5. **Task 5: Tests (21 tests)** - `0f2cf83` (test)

## Files Created/Modified

- `src/pipeline/live/governor/__init__.py` - Package exports: ConstraintBriefing, generate_briefing, GovernorDaemon
- `src/pipeline/live/governor/briefing.py` - ConstraintBriefing frozen model + generate_briefing() severity sorter
- `src/pipeline/live/governor/daemon.py` - GovernorDaemon: stateless JSON reader with retired/superseded filtering
- `src/pipeline/live/bus/server.py` - /api/check now calls daemon.get_briefing() instead of returning stub
- `tests/test_governing_daemon.py` - 21 tests: 8 briefing, 10 daemon, 3 integration
- `tests/test_bus_foundation.py` - Updated fixture to use isolated daemon (prevents reading real constraints.json)

## Decisions Made

- **Flat list over grouped-by-axis:** The ConstraintBriefing uses a flat `constraints` list rather than `by_axis` grouping because the existing server.py wire format (`briefing.constraints`) and CheckResponse model expect flat lists. No constraints currently have `ccd_axis` field anyway (0/274).
- **Direct JSON read over ConstraintStore:** The daemon reads constraints.json directly with `json.loads()` rather than importing ConstraintStore. This avoids coupling the live bus process to ConstraintStore's schema validation and logging dependencies.
- **Default daemon creation:** When `create_app()` is called without a daemon, it creates a default GovernorDaemon. This means /api/check always delivers real constraints rather than falling through to the empty stub.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_bus_foundation fixture isolation**
- **Found during:** Task 3 (wiring daemon into server.py)
- **Issue:** Existing `test_check_stub_returns_empty` test failed because the default GovernorDaemon reads real `data/constraints.json` (274 constraints) when no daemon is provided
- **Fix:** Updated the `app` fixture in `test_bus_foundation.py` to inject a GovernorDaemon with a non-existent constraints_path, isolating tests from real data
- **Files modified:** tests/test_bus_foundation.py
- **Verification:** All 14 existing bus foundation tests pass
- **Committed in:** `4bab5b3` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for test isolation after server behavior change. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Governing daemon complete: /api/check delivers real constraints
- Ready for Plan 19-04 (Wave 2 parallel): constraint evaluation and policy feedback
- Interventions list remains empty (LIVE-06 deferred) -- will be populated when DDF co-pilot integration lands
- 62 total Phase 19 tests passing (14 bus + 21 daemon + 27 stream processor)

## Self-Check: PASSED

All 6 files verified present. All 5 task commits verified in git log.

---
*Phase: 19-control-plane-integration*
*Completed: 2026-02-25*
