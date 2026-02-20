---
phase: 12-governance-protocol-integration
plan: 03
subsystem: governance
tags: [subprocess, duckdb, stability-checks, governance]

requires:
  - phase: 12-01
    provides: "GovernanceConfig, StabilityCheckDef, stability_outcomes table, episodes governance columns"
provides:
  - "StabilityRunner class executing config-registered commands via subprocess"
  - "StabilityOutcome dataclass for check result records"
  - "flag_missing_validation() for unchecked episode detection"
  - "mark_validated() for post-check episode status upgrade"
affects: [12-04, pipeline-integration]

tech-stack:
  added: []
  patterns:
    - "Subprocess execution with explicit TimeoutExpired handling"
    - "stdout/stderr truncation to 10000 chars for storage safety"
    - "Git actor caching in __init__ for consistent provenance"
    - "Optional conn parameter pattern for flexible DuckDB targeting"

key-files:
  created:
    - "src/pipeline/governance/stability.py"
    - "tests/test_governance_stability.py"
  modified: []

key-decisions:
  - "stdout/stderr truncated to 10000 chars to prevent DuckDB storage bloat"
  - "Git actor info cached once in __init__ (not per-check) for consistency"
  - "flag_missing_validation and mark_validated accept optional conn parameter for flexibility"
  - "TimeoutExpired produces exit_code=-1 as sentinel value (not a real process exit)"

patterns-established:
  - "Subprocess timeout pattern: catch TimeoutExpired explicitly, status=error, exit_code=-1"
  - "Episode governance column updates via COUNT then UPDATE for return value accuracy"

duration: 4min
completed: 2026-02-20
---

# Phase 12 Plan 03: Stability Runner Summary

**Subprocess-based stability check runner with DuckDB persistence, timeout handling, and episode validation flagging**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-20T16:54:57Z
- **Completed:** 2026-02-20T16:59:31Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- StabilityRunner executes config-registered subprocess commands with explicit timeout handling
- Outcomes persisted to DuckDB stability_outcomes table with actor provenance
- Episode governance flagging: flag_missing_validation() marks unchecked episodes, mark_validated() upgrades them
- 14 comprehensive tests covering all outcome types, DuckDB persistence, truncation, and real subprocess execution

## Task Commits

Each task was committed atomically:

1. **Task 1: StabilityRunner implementation** - `c307ef8` (feat)
2. **Task 2: Stability runner tests** - `e7ff1ee` (test)

## Files Created/Modified

- `src/pipeline/governance/stability.py` - StabilityRunner class with run_checks(), flag_missing_validation(), mark_validated(); StabilityOutcome dataclass
- `tests/test_governance_stability.py` - 14 tests covering pass/fail/timeout/error, DuckDB, truncation, flagging, real subprocess, actor info

## Decisions Made

- stdout/stderr truncated to 10000 chars to prevent DuckDB storage bloat (matches plan guidance)
- Git actor info cached once in __init__ rather than per-check for consistency and efficiency
- TimeoutExpired produces exit_code=-1 as sentinel (not a real process exit code)
- flag_missing_validation/mark_validated use COUNT-then-UPDATE pattern for accurate return values

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- StabilityRunner ready for pipeline integration in plan 12-04
- Exports: StabilityRunner, StabilityOutcome from src.pipeline.governance.stability
- 792 tests passing (733 baseline + 45 from plan 12-02 + 14 new)

## Self-Check: PASSED

- FOUND: src/pipeline/governance/stability.py
- FOUND: tests/test_governance_stability.py
- FOUND: commit c307ef8 (Task 1)
- FOUND: commit e7ff1ee (Task 2)

---
*Phase: 12-governance-protocol-integration*
*Completed: 2026-02-20*
