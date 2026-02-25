---
phase: 18-bridge-warden-structural-integrity
plan: 01
subsystem: database, ddf
tags: [duckdb, pydantic, structural-integrity, schema, writer]

# Dependency graph
requires:
  - phase: 17-candidate-assessment-system
    provides: assessment schema chain (create_assessment_schema)
  - phase: 15-ddf-detection-substrate
    provides: FlameEvent.make_id pattern, IntelligenceProfile model, DDFConfig
provides:
  - structural_events DuckDB table with 14 columns and CHECK constraints
  - StructuralEvent frozen Pydantic model with deterministic make_id
  - StructuralIntegrityResult frozen Pydantic model
  - StructuralConfig nested under DDFConfig (gravity_window=3)
  - write_structural_events() idempotent writer
  - IntelligenceProfile extended with integrity_score and structural_event_count
affects: [18-02 detectors, 18-03 Op-8, 18-04 CLI]

# Tech tracking
tech-stack:
  added: []
  patterns: [structural sub-package under ddf, config in config.py not domain package]

key-files:
  created:
    - src/pipeline/ddf/structural/__init__.py
    - src/pipeline/ddf/structural/models.py
    - src/pipeline/ddf/structural/schema.py
    - src/pipeline/ddf/structural/writer.py
    - tests/test_structural_schema.py
  modified:
    - src/pipeline/ddf/models.py
    - src/pipeline/models/config.py
    - src/pipeline/ddf/schema.py
    - src/pipeline/storage/schema.py

key-decisions:
  - "StructuralConfig placed in config.py alongside OAxsConfig, not in structural/models.py -- follows established config-not-domain pattern"
  - "contributing_flame_event_ids stored as VARCHAR[] (native DuckDB array) not JSON-serialized string"
  - "write_structural_events returns int count instead of dict (simpler than write_flame_events pattern since no ambiguity)"
  - "structural_events dropped FIRST in drop_schema (before axis_edges) to maintain dependency order"

patterns-established:
  - "structural sub-package pattern: __init__.py exports domain models only, config stays in config.py"
  - "Writer returns int count for simple single-table writers"

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 18 Plan 01: Structural Schema Foundation Summary

**DuckDB structural_events table with CHECK constraints, frozen StructuralEvent/StructuralIntegrityResult models, idempotent writer, and StructuralConfig nested under DDFConfig**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T00:23:08Z
- **Completed:** 2026-02-25T00:27:33Z
- **Tasks:** 2
- **Files modified:** 9 (5 created, 4 modified)

## Accomplishments
- structural_events table with all 14 columns, 3 CHECK constraints (subject, signal_type, op8_status), and 3 indexes created via schema chain
- StructuralEvent.make_id produces deterministic SHA-256[:16] hex IDs following FlameEvent pattern
- IntelligenceProfile extended with Optional integrity_score and structural_event_count (fully backward compatible)
- DDFConfig().structural.gravity_window == 3 with weights summing to 1.0
- 13 new tests all passing, zero regressions in 1368-test suite (1 pre-existing failure in test_segmenter.py unrelated)

## Task Commits

Each task was committed atomically:

1. **Task 1: Structural models, schema DDL, config, and writer** - `40ce49f` (feat)
2. **Task 2: Schema chain integration, drop_schema update, and tests** - `ec48793` (feat)

## Files Created/Modified
- `src/pipeline/ddf/structural/__init__.py` - Package init exporting StructuralEvent, StructuralIntegrityResult
- `src/pipeline/ddf/structural/models.py` - Frozen Pydantic models for structural events and integrity results
- `src/pipeline/ddf/structural/schema.py` - STRUCTURAL_EVENTS_DDL, indexes, create_structural_schema()
- `src/pipeline/ddf/structural/writer.py` - write_structural_events() idempotent INSERT OR REPLACE writer
- `src/pipeline/ddf/models.py` - IntelligenceProfile extended with integrity_score, structural_event_count
- `src/pipeline/models/config.py` - StructuralConfig added, nested under DDFConfig.structural
- `src/pipeline/ddf/schema.py` - create_ddf_schema() now calls create_structural_schema()
- `src/pipeline/storage/schema.py` - drop_schema() drops structural_events first
- `tests/test_structural_schema.py` - 13 tests covering schema, models, writer, config, compatibility

## Decisions Made
- StructuralConfig placed in config.py (not structural/models.py) following established OAxsConfig pattern -- config models are not domain models
- contributing_flame_event_ids uses native DuckDB VARCHAR[] rather than JSON string serialization -- cleaner queries, native array operations
- Writer returns plain int (not dict) since there is no ambiguity about what was written
- structural_events is the first table dropped in drop_schema() to respect dependency ordering (its contributing_flame_event_ids reference flame_events)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Schema and models ready for Phase 18-02 (structural detectors)
- StructuralConfig available for detector parameterization
- write_structural_events() ready to receive detector output
- IntelligenceProfile ready to carry integrity_score from aggregation

## Self-Check: PASSED

All 5 created files verified present. Both commit hashes (40ce49f, ec48793) confirmed in git log.

---
*Phase: 18-bridge-warden-structural-integrity*
*Completed: 2026-02-25*
