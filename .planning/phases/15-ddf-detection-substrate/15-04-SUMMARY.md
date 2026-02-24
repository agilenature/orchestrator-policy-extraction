---
phase: 15-ddf-detection-substrate
plan: 04
subsystem: detection, constraints
tags: [ddf, epistemological-origin, generalization-radius, stagnation, spiral-tracking, wisdom-promotion, duckdb]

# Dependency graph
requires:
  - phase: 15-ddf-detection-substrate (plan 01)
    provides: ConstraintMetric model, constraint_metrics table, DDFConfig with stagnation_min_firing_count
  - phase: 15-ddf-detection-substrate (plan 02)
    provides: flame_events table for spiral depth computation
  - phase: 10-cross-session-decision-durability
    provides: session_constraint_eval table with evidence_json
  - phase: 11-project-level-wisdom-layer
    provides: WisdomStore.upsert() and WisdomEntity.create() for spiral promotion
provides:
  - classify_epistemological_origin() for reactive/principled/inductive classification
  - epistemological_origin and epistemological_confidence fields on all constraints
  - compute_generalization_radius() with scope_path_prefix counting
  - compute_all_metrics() for batch constraint metric computation
  - detect_stagnation() for floating abstraction identification
  - write_constraint_metrics() for DuckDB persistence
  - detect_spirals() for ascending scope diversity detection
  - compute_spiral_depth() for flame_events marker_level streak analysis
  - promote_spirals_to_wisdom() depositing to project_wisdom via WisdomStore
affects: [15-05-intelligence-profile, 15-06-pipeline-integration, 15-07-cli]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Epistemological origin classification as first-match cascade with confidence float"
    - "Scope prefix extraction from evidence_json for count-based generalization proxy"
    - "Cumulative prefix set growth for spiral detection (skip-first-session baseline)"
    - "Lazy import of WisdomStore/WisdomEntity in spiral promotion to keep dependency optional"

key-files:
  created:
    - src/pipeline/ddf/epistemological.py
    - src/pipeline/ddf/generalization.py
    - src/pipeline/ddf/spiral.py
    - tests/test_ddf_epistemological.py
    - tests/test_ddf_generalization.py
  modified:
    - src/pipeline/constraint_extractor.py
    - src/pipeline/constraint_store.py
    - data/schemas/constraint.schema.json

key-decisions:
  - "Epistemological origin uses first-match cascade (reactive > principled > inductive > default principled) rather than weighted scoring"
  - "GeneralizationRadius uses scope_path_prefix from evidence_json, falling back to 'root' when no scope_path present"
  - "Spiral detection requires growth after first session (baseline excluded from growth check)"
  - "Spiral depth counts ascending levels (transitions + 1), not just transition count"
  - "Spiral promotion uses WisdomStore.upsert() for idempotent re-runs"

patterns-established:
  - "Epistemological classification at constraint extraction time (not post-hoc)"
  - "ConstraintStore backward compatibility via setdefault() in _load()"
  - "Spiral depth from longest ascending marker_level streak in flame_events"

# Metrics
duration: 11min
completed: 2026-02-24
---

# Phase 15 Plan 04: Epistemological Origin, GeneralizationRadius, and Spiral Tracking Summary

**Epistemological origin classification (reactive/principled/inductive) on all constraints, count-based GeneralizationRadius with stagnation detection, and spiral tracking with auto-promotion to project_wisdom via WisdomStore**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-24T12:02:17Z
- **Completed:** 2026-02-24T12:13:46Z
- **Tasks:** 2
- **Files created:** 5
- **Files modified:** 3

## Accomplishments
- Every constraint now carries epistemological_origin (reactive|principled|inductive) and epistemological_confidence (0.0-1.0) fields
- ConstraintExtractor.extract() classifies origin at extraction time using first-match cascade
- ConstraintStore backward-compatible: legacy constraints without epistemological fields get principled/1.0 defaults on load
- GeneralizationRadius computed from COUNT(DISTINCT scope_path_prefix) in session_constraint_eval evidence_json
- Stagnation detection flags constraints with radius=1 and firing_count >= 10 as floating abstractions
- Spiral tracking detects ascending scope diversity across sessions (cumulative prefix growth)
- Spiral candidates with length >= 3 auto-promoted to project_wisdom as 'breakthrough' entities via WisdomStore.upsert()
- compute_spiral_depth() analyzes flame_events marker_level ascending streaks for IntelligenceProfile
- 39 new tests (18 epistemological + 21 generalization/spiral), 1180 total passing, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Epistemological origin classification** - `c89c398` (feat)
2. **Task 2: GeneralizationRadius + spiral tracking + wisdom promotion** - `bd734e3` (feat)

