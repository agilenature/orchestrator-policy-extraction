---
phase: 09-obstacle-escalation-detection
plan: 02
subsystem: pipeline
tags: [escalation, detector, sliding-window, tdd, sequence-detection]

# Dependency graph
requires:
  - phase: 09-obstacle-escalation-detection
    provides: EscalationCandidate model, EscalationConfig on PipelineConfig, O_ESC label
  - phase: 01-event-stream-foundation
    provides: TaggedEvent, Classification, CanonicalEvent models, make_event/make_tagged_event helpers
provides:
  - EscalationDetector class with detect() method at src/pipeline/escalation/detector.py
  - 40 test cases (15 positive, 15 negative, 10 edge case) at tests/test_escalation_detector.py
  - EscalationDetector exported from src/pipeline/escalation/__init__.py
affects: [09-03-PLAN, 09-04-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: [sliding-window sequence detection with pending window list, two-layer bypass eligibility check, dataclass for internal window state]

key-files:
  created:
    - src/pipeline/escalation/detector.py
    - tests/test_escalation_detector.py
    - tests/fixtures/escalation/__init__.py
  modified:
    - src/pipeline/escalation/__init__.py

key-decisions:
  - "Two-layer bypass eligibility: tag-based (T_RISKY/T_GIT_COMMIT/T_TEST) AND tool-name-based (Write/Edit/Bash) -- either triggers bypass"
  - "Exempt tools completely transparent to window -- they do not decrement the turn counter and never trigger bypass"
  - "X_ASK/X_PROPOSE resets ALL pending windows via pending.clear() -- not just the most recent"
  - "Sequential block dedup: oldest window consumed per bypass event, at most 1 candidate per bypass"
  - "Window expiry check uses > (not >=) so window_turns=5 allows 5 non-exempt events before expiry"
  - "Always-bypass pattern matching uses case-insensitive substring containment (same as tagger _matches_any pattern)"

patterns-established:
  - "Sliding window detection with _PendingWindow dataclass tracking non-exempt turn count per open window"
  - "bypass_consumed flag for single-bypass-per-event deduplication across multiple pending windows"

# Metrics
duration: 6min
completed: 2026-02-19
---

# Phase 9 Plan 02: Escalation Detector Summary

**Sliding-window EscalationDetector with two-layer bypass eligibility, exempt-tool transparency, X_ASK window reset, sequential-block dedup, and 40 TDD test cases covering all 6 categories**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-20T00:48:19Z
- **Completed:** 2026-02-20T00:54:52Z
- **Tasks:** 3 (TDD RED, GREEN, REFACTOR)
- **Files modified:** 4

## Accomplishments
- Implemented EscalationDetector.detect() with sliding-window algorithm that walks TaggedEvent streams and identifies block-then-bypass sequences within configurable turn window
- Two-layer bypass eligibility check: tag-based (T_RISKY, T_GIT_COMMIT, T_TEST) AND tool-name-based (Write, Edit, Bash), plus always-bypass patterns (rm, chmod, sudo) in Bash command text
- Exempt tools (Read, Glob, Grep, WebFetch, WebSearch, Task) are completely transparent to window -- they neither count toward window turns nor trigger bypass detection (Pitfall 1)
- X_ASK/X_PROPOSE resets ALL pending windows entirely (approval sought)
- Sequential block deduplication: at most 1 EscalationCandidate per bypass event, consuming oldest matching window (Pitfall 2)
- 40 test cases: 5 blatant bypass + 5 delayed bypass + 5 indirect bypass + 5 read-only negative + 5 X_ASK-reset negative + 5 window-expired negative + 10 edge cases
- All 479 tests pass (439 existing + 40 new), zero regressions

## Task Commits

Each task was committed atomically (TDD flow):

1. **Task 1: TDD RED -- failing tests** - `395af06` (test)
2. **Task 2: TDD GREEN -- implementation** - `acff093` (feat)
3. **Task 3: TDD REFACTOR -- cleanup** - `cf199e4` (refactor)

## Files Created/Modified
- `src/pipeline/escalation/detector.py` - EscalationDetector class with detect() method, sliding window algorithm (208 lines)
- `tests/test_escalation_detector.py` - 40 test cases across 6 categories (688 lines)
- `src/pipeline/escalation/__init__.py` - Updated exports to include EscalationDetector
- `tests/fixtures/escalation/__init__.py` - Empty init for escalation test fixtures package

## Decisions Made
- Two-layer bypass eligibility: tag-based (T_RISKY/T_GIT_COMMIT/T_TEST) AND tool-name-based (Write/Edit/Bash) -- either triggers bypass. This ensures Write/Edit/Bash calls without T_RISKY tag are still caught (Pitfall 5)
- Exempt tools completely transparent to window -- they do not decrement the turn counter. A 5-turn window means 5 non-exempt events, not 5 total events (Pitfall 1)
- X_ASK/X_PROPOSE resets ALL pending windows via `pending.clear()` -- not just the most recent. This matches the research specification that "approval sought" clears the escalation state entirely
- Sequential block dedup: when a bypass event matches multiple pending windows (from sequential O_GATE then O_CORR), only the oldest window is consumed, producing at most 1 candidate per bypass event (Pitfall 2)
- Window expiry uses `>` comparison (`non_exempt_turns > window_turns`) so window_turns=5 allows exactly 5 non-exempt events before the window expires on the 6th
- Always-bypass pattern matching uses case-insensitive substring containment, consistent with the existing tagger's `_matches_any` pattern
- Used `_PendingWindow` dataclass (not dict) for type safety and clarity in internal window tracking

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- EscalationDetector ready for integration into PipelineRunner (Plan 03)
- detect() returns list[EscalationCandidate] ready for constraint generation (Plan 04)
- All test infrastructure in place for integration tests
- Pre-existing test_escalation_constraint_gen.py (from earlier session) imports non-existent constraint_gen module -- will be resolved in Plan 04

## Self-Check: PASSED

All 4 created/modified files verified present. All 3 task commits (395af06, acff093, cf199e4) verified in git log. 479 tests passing.

---
*Phase: 09-obstacle-escalation-detection*
*Completed: 2026-02-19*
