---
phase: 15-ddf-detection-substrate
plan: 06
subsystem: pipeline, cli
tags: [ddf, flame-events, pipeline-integration, intelligence-profile, cli, o-axs, segmenter, memory-candidates]

# Dependency graph
requires:
  - phase: 15-01
    provides: DDF schema, FlameEvent model, DDFConfig
  - phase: 15-02
    provides: write_flame_events, Tier 1 markers, O_AXS detector
  - phase: 15-03
    provides: Tier 2 enrichment, FlameEventExtractor, FalseIntegrationDetector, CausalIsolationRecorder
  - phase: 15-04
    provides: GeneralizationRadius, spiral tracking, promote_spirals_to_wisdom
  - phase: 15-05
    provides: compute_intelligence_profile, compute_ai_profile, compute_spiral_depth_for_human
provides:
  - Pipeline Steps 15-19 executing DDF detection end-to-end in run_session
  - O_AXS as episode start trigger in segmenter
  - DDF stats (ddf_tier1_count, ddf_tier2_count, etc.) in pipeline results
  - intelligence profile CLI command for human and AI subjects
  - intelligence stagnant CLI command for floating abstraction detection
  - Step 19 promote_spirals_to_wisdom (DDF-06 terminal act in pipeline)
affects: [15-07-shadow-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import + try/except fail-safe pattern for all DDF pipeline steps"
    - "DDF schema auto-creation in Step 15 before first DDF table write"
    - "Read-only DuckDB connection for CLI query commands"
    - "Tagged events -> dict conversion for AI marker detection in Tier 2"

key-files:
  created:
    - src/pipeline/cli/intelligence.py
    - tests/test_ddf_pipeline.py
    - tests/test_ddf_cli.py
  modified:
    - src/pipeline/runner.py
    - src/pipeline/segmenter.py
    - src/pipeline/cli/__main__.py

key-decisions:
  - "DDF schema creation happens lazily in Step 15 (first DDF step) rather than in PipelineRunner.__init__, keeping DDF optional"
  - "Tagged events converted to dicts for AI marker detection to avoid TaggedEvent attribute access complexity"
  - "CLI profile opens DB read-only; schema creation wrapped in try/except for read-only mode compatibility"
  - "O_AXS detection in pipeline uses per-event iteration over all_session_events rather than batch processing"

patterns-established:
  - "Pipeline DDF steps use same lazy import + try/except as Step 11.5 and Step 14.5"
  - "CLI read-only DB access pattern with graceful schema creation fallback"
  - "DDF stats as integer counts in pipeline result dict with zero defaults in _error_result"

# Metrics
duration: 9min
completed: 2026-02-24
---

# Phase 15 Plan 06: Pipeline Integration and Intelligence CLI Summary

**DDF Steps 15-19 wired into pipeline runner with O_AXS start trigger, intelligence profile CLI, and stagnant constraint detection -- all fail-safe with 21 new tests**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-24T12:19:00Z
- **Completed:** 2026-02-24T12:28:37Z
- **Tasks:** 2
- **Files created:** 3
- **Files modified:** 3

## Accomplishments
- Pipeline runner now executes 5 DDF steps (15-19): Tier 1 detection, Tier 2 enrichment, Level 6 deposit to memory_candidates, False Integration + Causal Isolation, GeneralizationRadius + spiral promotion
- O_AXS added as episode start trigger in segmenter -- O_AXS-tagged events open new episode boundaries
- Step 19 calls promote_spirals_to_wisdom (DDF-06 terminal act: spiral candidates auto-promoted to project_wisdom)
- All DDF steps fail-safe: ImportError silently skipped, runtime errors logged as warnings without blocking pipeline
- DDF stats (8 keys) included in pipeline results and _error_result zero defaults
- intelligence CLI group with `profile <human_id>` and `stagnant` commands
- Profile command displays IntelligenceProfile metrics with flood rate percentage
- 21 new tests (11 pipeline + 10 CLI), 1201 total passing, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Pipeline runner integration + segmenter O_AXS extension** - `6bd093c` (feat)
2. **Task 2: Intelligence CLI commands** - `3e840db` (feat)

## Files Created/Modified
- `src/pipeline/runner.py` - Added Steps 15-19 for DDF detection, enrichment, deposit, false integration, causal isolation, generalization metrics, and spiral promotion. Renamed Step 15 (stats) to Step 20. Added DDF stats to result dict and _error_result.
- `src/pipeline/segmenter.py` - Added O_AXS to START_TRIGGERS set
- `src/pipeline/cli/intelligence.py` - Click command group with profile and stagnant subcommands
- `src/pipeline/cli/__main__.py` - Registered intelligence_group in CLI
- `tests/test_ddf_pipeline.py` - 11 tests: O_AXS in START_TRIGGERS, pipeline DDF steps, fail-safety, error result keys, Level 6 deposit, batch stats, generalization metrics, O_AXS detection, segmenter episode boundary
- `tests/test_ddf_cli.py` - 10 tests: group registration, profile display (human, AI, no data, flood rate, read-only DB), stagnant listing and empty state

## Decisions Made
- DDF schema lazily created in Step 15 rather than in `__init__`. This keeps DDF completely optional -- if DDF modules are not installed, the pipeline runs identically to before.
- TaggedEvent objects converted to dicts for AI marker detection in Tier 2. The FlameEventExtractor.detect_ai_markers expects dicts with actor and payload.common.text structure, so we build these from TaggedEvent.event attributes.
- CLI profile command opens DuckDB in read-only mode and wraps create_ddf_schema in try/except. If tables already exist (normal case), the read-only mode works. If tables don't exist, the command gracefully reports "No flame events found."
- Pipeline Step 19 spiral promotion uses `self._db_path` to pass the DB path to WisdomStore, with a fallback to `data/ope.db` when running with `:memory:` databases.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed CanonicalEvent test construction with required fields**
- **Found during:** Task 1 (test writing)
- **Issue:** Test CanonicalEvent construction missing required `source_system` and `source_ref` fields; also Classification model requires `source` from a validated enum, not arbitrary strings
- **Fix:** Added `source_system="claude_jsonl"` and `source_ref="test:1"` to CanonicalEvent; changed `source="test"` to `source="direct"` for Classification
- **Files modified:** tests/test_ddf_pipeline.py
- **Verification:** All 11 pipeline tests pass
- **Committed in:** 6bd093c (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test fixture construction)
**Impact on plan:** Test fixture needed correct model field values. No scope creep.

## Issues Encountered

- Pre-existing test failure in `tests/test_segmenter.py::test_multiple_sequential_episodes` (known from Phase 14.1 X_ASK end-trigger changes). Not a regression.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- All DDF components now wired into the pipeline and CLI
- Plan 07 (shadow mode integration) can build on the DDF pipeline infrastructure
- Intelligence profile accessible via `python -m src.pipeline.cli intelligence profile <human_id>`
- Stagnant constraint detection accessible via `python -m src.pipeline.cli intelligence stagnant`

## Self-Check: PASSED
