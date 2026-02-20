---
phase: 12-governance-protocol-integration
plan: 01
subsystem: database, config, models
tags: [duckdb, pydantic, json-schema, governance, stability-checks, wisdom]

# Dependency graph
requires:
  - phase: 11-project-level-wisdom-layer
    provides: WisdomEntity model, WisdomStore CRUD, project_wisdom table
  - phase: 10-cross-session-decision-durability
    provides: DurabilityConfig pattern, constraint schema extensions
provides:
  - constraint.schema.json source_excerpt property
  - GovernanceConfig and StabilityCheckDef models in PipelineConfig
  - WisdomEntity.metadata field with WisdomStore persistence
  - DuckDB stability_outcomes table
  - DuckDB episodes governance columns (requires_stability_check, stability_check_status)
  - DuckDB project_wisdom metadata JSON column
affects: [12-02-constraint-ingestion, 12-03-stability-verification, 12-04-governance-cli]

# Tech tracking
tech-stack:
  added: []
  patterns: [idempotent ALTER TABLE for schema evolution, JSON column for flexible metadata storage]

key-files:
  created:
    - tests/test_governance_foundation.py
  modified:
    - data/schemas/constraint.schema.json
    - src/pipeline/models/config.py
    - data/config.yaml
    - src/pipeline/wisdom/models.py
    - src/pipeline/wisdom/store.py
    - src/pipeline/storage/schema.py

key-decisions:
  - "WisdomEntity.metadata stored as JSON column in DuckDB, serialized/deserialized via json.dumps/json.loads"
  - "stability_outcomes table uses CHECK constraint for status IN ('pass', 'fail', 'error')"
  - "Governance columns on episodes are nullable BOOLEAN/VARCHAR for backward compatibility"

patterns-established:
  - "JSON column for flexible metadata: store as JSON type, serialize with json.dumps, parse with json.loads"
  - "Governance schema extension: idempotent ALTER TABLE pattern consistent with Phase 9/10"

# Metrics
duration: 8min
completed: 2026-02-20
---

# Phase 12 Plan 01: Governance Foundation Summary

**Constraint schema source_excerpt, GovernanceConfig with stability checks, WisdomEntity metadata persistence, and DuckDB stability_outcomes table**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20T16:42:46Z
- **Completed:** 2026-02-20T16:50:51Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Extended constraint.schema.json with source_excerpt optional property (additionalProperties: false safe)
- Added GovernanceConfig (bulk_ingest_threshold=5, stability_checks=[]) and StabilityCheckDef to PipelineConfig
- Added metadata field to WisdomEntity with full WisdomStore round-trip support (add, get, update, list, upsert, search)
- Created stability_outcomes table with status CHECK constraint and session/check_id indexes
- Added governance columns (requires_stability_check, stability_check_status) to episodes table
- 21 new foundation tests covering config defaults, schema validation, metadata round-trip, and DuckDB tables

## Task Commits

Each task was committed atomically:

1. **Task 1: Constraint schema + GovernanceConfig + WisdomEntity metadata** - `c1b2323` (feat)
2. **Task 2: DuckDB schema updates + foundation tests** - `c58038d` (feat)

## Files Created/Modified
- `data/schemas/constraint.schema.json` - Added source_excerpt optional string property
- `src/pipeline/models/config.py` - Added StabilityCheckDef, GovernanceConfig models; wired into PipelineConfig
- `data/config.yaml` - Added governance section with defaults
- `src/pipeline/wisdom/models.py` - Added metadata: dict | None field to WisdomEntity
- `src/pipeline/wisdom/store.py` - Updated all SQL queries and _row_to_entity for metadata column; added json import
- `src/pipeline/storage/schema.py` - Added stability_outcomes table, episodes governance columns, project_wisdom metadata column
- `tests/test_governance_foundation.py` - 21 tests covering all foundation layer components

## Decisions Made
- WisdomEntity.metadata stored as DuckDB JSON column, serialized via json.dumps/json.loads in WisdomStore
- stability_outcomes table uses CHECK constraint to enforce status values ('pass', 'fail', 'error')
- Governance columns on episodes use nullable types for backward compatibility with existing data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All four foundation elements in place for downstream plans:
  1. Constraint schema accepts source_excerpt (needed by 12-02 constraint ingestion)
  2. GovernanceConfig available in PipelineConfig (needed by 12-03 stability verification)
  3. WisdomEntity.metadata persists related_constraint_ids (needed by 12-02)
  4. DuckDB stability_outcomes table ready (needed by 12-03)
- 733 tests passing (712 baseline + 21 new), zero regressions
- No blockers for plans 12-02, 12-03, or 12-04

---
*Phase: 12-governance-protocol-integration*
*Completed: 2026-02-20*
