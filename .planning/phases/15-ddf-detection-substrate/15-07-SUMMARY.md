---
phase: 15-ddf-detection-substrate
plan: 07
subsystem: testing
tags: [ddf, integration-tests, flame-events, memory-candidates, spiral, intelligence-profile, cli, duckdb]

# Dependency graph
requires:
  - phase: 15-ddf-detection-substrate (plans 01-06)
    provides: All DDF modules (schema, models, writer, deposit, tier1, tier2, epistemological, generalization, spiral, intelligence_profile, cli)
provides:
  - 18 integration tests covering all 10 DDF requirements (DDF-01 through DDF-10)
  - End-to-end deposit path verification (Tier 1 -> Tier 2 -> Level 6 -> memory_candidates)
  - Spiral promotion to project_wisdom verification
  - Module import smoke test for all 14 DDF modules
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Integration test fixtures using in-memory DuckDB with create_ddf_schema for isolated testing"
    - "CLI testing with CliRunner and file-based DuckDB for seeded data"
    - "Spiral promotion test using tmp_path for WisdomStore file-based DB"

key-files:
  created:
    - tests/test_ddf_integration.py
  modified: []

key-decisions:
  - "Tests organized by DDF requirement number (DDF-01 through DDF-10) for traceability"
  - "Each test is self-contained with own fixture data seeding for isolation"
  - "File-based DuckDB used only for WisdomStore and CLI tests (which require it); all others use in-memory"

patterns-established:
  - "DDF requirement coverage matrix: each requirement has at least one dedicated integration test"
  - "Shared pytest fixtures (ddf_pipeline, seeded_flame_events) for DuckDB + config setup"

# Metrics
duration: 6min
completed: 2026-02-24
---

# Phase 15 Plan 07: DDF Integration Tests Summary

**18 integration tests validating all 10 DDF requirements end-to-end: O_AXS episodes, flame_events, deposit path, IntelligenceProfile, spiral promotion to project_wisdom, epistemological origin, CLI display, false integration, and causal isolation**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-24T12:31:48Z
- **Completed:** 2026-02-24T12:37:52Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments
- All 10 DDF requirements (DDF-01 through DDF-10) validated by at least one integration test
- End-to-end deposit path verified: Tier 1 detection -> Tier 2 enrichment -> Level 6 deposit -> memory_candidates row with source_flame_event_id
- DDF-06 spiral promotion to project_wisdom verified: constraint with ascending scope diversity across 3 sessions auto-promoted as 'breakthrough' entity with source_constraint_id in metadata
- O_AXS detector and segmenter start trigger verified (DDF-01)
- IntelligenceProfile aggregation verified for both human and AI subjects (DDF-04)
- CLI profile output verified with seeded data showing all 6 metrics (DDF-08)
- Causal isolation markers from premise_registry verified with all 3 marker types (DDF-10)
- All 14 DDF modules importable without error (smoke test)
- 18 tests pass in 0.73s, zero regressions (1219 total tests pass, 1 pre-existing segmenter failure)

## Task Commits

Each task was committed atomically:

1. **Task 1: Integration tests for all 10 DDF requirements** - `7d7fba2` (test)

## Files Created/Modified
- `tests/test_ddf_integration.py` - 951-line integration test file with 18 tests organized by DDF requirement number, shared fixtures, and module import smoke test

## Decisions Made
- Tests organized into classes by DDF requirement number (TestDDF01OAxs, TestDDF02FlameEventsHuman, etc.) for clear traceability
- Shared fixtures (ddf_pipeline, seeded_flame_events, synthetic_session_events) reduce boilerplate while keeping each test self-contained
- File-based DuckDB used only where structurally required (WisdomStore, CLI) -- all other tests use in-memory for speed
- Spiral promotion test creates both the in-memory conn (for session_constraint_eval data) and a tmp_path file DB (for WisdomStore) to match production architecture

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 15 (DDF Detection Substrate) is COMPLETE: all 7 plans executed, all 10 DDF requirements verified
- All DDF infrastructure ready for downstream phases:
  - flame_events table populated by pipeline
  - memory_candidates deposit path active
  - IntelligenceProfile CLI operational
  - Spiral tracking with wisdom promotion active
  - Epistemological origin on all constraints
  - GeneralizationRadius + stagnation detection
  - False integration detection with dual output
  - Causal isolation markers from premise_registry

## DDF Requirement Coverage Matrix

| DDF Req | Tests | Description |
|---------|-------|-------------|
| DDF-01 | 2 | O_AXS episode mode + OAxsDetector |
| DDF-02 | 2 | flame_events human markers + detection_source |
| DDF-03 | 2 | ai_flame_events view + Level 6 deposit |
| DDF-04 | 2 | IntelligenceProfile human + AI aggregation |
| DDF-05 | 2 | GeneralizationRadius + stagnation |
| DDF-06 | 2 | Spiral detection + project_wisdom promotion |
| DDF-07 | 2 | Epistemological origin (reactive + default principled) |
| DDF-08 | 1 | Intelligence CLI profile output |
| DDF-09 | 1 | False integration marker |
| DDF-10 | 1 | Causal isolation records |
| Smoke  | 1 | All 14 DDF modules importable |
| **Total** | **18** | |

## Self-Check: PASSED

All files verified present:
- FOUND: tests/test_ddf_integration.py

Task commit verified in git log:
- FOUND: 7d7fba2

---
*Phase: 15-ddf-detection-substrate*
*Completed: 2026-02-24*
