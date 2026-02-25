---
phase: 19-control-plane-integration
plan: 01
subsystem: governance-bus
tags: [duckdb, starlette, pydantic, unix-socket, async]

# Dependency graph
requires: []
provides:
  - "bus_sessions + governance_signals DuckDB tables (schema.py)"
  - "BusSession, GovernanceSignal, CheckRequest, CheckResponse Pydantic models (models.py)"
  - "Starlette app with /api/register, /api/deregister, /api/check endpoints (server.py)"
  - "create_bus_schema() idempotent DDL function"
  - "Fail-open server design (DuckDB errors return 200, never 500)"
affects:
  - 19-02-stream-processor-wiring (emits GovernanceSignals to governance_signals table)
  - 19-03-governing-daemon (implements /api/check fully via daemon injection)
  - 19-04-pag-hook-bus-integration (calls /api/check from PreToolUse hook)
  - 19-05-end-to-end-integration (full bus integration test)

# Tech tracking
tech-stack:
  added: [starlette, httpx (test)]
  patterns:
    - "Fail-open server: DuckDB errors return 200 with empty payload"
    - "Daemon injection: create_app(daemon=obj) for 19-03 governing daemon"
    - "Body-read-once: async request body read once, cached for error handling"
    - "INSERT OR REPLACE for idempotent session registration"

key-files:
  created:
    - src/pipeline/live/bus/__init__.py
    - src/pipeline/live/bus/models.py
    - src/pipeline/live/bus/schema.py
    - src/pipeline/live/bus/server.py
    - tests/test_bus_foundation.py
  modified:
    - src/pipeline/live/__init__.py

key-decisions:
  - "Fail-open design: server never returns 500, DuckDB errors silently pass"
  - "run_id fallback: when absent, session_id used (pre-OpenClaw compatibility)"
  - "Daemon injection via create_app(daemon=obj) rather than global state"
  - "Body read once in register handler to avoid double-await failure"

patterns-established:
  - "Governance Bus fail-open: all endpoints return 200 on internal error"
  - "DuckDB schema idempotency: CREATE TABLE IF NOT EXISTS for all bus tables"
  - "Daemon injection: server.create_app(daemon=) for deferred /api/check implementation"

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 19 Plan 01: Bus Foundation Summary

**DuckDB-backed governance bus with Starlette server scaffold: bus_sessions + governance_signals tables, frozen Pydantic models, and fail-open /api/register, /api/deregister, /api/check endpoints**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T18:21:01Z
- **Completed:** 2026-02-25T18:25:01Z
- **Tasks:** 5
- **Files modified:** 6

## Accomplishments
- DuckDB schema with bus_sessions (session tracking) and governance_signals (signal routing) tables with CHECK constraints
- Frozen Pydantic models for type-safe bus communication (BusSession, GovernanceSignal, CheckRequest, CheckResponse)
- Starlette server with fail-open design: malformed requests and DuckDB errors return 200 with empty payload
- 14 tests covering schema, models, and all three endpoints including edge cases

## Task Commits

Each task was committed atomically:

1. **Task 1: DuckDB schema** - `0fb1e40` (feat)
2. **Task 2: Pydantic models** - `02041e3` (feat)
3. **Task 3: Starlette server scaffold** - `f545a4d` (feat)
4. **Task 4: Package inits** - `d3c9bac` (chore)
5. **Task 5: Tests (14 tests)** - `7b8c312` (test)

## Files Created/Modified
- `src/pipeline/live/bus/schema.py` - DuckDB DDL for bus_sessions + governance_signals, idempotent create_bus_schema()
- `src/pipeline/live/bus/models.py` - BusSession, GovernanceSignal (frozen), CheckRequest, CheckResponse Pydantic models
- `src/pipeline/live/bus/server.py` - Starlette app with /api/register, /api/deregister, /api/check; fail-open design
- `src/pipeline/live/bus/__init__.py` - Package exports for public API
- `src/pipeline/live/__init__.py` - Updated docstring for Phase 19 bus subpackage
- `tests/test_bus_foundation.py` - 14 tests: schema, models, server routes, fail-open, edge cases

## Decisions Made
- **Fail-open server:** DuckDB write failures return 200 with empty payload. Sessions must never be blocked by bus errors. This is a governance principle: the bus is instrumental; blocking the session would be a terminal failure.
- **run_id fallback:** When run_id is absent from /api/register, session_id is used as fallback. This supports pre-OpenClaw sessions that don't have a governing run_id.
- **Daemon injection:** The /api/check endpoint accepts an optional daemon object via create_app(daemon=obj). This defers the governing daemon implementation to 19-03 without any global state.
- **Body-read-once pattern:** The register handler reads `await request.json()` once and caches the result. The exception handler uses the cached body dict, avoiding the double-await failure that would occur if request.json() were called again.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Schema, models, and server scaffold are ready for 19-02 (stream processor wiring) and 19-03 (governing daemon)
- The governance_signals table is ready to receive signals from the stream processor
- The /api/check stub is ready for full implementation by the governing daemon
- 19-02 and 19-01 are in the same wave (Wave 1), so they can execute in parallel

## Self-Check: PASSED

All 6 files confirmed present. All 5 task commits verified in git log.

---
*Phase: 19-control-plane-integration*
*Completed: 2026-02-25*
