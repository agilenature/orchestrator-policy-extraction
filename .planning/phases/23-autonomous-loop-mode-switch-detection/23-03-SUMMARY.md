---
phase: 23-autonomous-loop-mode-switch-detection
plan: 03
subsystem: ebc, testing
tags: [ebc, drift-detection, integration-tests, tool-ratio, behavioral-signals, discovery-mode]

requires:
  - phase: 23-01
    provides: EBC models, parser, detector, writer
  - phase: 23-02
    provides: CLI --plan flag, STATE.md injector, runner wiring
provides:
  - "End-to-end integration tests for EBC drift pipeline (parse -> detect -> write)"
  - "Tool usage ratio signal (_compute_tool_ratio_signal) for Discovery Mode detection"
  - "Ratio-only alert guard using ratio_only_threshold (0.8)"
affects: [ebc, detector, testing]

tech-stack:
  added: []
  patterns:
    - "Secondary behavioral signal: read/write ratio as Discovery Mode indicator"
    - "Ratio-only threshold guard: higher bar for alerts with only behavioral signals"

key-files:
  created:
    - tests/test_ebc_integration.py
  modified:
    - src/pipeline/ebc/detector.py

key-decisions:
  - "Integration tests operate at component level (parse -> detect -> write) rather than full CLI pipeline -- cleaner and still validates end-to-end"
  - "High read/write ratio threshold set at 10:1 with minimum 20 read events -- avoids false positives on small sessions"
  - "Zero-write exploratory sessions get higher weight (0.5) than high-ratio sessions (0.3) -- pure exploration is stronger signal"
  - "Ratio-only alerts require ratio_only_threshold (0.8) not default (0.5) -- behavioral signals alone should not easily trigger alerts"

patterns-established:
  - "Behavioral pattern detection: tool usage ratios as secondary drift signals alongside file-set comparisons"

duration: 5min
completed: 2026-02-28
---

# Phase 23 Plan 03: Integration Tests and Behavioral Signal Summary

**End-to-end integration tests for EBC drift pipeline and tool usage ratio signal for Discovery Mode detection**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-28T00:16:02Z
- **Completed:** 2026-02-28T00:21:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- 18 integration tests covering the full parse_ebc_from_plan -> EBCDriftDetector.detect() -> write_alert() pipeline
- Tests include real PLAN.md parsing (22-01-PLAN.md), threshold overrides, empty sessions, JSON validity
- Tool usage ratio signal fires high_read_ratio when read/write ratio exceeds 10:1 with at least 20 read events
- Ratio-only alerts guarded by higher threshold (0.8) -- behavioral signals alone require stronger evidence
- Zero-write sessions classified as exploratory with weight 0.5; high-ratio sessions get weight 0.3
- 85 total EBC tests passing (16 detector + 15 models + 12 parser + 5 writer + 9 injector + 8 CLI + 18 integration + 2 real-plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create end-to-end integration tests for EBC drift pipeline** - `7125fb6` (test)
2. **Task 2: Add tool usage ratio signal to EBCDriftDetector** - `a033bc7` (feat)

## Files Created/Modified
- `tests/test_ebc_integration.py` - 18 integration tests: 6 parse-then-detect, 2 write-alert, 2 real-plan, 2 edge-case, 6 tool-ratio
- `src/pipeline/ebc/detector.py` - Added _compute_tool_ratio_signal(), _get_tool_name(), class constants, ratio-only guard in detect()

## Decisions Made
- Component-level integration tests (not full CLI) -- validates pipeline correctness without JSONL/DuckDB complexity
- 10:1 read/write ratio threshold with 20-event minimum -- calibrated to avoid false positives on normal build-test-fix cycles
- Separate weights for zero-write (0.5) vs high-ratio (0.3) -- pure exploration is a stronger behavioral signal than lopsided execution
- Ratio-only threshold (0.8) vs default (0.5) -- prevents behavioral-only signals from generating noisy alerts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Phase 23 Completion

Phase 23 (Autonomous Loop Mode-Switch Detection) is now complete with all 3 plans delivered:
- **Plan 01:** Core EBC models, parser, detector, writer, runner integration (5 min)
- **Plan 02:** CLI --plan/--inject-state flags, STATE.md injector, recovery command (5 min)
- **Plan 03:** Integration tests, tool usage ratio behavioral signal (5 min)

The EBC drift detection system is fully operational:
1. PLAN.md frontmatter is parsed into machine-readable ExternalBehavioralContract
2. Session events are compared against the contract for file-set drift
3. Tool usage ratio provides secondary behavioral signal for Discovery Mode detection
4. Drift alerts are persisted as JSON and optionally injected into STATE.md
5. 85 tests validate all components and their integration

---
*Phase: 23-autonomous-loop-mode-switch-detection*
*Completed: 2026-02-28*
