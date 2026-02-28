---
phase: 25-genus-protocol-propagation
plan: 02
subsystem: api
tags: [starlette, pydantic, genus, bus-server, fail-open]

# Dependency graph
requires:
  - phase: 25-01
    provides: "genus_count field in CheckResponse and GovernorDaemon"
provides:
  - "/api/genus-consult POST endpoint on governance bus"
  - "GenusConsultRequest and GenusConsultResponse Pydantic models"
  - "GenusOracleHandler stub for plan 25-03 to implement"
affects: [25-03-genus-oracle-query, 25-04, 25-05]

# Tech tracking
tech-stack:
  added: []
  patterns: ["genus-consult handler uses same closure-conn pattern as check/push-link"]

key-files:
  created:
    - src/pipeline/live/genus_oracle.py
  modified:
    - src/pipeline/live/bus/models.py
    - src/pipeline/live/bus/server.py

key-decisions:
  - "GenusOracleHandler stub returns null genus -- plan 25-03 replaces body with real search"
  - "Handler uses existing conn closure, no new DuckDB connection (avoids single-writer conflicts)"

patterns-established:
  - "Fail-open genus response: {genus: null, instances: [], valid: false, confidence: 0.0}"

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 25 Plan 02: Genus Consult Endpoint Summary

**POST /api/genus-consult endpoint with Pydantic models, fail-open handler, and GenusOracleHandler stub delegating to plan 25-03**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T13:47:35Z
- **Completed:** 2026-02-28T13:49:15Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Added GenusConsultRequest and GenusConsultResponse Pydantic models to bus/models.py
- Created GenusOracleHandler stub at src/pipeline/live/genus_oracle.py (returns null genus, ready for 25-03)
- Wired /api/genus-consult route in create_app() using the existing closure-conn pattern
- Endpoint fails open: malformed body or any error returns {genus: null, valid: false, confidence: 0.0}

## Task Commits

Each task was committed atomically:

1. **Task 1: Add GenusConsultRequest/Response models and /api/genus-consult handler + route** - `8ccd1c8` (feat)

## Files Created/Modified
- `src/pipeline/live/genus_oracle.py` - GenusOracleHandler stub (query_genus returns null genus)
- `src/pipeline/live/bus/models.py` - Added GenusConsultRequest and GenusConsultResponse models
- `src/pipeline/live/bus/server.py` - Added genus_consult handler, GenusOracleHandler init, route registration

## Decisions Made
- GenusOracleHandler stub returns empty response -- plan 25-03 replaces the stub body with real tokenization-based search
- Handler uses the server's existing `conn` closure (same DuckDB connection), avoiding single-writer conflicts per Pitfall 1 from research

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- /api/genus-consult endpoint operational (returns stub response)
- Ready for plan 25-03 to implement GenusOracleHandler.query_genus() with real axis_edges search
- All 23 existing bus tests (14 foundation + 9 integration) pass

## Self-Check: PASSED

- FOUND: src/pipeline/live/genus_oracle.py
- FOUND: src/pipeline/live/bus/models.py
- FOUND: src/pipeline/live/bus/server.py
- FOUND: commit 8ccd1c8

---
*Phase: 25-genus-protocol-propagation*
*Completed: 2026-02-28*
