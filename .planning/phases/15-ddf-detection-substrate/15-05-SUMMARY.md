---
phase: 15-ddf-detection-substrate
plan: 05
subsystem: ddf-detection
tags: [duckdb, pydantic, ddf, flame-events, intelligence-profile, aggregation, spiral-depth]

# Dependency graph
requires:
  - phase: 15-01
    provides: DDF schema (flame_events table), IntelligenceProfile model
  - phase: 15-02
    provides: write_flame_events for test seeding
provides:
  - compute_intelligence_profile: per-human aggregate metrics from flame_events
  - compute_ai_profile: AI-subject aggregate metrics from flame_events
  - compute_spiral_depth_for_human: longest ascending marker_level streak (Python-side)
  - list_available_humans: distinct human_ids for CLI discovery
affects: [15-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Python-side iteration for spiral depth instead of complex SQL window functions"
    - "SQL aggregation for frequency/avg/max/flood_rate with NULLIF for division safety"
    - "Separate spiral depth function reusable by both profile computation and CLI"

key-files:
  created:
    - src/pipeline/ddf/intelligence_profile.py
    - tests/test_ddf_intelligence.py
  modified: []

key-decisions:
  - "Spiral depth counts ascending transitions (N-1 for N levels in streak), not streak length"
  - "Python-side iteration for spiral depth avoids complex DuckDB window functions and is clearer"
  - "AI profile returns human_id='ai' as a sentinel value for the single AI subject"
  - "avg_marker_level rounded to 4 decimal places to avoid floating-point display noise"

patterns-established:
  - "Python-side computation pattern: SQL for set-based aggregation, Python for sequential/streak logic"
  - "list_available_* pattern for CLI discovery of valid parameter values"

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 15 Plan 05: IntelligenceProfile Aggregation Summary

**Per-human and per-AI aggregate metrics from flame_events with Python-side spiral depth computation as longest ascending marker_level streak**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T12:02:54Z
- **Completed:** 2026-02-24T12:07:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- compute_intelligence_profile aggregates flame_frequency, avg/max marker_level, flood_rate, session_count per human
- compute_ai_profile provides same aggregation filtered to subject='ai' events only
- compute_spiral_depth_for_human iterates ordered flame_events tracking longest ascending marker_level streak across sessions
- list_available_humans returns distinct human_ids for CLI parameter discovery
- Empty data returns None (not exception) for both human and AI profiles
- Flood rate computed as L6+ events / total events using NULLIF for zero-division safety
- 12 tests covering all aggregation paths, edge cases, spiral depth logic, and empty data

## Task Commits

Each task was committed atomically:

1. **Task 1: IntelligenceProfile aggregation + spiral depth + tests** - `fda41fd` (feat)

## Files Created/Modified
- `src/pipeline/ddf/intelligence_profile.py` - 4 functions: compute_intelligence_profile, compute_ai_profile, compute_spiral_depth_for_human, list_available_humans
- `tests/test_ddf_intelligence.py` - 12 tests covering basic aggregation, flood rate, session count, empty data, AI profile, spiral depth (ascending, broken streak, no ascending, multi-session), list humans

## Decisions Made
- Spiral depth = number of ascending transitions (e.g., L1->L2->L3->L4 = 3 transitions, depth=3)
- Python-side iteration chosen over SQL window functions for spiral depth -- clearer logic, easier to test, no complex DuckDB-specific syntax
- AI profile uses human_id='ai' sentinel to fit IntelligenceProfile model's required field
- avg_marker_level rounded to 4 decimal places to prevent floating-point display artifacts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test failure in `tests/test_segmenter.py::test_multiple_sequential_episodes` (known from prior plans). Not a regression from Plan 05 changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- IntelligenceProfile computation ready for CLI display (Plan 06)
- compute_spiral_depth_for_human exposed as standalone function for CLI reuse
- list_available_humans provides discovery mechanism for CLI human selection

## Self-Check: PASSED

- `src/pipeline/ddf/intelligence_profile.py` verified present on disk
- `tests/test_ddf_intelligence.py` verified present on disk
- Commit fda41fd (Task 1) verified in git log
- 12 tests passing, zero regressions (1141 passed, 1 pre-existing failure)

---
*Phase: 15-ddf-detection-substrate*
*Completed: 2026-02-24*
