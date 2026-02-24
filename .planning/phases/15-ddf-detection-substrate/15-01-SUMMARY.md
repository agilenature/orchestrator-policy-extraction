---
phase: 15-ddf-detection-substrate
plan: 01
subsystem: database, detection
tags: [duckdb, pydantic, ddf, flame-events, ccd-axis, o_axs]

# Dependency graph
requires:
  - phase: 14.1-premise-registry-premise-assertion-gate
    provides: premise_registry table and create_premise_schema pattern
  - phase: 13.3-identification-transparency
    provides: memory_candidates table and create_review_schema
provides:
  - flame_events table (human + AI unified storage)
  - ai_flame_events view
  - axis_hypotheses table
  - constraint_metrics table
  - memory_candidates extended with source_flame_event_id, fidelity, detection_count
  - FlameEvent, AxisHypothesis, ConstraintMetric, IntelligenceProfile models
  - DDFConfig with OAxsConfig in PipelineConfig
  - O_AXS classification label
  - axis_shift_detector, ddf_tier1, ddf_tier2 classification sources
affects: [15-02, 15-03, 15-04, 15-05, 15-06, 15-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unified flame_events table with subject CHECK constraint + view for AI-only access"
    - "memory_candidates schema extension via ALTER TABLE with try/except for idempotency"
    - "Frozen Pydantic models with deterministic SHA-256[:16] IDs for DDF markers"

key-files:
  created:
    - src/pipeline/ddf/__init__.py
    - src/pipeline/ddf/schema.py
    - src/pipeline/ddf/models.py
    - tests/test_ddf_schema.py
  modified:
    - src/pipeline/models/config.py
    - src/pipeline/models/events.py
    - src/pipeline/storage/schema.py
    - data/config.yaml

key-decisions:
  - "Single flame_events table with subject column instead of separate tables for human/AI"
  - "CREATE OR REPLACE VIEW for ai_flame_events (DuckDB does not support CREATE VIEW IF NOT EXISTS)"
  - "memory_candidates extensions use DEFAULT values only (no NOT NULL on ALTER TABLE)"

patterns-established:
  - "DDF schema creation follows lazy import pattern from create_premise_schema"
  - "Classification valid_labels and valid_sources extended for Phase 15 detectors"

# Metrics
duration: 6min
completed: 2026-02-24
---

# Phase 15 Plan 01: DDF Schema and Models Summary

**DDF DuckDB schema (flame_events, axis_hypotheses, constraint_metrics) + frozen Pydantic models + DDFConfig with O_AXS classification label integrated into pipeline**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-24T11:28:26Z
- **Completed:** 2026-02-24T11:34:21Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- flame_events table with 16 columns, subject CHECK constraint, and 4 indexes created
- ai_flame_events view filtering subject='ai' for backward-compatible AI-only access
- axis_hypotheses and constraint_metrics tables for CCD axis tracking
- memory_candidates extended with source_flame_event_id, fidelity, detection_count
- FlameEvent, AxisHypothesis, ConstraintMetric, IntelligenceProfile frozen Pydantic v2 models
- O_AXS label and axis_shift_detector/ddf_tier1/ddf_tier2 sources added to Classification
- DDFConfig with OAxsConfig integrated into PipelineConfig and config.yaml
- 12 new tests passing, zero regressions (1206 passed excluding pre-existing segmenter failure)

## Task Commits

Each task was committed atomically:

1. **Task 1: DDF DuckDB schema + Pydantic models** - `2e6c74d` (feat)
2. **Task 2: Config extensions + Classification labels + schema integration + tests** - `5772448` (feat)

## Files Created/Modified
- `src/pipeline/ddf/__init__.py` - Empty package init
- `src/pipeline/ddf/schema.py` - DDL for flame_events, ai_flame_events view, axis_hypotheses, constraint_metrics, memory_candidates extensions
- `src/pipeline/ddf/models.py` - FlameEvent, AxisHypothesis, ConstraintMetric, IntelligenceProfile frozen models
- `src/pipeline/models/config.py` - OAxsConfig, DDFConfig classes + ddf field on PipelineConfig
- `src/pipeline/models/events.py` - O_AXS label + axis_shift_detector/ddf_tier1/ddf_tier2 sources
- `src/pipeline/storage/schema.py` - create_ddf_schema integration + drop_schema DDF cleanup
- `data/config.yaml` - ddf configuration section with O_AXS thresholds
- `tests/test_ddf_schema.py` - 12 tests covering schema, models, config, idempotency, constraints

## Decisions Made
- Used single flame_events table with subject CHECK constraint ('human'|'ai') instead of separate tables -- view provides backward-compatible AI-only access
- CREATE OR REPLACE VIEW used for ai_flame_events because DuckDB lacks CREATE VIEW IF NOT EXISTS
- memory_candidates ALTER TABLE columns use DEFAULT values only (not NOT NULL) to avoid failure on existing rows

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All DDF schema tables ready for write-on-detect implementation (15-02)
- FlameEvent and AxisHypothesis models ready for Tier 1 detectors (15-03, 15-04)
- DDFConfig loaded from YAML and available via PipelineConfig for all detection components
- O_AXS label accepted by Classification validator, ready for axis shift detector (15-05)
- constraint_metrics table ready for stagnation detection (15-06)

## Self-Check: PASSED

All 9 files verified present. Both task commits (2e6c74d, 5772448) confirmed in git log.

---
*Phase: 15-ddf-detection-substrate*
*Completed: 2026-02-24*
