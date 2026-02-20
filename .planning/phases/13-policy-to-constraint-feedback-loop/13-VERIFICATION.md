---
phase: 13-policy-to-constraint-feedback-loop
verified: 2026-02-20T19:11:31Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 13: Policy-to-Constraint Feedback Loop Verification Report

**Phase Goal:** Close the feedback loop: when the trained policy recommends an action that a human subsequently blocks or corrects, that correction automatically propagates back into the constraint store and guardrail system. The policy becomes a source of new constraints, not just a consumer of them.
**Verified:** 2026-02-20T19:11:31Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1 | Every policy recommendation receiving a block/correct human reaction is automatically fed back into the constraint extraction pipeline — producing a new constraint entry attributed to the policy recommendation, not the human episode | VERIFIED | `PolicyFeedbackExtractor.extract()` in `src/pipeline/feedback/extractor.py` converts block/correct reactions to `source="policy_feedback", status="candidate"` constraints. Verified live: generated constraint has `source=policy_feedback`. `ShadowModeRunner.run_all()` batch-calls `extractor.extract()` after all sessions complete. |
| 2 | Constraint entries sourced from policy feedback are distinguishable from human-sourced constraints (source: policy_feedback vs source: human_correction) | VERIFIED | Two distinct ID namespaces confirmed: `PolicyFeedbackExtractor._make_constraint_id()` uses `SHA-256(text + JSON.dumps(sorted(scope_paths)) + ":policy_feedback")[:16]` while `ConstraintExtractor._make_constraint_id()` uses `SHA-256(text + "|".join(sorted(scope_paths)) + ":human_correction")[:16]`. Live verification: IDs are different (`ca8bc24d52a01486` vs `bc307ec31085b7c7` for same text/scope). Existing 194 constraints in `data/constraints.json` are unaffected (old format without source suffix). |
| 3 | The constraint store accumulates policy-feedback constraints over time; durability tracking (Phase 10) applies to these constraints identically to human-sourced ones | VERIFIED | `session_constraint_eval` and `amnesia_events` tables accept any constraint_id regardless of source. Phase 10 durability evaluator operates on all active constraints via `ConstraintStore.get_active_constraints()` with no source filtering. Verified: policy_feedback constraint IDs insert successfully into both durability tables. |
| 4 | The system detects when a policy recommendation would violate an existing constraint before surfacing it — policy recommendations that conflict with active constraints are suppressed and logged as policy errors, not surfaced to the human | VERIFIED | `PolicyViolationChecker.check()` in `src/pipeline/feedback/checker.py` returns `(True, constraint)` for forbidden/requires_approval hint matches and `(False, None)` for no match. `ShadowModeRunner.run_session()` checks via checker before evaluation; on `should_suppress=True`, records `PolicyErrorEvent(error_type='suppressed')` and calls `continue` to skip evaluation. Warning-severity matches return `(False, constraint)` (log only, not suppressed). Verified live: forbidden constraint correctly suppresses recommendation. |
| 5 | A policy error rate metric is tracked: fraction of policy recommendations that conflict with active constraints. Target < 5% after 100 sessions of feedback integration | VERIFIED | `ShadowReporter._compute_policy_error_metrics()` computes `rate = total_errors / total_attempted` where `total_attempted = COUNT(*) FROM shadow_mode_results + COUNT(suppressed) FROM policy_error_events`. CLI `audit policy-errors` surfaces this with PASS/FAIL gate. Verified live: 5 suppressed + 95 evaluated = 100 denominator, rate = 5%. `meets_threshold = rate < 0.05` (5% exactly is FAIL). Format_report shows "PASS" for rate < 5%. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/feedback/__init__.py` | Package init with exports | VERIFIED | 14 lines, exports `PolicyErrorEvent` and `make_policy_error_event` |
| `src/pipeline/feedback/models.py` | PolicyErrorEvent frozen Pydantic model + factory | VERIFIED | 89 lines, frozen=True, deterministic SHA-256 error_id, `make_policy_error_event` factory |
| `src/pipeline/feedback/checker.py` | PolicyViolationChecker with pre-surfacing constraint check | VERIFIED | 105 lines, pre-compiled regex patterns, severity-based suppression |
| `src/pipeline/feedback/extractor.py` | PolicyFeedbackExtractor with constraint generation and promotion | VERIFIED | 211 lines, `extract()`, `promote_confirmed()`, `_make_constraint_id()`, `_build_detection_hints()` |
| `src/pipeline/models/config.py` | PolicyFeedbackConfig added to PipelineConfig | VERIFIED | `PolicyFeedbackConfig` with `promote_after_sessions=3`, `error_rate_target=0.05`, `rolling_window_sessions=100`. Wired as `feedback` field in `PipelineConfig`. |
| `src/pipeline/storage/schema.py` | policy_error_events CREATE TABLE and index | VERIFIED | Table with CHECK constraint on `error_type IN ('suppressed', 'surfaced_and_blocked')`, `idx_policy_error_session` index, `DROP TABLE IF EXISTS policy_error_events` first in `drop_schema()` |
| `src/pipeline/storage/writer.py` | write_policy_error_events function | VERIFIED | 1012-line file exports `write_policy_error_events`, uses INSERT OR REPLACE for idempotent storage |
| `src/pipeline/constraint_extractor.py` | Updated _make_constraint_id with source parameter | VERIFIED | `_make_constraint_id(text, scope_paths, source="human_correction")` with pipe separator, appends `:source` to key |
| `src/pipeline/constraint_store.py` | find_by_hints() method | VERIFIED | `find_by_hints(detection_hints, min_overlap=2)` at line 226, case-insensitive overlap matching |
| `src/pipeline/shadow/runner.py` | Pre-surfacing check and feedback extraction in ShadowModeRunner | VERIFIED | Optional `checker` and `constraint_store` params, pre-surfacing check with `continue` on suppress, batch extraction after `run_all()` |
| `src/pipeline/shadow/reporter.py` | policy_error_rate metric in compute_report and format_report | VERIFIED | `_compute_policy_error_metrics()` with correct denominator, PASS/FAIL gate in `format_report()` |
| `src/pipeline/cli/audit.py` | policy-errors subcommand | VERIFIED | `@audit_group.command(name="policy-errors")` at line 273, exit codes 0/1/2, JSON output option |
| `tests/test_feedback_models.py` | Unit tests for models, config, writer, schema | VERIFIED | 324 lines, 23 tests |
| `tests/test_policy_violation_checker.py` | TDD tests for PolicyViolationChecker | VERIFIED | 358 lines, 13 tests |
| `tests/test_policy_feedback_extractor.py` | TDD tests for PolicyFeedbackExtractor | VERIFIED | 464 lines, 15 tests |
| `tests/test_feedback_integration.py` | Integration tests for full feedback loop pipeline | VERIFIED | 635 lines, 16 tests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/pipeline/feedback/extractor.py` | `src/pipeline/feedback/models.py` | `make_policy_error_event` import | VERIFIED | Line 20: `from src.pipeline.feedback.models import make_policy_error_event` |
| `src/pipeline/feedback/extractor.py` | `src/pipeline/constraint_store.py` | `find_by_hints()` for dedup, `add_status_history_entry()` for promotion | VERIFIED | `constraint_store.find_by_hints(detection_hints, min_overlap=2)` and `constraint_store.add_status_history_entry(constraint_id, "active", now_utc)` |
| `src/pipeline/feedback/checker.py` | `src/pipeline/constraint_store.py` | `get_active_constraints()` for loading constraints | VERIFIED | `constraint_store.get_active_constraints()` in `__init__` |
| `src/pipeline/shadow/runner.py` | `src/pipeline/feedback/checker.py` | `PolicyViolationChecker.check()` before evaluation | VERIFIED | Lines 31, 261-285: imported at top, used in `run_session()` |
| `src/pipeline/shadow/runner.py` | `src/pipeline/feedback/extractor.py` | `PolicyFeedbackExtractor.extract()` after run_all | VERIFIED | Lines 32, 124-139: imported at top, batch called after `_write_results()` |
| `src/pipeline/shadow/runner.py` | `src/pipeline/storage/writer.py` | `write_policy_error_events()` called to persist errors | VERIFIED | Lines 36, 120: imported at top, called after writing results |
| `src/pipeline/shadow/reporter.py` | policy_error_events table | Queries `policy_error_events` in `_compute_policy_error_metrics()` | VERIFIED | SQL query at line 300: `FROM policy_error_events` |
| `src/pipeline/cli/audit.py` | `src/pipeline/shadow/reporter.py` | `ShadowReporter._compute_policy_error_metrics()` | VERIFIED | Lines 294-300: `from src.pipeline.shadow.reporter import ShadowReporter; reporter._compute_policy_error_metrics()` |

