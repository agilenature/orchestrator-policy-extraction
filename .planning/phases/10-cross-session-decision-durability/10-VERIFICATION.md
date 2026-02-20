---
phase: 10-cross-session-decision-durability
verified: 2026-02-20T11:24:27Z
status: passed
score: 5/5 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "data/constraints.json migrated: all 185 constraints now have type=behavioral_constraint, status_history, and supersedes fields (committed in feat(constraints): add type, status history, and supersedes metadata to all constraints)"
  gaps_remaining: []
  regressions: []
---

# Phase 10: Cross-Session Decision Durability Verification Report

**Phase Goal:** The system tracks which constraints were read, honored, and violated in each session. A decision durability index gives each constraint a survival score across sessions. Sessions that violate active constraints are flagged as amnesia events.
**Verified:** 2026-02-20T11:24:27Z
**Status:** passed
**Re-verification:** Yes -- after gap closure (migration executed and committed)

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Session start audit surfaces all constraints relevant to current task scope (via `audit session` command) | VERIFIED | `audit session` completes in 0.575s against real DB; evaluates 176 active constraints with scope/temporal filtering |
| 2  | Decision durability index: each constraint has `durability_score` = sessions_honored / sessions_active | VERIFIED | DurabilityIndex.compute_score() returns float for constraints with >= 3 sessions (96 of 166 have scores); null for insufficient data (70 of 166); SQL formula confirmed as sessions_honored / sessions_active |
| 3  | Cross-session amnesia detection: sessions violating pre-existing constraints produce amnesia events | VERIFIED | 1309 amnesia events in real DB; 167 sessions flagged; SHA-256 deterministic IDs; `audit session` exits with code 2 |
| 4  | `data/constraints.json` constraints have type=behavioral_constraint and status_history fields | VERIFIED | 185/185 constraints have `type` field; 185/185 have `status_history`; spot-check shows type=behavioral_constraint with bootstrapped status_history from created_at; migration committed in git (470624a) |
| 5  | `python -m src.pipeline.cli audit session` reports amnesia events for any session | VERIFIED | CLI runs, exits with code 2 for sessions with violations, returns structured JSON with amnesia event details; `audit --help` shows session and durability subcommands |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/durability/scope_extractor.py` | extract_session_scope() | VERIFIED | 134 lines; exports `extract_session_scope`; handles Read/Edit/Write details + Bash regex; 14 tests pass |
| `src/pipeline/durability/evaluator.py` | SessionConstraintEvaluator with 3-state eval | VERIFIED | 285 lines; exports `SessionConstraintEvaluator`, `ConstraintEvalResult`; HONORED/VIOLATED with temporal+scope+O_ESC+hints logic; 17 tests pass |
| `src/pipeline/durability/amnesia.py` | AmnesiaDetector with SHA-256 IDs | VERIFIED | 100 lines; exports `AmnesiaDetector`, `AmnesiaEvent`; deterministic SHA-256(session_id + constraint_id)[:16]; 13 tests pass |
| `src/pipeline/durability/index.py` | DurabilityIndex SQL aggregation | VERIFIED | 171 lines; exports `DurabilityIndex`; compute_score(), compute_all_scores(), get_amnesia_events(); 15 tests pass |
| `src/pipeline/durability/migration.py` | migrate_constraints() | VERIFIED | 170 lines; exports `migrate_constraints`; idempotent field backfill with schema validation; 15 tests pass |
| `src/pipeline/cli/audit.py` | audit session + audit durability commands | VERIFIED | 275 lines; exports `audit_group`; session (exit 0/1/2) and durability subcommands; 16 tests pass |
| `src/pipeline/runner.py` | Step 14 session constraint evaluation | VERIFIED | Step 14 present, between Step 13 (escalation) and Step 15 (stats); imports SessionConstraintEvaluator, AmnesiaDetector, extract_session_scope |
| `src/pipeline/shadow/reporter.py` | amnesia_rate in compute_report() | VERIFIED | `_compute_amnesia_metrics()` method; amnesia_rate and avg_durability_score returned; "Decision Durability Metrics:" section in format_report() with PASS/FAIL gate |
| `data/schemas/constraint.schema.json` | type, status_history, supersedes fields | VERIFIED | All three fields present; type enum, status_history array with status/changed_at objects, supersedes string/null |
| `src/pipeline/storage/schema.py` | session_constraint_eval and amnesia_events tables | VERIFIED | Both tables created with CREATE TABLE IF NOT EXISTS; composite PK on session_constraint_eval; 4 indexes; correct columns |
| `src/pipeline/models/config.py` | DurabilityConfig wired into PipelineConfig | VERIFIED | DurabilityConfig(min_sessions_for_score=3, evidence_excerpt_max_chars=500); `durability: DurabilityConfig = Field(default_factory=DurabilityConfig)` in PipelineConfig |
| `src/pipeline/utils.py` | scopes_overlap() shared utility | VERIFIED | Function at line 12; bidirectional prefix matching; either empty list = repo-wide scope |
| `data/constraints.json` | Migrated with type=behavioral_constraint and status_history | VERIFIED | 185/185 have type field; 185/185 have status_history; migration committed in git (commit 470624a) -- gap from initial verification is now closed |
| `tests/test_durability_migration.py` | Migration + temporal method tests | VERIFIED | 15 tests pass |
| `tests/test_durability_scope.py` | Scope extractor tests | VERIFIED | 14 tests pass |
| `tests/test_durability_evaluator.py` | Evaluator tests | VERIFIED | 17 tests pass |
| `tests/test_durability_amnesia.py` | Amnesia detector tests | VERIFIED | 13 tests pass |
| `tests/test_durability_index.py` | Index + writer tests | VERIFIED | 15 tests pass |
| `tests/test_audit_cli.py` | CLI audit tests | VERIFIED | 16 tests pass |
| `tests/test_durability_integration.py` | End-to-end integration tests | VERIFIED | 12 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/pipeline/durability/evaluator.py` | `src/pipeline/utils.py` | `scopes_overlap()` for scope matching | WIRED | `from src.pipeline.utils import scopes_overlap` at line 26; called in `_evaluate_single()` |
| `src/pipeline/durability/evaluator.py` | `src/pipeline/models/config.py` | DurabilityConfig for max_excerpt | WIRED | `self._max_excerpt = config.durability.evidence_excerpt_max_chars` |
| `src/pipeline/durability/amnesia.py` | `src/pipeline/durability/evaluator.py` | Takes VIOLATED results | WIRED | `from src.pipeline.durability.evaluator import ConstraintEvalResult`; filters `eval_state == "VIOLATED"` |
| `src/pipeline/durability/index.py` | `session_constraint_eval` table | SQL aggregation for scores | WIRED | SELECT with GROUP BY constraint_id and COUNT/SUM aggregation |
| `src/pipeline/storage/writer.py` | `session_constraint_eval` table | INSERT OR REPLACE | WIRED | `INSERT OR REPLACE INTO session_constraint_eval` at line 915; verified in tests |
| `src/pipeline/storage/writer.py` | `amnesia_events` table | INSERT OR REPLACE | WIRED | `INSERT OR REPLACE INTO amnesia_events` at line 954; verified in tests |
| `src/pipeline/runner.py` | `src/pipeline/durability/evaluator.py` | Step 14 calls evaluate() | WIRED | `from src.pipeline.durability.evaluator import SessionConstraintEvaluator` at line 38; `evaluator.evaluate()` called in Step 14 block |
| `src/pipeline/runner.py` | `src/pipeline/durability/amnesia.py` | Step 14 creates amnesia events | WIRED | `from src.pipeline.durability.amnesia import AmnesiaDetector` at line 37; `detector.detect()` called after eval |
| `src/pipeline/cli/audit.py` | `src/pipeline/durability/evaluator.py` | Audit session evaluates constraints | WIRED | `SessionConstraintEvaluator` imported and used in `audit_session()` |
| `src/pipeline/cli/audit.py` | `src/pipeline/durability/index.py` | Audit durability shows scores | WIRED | `DurabilityIndex` instantiated in `audit_durability()` |
| `src/pipeline/cli/__main__.py` | `src/pipeline/cli/audit.py` | CLI registers audit group | WIRED | `from src.pipeline.cli.audit import audit_group` and `cli.add_command(audit_group, name="audit")` |
| `src/pipeline/shadow/reporter.py` | `session_constraint_eval` table | SQL LEFT JOIN for amnesia_rate | WIRED | LEFT JOIN query in `_compute_amnesia_metrics()`; "Decision Durability Metrics:" section in format_report() |
| `src/pipeline/durability/__init__.py` | All submodules | Public API exports | WIRED | All 7 exports verified |
| `data/constraints.json` | `src/pipeline/durability/migration.py` | Migration backfills type/status_history | WIRED | Migration was executed and committed (commit 470624a); 185/185 constraints now carry migrated fields |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| AMNESIA-01: Track constraint compliance per session | SATISFIED | SessionConstraintEvaluator + write_constraint_evals() writing to session_constraint_eval; Step 14 in pipeline |
| AMNESIA-02: Durability score per constraint | SATISFIED | DurabilityIndex.compute_score() returns sessions_honored / sessions_active with min_sessions=3 threshold |
| AMNESIA-03: Amnesia event flagging + CLI audit | SATISFIED | AmnesiaDetector produces events; `audit session` reports them; exit code 2 on violations |

