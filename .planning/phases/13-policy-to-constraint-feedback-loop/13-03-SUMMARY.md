---
phase: 13-policy-to-constraint-feedback-loop
plan: 03
subsystem: shadow-pipeline
tags: [feedback-loop, policy-errors, shadow-mode, constraint-extraction, cli]

# Dependency graph
requires:
  - phase: 13-01
    provides: "PolicyErrorEvent model, policy_error_events table, write_policy_error_events, PolicyFeedbackConfig"
  - phase: 13-02
    provides: "PolicyViolationChecker with detection_hints regex, PolicyFeedbackExtractor with dedup and promote_confirmed, find_by_hints on ConstraintStore"
provides:
  - "Pre-surfacing constraint check in ShadowModeRunner.run_session()"
  - "Batch feedback extraction after ShadowModeRunner.run_all()"
  - "ShadowReporter policy_error_rate metric with correct denominator"
  - "CLI 'audit policy-errors' subcommand with PASS/FAIL gate"
  - "16 integration tests proving full feedback loop"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-surfacing check pattern: check constraints before evaluation, skip suppressed"
    - "Batch-after-run pattern: persist errors and extract constraints only after all sessions complete"
    - "Denominator inclusion pattern: suppressed recs added back to denominator since they skip evaluation"

key-files:
  created:
    - "tests/test_feedback_integration.py"
  modified:
    - "src/pipeline/shadow/runner.py"
    - "src/pipeline/shadow/reporter.py"
    - "src/pipeline/cli/audit.py"

key-decisions:
  - "Pre-surfacing check uses PolicyViolationChecker.build_recommendation_text() to build searchable text from Recommendation fields"
  - "Suppressed recommendations skip evaluation entirely (continue in loop) and are NOT in shadow_mode_results"
  - "Surfaced-and-blocked detection uses reaction_label in (block, correct) after evaluation"
  - "Batch constraint write and promotion happens AFTER run_all completes, not during individual sessions"
  - "Policy error rate denominator = evaluated + suppressed to avoid undercounting total_attempted"
  - "CLI exit code 2 for error rate >= 5%, exit code 0 for clean or no data"

patterns-established:
  - "Feedback loop end-to-end: checker suppresses -> error recorded -> extractor generates constraints -> promote_confirmed"
  - "Policy error rate gate: PASS if rate < 5%, FAIL if >= 5%, N/A if no data"

# Metrics
duration: 8min
completed: 2026-02-20
---

# Phase 13 Plan 03: Feedback Loop Pipeline Integration Summary

**End-to-end feedback loop wired into ShadowModeRunner with pre-surfacing constraint checks, batch constraint extraction, policy_error_rate metric in ShadowReporter, and CLI audit policy-errors subcommand**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20T18:56:34Z
- **Completed:** 2026-02-20T19:04:21Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- ShadowModeRunner now integrates PolicyViolationChecker for pre-surfacing checks -- forbidden/requires_approval recommendations are suppressed before evaluation
- Batch feedback extraction after run_all: blocked recommendations generate new candidate constraints, with promote_confirmed() promoting 3+ session candidates to active
- ShadowReporter includes policy_error_rate metric with correct denominator (evaluated + suppressed) and PASS/FAIL gate
- CLI 'audit policy-errors' subcommand reports error rate with exit codes 0/1/2
- 16 integration tests proving the full feedback loop, denominator correctness, backward compatibility, and batch write timing

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire pre-surfacing check and feedback extraction into ShadowModeRunner** - `34ff058` (feat)
2. **Task 2: ShadowReporter policy_error_rate metric + CLI audit command + integration tests** - `4cc1595` (feat)

## Files Created/Modified
- `src/pipeline/shadow/runner.py` - Added optional checker/constraint_store params, pre-surfacing check, surfaced-and-blocked detection, batch feedback extraction
- `src/pipeline/shadow/reporter.py` - Added _compute_policy_error_metrics() with correct denominator, policy error section in format_report
- `src/pipeline/cli/audit.py` - Added 'policy-errors' subcommand with JSON output and exit codes 0/1/2
- `tests/test_feedback_integration.py` - 16 integration tests covering full feedback loop pipeline

## Decisions Made
- Pre-surfacing check uses `PolicyViolationChecker.build_recommendation_text()` to concatenate recommendation fields for hint matching
- Suppressed recommendations skip evaluation with `continue` and are NOT in shadow_mode_results
- Surfaced-and-blocked uses empty constraint_id since no specific constraint matched (detected via reaction_label)
- Policy error rate denominator includes suppressed count because suppressed recs never enter shadow_mode_results
- CLI exits with code 2 for rate >= 5%, 0 for clean or no data

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed temp file creation for DuckDB in CLI exit code test**
- **Found during:** Task 2 (integration tests)
- **Issue:** NamedTemporaryFile creates an empty file that DuckDB cannot open as a database
- **Fix:** Added os.unlink() after creating temp path to let DuckDB create a fresh database file
- **Files modified:** tests/test_feedback_integration.py
- **Verification:** Test passes, exit code 2 correctly returned
- **Committed in:** 4cc1595 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test infrastructure fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 13 (Policy-to-Constraint Feedback Loop) is now complete with all 3 plans delivered
- Full feedback loop operational: policy violations are detected, suppressed, and generate new constraints
- 889 tests passing with zero regressions
- Project is complete at 41/41 plans across all 13 phases

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 13-policy-to-constraint-feedback-loop*
*Completed: 2026-02-20*
