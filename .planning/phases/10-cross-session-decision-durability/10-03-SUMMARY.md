---
phase: 10-cross-session-decision-durability
plan: 03
subsystem: pipeline, cli, shadow
tags: [durability, amnesia, audit, constraint-evaluation, duckdb, click]

requires:
  - phase: 10-cross-session-decision-durability
    provides: "Plan 01 schema/config/tables, Plan 02 evaluator/amnesia/index/writer"
provides:
  - "Pipeline Step 14: automatic constraint evaluation during extraction"
  - "CLI audit session: per-session compliance reporting with exit codes"
  - "CLI audit durability: per-constraint durability score display"
  - "ShadowReporter amnesia_rate and avg_durability_score metrics"
affects: [10-04, 10-05, shadow-reporting, pipeline-runner]

tech-stack:
  added: []
  patterns:
    - "CLI exit code convention: 0=clean, 1=error, 2=amnesia detected"
    - "ShadowReporter SQL aggregation for cross-table amnesia metrics"

key-files:
  created:
    - src/pipeline/cli/audit.py
    - tests/test_audit_cli.py
    - tests/test_durability_integration.py
  modified:
    - src/pipeline/runner.py
    - src/pipeline/cli/__main__.py
    - src/pipeline/shadow/reporter.py

key-decisions:
  - "Step 14 placed after escalation detection (Step 13), before stats (Step 15)"
  - "CLI audit session writes eval results to DB during audit (not read-only)"
  - "ShadowReporter amnesia_rate: sessions_with_amnesia / audited_sessions"
  - "PASS/FAIL gate on amnesia_rate: PASS if 0.0%, FAIL otherwise (zero tolerance)"
  - "avg_durability_score excludes constraints with < 3 sessions from average"

patterns-established:
  - "CLI exit code 2 for amnesia detection (distinct from error code 1)"
  - "ShadowReporter cross-table SQL aggregation pattern for Phase 10 metrics"

duration: 8min
completed: 2026-02-20
---

# Phase 10 Plan 03: Pipeline Integration + CLI Summary

**Pipeline Step 14 evaluates constraint compliance during extraction; CLI audit session/durability commands with exit code 2 for amnesia; ShadowReporter includes amnesia_rate and avg_durability_score**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20T11:03:46Z
- **Completed:** 2026-02-20T11:11:59Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Pipeline run_session() automatically evaluates constraint compliance as Step 14 between escalation detection and stats computation
- CLI `audit session` command reports HONORED/VIOLATED per constraint with amnesia detection and exit code 2 on violations
- CLI `audit durability` command shows per-constraint durability scores with minimum sessions threshold display
- ShadowReporter includes amnesia_rate and avg_durability_score in compute_report() with PASS/FAIL gate formatting
- 643 tests passing (616 baseline + 27 new, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Pipeline Step 14 + CLI audit commands** - `cccc68d` (feat)
2. **Task 2: ShadowReporter amnesia metrics + integration tests** - `edcddaa` (feat)

## Files Created/Modified
- `src/pipeline/runner.py` - Added Step 14 (constraint evaluation), renumbered Step 14->15 (stats)
- `src/pipeline/cli/audit.py` - New audit group with session and durability subcommands
- `src/pipeline/cli/__main__.py` - Registered audit_group in CLI entry point
- `src/pipeline/shadow/reporter.py` - Added _compute_amnesia_metrics(), updated compute_report() and format_report()
- `tests/test_audit_cli.py` - 15 CLI tests (session output, filtering, JSON, exit codes, durability)
- `tests/test_durability_integration.py` - 12 integration tests (full flow, reporter, threshold)

## Decisions Made
- Step 14 evaluates all active constraints with scope overlap against session events, writing results to session_constraint_eval table
- CLI audit session is not read-only: it writes eval results and amnesia events to the database during audit
- Exit code 2 chosen for amnesia detection (distinct from error code 1) per locked decision 9
- Reporter amnesia_rate = sessions_with_amnesia / total_audited_sessions (left join SQL pattern)
- avg_durability_score excludes constraints below min_sessions threshold from the average calculation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 10 Plans 01-03 complete: schema, evaluator engine, and pipeline integration all wired
- Ready for Plan 04 (if exists): further durability enhancements or phase completion
- All three AMNESIA requirements (01/02/03) are now implemented end-to-end

---
*Phase: 10-cross-session-decision-durability*
*Completed: 2026-02-20*