## Files Created/Modified
- `src/pipeline/ddf/epistemological.py` - classify_epistemological_origin() with reactive/principled/inductive cascade
- `src/pipeline/ddf/generalization.py` - compute_generalization_radius(), compute_all_metrics(), write_constraint_metrics(), detect_stagnation()
- `src/pipeline/ddf/spiral.py` - detect_spirals(), compute_spiral_depth(), get_spiral_promotion_candidates(), promote_spirals_to_wisdom()
- `src/pipeline/constraint_extractor.py` - Added classify_epistemological_origin import and call in extract()
- `src/pipeline/constraint_store.py` - Added setdefault() backward compatibility in _load()
- `data/schemas/constraint.schema.json` - Added epistemological_origin enum and epistemological_confidence number properties
- `tests/test_ddf_epistemological.py` - 18 tests: classification logic, extractor integration, store compatibility, schema validation
- `tests/test_ddf_generalization.py` - 21 tests: radius, stagnation, spirals, depth, promotion candidates, wisdom upsert, idempotency

## Decisions Made
- Epistemological origin is a first-match cascade (reactive checked first, then principled, then inductive, then default) rather than the weighted scoring approach described in CONTEXT.md Q5. This is simpler and produces deterministic results with explicit confidence values per category.
- ESCALATE mode blocks reactive classification (per plan: "episode mode != ESCALATE") since escalation episodes are structural, not corrective.
- Spiral detection skips the first session from growth checks (it's the baseline, not a growth event). This prevents single-scope evaluation chains from being falsely detected as spirals.
- Spiral depth counts the number of ascending levels (transitions + 1), so L1->L2->L3 = depth 3, matching the plan's test specification.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed spiral detection false positives from first-session growth**
- **Found during:** Task 2 (spiral tracking)
- **Issue:** First session in a constraint's history was counting as "growth" (from 0 to 1 prefix), causing single-scope constraint chains to appear as spirals
- **Fix:** Added `i == 0: continue` to skip growth check on baseline session
- **Files modified:** src/pipeline/ddf/spiral.py
- **Verification:** test_spiral_non_ascending_not_detected now passes
- **Committed in:** bd734e3 (Task 2 commit)

**2. [Rule 1 - Bug] Fixed test for WisdomStore promotion with file-based DuckDB**
- **Found during:** Task 2 (wisdom promotion tests)
- **Issue:** Test closed file-based DuckDB connection and re-opened it, but data from CREATE TABLE was persisted, causing PK violation on re-insert
- **Fix:** Kept single connection open for both data insertion and promotion call
- **Files modified:** tests/test_ddf_generalization.py
- **Verification:** test_promote_spirals_to_wisdom_writes_project_wisdom now passes
- **Committed in:** bd734e3 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered

- Pre-existing test failure in tests/test_segmenter.py (dirty working tree modification to src/pipeline/segmenter.py) -- not caused by our changes. All 1180 non-segmenter tests pass.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- Epistemological origin available on all constraints for IntelligenceProfile aggregation (15-05)
- GeneralizationRadius and stagnation metrics ready for constraint_metrics table population in pipeline integration (15-06)
- Spiral tracking and wisdom promotion ready for pipeline runner step (15-06)
- compute_spiral_depth() ready for IntelligenceProfile (15-05)

## Self-Check: PASSED

All 8 files verified present:
- FOUND: src/pipeline/ddf/epistemological.py
- FOUND: src/pipeline/ddf/generalization.py
- FOUND: src/pipeline/ddf/spiral.py
- FOUND: src/pipeline/constraint_extractor.py
- FOUND: src/pipeline/constraint_store.py
- FOUND: data/schemas/constraint.schema.json
- FOUND: tests/test_ddf_epistemological.py
- FOUND: tests/test_ddf_generalization.py

Both task commits verified in git log:
- FOUND: c89c398
- FOUND: bd734e3

---
*Phase: 15-ddf-detection-substrate*
*Completed: 2026-02-24*
