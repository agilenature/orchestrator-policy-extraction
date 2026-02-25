---
phase: 19-control-plane-integration
plan: 04
subsystem: hooks, control-plane
tags: [unix-socket, http-client, fail-open, hooks, governance-bus, session-start]

# Dependency graph
requires:
  - phase: 19-01
    provides: "Governance Bus API (/api/check, /api/register endpoints)"
provides:
  - "PAG hook wired to governance bus via /api/check (constraint count in response)"
  - "SessionStart hook: /api/register + constraint briefing to stdout"
  - "settings.local.json updated with SessionStart hook entry"
  - "14 tests covering bus call fail-open, session start, env vars"
affects: [19-05-shadow-mode, future OpenClaw integration]

# Tech tracking
tech-stack:
  added: [http.client (stdlib), socket.AF_UNIX]
  patterns: [fail-open bus integration, Unix socket HTTP from hooks, module-level env var constants]

key-files:
  created:
    - src/pipeline/live/hooks/session_start.py
    - tests/test_pag_bus_connection.py
  modified:
    - src/pipeline/live/hooks/premise_gate.py
    - .claude/settings.local.json

key-decisions:
  - "PAG always emits response JSON now (was conditional on additionalContext) to include ope_constraint_count"
  - "Session start hook uses [OPE] prefix for stdout output per Phase 14 locked decision"
  - "Module-level env var constants read at import time; tests use monkeypatch + patch on module attrs"

patterns-established:
  - "Fail-open bus integration: try/except around entire socket call, return empty dict on any error"
  - "Unix socket HTTP: http.client.HTTPConnection with AF_UNIX socket injected into conn.sock"
  - "Constraint briefing to stdout: user-visible channel for governance information"

# Metrics
duration: 3min
completed: 2026-02-25
---

# Phase 19 Plan 04: PAG Bus Wiring + SessionStart Hook Summary

**PAG hook extended with /api/check bus call injecting constraint counts, plus new SessionStart hook for bus registration and constraint briefing to stdout**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-25T18:32:29Z
- **Completed:** 2026-02-25T18:35:52Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments
- Extended PAG hook with _call_bus_check() helper that calls /api/check on the governance bus via Unix socket, fail-open
- PAG response now always includes ope_constraint_count metadata field
- Created session_start.py hook that registers with /api/register and prints constraint briefing to stdout
- Updated .claude/settings.local.json with SessionStart hook entry
- 14 tests covering fail-open behavior, mock bus responses, constraint briefing output, env var reading, script exit code

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend PAG hook with /api/check call** - `d138eea` (feat)
2. **Task 2: Create SessionStart hook** - `9c5237c` (feat)
3. **Task 3: Update .claude/settings.local.json** - N/A (file is in global gitignore, updated on disk only)
4. **Task 4: Tests (14 tests)** - `7a266a6` (test)

## Files Created/Modified
- `src/pipeline/live/hooks/premise_gate.py` - Extended with _call_bus_check(), bus constants, ope_constraint_count in response
- `src/pipeline/live/hooks/session_start.py` - New hook: /api/register + constraint briefing to stdout
- `.claude/settings.local.json` - Added hooks.SessionStart entry (local only, gitignored)
- `tests/test_pag_bus_connection.py` - 14 tests across 3 test classes

## Decisions Made
- PAG response JSON is now always emitted (previously conditional on having additionalContext warnings). This ensures ope_constraint_count is always present in the hook response, even when there are no warnings.
- Session start constraint briefing uses `[OPE]` prefix and prints only forbidden constraints (up to 3) for conciseness.
- Run_id fallback: pre-OpenClaw defaults to session_id. Post-OpenClaw: platform-core sets OPE_RUN_ID. Protocol unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] settings.local.json in global gitignore**
- **Found during:** Task 3
- **Issue:** `.claude/settings.local.json` is excluded by global gitignore rule (`~/.config/git/ignore`). Cannot be committed.
- **Fix:** File updated on disk (functional), but no commit for this task. The file is intentionally local-only per the gitignore configuration.
- **Files modified:** .claude/settings.local.json (on disk, not tracked)
- **Verification:** File contains valid JSON with SessionStart hook entry
- **Impact:** None -- settings.local.json is per-machine configuration, not meant for repository tracking

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal. The gitignored file is correctly updated on disk where it functions. No scope creep.

## Issues Encountered
None beyond the gitignore deviation documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PAG hook now calls /api/check and injects constraint count into response
- SessionStart hook registers sessions and delivers briefings
- Both hooks are fail-open: bus unavailability never blocks Claude Code operation
- Ready for 19-05 (Shadow Mode) which uses these hooks as the delivery mechanism

## Self-Check: PASSED

- All 4 files exist on disk
- All 3 commits found in git log (Task 3 was disk-only due to gitignore)
- premise_gate.py contains _call_bus_check, ope_constraint_count, _BUS_SOCKET
- session_start.py contains /api/register, /api/check, [OPE] prefix
- settings.local.json contains hooks.SessionStart entry
- 14 tests pass, 0 regressions in existing PAG tests (26 total pass)

---
*Phase: 19-control-plane-integration*
*Completed: 2026-02-25*