### Anti-Patterns Found

None. The data migration gap from initial verification has been resolved.

### Human Verification Required

None. All behaviors are verifiable programmatically.

### Gaps Summary

No gaps. The one gap from initial verification (migration never executed against data/constraints.json) was closed by running `python -m src.pipeline.durability.migration` and committing the result. All 185 constraints now carry `type=behavioral_constraint`, a bootstrapped `status_history`, and `supersedes=None`. The commit is logged as `470624a feat(constraints): add type, status history, and supersedes metadata to all constraints`. The test suite passes at 643/643 with zero regressions.

---

## Verification Command Results

| Command | Result |
|---------|--------|
| `python -m pytest tests/ -q --tb=short` | 643 passed (zero regressions) |
| `python -m src.pipeline.cli audit --help` | Shows `session` and `durability` subcommands |
| `python -c "import json; d=json.load(open('data/constraints.json')); print(sum(1 for c in d if c.get('type')), '/', len(d), 'have type field')"` | `185 / 185 have type field` |
| `python -c "import json; d=json.load(open('data/constraints.json')); print(sum(1 for c in d if c.get('status_history')), '/', len(d), 'have status_history')"` | `185 / 185 have status_history` |
| Spot-check first constraint type field | `type: behavioral_constraint` |
| Spot-check first constraint status_history | `[{'status': 'active', 'changed_at': '2026-02-06T00:00:00.636000+00:00'}]` |
| `git log --oneline -1 -- data/constraints.json` | `470624a feat(constraints): add type, status history, and supersedes metadata to all constraints` |
| `git status data/constraints.json` | `nothing to commit, working tree clean` |
| `python -c "from src.pipeline.durability import SessionConstraintEvaluator, AmnesiaDetector, DurabilityIndex, extract_session_scope; print('ok')"` | `ok` |
| `python -c "from src.pipeline.models.config import PipelineConfig; c=PipelineConfig(); print(c.durability.min_sessions_for_score)"` | `3` |
| `python -m src.pipeline.cli audit session --db data/ope.db --json > /dev/null 2>&1; echo $?` | `2` (amnesia events detected, correct exit code) |
| Audit execution time for single session | 0.575 seconds (well under 3-minute threshold) |
| Constraints with durability scores in real DB | 96 of 166 (with >= 3 sessions); 70 with null (insufficient data) |
| Total amnesia events in real DB | 1309 across 167 sessions |

---

_Verified: 2026-02-20T11:24:27Z_
_Verifier: Claude (gsd-verifier)_
