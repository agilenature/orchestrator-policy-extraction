---
phase: 17-candidate-assessment-system
plan: 03
subsystem: assessment
tags: [session-runner, subprocess, rejection-detector, te-computation, cli, observer]

# Dependency graph
requires:
  - phase: 17-01
    provides: "Assessment schema (assessment_te_sessions, assessment_baselines, ALTER extensions)"
  - phase: 17-02
    provides: "ScenarioSpec model, ScenarioGenerator, assess CLI group"
provides:
  - "AssessmentSessionRunner: full session lifecycle (setup, launch, cleanup)"
  - "AssessmentObserver: post-session pipeline integration via PipelineRunner"
  - "RejectionDetector: outcome-gated L5-7 rejection classification"
  - "3-metric assessment TE computation (raven_depth * crow_efficiency * trunk_quality)"
  - "run and calibrate CLI commands under assess group"
  - "assessment_session_id IS NULL filter on all IntelligenceProfile queries"
affects: [17-04, intelligence-profile, assessment-reporting]

# Tech tracking
tech-stack:
  added: [tarfile, statistics]
  patterns: [outcome-gated-classification, 3-metric-te-formula, subprocess-actor-launch, lazy-import-mocking]

key-files:
  created:
    - src/pipeline/assessment/session_runner.py
    - src/pipeline/assessment/observer.py
    - src/pipeline/assessment/rejection_detector.py
    - src/pipeline/assessment/te_assessment.py
    - tests/test_session_runner.py
    - tests/test_assessment_observer.py
    - tests/test_rejection_detector.py
    - tests/test_te_assessment.py
  modified:
    - src/pipeline/cli/assess.py
    - src/pipeline/ddf/intelligence_profile.py

key-decisions:
  - "Assessment TE uses 3-metric formula (no transport_speed) because sessions are too short for meaningful speed measurement"
  - "Rejection threshold uses strict > (not >=): candidate at exactly threshold is stubbornness"
  - "Fringe-signal rejections bypass outcome gate entirely (fringe_L5)"
  - "Observer uses lazy imports for PipelineRunner to avoid circular dependencies"
  - "load_config source is src.pipeline.models.config (not src.pipeline.config as plan pitfall #7 suggested)"

patterns-established:
  - "Outcome-gated classification: reject only if TE exceeds threshold, otherwise stubbornness"
  - "Lazy import pattern for heavy modules in assessment/observer.py"
  - "DELETE + INSERT upsert pattern for DuckDB tables without INSERT OR REPLACE support"
  - "assessment_session_id IS NULL filter pattern for production query isolation"

# Metrics
duration: 12min
completed: 2026-02-24
---

# Phase 17 Plan 03: Session Runner + Observer + Rejection Detector Summary

**Assessment session lifecycle with subprocess Actor launch, pipeline-integrated Observer, outcome-gated L5-7 rejection classification, and 3-metric TE formula (no transport_speed)**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-24T22:21:27Z
- **Completed:** 2026-02-24T22:33:34Z
- **Tasks:** 4
- **Files modified:** 10

## Accomplishments
- Full assessment session lifecycle: directory setup with scenario files + CLAUDE.md + MEMORY.md pre-seeding, Actor subprocess launch, tar.gz archive cleanup
- Outcome-gated rejection detection: L5 (above threshold), stubbornness (below), fringe_L5 (bypass gate)
- 3-metric assessment TE: raven_depth * crow_efficiency * trunk_quality (0.5 placeholder)
- Production IntelligenceProfile isolation: all 5 flame_events queries filtered by assessment_session_id IS NULL
- 40 new tests passing, 1558 total (zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: session_runner.py + te_assessment.py** - `42d76d1` (feat)
2. **Task 2: observer.py + rejection_detector.py** - `8080b42` (feat)
3. **Task 3: CLI additions + 40 tests** - `1b4145c` (feat)
4. **Task 4: intelligence_profile.py IS NULL filter** - `a1b484c` (fix)

## Files Created/Modified
- `src/pipeline/assessment/session_runner.py` - Assessment dir setup, Actor launch, cleanup/archive
- `src/pipeline/assessment/observer.py` - Post-session OPE pipeline integration, flame_event tagging
- `src/pipeline/assessment/rejection_detector.py` - Outcome-gated L5-7 rejection classification
- `src/pipeline/assessment/te_assessment.py` - 3-metric TE computation, baselines, row writer
- `src/pipeline/cli/assess.py` - Added run and calibrate commands
- `src/pipeline/ddf/intelligence_profile.py` - Added assessment_session_id IS NULL to 5 queries
- `tests/test_session_runner.py` - 11 tests for session lifecycle
- `tests/test_assessment_observer.py` - 4 tests for observer
- `tests/test_rejection_detector.py` - 11 tests for rejection detection
- `tests/test_te_assessment.py` - 14 tests for TE computation

## Decisions Made
- Used `src.pipeline.models.config.load_config` (correct path, not plan pitfall #7's `src.pipeline.config`)
- Observer patches target source modules (`src.pipeline.runner.PipelineRunner`) because lazy imports prevent module-level patching
- DELETE + INSERT upsert for DuckDB tables that lack INSERT OR REPLACE support
- trunk_quality hardcoded to 0.5 as placeholder until human review confirms quality

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed observer test mock targets**
- **Found during:** Task 3 (tests)
- **Issue:** Plan specified `patch("src.pipeline.assessment.observer.PipelineRunner")` but observer uses lazy imports inside method body, so module-level attribute doesn't exist for patching
- **Fix:** Changed mock targets to source modules: `patch("src.pipeline.runner.PipelineRunner")` and `patch("src.pipeline.models.config.load_config")`
- **Files modified:** tests/test_assessment_observer.py
- **Verification:** All 4 observer tests pass
- **Committed in:** 1b4145c

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Corrected mock target for lazy-import pattern. No scope creep.

## Issues Encountered
- Pre-existing test failure in tests/test_segmenter.py (test_multiple_sequential_episodes) -- unrelated to this plan, not addressed

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Assessment session lifecycle complete: setup, launch, observe, score, cleanup
- Ready for Plan 17-04 (Reporting + Assessment CLI dashboard)
- Scenario calibration available via `intelligence assess calibrate`
- Full assessment runs available via `intelligence assess run`

---
*Phase: 17-candidate-assessment-system*
*Completed: 2026-02-24*
