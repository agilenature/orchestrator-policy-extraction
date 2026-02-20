---
phase: 13-policy-to-constraint-feedback-loop
plan: 02
subsystem: feedback
tags: [constraint-checker, feedback-extractor, tdd, sha256, dedup, promotion]

# Dependency graph
requires:
  - phase: 13-01
    provides: "PolicyErrorEvent model, policy_error_events schema, make_policy_error_event factory"
provides:
  - "PolicyViolationChecker with pre-surfacing constraint check"
  - "PolicyFeedbackExtractor with constraint generation and promotion"
  - "ConstraintStore.find_by_hints() for dedup matching"
affects: [13-03-pipeline-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [pre-compiled-regex-hints, sha256-constraint-ids, hint-overlap-dedup, session-count-promotion]

key-files:
  created:
    - src/pipeline/feedback/checker.py
    - src/pipeline/feedback/extractor.py
    - tests/test_policy_violation_checker.py
    - tests/test_policy_feedback_extractor.py
  modified:
    - src/pipeline/constraint_store.py

key-decisions:
  - "Scope overlap without detection_hints is intentionally NOT matched -- deferred to future gap closure plan"
  - "Warning-severity constraints are logged but never suppressed"
  - "Dedup threshold: 2+ shared detection_hints (case-insensitive) to match existing human constraints"
  - "Promotion threshold: 3+ distinct sessions with surfaced_and_blocked events"

patterns-established:
  - "Pre-compiled regex patterns at init time for detection_hints matching"
  - "SHA-256 constraint ID with source suffix (:policy_feedback) for namespace isolation"
  - "Stateless extractor pattern: caller handles ConstraintStore.add()"

# Metrics
duration: 7min
completed: 2026-02-20
---

# Phase 13 Plan 02: Core Feedback Loop Components Summary

**PolicyViolationChecker and PolicyFeedbackExtractor with TDD: pre-surfacing constraint check, constraint generation from blocked recommendations, find_by_hints dedup, and session-count promotion**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-20T18:46:50Z
- **Completed:** 2026-02-20T18:53:26Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- PolicyViolationChecker with pre-compiled regex hint matching, severity-based suppression (forbidden/requires_approval suppress, warning logs only)
- PolicyFeedbackExtractor generating candidate constraints from blocked/corrected recommendations with deterministic SHA-256 IDs and 2+ hint dedup
- ConstraintStore.find_by_hints() for case-insensitive detection_hints overlap matching
- promote_confirmed() promoting candidates with 3+ distinct session evidence to active status
- 28 new TDD tests (13 checker + 15 extractor) all passing, zero regressions (1022 total)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write failing tests** - `77ffaa0` (test)
2. **Task 2: GREEN + REFACTOR -- Implement all components** - `6a352ae` (feat)

_TDD plan: RED phase committed separately from GREEN phase._

## Files Created/Modified
- `src/pipeline/feedback/checker.py` - PolicyViolationChecker with pre-compiled regex patterns and severity-based suppression logic
- `src/pipeline/feedback/extractor.py` - PolicyFeedbackExtractor with extract(), promote_confirmed(), SHA-256 ID generation
- `src/pipeline/constraint_store.py` - Added find_by_hints() method for detection_hints overlap dedup
- `tests/test_policy_violation_checker.py` - 13 tests covering suppression, warnings, case-insensitive, empty hints, scope deferral
- `tests/test_policy_feedback_extractor.py` - 15 tests covering extraction, dedup, constraint IDs, promotion

## Decisions Made
- Scope overlap without detection_hints intentionally NOT matched (documents CONTEXT.md Gray Area 2 deferral)
- Warning constraints return (False, constraint) to allow logging without suppression
- Detection hints include mode, scope paths, and key reasoning terms (up to 8 hints)
- Common stopwords filtered from reasoning when building detection hints

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PolicyViolationChecker and PolicyFeedbackExtractor ready for pipeline integration (Plan 03)
- ConstraintStore.find_by_hints() available for dedup checks
- 1022 tests passing, zero regressions

---
*Phase: 13-policy-to-constraint-feedback-loop*
*Completed: 2026-02-20*
