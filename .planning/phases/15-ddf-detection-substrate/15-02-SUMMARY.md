---
phase: 15-ddf-detection-substrate
plan: 02
subsystem: detection
tags: [regex, ddf, flame-events, duckdb, memory-candidates, o-axs]

# Dependency graph
requires:
  - phase: 15-ddf-detection-substrate (plan 01)
    provides: FlameEvent model, flame_events table, OAxsConfig, DDFConfig, memory_candidates extensions
provides:
  - L0/L1/L2 regex marker detectors (high recall, pre-compiled)
  - OAxsDetector (granularity drop + novel concept dual-signal)
  - detect_markers integration function (events -> FlameEvents)
  - write_flame_events DuckDB writer (idempotent INSERT OR REPLACE)
  - deposit_to_memory_candidates with soft dedup on (ccd_axis, scope_rule)
  - mark_deposited flag update
affects: [15-03-tier2-detectors, 15-04-pipeline-runner, 15-05-assessment, 15-06-intelligence-profile]

# Tech tracking
tech-stack:
  added: []
  patterns: [pre-compiled regex at module level, soft dedup with case+whitespace normalization, dual-signal detection]

key-files:
  created:
    - src/pipeline/ddf/tier1/__init__.py
    - src/pipeline/ddf/tier1/markers.py
    - src/pipeline/ddf/tier1/o_axs.py
    - src/pipeline/ddf/writer.py
    - src/pipeline/ddf/deposit.py
    - tests/test_ddf_tier1.py
    - tests/test_ddf_writer.py
  modified: []

key-decisions:
  - "L0-L2 detectors are HIGH RECALL by design -- false positives expected and filtered downstream by Tier 2"
  - "OAxsDetector requires BOTH granularity drop AND novel concept (dual-signal to reduce false positives)"
  - "deposit_to_memory_candidates uses soft dedup: duplicate (axis, scope_rule) increments detection_count rather than creating new rows"
  - "write_flame_events uses INSERT OR REPLACE for idempotent writes"

patterns-established:
  - "Tier 1 detection: pre-compiled regex patterns at module level, returning (bool, evidence_excerpt) tuples"
  - "detect_markers: filter by actor+event_type, assign sequential prompt_numbers, return FlameEvent list"
  - "Deposit pattern: soft dedup on normalized (ccd_axis, scope_rule), deterministic SHA-256[:16] IDs"

# Metrics
duration: 6min
completed: 2026-02-24
---

# Phase 15 Plan 02: Tier 1 DDF Marker Detectors and DuckDB Writer Summary

**L0-L2 regex marker detectors with OAxsDetector dual-signal detection, idempotent DuckDB flame_events writer, and memory_candidates deposit with soft dedup**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-24T11:38:29Z
- **Completed:** 2026-02-24T11:44:29Z
- **Tasks:** 2
- **Files created:** 7

## Accomplishments
- Tier 1 marker detectors: L0 (5 patterns, trunk identification), L1 (3 patterns, causal language), L2 (10 patterns, assertive causal) -- all pre-compiled, case-insensitive, HIGH RECALL
- OAxsDetector: dual-signal detection requiring both granularity drop (token count below ratio * avg prior) AND novel concept (capitalized noun phrase appearing N+ times in recent window)
- write_flame_events: idempotent INSERT OR REPLACE from FlameEvent Pydantic models to DuckDB
- deposit_to_memory_candidates: soft dedup on normalized (ccd_axis, scope_rule), increments detection_count on duplicate, returns candidate_id on new entry
- 30 new tests (18 tier1 + 12 writer), 1236 total passing, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Tier 1 marker detectors L0-L2 + OAxsDetector** - `9db769a` (feat)
2. **Task 2: DuckDB writer + deposit function** - `236ff6b` (feat)

## Files Created/Modified
- `src/pipeline/ddf/tier1/__init__.py` - Empty package file
- `src/pipeline/ddf/tier1/markers.py` - L0/L1/L2 regex detectors + detect_markers integration
- `src/pipeline/ddf/tier1/o_axs.py` - OAxsDetector with dual-signal detection
- `src/pipeline/ddf/writer.py` - write_flame_events (idempotent DuckDB INSERT OR REPLACE)
- `src/pipeline/ddf/deposit.py` - deposit_to_memory_candidates (soft dedup) + mark_deposited
- `tests/test_ddf_tier1.py` - 18 tests for L0-L2 detectors and OAxsDetector
- `tests/test_ddf_writer.py` - 12 tests for writer and deposit functions

## Decisions Made
- L0-L2 detectors prioritize recall over precision (HIGH RECALL by design)
- OAxsDetector dual-signal prevents false positives from either condition alone
- Soft dedup normalizes case and whitespace before comparison, increment detection_count on duplicates
- deposit_to_memory_candidates uses both source_instance_id and source_flame_event_id (same value) for backward compatibility with Phase 13.3 schema

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

- Pre-existing test failure in tests/test_segmenter.py (dirty working tree modification to src/pipeline/segmenter.py) -- not caused by our changes, confirmed by stash test. All 1236 non-segmenter tests pass.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- Tier 1 detectors ready for Tier 2 false integration detector (Plan 03)
- write_flame_events and deposit functions ready for pipeline runner integration (Plan 04)
- FlameEvent flow complete: detect -> write -> deposit -> mark

## Self-Check: PASSED

All 8 created files verified present. Both task commits (9db769a, 236ff6b) verified in git log.

---
*Phase: 15-ddf-detection-substrate*
*Completed: 2026-02-24*
