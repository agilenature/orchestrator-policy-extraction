---
phase: 19-control-plane-integration
plan: 02
subsystem: pipeline
tags: [stream-processor, state-machine, temporal-closure, episode-boundary, governance-signal]

# Dependency graph
requires:
  - phase: 14-live-session-governance-research
    provides: locked decision that X_ASK is mid-episode; event_level vs episode_level classification
provides:
  - SessionStateMachine with ACTIVE/TENTATIVE_END/CONFIRMED_END/REOPENED states
  - Signal boundary_dependency classification (event_level vs episode_level)
  - StreamProcessor with process_event(), flush_episode_signals(), TTL expiry
  - GovernanceSignal stub for parallel execution with Plan 19-01
  - MID_EPISODE_TYPES guard enforcing X_ASK Phase 14 locked decision
affects: [19-03-PLAN, 19-04-PLAN, 19-05-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: [temporal-closure-dependency state machine, boundary_dependency signal routing, mid-episode type guard]

key-files:
  created:
    - src/pipeline/live/stream/__init__.py
    - src/pipeline/live/stream/state_machine.py
    - src/pipeline/live/stream/signals.py
    - src/pipeline/live/stream/processor.py
    - tests/test_stream_processor.py
  modified: []

key-decisions:
  - "Added MID_EPISODE_TYPES frozenset with X_ASK guard at top of transition() to enforce Phase 14 locked decision"
  - "GovernanceSignal defined as local stub via try/except import since Plan 19-01 bus package runs in parallel"
  - "Conservative episode_level default for unknown signal types (defer rather than emit prematurely)"

patterns-established:
  - "MID_EPISODE_TYPES guard: check before any state transition logic to prevent mid-episode events from affecting boundary detection"
  - "boundary_dependency classification: every GovernanceSignal is event_level (fire immediately) or episode_level (buffer until CONFIRMED_END)"
  - "StreamProcessor._detect_signals() stub: governing daemon (Plan 03) wires real detectors via dependency injection"

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 19 Plan 02: Stream Processor Summary

**Real-time stream processor with SessionStateMachine (4-state episode boundary detection), boundary_dependency signal routing, and 27 tests enforcing temporal-closure-dependency CCD**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T18:21:56Z
- **Completed:** 2026-02-25T18:26:58Z
- **Tasks:** 5
- **Files created:** 5

## Accomplishments
- SessionStateMachine with ACTIVE -> TENTATIVE_END -> CONFIRMED_END lifecycle, plus REOPENED for continuation events
- Signal classification separating event_level (escalation, policy_violation, premise_warning) from episode_level (amnesia, constraint_eval, training_write)
- StreamProcessor that routes event_level signals immediately and buffers episode_level signals until CONFIRMED_END or TTL expiry
- Fixed X_ASK mid-episode invariant: plan code would have treated X_ASK as a continuation event (reopening TENTATIVE_END to ACTIVE), violating Phase 14 locked decision

## Task Commits

Each task was committed atomically:

1. **Task 1: SessionState enum and state machine** - `c7f6f0b` (feat)
2. **Task 2: Signal classification** - `a19fbac` (feat)
3. **Task 3: StreamProcessor** - `9731e37` (feat)
4. **Task 4: Package init** - `6c0111c` (feat)
5. **Task 5: Tests + X_ASK fix** - `cf42581` (test/fix)

## Files Created/Modified
- `src/pipeline/live/stream/state_machine.py` - SessionState enum, SessionStateMachine with transition() and is_ttl_expired()
- `src/pipeline/live/stream/signals.py` - EVENT_LEVEL_SIGNAL_TYPES, EPISODE_LEVEL_SIGNAL_TYPES, classify_boundary_dependency()
- `src/pipeline/live/stream/processor.py` - StreamProcessor with process_event(), flush_episode_signals(), GovernanceSignal stub
- `src/pipeline/live/stream/__init__.py` - Public API exports for stream package
- `tests/test_stream_processor.py` - 27 tests covering state machine, signal classification, and processor routing

## Decisions Made
- Added `MID_EPISODE_TYPES` frozenset checked at the top of `transition()` to enforce the Phase 14 locked decision that X_ASK never triggers state changes, in any state
- Used `try/except ImportError` for GovernanceSignal import from `..bus.models` since Plan 19-01 (bus package) runs in parallel and may not be deployed yet
- Unknown signal types default to `episode_level` (conservative: defer rather than emit prematurely)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] X_ASK treated as continuation event in TENTATIVE_END state**
- **Found during:** Task 5 (writing tests)
- **Issue:** Plan's state machine code checks `event_type not in END_TRIGGER_TYPES` as the continuation condition. X_ASK is not in END_TRIGGER_TYPES, so it would be treated as a continuation event, reopening from TENTATIVE_END to ACTIVE. This violates the plan's own must_have: "X_ASK events never trigger state transition."
- **Fix:** Added `MID_EPISODE_TYPES = frozenset({"X_ASK"})` and a guard at the top of `transition()` that returns `(self.state, False)` for any mid-episode event type before any state-specific logic executes.
- **Files modified:** `src/pipeline/live/stream/state_machine.py`, `src/pipeline/live/stream/__init__.py`
- **Verification:** Two dedicated tests confirm X_ASK preserves state in both ACTIVE and TENTATIVE_END
- **Committed in:** `cf42581` (Task 5 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential correctness fix. Without it, X_ASK would silently reopen episodes during TENTATIVE_END, producing false-positive boundary resets and corrupting episode_level signal timing. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Stream processor package complete; ready for Plan 03 (governing daemon) to wire real detectors
- GovernanceSignal stub will be replaced by canonical model when Plan 19-01 bus package completes
- Plan 03 can import from `src.pipeline.live.stream` and inject detectors via `StreamProcessor._detect_signals()` override

## Self-Check: PASSED

- All 5 source/test files: FOUND
- All 5 commit hashes: FOUND (c7f6f0b, a19fbac, 9731e37, 6c0111c, cf42581)
- 27/27 tests: PASSED (0.03s)

---
*Phase: 19-control-plane-integration*
*Completed: 2026-02-25*
