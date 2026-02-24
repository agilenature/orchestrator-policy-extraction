---
phase: 17-candidate-assessment-system
plan: 01
subsystem: database
tags: [duckdb, pydantic, assessment, schema, transport-efficiency]

# Dependency graph
requires:
  - phase: 16-sacred-fire-intelligence-system
    provides: transport_efficiency_sessions table, flame_events table, memory_candidates extensions
  - phase: 15-ddf-detection-substrate
    provides: flame_events DDL, ai_flame_events view, DDF schema chain
provides:
  - assessment_te_sessions table for per-candidate TE scoring
  - assessment_baselines table for per-scenario population statistics
  - ScenarioSpec, AssessmentSession, AssessmentReport frozen Pydantic models
  - AssessmentSession.derive_jsonl_path for JSONL artifact location
  - ALTER TABLE extensions on memory_candidates, flame_events, project_wisdom
affects: [17-02-scenario-generator, 17-03-session-runner, 17-04-report-deposit]

# Tech tracking
tech-stack:
  added: []
  patterns: [assessment schema chain integration, JSONL path derivation from assessment_dir encoding]

key-files:
  created:
    - src/pipeline/assessment/__init__.py
    - src/pipeline/assessment/schema.py
    - src/pipeline/assessment/models.py
    - tests/test_assessment_schema.py
    - tests/test_assessment_models.py
  modified:
    - src/pipeline/ddf/schema.py
    - tests/test_ddf_schema.py

key-decisions:
  - "Claude CLI --session-id flag exists -- enables deterministic JSONL path derivation before session launch"
  - "MEMORY.md pre-seeding via ~/.claude/projects/{encoded}/memory/ verified working"
  - "ai_flame_events view requires refresh after ALTER TABLE on flame_events (DuckDB caches SELECT * column types)"
  - "source_type validation in Pydantic only (not DuckDB CHECK) per DuckDB ALTER TABLE limitation"

patterns-established:
  - "Assessment dir encoding: all slashes replaced with dashes (/tmp/foo -> -tmp-foo)"
  - "View refresh after ALTER TABLE: CREATE OR REPLACE VIEW to re-capture column list"

# Metrics
duration: 10min
completed: 2026-02-24
---

# Phase 17 Plan 01: Schema + Models + Session Launch Spike Summary

**DuckDB assessment_te_sessions/assessment_baselines tables, frozen Pydantic v2 models (ScenarioSpec/AssessmentSession/AssessmentReport), and Claude CLI --session-id spike confirming deterministic JSONL path derivation**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-24T21:55:07Z
- **Completed:** 2026-02-24T22:04:58Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Created assessment_te_sessions and assessment_baselines DuckDB tables with full schema chain integration
- Added ALTER TABLE extensions: memory_candidates.source_type, flame_events.assessment_session_id, project_wisdom.scenario_seed, project_wisdom.ddf_target_level
- Created three frozen Pydantic v2 models with deterministic SHA-256[:16] ID generation
- Verified Claude CLI --session-id flag exists, enabling deterministic JSONL path derivation
- Confirmed MEMORY.md pre-seeding works via ~/.claude/projects/{encoded}/memory/
- 16 new tests, 1533 total passing (zero regressions from 1517 baseline)

## Task Commits

Each task was committed atomically:

1. **Task 1: Assessment schema DDL + chain integration** - `cc9e4d8` (feat)
2. **Task 2: Frozen Pydantic v2 assessment models** - `224a2a9` (feat)
3. **Task 3: 16 tests + DuckDB view fix** - `2d7de7e` (test)

## Files Created/Modified

- `src/pipeline/assessment/__init__.py` - Module init
- `src/pipeline/assessment/schema.py` - DDL for assessment tables, ALTER TABLE extensions, view refresh
- `src/pipeline/assessment/models.py` - ScenarioSpec, AssessmentSession, AssessmentReport frozen models
- `src/pipeline/ddf/schema.py` - Added create_assessment_schema() call at end of chain
- `tests/test_assessment_schema.py` - 8 schema tests (creation, idempotency, extensions, constraints)
- `tests/test_assessment_models.py` - 8 model tests (frozen, IDs, validation, path derivation)
- `tests/test_ddf_schema.py` - Updated flame_events column count assertion for new column

