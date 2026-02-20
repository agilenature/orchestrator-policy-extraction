---
phase: 10-cross-session-decision-durability
plan: 02
subsystem: pipeline
tags: [durability, evaluation, amnesia, duckdb, pydantic, scope-extraction]

# Dependency graph
requires:
  - phase: 10-cross-session-decision-durability (plan 01)
    provides: "DuckDB tables (session_constraint_eval, amnesia_events), DurabilityConfig, scopes_overlap(), ConstraintStore temporal methods"
provides:
  - "SessionConstraintEvaluator with 3-state HONORED/VIOLATED/UNKNOWN evaluation"
  - "AmnesiaDetector with deterministic SHA-256 amnesia IDs"
  - "DurabilityIndex for SQL-based score computation (min_sessions=3)"
  - "extract_session_scope() for file path derivation from event payloads"
  - "write_constraint_evals() and write_amnesia_events() DuckDB writers"
affects: [10-03-pipeline-integration, 10-04-cli-commands, 10-05-reporting]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Compiled regex for Bash file path extraction (avoids URL false positives)"
    - "Pre-compiled case-insensitive patterns per constraint (not per event)"
    - "INSERT OR REPLACE for idempotent DuckDB writes"
    - "Frozen Pydantic models for immutable evaluation/amnesia results"

key-files:
  created:
    - src/pipeline/durability/scope_extractor.py
    - src/pipeline/durability/evaluator.py
    - src/pipeline/durability/amnesia.py
    - src/pipeline/durability/index.py
    - tests/test_durability_scope.py
    - tests/test_durability_evaluator.py
    - tests/test_durability_amnesia.py
    - tests/test_durability_index.py
  modified:
    - src/pipeline/storage/writer.py
    - src/pipeline/durability/__init__.py

key-decisions:
  - "Evaluator operates on raw constraint dicts (no ConstraintStore dependency) for flexibility"
  - "Detection hints scan uses case-insensitive substring containment (matches Phase 9 pattern)"
  - "Evidence payload_excerpt truncated to DurabilityConfig.evidence_excerpt_max_chars (default 500)"
  - "One match per event is sufficient (break after first hint match per event)"
  - "AmnesiaDetector is stateless; detected_at uses current UTC"

patterns-established:
  - "Evaluator returns results, writer stores them (separation of concerns)"
  - "Temporal status check inline in evaluator (mirrors ConstraintStore logic)"
  - "Deterministic ID pattern: SHA-256(composite_key).hexdigest()[:16]"

# Metrics
duration: 6min
completed: 2026-02-20
---

# Phase 10 Plan 02: Durability Evaluator Summary

**3-state constraint evaluator (HONORED/VIOLATED/excluded) with temporal+scope filtering, amnesia detector with SHA-256 deterministic IDs, durability index via SQL aggregation, and idempotent DuckDB writers**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-20T10:53:09Z
- **Completed:** 2026-02-20T11:00:03Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- SessionScopeExtractor derives file paths from Read/Edit/Write tool payloads and Bash commands with compiled regex
- SessionConstraintEvaluator produces HONORED/VIOLATED results with temporal existence, temporal status, scope overlap, O_ESC auto-violation, and detection hints scanning
- AmnesiaDetector generates deterministic amnesia events (SHA-256(session_id + constraint_id)[:16]) from VIOLATED results with constraint metadata lookup
- DurabilityIndex computes per-constraint durability scores via SQL aggregation with configurable min_sessions threshold (default 3, null below)
- write_constraint_evals and write_amnesia_events provide idempotent INSERT OR REPLACE storage
- 59 new tests across 4 test files, 616 total passing, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Session scope extractor + constraint evaluator + amnesia detector** - `4d9ee51` (feat)
2. **Task 2: Durability index + DuckDB writers + module exports** - `0bd27a7` (feat)

## Files Created/Modified
- `src/pipeline/durability/scope_extractor.py` - Extracts file paths from event payloads (Read/Edit/Write details + Bash regex)
- `src/pipeline/durability/evaluator.py` - 3-state constraint evaluator with temporal/scope/O_ESC/hints logic
- `src/pipeline/durability/amnesia.py` - Creates deterministic amnesia events from VIOLATED results
- `src/pipeline/durability/index.py` - SQL aggregation for durability scores with min_sessions threshold
- `src/pipeline/durability/__init__.py` - Public API exports for durability module
- `src/pipeline/storage/writer.py` - Added write_constraint_evals() and write_amnesia_events()
- `tests/test_durability_scope.py` - 14 scope extraction tests
- `tests/test_durability_evaluator.py` - 17 evaluator tests (HONORED, VIOLATED, temporal, O_ESC, multi)
- `tests/test_durability_amnesia.py` - 13 amnesia detector tests (determinism, metadata, evidence)
- `tests/test_durability_index.py` - 15 index + writer tests (scores, idempotency, filtering)

## Decisions Made
- Evaluator operates on raw constraint dicts rather than requiring ConstraintStore, enabling use from both pipeline runner and CLI
- Detection hints scan uses case-insensitive substring containment (re.escape + re.IGNORECASE), matching the Phase 9 always-bypass pattern
- Pre-compile hint patterns once per constraint (not per event) as noted in research pitfall
- One match per event is sufficient: break after first hint match to avoid redundant evidence
- AmnesiaDetector is stateless; detected_at set to current UTC at detection time

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All durability evaluation modules are ready for pipeline integration (Plan 03: Step 14 in run_session)
- DurabilityIndex ready for CLI audit commands (Plan 03/04)
- Module exports verified: `from src.pipeline.durability import SessionConstraintEvaluator, AmnesiaDetector, DurabilityIndex, extract_session_scope, migrate_constraints`

## Self-Check: PASSED

All 10 created/modified files verified present. Both task commits (4d9ee51, 0bd27a7) verified in git log. 59 new tests passing, 616 total.

---
*Phase: 10-cross-session-decision-durability*
*Completed: 2026-02-20*
