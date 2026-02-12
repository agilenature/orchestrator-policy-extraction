---
phase: 06-mission-control-integration
plan: 03
subsystem: mission-control
tags: [websocket, provenance, sqlite, tool-capture, aggregation]

# Dependency graph
requires:
  - phase: 06-mission-control-integration/plan-01
    provides: "SQLite episode schema (episode_events table), CRUD functions (insertEpisodeEvent, getEpisodeEvents)"
provides:
  - "ProvenanceCapture adapter for Gateway WebSocket tool event capture"
  - "ProvenanceAggregator for episode outcome population with executor_effects and quality metrics"
  - "ToolProvenanceEvent and GatewayMessage interfaces"
  - "Batch-buffered transactional SQLite writes for provenance events"
affects: [06-mission-control-integration/plan-02, 06-mission-control-integration/plan-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Batch buffer + periodic flush + transactional write for SQLite event capture"
    - "Defensive Gateway message parsing with console.debug for unrecognized types"
    - "Tool classification via command content analysis (git/test/lint/build sub-types)"

key-files:
  created:
    - "mission-control/src/lib/openclaw/provenance.ts"
    - "mission-control/src/lib/episodes/provenance-aggregator.ts"
  modified: []

key-decisions:
  - "classifyTool inspects Bash command content for git/test/lint/build sub-classification rather than relying on tool_name alone"
  - "tool_result events not counted as separate tool_calls (they are responses to preceding calls)"
  - "Failed flush re-adds events to buffer for retry rather than dropping them"
  - "Aggregator uses snake_case field names matching Pydantic model (executor_effects not executorEffects)"

patterns-established:
  - "Batch buffer pattern: configurable interval/size, periodic setInterval flush, transactional SQLite write"
  - "Defensive WS adapter pattern: flexible interface, console.debug for unknown, never crash"

# Metrics
duration: 3min
completed: 2026-02-12
---

# Phase 6 Plan 3: Tool Provenance Capture Summary

**ProvenanceCapture adapter for Gateway WS tool events with batch-buffered SQLite writes and ProvenanceAggregator for episode outcome population**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-12T01:47:16Z
- **Completed:** 2026-02-12T01:50:09Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- ProvenanceCapture adapter hooks into Gateway WebSocket messages, classifies tool events by type, buffers them, and writes to episode_events in batched transactions
- ProvenanceAggregator reads raw events, computes executor_effects (tool counts, files touched, commands, git events) and quality metrics (test/lint status, diff stats), and merges into episode outcome JSON
- Defensive handling throughout: unrecognized messages logged not crashed, failed flushes retry, null-safe aggregation returns zeroed structures

## Task Commits

Each task was committed atomically:

1. **Task 1: ProvenanceCapture adapter for Gateway WebSocket** - `7f0e5ae` (feat)
2. **Task 2: ProvenanceAggregator for episode outcome population** - `af4a6cc` (feat)

## Files Created/Modified
- `mission-control/src/lib/openclaw/provenance.ts` - ProvenanceCapture class, ToolProvenanceEvent/GatewayMessage interfaces, tool classification, batch buffering with transactional SQLite writes
- `mission-control/src/lib/episodes/provenance-aggregator.ts` - ProvenanceAggregator class, ExecutorEffects/OutcomeQuality interfaces, event aggregation, episode outcome JSON merging

## Decisions Made
- classifyTool inspects Bash command content (starts with "git ", includes "pytest", etc.) for sub-classification into git_event, test_result, lint_result, build_result rather than relying on tool_name alone
- tool_result events are not counted as separate tool_calls in aggregation (they are responses to preceding tool_call/file_touch events)
- Failed flush operations re-add events to buffer for retry on next flush rather than dropping them (provenance is valuable but not mission-critical)
- AggregationResult uses snake_case field names (executor_effects, not executorEffects) matching the Pydantic Episode model on the Python side

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added error recovery in flush()**
- **Found during:** Task 1 (ProvenanceCapture implementation)
- **Issue:** Plan specified flush() with transaction but no error handling. A failed transaction would leave the buffer empty with data lost.
- **Fix:** Added try/catch around insertBatch that logs the error and re-adds events to buffer for retry on next flush.
- **Files modified:** mission-control/src/lib/openclaw/provenance.ts
- **Verification:** Error path logs via console.error and buffer is restored
- **Committed in:** 7f0e5ae (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added command content analysis for sub-classification**
- **Found during:** Task 1 (classifyTool implementation)
- **Issue:** Plan specified simple tool_name-to-event_type mapping. But all git/test/lint/build commands go through Bash tool, so they would all be classified as 'command_run' without content inspection.
- **Fix:** classifyTool inspects Bash command content for git/test/lint/build patterns to provide accurate sub-classification.
- **Files modified:** mission-control/src/lib/openclaw/provenance.ts
- **Verification:** git commands classified as git_event, pytest as test_result, eslint as lint_result, tsc as build_result
- **Committed in:** 7f0e5ae (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 missing critical)
**Impact on plan:** Both auto-fixes essential for data accuracy and reliability. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ProvenanceCapture ready for integration with real-time task execution (Plan 02)
- ProvenanceAggregator ready for dashboard integration (Plan 04)
- Both classes depend on better-sqlite3 Database type (already established in Plan 01)

---
*Phase: 06-mission-control-integration*
*Completed: 2026-02-12*

## Self-Check: PASSED

- FOUND: mission-control/src/lib/openclaw/provenance.ts
- FOUND: mission-control/src/lib/episodes/provenance-aggregator.ts
- FOUND: commit 7f0e5ae (Task 1)
- FOUND: commit af4a6cc (Task 2)
