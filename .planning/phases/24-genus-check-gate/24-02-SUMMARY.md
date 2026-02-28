---
phase: 24-genus-check-gate
plan: 02
subsystem: premise-gate
tags: [fundamentality, genus, causal-indicator, pag-hook]

requires:
  - phase: 24-genus-check-gate
    provides: ParsedPremise genus_name/genus_instances fields, config.yaml genus_check section
provides:
  - FundamentalityChecker with two-instance causal criterion
  - PAG hook step 6.5 genus declaration validation (fail-open, warn-only)
affects: [24-genus-check-gate, premise-gate]

tech-stack:
  added: []
  patterns: [fail-open genus validation, causal-indicator word matching]

key-files:
  created:
    - src/pipeline/premise/fundamentality.py
    - tests/pipeline/premise/test_fundamentality.py
  modified:
    - src/pipeline/live/hooks/premise_gate.py
    - tests/pipeline/live/hooks/test_premise_gate.py

key-decisions:
  - "block_on_invalid=false (config default): hook always exits 0, GENUS_INVALID is a warning not a block"
  - "Causal structure rule: genus name must contain a causal indicator word OR have >= 3 words"
  - "Fail-open on missing FundamentalityChecker import: returns empty warnings list"

patterns-established:
  - "PAG step numbering: 6.5 between cross-axis (6) and bus check (7)"
  - "Genus validation loads config with hardcoded fallback for resilience"

duration: 3min
completed: 2026-02-28
---

# Phase 24 Plan 02: FundamentalityChecker + PAG Hook Step 6.5 Summary

**FundamentalityChecker validates genus declarations (two-instance + causal explanation criterion) integrated into PAG hook as step 6.5 with fail-open warn-only behavior**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T11:30:26Z
- **Completed:** 2026-02-28T11:33:01Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- FundamentalityChecker enforces fundamentality criterion: >= 2 citable instances + causal indicator word (or >= 3 word name)
- PAG hook extended with step 6.5: _check_genus() emits GENUS_INVALID warning on invalid genus declarations
- Fail-open on all paths: missing GENUS field silently skipped, missing module returns empty list
- A7/CRAD test case validates correctly: genus="corpus-relative identity retrieval" + 2 instances -> valid=True

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FundamentalityChecker** - `9ed3c40` (feat)
2. **Task 2: Add _check_genus() to PAG hook as step 6.5** - `f4cfa93` (feat)

## Files Created/Modified
- `src/pipeline/premise/fundamentality.py` - FundamentalityChecker + FundamentalityResult dataclass
- `tests/pipeline/premise/test_fundamentality.py` - 9 tests including A7/CRAD test case
- `src/pipeline/live/hooks/premise_gate.py` - _check_genus() function + step 6.5 insertion in main()
- `tests/pipeline/live/hooks/test_premise_gate.py` - TestGenusCheck class with 3 integration tests

## Decisions Made
- block_on_invalid=false (config default): hook always exits 0. GENUS_INVALID is a warning, not a block. Wave 3 writes accepted genera to axis_edges staging.
- Causal structure validated via word-level matching against config-loaded causal_indicator_words list
- FundamentalityChecker lazy-imported inside _check_genus() to maintain fail-open if module unavailable

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Wave 2 complete: FundamentalityChecker and PAG integration are functional
- Wave 3 (plan 24-03) can proceed: axis_edges staging writes for accepted genera
- All 182 premise + PAG hook tests pass (including 12 new tests from this plan)

## Self-Check: PASSED

All artifacts verified:
- src/pipeline/premise/fundamentality.py: FOUND
- tests/pipeline/premise/test_fundamentality.py: FOUND
- src/pipeline/live/hooks/premise_gate.py (_check_genus, step 6.5): FOUND
- tests/pipeline/live/hooks/test_premise_gate.py (TestGenusCheck): FOUND
- Commit 9ed3c40: FOUND
- Commit f4cfa93: FOUND

---
*Phase: 24-genus-check-gate*
*Completed: 2026-02-28*