## Decisions Made

1. **Claude CLI supports --session-id** -- The spike confirmed that `claude --session-id <uuid>` exists, which means Plan 17-03 (session runner) can assign a UUID before launch and derive the JSONL path deterministically without post-hoc discovery.
2. **MEMORY.md pre-seeding verified** -- Writing `~/.claude/projects/{encoded_dir}/memory/MEMORY.md` before session launch successfully seeds the session's MEMORY.md. This enables handicap injection for assessment scenarios.
3. **source_type validated in Pydantic only** -- Per the locked decision Q4, DuckDB ALTER TABLE cannot add CHECK constraints. The AssessmentReport.source_type validator enforces the `(production, assessment, simulation_review)` constraint.
4. **View refresh required after ALTER TABLE** -- DuckDB's `ai_flame_events` view (using `SELECT *`) caches column types at creation time. Adding `assessment_session_id` via ALTER TABLE causes a BinderException. Resolution: `CREATE OR REPLACE VIEW` at the end of `create_assessment_schema()`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DuckDB ai_flame_events view schema mismatch after ALTER TABLE**
- **Found during:** Task 3 (test execution)
- **Issue:** The `ai_flame_events` view uses `SELECT *` from `flame_events`, but DuckDB caches column types at view creation time. Adding `assessment_session_id` via ALTER TABLE in `create_assessment_schema()` caused a BinderException when the view was queried (expected 16 columns, found 17).
- **Fix:** Added `CREATE OR REPLACE VIEW ai_flame_events AS SELECT * FROM flame_events WHERE subject = 'ai'` at the end of `create_assessment_schema()` to refresh the view's cached schema.
- **Files modified:** `src/pipeline/assessment/schema.py`, `tests/test_ddf_schema.py`
- **Verification:** All 3 previously failing DDF tests now pass; full suite at 1533 passing.
- **Committed in:** `2d7de7e` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Bug fix was necessary for correctness -- without it, all existing `ai_flame_events` view queries would fail. No scope creep.

## Spike Results: Claude Code Session Launch

| Finding | Result |
|---------|--------|
| JSONL path derivation formula | Confirmed: `/tmp/dir/` -> `~/.claude/projects/-tmp-dir/{session_id}.jsonl` |
| `--session-id <uuid>` CLI flag | EXISTS -- deterministic path derivation possible |
| `--permission-mode bypassPermissions` | EXISTS -- enables unattended assessment runs |
| `--print` mode | EXISTS -- non-interactive execution |
| MEMORY.md pre-seeding | WORKS -- write to `~/.claude/projects/{encoded}/memory/MEMORY.md` before launch |
| `--no-session-persistence` | EXISTS but NOT wanted (we need JSONL persistence) |
| `--worktree` | EXISTS -- could isolate assessment git state |

**Critical finding for Plan 17-03:** The combination of `--session-id`, `--print`, and `--permission-mode bypassPermissions` provides all three requirements for automated assessment sessions: deterministic artifact paths, non-interactive execution, and unattended file operations.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Schema foundation complete: assessment_te_sessions, assessment_baselines, and all ALTER TABLE extensions in place
- Models ready: ScenarioSpec, AssessmentSession, AssessmentReport importable from `src.pipeline.assessment.models`
- Spike findings documented: Claude CLI flags for 17-03 session runner confirmed
- All tests passing: 1533 total (16 new + 1517 baseline)
- Ready for Plan 17-02 (Scenario Generator + CLI)

## Self-Check: PASSED

All 6 created files verified present. All 3 task commits verified in git log.

---
*Phase: 17-candidate-assessment-system*
*Completed: 2026-02-24*
