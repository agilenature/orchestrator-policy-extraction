---
phase: 09-obstacle-escalation-detection
plan: 01
subsystem: pipeline
tags: [pydantic, duckdb, escalation, config, schema]

# Dependency graph
requires:
  - phase: 01-event-stream-foundation
    provides: Classification model, TaggedEvent model, PipelineConfig with sub-models
  - phase: 02-episode-population-storage
    provides: DuckDB episodes table, EpisodeValidator, EpisodePopulationConfig pattern
provides:
  - EscalationCandidate frozen Pydantic model at src/pipeline/escalation/models.py
  - EscalationConfig sub-model wired into PipelineConfig
  - ESCALATE mode in Pydantic model, JSON Schema, and EpisodeValidator (all 3 synced)
  - O_ESC classification label and escalation_detector source
  - 6 nullable escalation columns in DuckDB episodes table
  - Constraint schema with optional status and source lifecycle fields
affects: [09-02-PLAN, 09-03-PLAN, 09-04-PLAN, 10-decision-durability]

# Tech tracking
tech-stack:
  added: []
  patterns: [idempotent ALTER TABLE for schema evolution, frozen Pydantic model for detection output]

key-files:
  created:
    - src/pipeline/escalation/__init__.py
    - src/pipeline/escalation/models.py
  modified:
    - src/pipeline/models/config.py
    - src/pipeline/models/events.py
    - src/pipeline/models/episodes.py
    - src/pipeline/episode_validator.py
    - src/pipeline/storage/schema.py
    - data/config.yaml
    - data/schemas/orchestrator-episode.schema.json
    - data/schemas/constraint.schema.json

key-decisions:
  - "EscalationConfig defined inline in config.py (same pattern as EpisodePopulationConfig, RiskModelConfig)"
  - "O_ESC added to Classification valid_labels with escalation_detector as new valid source"
  - "Idempotent ALTER TABLE with try/except for DuckDB column additions (no migration tool needed)"
  - "Constraint status enum: active, candidate, retired (lifecycle for human vs inferred constraints)"
  - "block_event_tag validator restricts to O_GATE and O_CORR only"

patterns-established:
  - "Idempotent ALTER TABLE for adding nullable columns to existing DuckDB tables"
  - "EscalationCandidate as frozen model pattern for detection output (immutable, serializable)"

# Metrics
duration: 5min
completed: 2026-02-19
---

# Phase 9 Plan 01: Data Model Foundation Summary

**EscalationCandidate frozen model, EscalationConfig on PipelineConfig, ESCALATE mode synced across 3 enum locations, 6 DuckDB escalation columns, and constraint lifecycle fields**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-20T00:40:09Z
- **Completed:** 2026-02-20T00:44:56Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Created EscalationCandidate frozen Pydantic model capturing block-bypass event pairs with all required detection metadata
- Wired EscalationConfig into PipelineConfig with configurable window_turns, exempt_tools, bypass_eligible_tools, always_bypass_patterns, and detector_version
- Synchronized ESCALATE mode across all 3 enum locations: Pydantic Literal, JSON Schema, and EpisodeValidator valid_modes
- Added O_ESC as valid Classification label with escalation_detector source for multi-event pattern detection
- Extended DuckDB episodes table with 6 nullable escalation columns via idempotent ALTER TABLE
- Added optional status and source fields to constraint schema for lifecycle tracking of human vs inferred constraints
- All 439 existing tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Escalation data models and config extension** - `ec6186e` (feat)
2. **Task 2: Mode enum sync, DuckDB schema, and constraint schema extension** - `309b194` (feat)

## Files Created/Modified
- `src/pipeline/escalation/__init__.py` - Package exports for EscalationCandidate
- `src/pipeline/escalation/models.py` - EscalationCandidate frozen Pydantic model with validation
- `src/pipeline/models/config.py` - EscalationConfig sub-model wired into PipelineConfig
- `src/pipeline/models/events.py` - O_ESC label and escalation_detector source added to Classification
- `src/pipeline/models/episodes.py` - ESCALATE added to OrchestratorAction mode Literal
- `src/pipeline/episode_validator.py` - ESCALATE added to valid_modes business rule check
- `src/pipeline/storage/schema.py` - 6 nullable escalation columns via idempotent ALTER TABLE
- `data/config.yaml` - Escalation section with all configurable values
- `data/schemas/orchestrator-episode.schema.json` - ESCALATE added to mode enum
- `data/schemas/constraint.schema.json` - Optional status and source properties added

## Decisions Made
- EscalationConfig defined inline in config.py following the established sub-model pattern (same as EpisodePopulationConfig, RiskModelConfig) rather than importing from escalation package -- keeps config self-contained
- O_ESC added to Classification valid_labels with "escalation_detector" as a new valid source value, distinguishing multi-event pattern detections from single-event classifications
- Idempotent ALTER TABLE with try/except for DuckDB column additions -- simple and effective without requiring a migration framework
- Constraint status enum uses three values (active, candidate, retired) to support the full lifecycle from human-extracted constraints through inferred-from-escalation candidates
- EscalationCandidate.block_event_tag validated to only allow O_GATE or O_CORR as blocking event types

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- EscalationCandidate model ready for EscalationDetector (Plan 02) to instantiate
- EscalationConfig loaded from config.yaml and accessible via PipelineConfig.escalation
- ESCALATE mode ready for episode population in Plan 03
- O_ESC label ready for TaggedEvent creation in Plan 02
- DuckDB escalation columns ready for storage in Plan 03
- Constraint status/source fields ready for escalation-derived constraint generation in Plan 04

## Self-Check: PASSED

All 10 created/modified files verified present. Both task commits (ec6186e, 309b194) verified in git log. 439 tests passing.

---
*Phase: 09-obstacle-escalation-detection*
*Completed: 2026-02-19*
