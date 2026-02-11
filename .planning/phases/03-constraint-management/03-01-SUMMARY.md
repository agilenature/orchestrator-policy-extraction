---
phase: 03-constraint-management
plan: 01
subsystem: pipeline
tags: [constraint-extraction, regex, sha256, severity, scope-inference, tdd]

# Dependency graph
requires:
  - phase: 02-episode-population-storage
    provides: "Episode dicts with outcome.reaction (label, message, confidence)"
provides:
  - "ConstraintExtractor class with extract() method"
  - "Constraint dicts matching constraint.schema.json"
  - "50 tests covering all extraction paths"
affects: [03-02 constraint-store, pipeline-runner-integration, phase-4-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Regex-based keyword matching for severity assignment", "Narrowest-applicable scope inference (3-tier fallback)", "Deterministic SHA-256 constraint IDs for dedup"]

key-files:
  created:
    - src/pipeline/constraint_extractor.py
    - tests/test_constraint_extractor.py
  modified: []

key-decisions:
  - "Text normalization strips conversational prefixes (no, nope, wrong, that's wrong) via compiled regex patterns"
  - "Forbidden keywords take precedence over preferred keywords when both present in message"
  - "Examples array populated with source episode as first entry during extraction"

patterns-established:
  - "ConstraintExtractor pattern: config-driven keyword matching with compiled word-boundary regex"
  - "Scope inference priority chain: reaction message paths > episode scope paths > empty (repo-wide)"
  - "Detection hint extraction: quoted strings + file paths + prohibition-adjacent terms"

# Metrics
duration: 3min
completed: 2026-02-11
---

# Phase 3 Plan 1: ConstraintExtractor Summary

**TDD-built ConstraintExtractor converting correct/block reactions into structured constraints with 3-tier severity, narrowest-scope inference, and deterministic IDs**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-11T21:13:50Z
- **Completed:** 2026-02-11T21:16:34Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files created:** 2

## Accomplishments
- ConstraintExtractor class with extract() method producing constraint dicts matching constraint.schema.json
- 50 tests passing across 7 categories (filtering, severity, scope, normalization, hints, IDs, full flow)
- 248 total tests passing (zero regressions from 198 existing)
- Block reactions always produce "forbidden"; correct reactions produce "requires_approval" or "warning" based on keyword analysis

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write failing tests** - `8917130` (test)
2. **Task 2: GREEN -- Implement ConstraintExtractor** - `7a833cf` (feat)

## Files Created/Modified
- `src/pipeline/constraint_extractor.py` - ConstraintExtractor class: extract(), severity assignment, scope inference, text normalization, detection hints, deterministic IDs
- `tests/test_constraint_extractor.py` - 50 TDD tests across 7 test classes covering all extraction paths

## Decisions Made
- Text normalization strips conversational prefixes (no, nope, wrong, that's wrong) via compiled regex patterns rather than NLP
- Forbidden keywords take precedence over preferred keywords when both present in a message (ensures hard corrections are not downgraded to warnings)
- Examples array populated with source episode as first entry during extraction (enriches constraints with evidence)
- Reused scope path regex from EpisodePopulator for consistent file path extraction across pipeline

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ConstraintExtractor ready for integration with ConstraintStore (plan 03-02)
- extract() returns constraint dicts matching constraint.schema.json structure
- Pipeline integration point: call extract() on episodes with correct/block reactions after validation

## Self-Check: PASSED

- FOUND: src/pipeline/constraint_extractor.py
- FOUND: tests/test_constraint_extractor.py
- FOUND: commit 8917130 (test)
- FOUND: commit 7a833cf (feat)

---
*Phase: 03-constraint-management*
*Completed: 2026-02-11*
