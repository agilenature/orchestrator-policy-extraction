---
phase: 17-candidate-assessment-system
plan: 02
subsystem: assessment
tags: [scenario-generation, cli, click, duckdb, subprocess, ddf-levels]

# Dependency graph
requires:
  - phase: 17-01
    provides: "ScenarioSpec model, assessment schema with project_wisdom extensions"
provides:
  - "ScenarioGenerator class for building assessment scenarios from project_wisdom"
  - "assess CLI group with annotate-scenarios and list-scenarios commands"
  - "generate_scenario convenience function"
  - "Broken implementation validation via subprocess"
affects: [17-03, 17-04]

# Tech tracking
tech-stack:
  added: []
  patterns: ["subprocess.run with timeout for broken impl validation", "Click nested group registration pattern", "Solution hint stripping from scenario context"]

key-files:
  created:
    - src/pipeline/assessment/scenario_generator.py
    - src/pipeline/cli/assess.py
    - tests/test_scenario_generator.py
    - tests/test_assess_cli.py
  modified:
    - src/pipeline/cli/intelligence.py

key-decisions:
  - "ScenarioGenerator produces default RuntimeError-based broken impls when no seed provided"
  - "L5-L7 handicap uses generic surface-level wrong-cause framing template"
  - "list-scenarios opens DB read-only with graceful error if assessment schema not applied"
  - "assess group nested under intelligence_group (not top-level CLI)"

patterns-established:
  - "Click group nesting: assess_group registered via intelligence_group.add_command()"
  - "Broken impl validation: subprocess.run with 30s timeout, checking exit code != 0"
  - "Solution hint stripping: filter lines starting with solution:/fix:/answer:/resolution:"

# Metrics
duration: 8min
completed: 2026-02-24
---

# Phase 17 Plan 02: Scenario Generator + Annotation CLI Summary

**ScenarioGenerator builds calibrated pile problems from project_wisdom with L5-L7 handicap CLAUDE.md, plus annotate-scenarios and list-scenarios CLI under intelligence assess**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-24T22:08:40Z
- **Completed:** 2026-02-24T22:17:15Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- ScenarioGenerator produces ScenarioSpec from project_wisdom entries with scenario_context.md, broken_impl.py, and optional handicap CLAUDE.md
- L5-L7 scenarios include plausible-but-wrong analysis framing designed to test candidate resistance
- annotate-scenarios CLI enables interactive DDF level annotation with optional seed text
- list-scenarios CLI displays scenario inventory with level filtering and annotation status
- 18 new tests covering generator logic, file creation, validation, and all CLI commands

## Task Commits

Each task was committed atomically:

1. **Task 1: ScenarioGenerator** - `30d7daf` (feat)
2. **Task 2: assess CLI + registration** - `f4a602d` (feat)
3. **Task 3: Tests (11 generator + 7 CLI)** - `909f63d` (test)

## Files Created/Modified
- `src/pipeline/assessment/scenario_generator.py` - ScenarioGenerator class with generate_scenario, generate_scenario_files, validate_broken_impl
- `src/pipeline/cli/assess.py` - Click group with annotate-scenarios and list-scenarios commands
- `src/pipeline/cli/intelligence.py` - Added assess_group registration under intelligence_group
- `tests/test_scenario_generator.py` - 11 tests for scenario generation, validation, file creation
- `tests/test_assess_cli.py` - 7 tests for CLI commands and group registration

## Decisions Made
- ScenarioGenerator uses a default RuntimeError-based template when no scenario_seed is provided, ensuring broken impls always fail
- L5-L7 handicap framing uses generic wrong-cause template (configuration handling / parameter ordering) rather than scenario-specific wrong analysis
- list-scenarios opens DB in read-only mode with a graceful error message when assessment schema columns are missing
- assess group is nested under intelligence (not top-level), accessed via `intelligence assess <command>`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Graceful error for missing assessment schema in list-scenarios**
- **Found during:** Task 2 (verify CLI against production DB)
- **Issue:** list-scenarios opened DB read-only, so it could not ALTER TABLE to add assessment columns, producing an opaque DuckDB error
- **Fix:** Added schema detection in the except block -- if `ddf_target_level` or `scenario_seed` is in the error message, show a helpful message directing user to run annotate-scenarios first
- **Files modified:** src/pipeline/cli/assess.py
- **Verification:** CLI shows helpful message against production DB
- **Committed in:** 909f63d (part of Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Minor improvement to user experience. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ScenarioGenerator ready for Plan 03 (Session Launcher) to consume
- assess CLI provides the annotation workflow needed before assessment sessions can run
- 1518 tests passing (1500 baseline + 18 new), zero regressions

## Self-Check: PASSED

All 4 created files verified present. All 3 commit hashes verified in git log.

---
*Phase: 17-candidate-assessment-system*
*Completed: 2026-02-24*
