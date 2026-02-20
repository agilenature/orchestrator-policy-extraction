---
phase: 13-policy-to-constraint-feedback-loop
plan: 01
subsystem: feedback
tags: [pydantic, duckdb, sha256, feedback-loop, constraint-extractor]

# Dependency graph
requires:
  - phase: 03-constraint-management
    provides: "ConstraintExtractor with _make_constraint_id"
  - phase: 10-cross-session-decision-durability
    provides: "DuckDB schema pattern, writer pattern (write_amnesia_events)"
  - phase: 12-governance-protocol-integration
    provides: "GovernanceConfig pattern in PipelineConfig"
provides:
  - "PolicyErrorEvent frozen Pydantic model with deterministic SHA-256 IDs"
  - "make_policy_error_event factory function"
  - "PolicyFeedbackConfig in PipelineConfig (promote_after_sessions, error_rate_target, rolling_window_sessions)"
  - "policy_error_events DuckDB table with CHECK constraint and session index"
  - "write_policy_error_events idempotent writer function"
  - "ConstraintExtractor._make_constraint_id source parameter for multi-origin constraint IDs"
affects: [13-02, 13-03, policy-checker, feedback-extractor]

# Tech tracking
tech-stack:
  added: []
  patterns: ["source parameter on constraint ID generation for multi-origin tracking"]

key-files:
  created:
    - "src/pipeline/feedback/__init__.py"
    - "src/pipeline/feedback/models.py"
    - "tests/test_feedback_models.py"
  modified:
    - "src/pipeline/models/config.py"
    - "src/pipeline/storage/schema.py"
    - "src/pipeline/storage/writer.py"
    - "src/pipeline/constraint_extractor.py"

key-decisions:
  - "Single PolicyErrorEvent model serves both domain and storage roles (no separate PolicyError)"
  - "Forward-only ID break: _make_constraint_id now appends :source, old constraints keep old IDs"
  - "Pipe separator kept in ConstraintExtractor per locked decision; JSON separator deferred to PolicyFeedbackExtractor in Plan 02"

patterns-established:
  - "source parameter on ID generation: enables multi-origin constraint tracking without breaking existing data"
  - "PolicyFeedbackConfig follows same sub-model pattern as EscalationConfig, DurabilityConfig, GovernanceConfig"

# Metrics
duration: 4min
completed: 2026-02-20
---

# Phase 13 Plan 01: Feedback Data Models Summary

**Frozen PolicyErrorEvent model with deterministic SHA-256 IDs, DuckDB policy_error_events table, idempotent writer, and source-aware constraint ID generation**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-20T18:39:15Z
- **Completed:** 2026-02-20T18:43:28Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- PolicyErrorEvent frozen Pydantic model with make_policy_error_event factory generating deterministic SHA-256 error IDs
- PolicyFeedbackConfig wired into PipelineConfig with promote_after_sessions=3, error_rate_target=0.05, rolling_window_sessions=100
- policy_error_events DuckDB table with CHECK constraint on error_type and session index
- write_policy_error_events idempotent writer using INSERT OR REPLACE pattern
- ConstraintExtractor._make_constraint_id updated with source parameter (forward-only ID break, pipe separator preserved)
- 23 comprehensive tests covering all new functionality including backward compatibility verification

## Task Commits

Each task was committed atomically:

1. **Task 1: Feedback package models + PolicyFeedbackConfig** - `b96a86a` (feat)
2. **Task 2: DuckDB schema + writer + ConstraintExtractor ID update + tests** - `b72f1db` (feat)

## Files Created/Modified
- `src/pipeline/feedback/__init__.py` - Package init with exports
- `src/pipeline/feedback/models.py` - PolicyErrorEvent frozen model + make_policy_error_event factory
- `src/pipeline/models/config.py` - Added PolicyFeedbackConfig sub-model to PipelineConfig
- `src/pipeline/storage/schema.py` - Added policy_error_events table and index to create_schema/drop_schema
- `src/pipeline/storage/writer.py` - Added write_policy_error_events function
- `src/pipeline/constraint_extractor.py` - Updated _make_constraint_id with source parameter
- `tests/test_feedback_models.py` - 23 tests for models, config, schema, writer, and constraint ID

## Decisions Made
- Used a single PolicyErrorEvent model for both domain and storage (no separate PolicyError class needed since fields are identical)
- Forward-only ID break on _make_constraint_id: appending `:source` changes new IDs but existing constraints.json IDs are not retroactively recomputed
- Kept pipe separator in ConstraintExtractor per locked decision; JSON separator reserved for PolicyFeedbackExtractor in Plan 02

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- PolicyErrorEvent model and storage ready for PolicyChecker (Plan 02) to detect and record errors
- ConstraintExtractor source parameter ready for PolicyFeedbackExtractor to use source='feedback_loop'
- PolicyFeedbackConfig defaults ready for aggregation and promotion logic in Plan 03

---
*Phase: 13-policy-to-constraint-feedback-loop*
*Completed: 2026-02-20*
