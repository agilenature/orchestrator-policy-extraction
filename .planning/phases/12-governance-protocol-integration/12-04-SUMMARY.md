---
phase: 12-governance-protocol-integration
plan: 04
subsystem: cli, governance
tags: [click, cli, governance, ingest, stability, integration-tests]

# Dependency graph
requires:
  - phase: 12-02
    provides: GovDocParser + GovDocIngestor + pre-mortem fixture
  - phase: 12-03
    provides: StabilityRunner + DuckDB persistence + episode flagging
provides:
  - govern CLI group with ingest and check-stability commands
  - Full end-to-end integration test coverage for governance pipeline
  - CLI surface for GOVERN-01 and GOVERN-02 requirements
affects: [13-policy-feedback-loop]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Click group registration for govern subcommands
    - CliRunner-based testing for governance CLI
    - Bulk ingest episode flagging via DuckDB UPDATE

key-files:
  created:
    - src/pipeline/cli/govern.py
    - tests/test_governance_cli.py
    - tests/test_governance_integration.py
  modified:
    - src/pipeline/cli/__main__.py

key-decisions:
  - "Reuse wisdom_store._conn for bulk episode flagging to avoid DuckDB two-writer IOException"
  - "Exit codes: 0=clean, 1=runtime-error, 2=failure-or-violation (consistent with audit CLI)"
  - "except SystemExit: raise pattern for try blocks containing sys.exit calls"
  - "CliRunner() without mix_stderr (not supported in installed Click version)"

patterns-established:
  - "Governance CLI follows same Click group pattern as wisdom.py (lazy imports, _setup_logging)"
  - "Integration tests use real objectivism_premortem.md fixture for ground-truth assertions"

# Metrics
duration: 9min
completed: 2026-02-20
---

# Phase 12 Plan 04: Governance CLI and Integration Tests Summary

**Click-based govern CLI group (ingest + check-stability) with 30 integration tests proving end-to-end objectivism pre-mortem ingestion: 15 constraints, 11 dead_end wisdom, bulk flagging, and stability runner flow**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-20T17:28:00Z
- **Completed:** 2026-02-20T17:37:24Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- govern CLI group registered in __main__.py with ingest and check-stability subcommands
- Full end-to-end integration tests: objectivism pre-mortem produces exactly 15 constraints and 11 dead_end wisdom entities
- 30 new tests (10 CLI + 20 integration), 822 total passing, zero regressions
- CLI dry-run mode verified, bulk ingest flagging verified, stability runner pass/fail/JSON output verified

## Task Commits

Each task was committed atomically:

1. **Task 1: CLI govern group + __main__.py registration** - `b010e0c` (feat)
2. **Task 2: CLI tests + end-to-end integration test** - `55c97dc` (test)

## Files Created/Modified
- `src/pipeline/cli/govern.py` - govern_group with ingest and check-stability commands
- `src/pipeline/cli/__main__.py` - Added govern_group import and registration
- `tests/test_governance_cli.py` - 10 CLI tests: help, ingest dry-run/write/empty/source-id, check-stability no-config/pass/fail/json
- `tests/test_governance_integration.py` - 20 integration tests: full pre-mortem counts, metadata linkage, idempotency, DECISIONS.md, bulk flag, stability runner, CLI integration

## Decisions Made
- Reuse wisdom_store._conn for bulk episode flagging to avoid DuckDB two-writer IOException (single connection for both wisdom and episodes tables)
- Exit codes follow existing audit CLI convention: 0=clean, 1=runtime-error, 2=failure/violation
- except SystemExit: raise pattern ensures sys.exit() propagates through try/except blocks
- CliRunner() instantiated without mix_stderr parameter (not supported in installed Click version)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CliRunner mix_stderr parameter not supported**
- **Found during:** Task 2 (CLI tests)
- **Issue:** Click version installed does not support `mix_stderr=False` parameter on CliRunner
- **Fix:** Removed mix_stderr parameter from all CliRunner() calls; adjusted assertions to check result.output instead of result.stderr
- **Files modified:** tests/test_governance_cli.py, tests/test_governance_integration.py
- **Verification:** All 30 tests pass
- **Committed in:** 55c97dc (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial API compatibility fix. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 12 is now complete (all 4 plans delivered)
- All GOVERN-01 and GOVERN-02 requirements met
- Ready for Phase 13: Policy-to-Constraint Feedback Loop (requires planning via /gsd:plan-phase)

---
*Phase: 12-governance-protocol-integration*
*Completed: 2026-02-20*