### Requirements Coverage

All 5 phase success criteria satisfied:
- Policy feedback constraint generation from human corrections: SATISFIED
- Source distinguishability (policy_feedback vs human_correction): SATISFIED
- Durability tracking applies equally to policy-feedback constraints: SATISFIED
- Pre-surfacing suppression of violating recommendations: SATISFIED
- Policy error rate metric with PASS/FAIL gate: SATISFIED

### Anti-Patterns Found

No blocking anti-patterns detected.

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/pipeline/feedback/checker.py` | Scope overlap without detection_hints intentionally deferred (documented in code comments and by test `test_no_detection_hints_skipped_not_scope_matched`) | Info | Intentional deferral, not a gap — future gap closure plan scope |

### Human Verification Required

None — all critical behaviors verified programmatically:
- Suppression logic verified via live Python execution
- Source ID differentiation verified via SHA-256 hash computation
- Denominator correctness verified via ShadowReporter query execution
- Promotion path verified via ConstraintStore.add_status_history_entry()

### Gaps Summary

No gaps found. All 5 observable truths verified against the actual codebase. The feedback loop is fully closed:

1. Blocked/corrected policy recommendations automatically become `source="policy_feedback", status="candidate"` constraints via `PolicyFeedbackExtractor.extract()`
2. Source namespace isolation enforced via distinct ID generation (JSON separator + `:policy_feedback` vs pipe separator + `:human_correction`)
3. Policy-feedback constraints participate in Phase 10 durability tracking identically (same tables, same evaluator)
4. `PolicyViolationChecker` suppresses forbidden/requires_approval matches before evaluation with `continue`, recording `PolicyErrorEvent(error_type='suppressed')`
5. `ShadowReporter._compute_policy_error_metrics()` tracks error rate with correct denominator (evaluated + suppressed), surfaced via CLI `audit policy-errors` with PASS/FAIL gate and exit codes 0/1/2

Test suite: 889 tests pass (project scope), 0 regressions. All 67 feedback-loop-specific tests pass in 0.84s.

---

_Verified: 2026-02-20T19:11:31Z_
_Verifier: Claude (gsd-verifier)_
