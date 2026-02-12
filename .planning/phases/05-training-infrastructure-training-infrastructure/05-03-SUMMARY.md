---
phase: 05-training-infrastructure
plan: 03
subsystem: shadow-mode
tags: [shadow-mode, leave-one-out, agreement-metrics, jaccard-similarity, cli-train, duckdb]

# Dependency graph
requires:
  - phase: 05-01-episode-embedding
    provides: EpisodeEmbedder, observation_to_text, episode_embeddings and episode_search_text tables
  - phase: 05-02-hybrid-retriever
    provides: HybridRetriever, Recommender, Recommendation model, check_dangerous, exclude_episode_id support
provides:
  - ShadowModeRunner with run_all() and run_session() batch evaluation using leave-one-out protocol
  - ShadowEvaluator with evaluate() comparing recommendations to actual decisions
  - ShadowReporter with compute_report() aggregate metrics and format_report() human-readable output
  - shadow_mode_results DuckDB table storing all evaluation data
  - CLI train group with embed, recommend, shadow-run, shadow-report subcommands
  - 70% mode agreement threshold and 50 session minimum PASS/FAIL gates
affects: [06-mission-control-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [leave-one-out exclude_episode_id protocol, Jaccard similarity for scope overlap, INSERT OR REPLACE for idempotent shadow runs, click.group CLI pattern for train subcommands]

key-files:
  created:
    - src/pipeline/shadow/__init__.py
    - src/pipeline/shadow/evaluator.py
    - src/pipeline/shadow/runner.py
    - src/pipeline/shadow/reporter.py
    - src/pipeline/cli/train.py
    - tests/test_shadow_mode.py
  modified:
    - src/pipeline/storage/schema.py
    - src/pipeline/cli/__main__.py

key-decisions:
  - "Jaccard similarity for scope overlap: |intersection|/|union|, 1.0 when both empty, 0.0 when one empty"
  - "shadow_run_id as UUID primary key (not episode_id) to allow multiple runs per episode across batches"
  - "Gate agreement uses exact set match (both sets must be equal) not subset"
  - "Reporter threshold: 70% mode agreement rate and 50 session minimum as PASS/FAIL gates"

patterns-established:
  - "Leave-one-out protocol: exclude_episode_id passed through recommender -> retriever for unbiased evaluation"
  - "Shadow mode batch results table with run_batch_id for grouping and filtering"
  - "CLI train group: click.group pattern matching validate group structure"
  - "Reporter compute + format separation for testability"

# Metrics
duration: 7min
completed: 2026-02-11
---

# Phase 5 Plan 3: Shadow Mode Testing Framework Summary

**Leave-one-out shadow mode evaluation with ShadowModeRunner, ShadowEvaluator, ShadowReporter, DuckDB results storage, and CLI train subcommand for embed/recommend/shadow-run/shadow-report**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-12T00:56:52Z
- **Completed:** 2026-02-12T01:04:19Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- ShadowModeRunner processes all episodes with leave-one-out protocol, excluding each episode from its own retrieval to prevent data leakage
- ShadowEvaluator computes four agreement metrics: mode agreement, risk agreement, scope overlap (Jaccard), and gate agreement (exact set match)
- ShadowReporter computes aggregate metrics with 70% mode agreement threshold and 50 session minimum PASS/FAIL indicators, plus per-session breakdown and danger category counts
- shadow_mode_results DuckDB table stores all evaluation data with session and batch indexes
- CLI train group provides embed, recommend, shadow-run, and shadow-report subcommands following the click.group pattern
- 426 tests pass (32 new + 394 existing), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Shadow mode schema + evaluator + runner** - `8c86fec` (feat)
2. **Task 2: Reporter + CLI train subcommand + integration** - `09e0457` (feat)

## Files Created/Modified
- `src/pipeline/shadow/__init__.py` - Module init exporting ShadowEvaluator, ShadowModeRunner, ShadowReporter
- `src/pipeline/shadow/evaluator.py` - ShadowEvaluator with evaluate() comparing recommendation to actual decision
- `src/pipeline/shadow/runner.py` - ShadowModeRunner with run_all(), run_session(), and _write_results()
- `src/pipeline/shadow/reporter.py` - ShadowReporter with compute_report() and format_report()
- `src/pipeline/cli/train.py` - CLI train group with embed, recommend, shadow-run, shadow-report commands
- `src/pipeline/cli/__main__.py` - Updated to register train_group
- `src/pipeline/storage/schema.py` - Extended with shadow_mode_results table and indexes
- `tests/test_shadow_mode.py` - 32 tests: evaluator (12), runner (6), schema (2), integration (2), reporter (7), CLI (3)

## Decisions Made
- Used Jaccard similarity (|intersection|/|union|) for scope overlap with convention: both-empty = 1.0 (agreement), one-empty = 0.0
- shadow_run_id is UUID primary key rather than episode_id, allowing multiple evaluation runs per episode across different batches
- Gate agreement requires exact set equality (not subset) for strict comparison
- Reporter uses 70% mode agreement and 50 session minimum thresholds matching the graduated autonomy spec

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Shadow mode testing framework complete, TRAIN-02 requirement satisfied
- Full pipeline: embed -> shadow-run -> shadow-report available via CLI
- Phase 5 complete: all 3 plans (embedding, retriever/recommender, shadow mode) delivered
- Phase 6 (Mission Control Integration) can proceed when Mission Control repository access is available

## Self-Check: PASSED

- All 8 files verified present on disk (checked below)
- Commit `8c86fec` (Task 1) verified in git log
- Commit `09e0457` (Task 2) verified in git log
- 426 tests pass, zero regressions

---
*Phase: 05-training-infrastructure*
*Completed: 2026-02-11*
