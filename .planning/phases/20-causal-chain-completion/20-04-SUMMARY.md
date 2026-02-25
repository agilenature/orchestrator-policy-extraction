---
phase: 20-causal-chain-completion
plan: 04
subsystem: governance
tags: [constraint-filtering, repo-scope, governor-daemon, bus-api]

# Dependency graph
requires:
  - phase: 20-causal-chain-completion
    plan: 01
    provides: "GovernorDaemon, /api/check endpoint, bus_sessions with repo column"
provides:
  - "Repo-scoped constraint filtering in GovernorDaemon.get_briefing()"
  - "_filter_by_repo() static method for universal vs scoped constraint logic"
  - "/api/check passes repo from request body to get_briefing"
  - "8 tests covering all repo scope filtering scenarios"
affects: [20-05-causal-chain-completion, phase-21-plans-needing-repo-scoped-constraints]

# Tech tracking
tech-stack:
  added: []
  patterns: ["repo_scope list field on constraints for multi-repo filtering", "universal-by-default constraint delivery"]

key-files:
  created: []
  modified:
    - src/pipeline/live/governor/daemon.py
    - src/pipeline/live/bus/server.py
    - tests/test_governing_daemon.py

key-decisions:
  - "Universal-by-default: constraints without repo_scope, with None, or with empty list are delivered to all sessions"
  - "_filter_by_repo as @staticmethod: pure function, no instance state needed"
  - "Backward compatible: repo=None skips filtering entirely, existing callers unaffected"

patterns-established:
  - "repo_scope convention: list[str] field on constraint dicts; absent/None/[] = universal, non-empty = scoped"

# Metrics
duration: 2min
completed: 2026-02-25
---

# Phase 20 Plan 04: Repo-Scoped Constraint Filtering Summary

**GovernorDaemon.get_briefing() with optional repo parameter for scope-based constraint filtering, wired through /api/check**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T21:05:00Z
- **Completed:** 2026-02-25T21:07:19Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- GovernorDaemon.get_briefing() accepts optional `repo` parameter for scope filtering
- `_filter_by_repo()` implements universal (no/None/empty repo_scope) vs scoped (non-empty repo_scope) constraint delivery
- /api/check passes `repo` from request body to get_briefing, enabling per-session repo filtering
- 8 new tests covering all filtering scenarios: scoped match, universal variants (absent/None/empty), backward compat (repo=None), multi-repo scope, exclusion, and /api/check integration

## Task Commits

Each task was committed atomically:

1. **Task 1: Add repo scope filtering to GovernorDaemon + wire /api/check** - `b62a60f` (feat)
2. **Task 2: Tests for repo scope filtering** - `cb670a3` (test)

## Files Created/Modified
- `src/pipeline/live/governor/daemon.py` - get_briefing() with repo param, _filter_by_repo() static method
- `src/pipeline/live/bus/server.py` - /api/check passes repo from request body to get_briefing
- `tests/test_governing_daemon.py` - 8 new tests (TestRepoScopeFilter + TestCheckWithRepoFilter)

## Decisions Made
- Universal-by-default: constraints without repo_scope, with None, or with empty list are delivered to all sessions regardless of requesting repo
- _filter_by_repo as @staticmethod: pure function operating on constraint list, no daemon instance state needed
- Backward compatible: when repo=None (default), filtering is skipped entirely -- existing callers unaffected

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Repo-scoped constraint filtering complete; sessions can now receive only constraints relevant to their repository
- Plan 05 (migration_run_id cross-session linking) can proceed -- it depends on Plan 01 (complete) not Plan 04
- All 52 bus/daemon tests pass with no regressions

## Self-Check: PASSED

- All 3 files FOUND
- Both commit hashes FOUND (b62a60f, cb670a3)
- get_briefing signature verified: ['self', 'session_id', 'run_id', 'repo']

---
*Phase: 20-causal-chain-completion*
*Completed: 2026-02-25*
