---
phase: 11-project-level-wisdom-layer
plan: 06
subsystem: cli
tags: [click, validation, exit-codes, constraints, scope-checking]

# Dependency graph
requires:
  - phase: 11-project-level-wisdom-layer
    provides: WisdomStore.search_by_scope(), wisdom CLI group
  - phase: 03-constraint-management
    provides: ConstraintStore.get_active_constraints()
  - phase: 10-cross-session-decision-durability
    provides: scopes_overlap() in utils.py
provides:
  - check-scope validation command with 0/1/2 exit codes
  - CI-usable scope violation detection via constraint text matching
affects: [governance, ci-pipelines]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "except SystemExit: raise before general except for sys.exit propagation"
    - "Exit code protocol: 0=clean, 1=violations, 2=runtime error"
    - "Title word extraction (>3 chars) for text-based constraint matching"

key-files:
  created: []
  modified:
    - src/pipeline/cli/wisdom.py
    - tests/test_cli_wisdom.py

key-decisions:
  - "Title words > 3 chars used for text matching (filters noise words)"
  - "2+ title word matches required for constraint linkage (reduces false positives)"
  - "Constraint scope paths checked via scopes_overlap() only when non-empty (empty = repo-wide)"
  - "All wisdom CLI commands use exit code 2 for runtime errors (consistent protocol)"

patterns-established:
  - "except SystemExit: raise pattern for try blocks containing sys.exit calls"
  - "Text-based constraint matching via extracted title words and case-insensitive containment"

# Metrics
duration: 5min
completed: 2026-02-20
---

# Phase 11 Plan 06: Gap Closure - check-scope Validation Summary

**check-scope rewritten from display-only to validation command with 0/1/2 exit codes and constraint violation detection via title-word text matching**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-20T15:44:17Z
- **Completed:** 2026-02-20T15:49:28Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Rewrote check-scope from a lookup/display command to a validation command with structured exit codes (0=no violations, 1=violation found, 2=runtime error)
- Implemented violation detection by matching scope_decision entity title words against active constraint text with scope overlap filtering
- Unified all wisdom CLI commands to use exit code 2 for runtime errors (previously exit 1)
- Added 5 new tests covering all three exit codes and edge cases (scope mismatch, empty DB)
- 712 total project tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite check-scope with 0/1/2 exit codes and violation detection** - `07fb7bb` (feat)
2. **Task 2: Add tests for check-scope exit codes and violation detection** - `6ae4e76` (test)

## Files Created/Modified
- `src/pipeline/cli/wisdom.py` - Rewrote check-scope to validation command with --constraints option, 0/1/2 exit codes, text-based violation detection; updated ingest/reindex/list to use exit code 2 for errors
- `tests/test_cli_wisdom.py` - Added constraints_json and empty_constraints_json fixtures; added 5 new tests for exit codes 0, 1, 2 and scope mismatch scenarios; updated existing test for new validation behavior

## Decisions Made
- Title words extracted by splitting title.lower() and filtering to length > 3 characters (removes noise words like "a", "the", "for")
- Require 2+ matching title words in constraint text for linkage (balances recall vs false positives)
- Constraint scope paths checked via scopes_overlap() only when constraint has non-empty paths (empty paths = repo-wide scope per utils.py convention)
- Updated existing test_wisdom_check_scope_with_match to pass --constraints with empty file, matching new validation behavior
- Severity filter: only "forbidden" and "requires_approval" count as violations (warnings are informational)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test for new command behavior**
- **Found during:** Task 1 (check-scope rewrite)
- **Issue:** test_wisdom_check_scope_with_match expected "[scope_decision]" in output, but rewritten command outputs "No violations found" instead of displaying individual scope decisions
- **Fix:** Updated test to pass --constraints with empty JSON file and assert "No violations found" instead of "[scope_decision]"
- **Files modified:** tests/test_cli_wisdom.py
- **Verification:** All 8 existing tests pass
- **Committed in:** 07fb7bb (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary update to existing test for API behavior change. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Gap 2 from 11-VERIFICATION.md is now closed: check-scope validates scope decisions against constraints with proper exit codes
- Both gap closure plans (05 + 06) complete for Phase 11
- Phase 11 fully delivered with all gaps closed
- Ready for Phase 12 (Governance) when needed

## Self-Check: PASSED

- FOUND: src/pipeline/cli/wisdom.py
- FOUND: tests/test_cli_wisdom.py
- FOUND: .planning/phases/11-project-level-wisdom-layer/11-06-SUMMARY.md
- FOUND: commit 07fb7bb (Task 1)
- FOUND: commit 6ae4e76 (Task 2)

---
*Phase: 11-project-level-wisdom-layer*
*Completed: 2026-02-20*
