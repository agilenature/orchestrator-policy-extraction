---
phase: 10-cross-session-decision-durability
plan: 01
subsystem: database, constraints
tags: [duckdb, jsonschema, pydantic, migration, temporal-status]

requires:
  - phase: 09-obstacle-escalation-detection
    provides: "Constraint schema with status/source/bypassed_constraint_id fields, 542 test baseline"
provides:
  - "Constraint schema with type, status_history, supersedes fields"
  - "ConstraintStore temporal status methods (get_status_at_time, add_status_history_entry, get_by_type, get_active_constraints)"
  - "Constraint migration script (migrate_constraints)"
  - "DuckDB session_constraint_eval and amnesia_events tables"
  - "DurabilityConfig model wired into PipelineConfig"
  - "Shared scopes_overlap() utility"
affects: [10-02, 10-03, 10-04, 10-05]

tech-stack:
  added: []
  patterns:
    - "Temporal status history: chronological log with point-in-time lookup using datetime comparison"
    - "Constraint migration: idempotent field backfill with schema validation"
    - "Shared utility module: src/pipeline/utils.py for cross-module functions"

key-files:
  created:
    - "src/pipeline/durability/__init__.py"
    - "src/pipeline/durability/migration.py"
    - "src/pipeline/utils.py"
    - "tests/test_durability_migration.py"
  modified:
    - "data/schemas/constraint.schema.json"
    - "src/pipeline/constraint_store.py"
    - "src/pipeline/constraint_extractor.py"
    - "src/pipeline/escalation/constraint_gen.py"
    - "src/pipeline/storage/schema.py"
    - "src/pipeline/models/config.py"
    - "data/config.yaml"

key-decisions:
  - "status_history uses datetime.fromisoformat() comparison (not string) for timezone safety"
  - "Empty status_history falls back to current status field (backward-compatible)"
  - "get_active_constraints() treats missing status as active (behavioral default)"
  - "scopes_overlap() in utils.py treats EITHER empty list as repo-wide (differs from validation/layers.py)"
  - "DurabilityConfig defaults: min_sessions_for_score=3, evidence_excerpt_max_chars=500"

patterns-established:
  - "Temporal status pattern: chronological status_history array with point-in-time lookup"
  - "Idempotent migration: check for field existence before adding, validate after"
  - "Shared utility module at src/pipeline/utils.py"

duration: 7min
completed: 2026-02-20
---

# Phase 10 Plan 01: Decision Durability Foundation Summary

**Constraint schema extended with type/status_history/supersedes, ConstraintStore temporal methods, DuckDB evaluation tables, DurabilityConfig model, and shared scope utility**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-20T10:42:18Z
- **Completed:** 2026-02-20T10:49:21Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Extended constraint.schema.json with type, status_history, and supersedes fields (all with additionalProperties: false)
- Created durability migration script that backfills 185 existing constraints with type=behavioral_constraint and bootstrapped status_history
- Added 4 temporal methods to ConstraintStore: get_status_at_time(), add_status_history_entry(), get_by_type(), get_active_constraints()
- Created session_constraint_eval (composite PK) and amnesia_events tables in DuckDB schema
- Added DurabilityConfig model wired into PipelineConfig with config.yaml defaults
- Created shared scopes_overlap() utility in src/pipeline/utils.py
- 557 tests passing (542 baseline + 15 new, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Constraint schema migration + ConstraintStore temporal methods** - `0fb8227` (feat)
2. **Task 2: DuckDB evaluation tables + DurabilityConfig + shared scope utility** - `f148560` (feat)

## Files Created/Modified
- `data/schemas/constraint.schema.json` - Added type, status_history, supersedes properties
- `src/pipeline/constraint_store.py` - Added 4 temporal status methods
- `src/pipeline/constraint_extractor.py` - Emits type + status_history fields on extracted constraints
- `src/pipeline/escalation/constraint_gen.py` - Emits type + status_history fields on generated constraints
- `src/pipeline/durability/__init__.py` - Empty init for durability module
- `src/pipeline/durability/migration.py` - migrate_constraints() with schema validation
- `src/pipeline/storage/schema.py` - session_constraint_eval + amnesia_events tables with indexes
- `src/pipeline/models/config.py` - DurabilityConfig model
- `data/config.yaml` - durability section with defaults
- `src/pipeline/utils.py` - Shared scopes_overlap() utility
- `tests/test_durability_migration.py` - 15 tests for migration and temporal methods

## Decisions Made
- status_history uses datetime.fromisoformat() for comparison (not string comparison) to handle timezone variations safely
- Empty status_history falls back to current status field for backward compatibility with unmigrated constraints
- get_active_constraints() treats missing status as active (behavioral default matching existing constraint semantics)
- Shared scopes_overlap() in utils.py treats EITHER empty list as repo-wide, intentionally differing from validation/layers.py which only treats constraint-side empty as repo-wide
- DurabilityConfig keeps min_sessions_for_score=3 and evidence_excerpt_max_chars=500 as defaults

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Constraint schema ready for evaluator (Plan 02) to use type and status_history fields
- DuckDB tables ready for writing evaluation results and amnesia events
- ConstraintStore temporal methods ready for point-in-time status lookups
- DurabilityConfig ready for evaluator configuration
- Shared scopes_overlap() ready for evaluator scope matching

---
*Phase: 10-cross-session-decision-durability*
*Completed: 2026-02-20*
