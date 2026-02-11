---
phase: 02-episode-population-storage
plan: 02
subsystem: pipeline, models
tags: [episode, populator, mode-inference, observation, outcome, provenance, tdd]

# Dependency graph
requires:
  - phase: 01-event-stream-foundation
    provides: EpisodeSegment model, tagged events with primary_tag, DuckDB events table
  - phase: 02-episode-population-storage
    plan: 01
    provides: Episode Pydantic models, EpisodeValidator, EpisodePopulationConfig, DuckDB episodes table
provides:
  - EpisodePopulator class that transforms (segment, events, context_events) into episode dicts
  - Priority-based mode inference with position tie-breaking from config.mode_inference
  - Observation derivation from context events, action from start trigger, outcome from body events
  - Provenance building with deduplication and git commit ref inclusion
affects: [02-03 reaction-labeler, 02-04 pipeline-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [position-based tie-breaking for same-priority mode inference, deterministic episode IDs via SHA-256]

key-files:
  created:
    - src/pipeline/populator.py
    - tests/test_populator.py
  modified: []

key-decisions:
  - "Position-based tie-breaking for mode inference: when multiple modes match at the same priority, the keyword appearing earliest in text wins"
  - "Observation uses context events only (preceding the episode), never events from within the segment body"

patterns-established:
  - "EpisodePopulator pattern: populate(segment, events, context_events) -> dict matching JSON Schema"
  - "Config-driven mode inference with pre-compiled word-boundary regex patterns"
  - "Risk computation: base risk from mode + bump for protected path matches"

# Metrics
duration: 4min
completed: 2026-02-11
---

# Phase 2 Plan 2: EpisodePopulator Summary

**TDD-built EpisodePopulator deriving observation/action/outcome from segments using config-driven mode inference with 30 tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-11T20:22:55Z
- **Completed:** 2026-02-11T20:27:36Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- EpisodePopulator class with populate() method producing dicts matching orchestrator-episode.schema.json
- Priority-based mode inference with position tie-breaking handles all 7 modes correctly
- Observation derived from context events (not segment body), action from start trigger, outcome from body events
- Provenance deduplicates source refs and includes git commit hashes from event links
- 30 tests covering observation, action, outcome derivation, provenance, schema validation, risk, all 7 modes

## Task Commits

Each task was committed atomically (TDD flow):

1. **RED: Failing tests for EpisodePopulator** - `9bd9fed` (test)
2. **GREEN: EpisodePopulator implementation** - `7042607` (feat)

_Note: No separate REFACTOR commit needed -- code was clean after GREEN phase._

## Files Created/Modified
- `src/pipeline/populator.py` - EpisodePopulator class with 15 methods for episode field derivation
- `tests/test_populator.py` - 30 TDD tests across 8 test classes

## Decisions Made
- Position-based tie-breaking for mode inference: when "debug" (Triage, priority 4) and "test" (Verify, priority 4) both match, the keyword appearing first in text determines the mode -- "debug this test" -> Triage because "debug" appears before "test"
- Observation context limited by config.episode_population.observation_context_events (default 20) -- honors existing config from 02-01

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Mode inference tie-breaking for same-priority keywords**
- **Found during:** Task 2 (GREEN -- initial test run)
- **Issue:** "debug this failing test" matched both Verify (keyword "test", priority 4) and Triage (keyword "debug", priority 4). Dict iteration order determined winner, causing non-deterministic results.
- **Fix:** Added match position as secondary sort key -- when priorities tie, the keyword appearing earliest in text wins. This correctly resolves "debug this test" to Triage since "debug" appears first.
- **Files modified:** src/pipeline/populator.py
- **Verification:** Both ambiguous-text tests now pass consistently
- **Committed in:** 7042607 (GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential fix for deterministic mode inference. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- EpisodePopulator ready for pipeline integration (02-04) to wire into PipelineRunner
- populate() produces schema-valid dicts ready for EpisodeValidator and DuckDB storage
- ReactionLabeler (02-03) can enhance outcome.reaction field on populated episodes
- 134 total tests passing (104 Phase 1 + 14 episode validator + 30 populator; excludes 3 pre-existing reaction_labeler WIP failures)

## Self-Check: PASSED

All 2 files verified present (src/pipeline/populator.py, tests/test_populator.py). Both commit hashes (9bd9fed, 7042607) confirmed in git log. 30 tests collected and passing.

---
*Phase: 02-episode-population-storage*
*Completed: 2026-02-11*
