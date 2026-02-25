---
phase: 18-bridge-warden-structural-integrity
plan: 02
subsystem: ddf
tags: [structural-integrity, detectors, op8, pipeline, duckdb, flame-events]

# Dependency graph
requires:
  - phase: 18-01
    provides: "structural_events table schema, StructuralEvent/StructuralIntegrityResult models, writer, StructuralConfig"
  - phase: 15
    provides: "flame_events table with ccd_axis, axis_identified, marker_level columns"
  - phase: 16.1
    provides: "axis_edges table for topological edge queries"
  - phase: 11
    provides: "project_wisdom table for spiral reinforcement cross-reference"
provides:
  - "Four structural signal detectors: gravity_check, main_cable, dependency_sequencing, spiral_reinforcement"
  - "detect_structural_signals orchestrator combining all four detectors"
  - "compute_structural_integrity with locked weighted formula and neutral fallback"
  - "deposit_op8_corrections for AI floating cables to memory_candidates"
  - "Pipeline Step 21 structural analysis (after Step 20 TE, before Step 22 stats)"
  - "26 tests covering detectors, computer, Op-8, and pipeline integration"
affects: [18-03, 18-04, assessment-system]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Second-pass detector pattern (READ-ONLY on existing tables, produces StructuralEvent list)", "Dual assess_clause pattern (aliased f. for main queries, bare for sub-queries)", "SHA-256 dedup ID for idempotent deposits"]

key-files:
  created:
    - "src/pipeline/ddf/structural/detectors.py"
    - "src/pipeline/ddf/structural/computer.py"
    - "src/pipeline/ddf/structural/op8.py"
    - "tests/test_structural_detectors.py"
  modified:
    - "src/pipeline/ddf/structural/__init__.py"
    - "src/pipeline/runner.py"

key-decisions:
  - "Main Cable detector uses axis_edges presence only (no generalization_radius on flame_events) -- deviation from plan"
  - "Spiral reinforcement queries project_wisdom.metadata JSON (no source_session_id column) -- schema-driven deviation"
  - "Assessment filter uses dual clause pattern: f.assessment_session_id for aliased queries, bare assessment_session_id for sub-queries"
  - "Op-8 deposits use INSERT OR REPLACE with SHA-256 dedup ID for idempotent re-runs"

patterns-established:
  - "Second-pass detector: query existing tables READ-ONLY, return model list, let writer handle persistence"
  - "Neutral fallback: 0.5 for empty denominators in ratio calculations (no evidence of failure = neutral, not bad)"
  - "Pipeline step: lazy import + try/except ImportError + try/except Exception for graceful degradation"

# Metrics
duration: 11min
completed: 2026-02-25
---

# Phase 18 Plan 02: Structural Detectors, Computer, Op-8, and Pipeline Step 21 Summary

**Four structural integrity signal detectors with weighted score formula, Op-8 floating-cable depositor, and pipeline Step 21 integration producing 26 passing tests**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-25T00:32:01Z
- **Completed:** 2026-02-25T00:42:56Z
- **Tasks:** 5
- **Files modified:** 6

## Accomplishments
- Four signal detectors operating as second-pass analysis over flame_events, axis_edges, project_wisdom
- StructuralIntegrityComputer with locked formula (0.30 gravity + 0.40 main_cable + 0.20 dependency + 0.10 spiral) and neutral_fallback=0.5
- Op-8 correction depositor writing AI floating cables to memory_candidates with source_type='op8_correction'
- Pipeline Step 21 wired after Step 20 (TE) with lazy imports and graceful fallback
- 26 tests all passing with zero regressions (1619 existing tests green)

## Task Commits

Each task was committed atomically:

1. **Task 1: Four signal detectors** - `260c1e0` (feat)
2. **Task 2: StructuralIntegrityComputer** - `9ee6f1e` (feat)
3. **Task 3: Op-8 depositor** - `be0acb0` (feat)
4. **Task 4: Pipeline Step 21 integration** - `5334145` (feat)
5. **Task 5: Tests** - `10ad4fc` (test)

## Files Created/Modified
- `src/pipeline/ddf/structural/detectors.py` - Four signal detectors + orchestrator (5 functions)
- `src/pipeline/ddf/structural/computer.py` - Weighted score computation with neutral fallback
- `src/pipeline/ddf/structural/op8.py` - Op-8 correction depositor to memory_candidates
- `src/pipeline/ddf/structural/__init__.py` - Updated exports for all Plan 02 symbols
- `src/pipeline/runner.py` - Step 21 structural analysis after Step 20
- `tests/test_structural_detectors.py` - 26 tests for all components

## Decisions Made
- **Main Cable uses axis_edges only:** Plan specified generalization_radius >= 2 as alternative Main Cable criterion, but flame_events has no generalization_radius column (it's on constraint_metrics). Used axis_edges presence as the sole Main Cable test.
- **Spiral reinforcement queries metadata JSON:** Plan specified `source_session_id` column on project_wisdom, but the table stores session references in the `metadata` JSON column. Used `metadata::VARCHAR LIKE '%' || ? || '%'` pattern.
- **Column name corrections:** flame_events PK is `flame_event_id` (not `event_id`), axis_edges uses `axis_a`/`axis_b` (not `axis_1`/`axis_2`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed assess_clause table alias mismatch in sub-queries**
- **Found during:** Task 5 (tests)
- **Issue:** assess_clause used `f.assessment_session_id` (with table alias) but was reused in sub-queries without the `f` alias, causing `BinderException: Referenced table "f" not found`
- **Fix:** Created dual clause pattern: `assess_clause_f` (aliased) for main queries, `assess_clause` (bare) for sub-queries
- **Files modified:** src/pipeline/ddf/structural/detectors.py
- **Verification:** All 26 tests pass after fix
- **Committed in:** 10ad4fc (Task 5 commit)

**2. [Rule 3 - Blocking] Adapted to actual schema column names**
- **Found during:** Task 1 (detectors implementation)
- **Issue:** Plan referenced `event_id` (actual: `flame_event_id`), `axis_1`/`axis_2` (actual: `axis_a`/`axis_b`), `source_session_id` (not on project_wisdom), `generalization_radius` (not on flame_events)
- **Fix:** Used actual column names from validated DESCRIBE outputs
- **Files modified:** src/pipeline/ddf/structural/detectors.py
- **Verification:** All imports and queries succeed
- **Committed in:** 260c1e0 (Task 1 commit)

**3. [Rule 1 - Bug] Fixed FLOAT precision assertion in Op-8 test**
- **Found during:** Task 5 (tests)
- **Issue:** DuckDB FLOAT type returns 0.6000000238418579 instead of exactly 0.60
- **Fix:** Used `pytest.approx(0.60, abs=1e-4)` for FLOAT comparison
- **Files modified:** tests/test_structural_detectors.py
- **Verification:** Test passes
- **Committed in:** 10ad4fc (Task 5 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All fixes necessary for correctness. Schema column name corrections were required because plan was written against assumed column names rather than actual schema. No scope creep.

## Issues Encountered
- Pre-existing test failure in `test_segmenter.py::TestBasicSegmentation::test_multiple_sequential_episodes` (unrelated to this plan). All 1619 other tests pass green.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Structural detection pipeline fully operational through Step 21
- structural_events table populated by detect + write cycle
- Op-8 corrections depositing to memory_candidates
- Ready for Plan 18-03 (IntelligenceProfile integration) and Plan 18-04 (CLI/visualization)
- compute_structural_integrity available but not yet called in pipeline (awaiting Plan 03 integration)

---
*Phase: 18-bridge-warden-structural-integrity*
*Completed: 2026-02-25*
