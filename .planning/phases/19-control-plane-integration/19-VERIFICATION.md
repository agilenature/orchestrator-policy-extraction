---
phase: 19-control-plane-integration
verified: 2026-02-25T20:00:00Z
status: gaps_found
score: 7/7 must-haves verified (1 test hygiene regression noted)
gaps:
  - truth: "PAG hook extended to call /api/check on the bus; fails open when bus unavailable"
    status: partial
    reason: "Bus integration is implemented and functional (fail-open, /api/check wired, ope_constraint_count in response). However, one pre-existing test (test_no_warnings_no_output) was not updated to match the intentional behavioral change: PAG now always emits JSON even when no warnings exist. The test expects empty stdout; Phase 19 intentionally produces {\"hookSpecificOutput\": {\"ope_constraint_count\": 0}}. The functional goal is achieved. The test is stale relative to the new behavior."
    artifacts:
      - path: "tests/pipeline/live/hooks/test_premise_gate.py"
        issue: "TestAdditionalContextFormat::test_no_warnings_no_output asserts captured.getvalue() == '' but PAG now always emits hookSpecificOutput JSON. Test expectation must be updated to match the intentional Phase 19 output change."
    missing:
      - "Update test_no_warnings_no_output to assert output contains '{\"hookSpecificOutput\": {\"ope_constraint_count\": 0}}' instead of asserting empty string"
---

# Phase 19: Control Plane Integration Verification Report

**Phase Goal:** Build the OPE Governance Bus (Unix socket server + stream processor + governing daemon) and wire it to the PAG hook — transforming OPE from a post-hoc analyzer into a prospective governor. Establish OPE's structural position in the SEMF three-plane architecture by resolving two active CCD violations: `run-id-dissolves-repo-boundary` and `identity-firewall x bootstrap-circularity`.
**Verified:** 2026-02-25T20:00:00Z
**Status:** gaps_found (1 test hygiene gap — functional goal achieved)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Bus server exists using Unix socket; /api/register, /api/check, /api/deregister endpoints present; no session write endpoint | VERIFIED | server.py 122 lines, 3 routes only, SOCKET_PATH from OPE_BUS_SOCKET env, /api/constraints returns 404 (confirmed by test) |
| 2 | Stream processor has TENTATIVE_END/CONFIRMED_END state machine; X_ASK never triggers state transitions; event_level vs episode_level routing | VERIFIED | state_machine.py: MID_EPISODE_TYPES = frozenset({"X_ASK"}), checked before any transition logic; 27 tests all pass including test_x_ask_never_triggers_state_change_from_active and test_x_ask_during_tentative_does_not_confirm |
| 3 | PAG hook extended to call /api/check; fails open when bus unavailable | PARTIAL | _call_bus_check() implemented with Unix socket, 0.5s timeout, exception returns {"constraints": [], "interventions": []}. ope_constraint_count wired. One test (test_no_warnings_no_output) fails because it was not updated to match Phase 19's intentional change: PAG now always emits JSON. |
| 4 | SessionStart hook calls /api/register and writes constraint briefing to stdout | VERIFIED | session_start.py 77 lines: calls /api/register then /api/check, prints "[OPE] N active constraint(s)" to stdout, always exits 0 (fail-open) |
| 5 | Two sessions sharing same OPE_RUN_ID both appear in bus_sessions under that run_id (test exists and passes) | VERIFIED | test_two_sessions_same_run_id_grouped_in_db PASSES: registers session-A and session-B with run_id="run-42", queries DuckDB bus_sessions, asserts both present |
| 6 | BUILDER-OPERATOR-BOUNDARY.md exists documenting OPE_RUN_ID injection, bus read-channel enforcement, Skills Pack authorship protocol | VERIFIED | docs/architecture/BUILDER-OPERATOR-BOUNDARY.md 174 lines, Layer 1 canon, 5 sections: Two Roles, OPE_RUN_ID Injection Mechanism, Bus Read-Channel Enforcement, Skills Pack Authorship Protocol (deferred), Validation Evidence |
| 7 | PROGRAM-SEQUENCE.md updated: OPE Phases 13.3-18 marked complete, Phase 19 entry added | VERIFIED | .planning/PROGRAM-SEQUENCE.md Status Log: all phases 13.3 through 18 marked COMPLETE, Phase 19 row present marked COMPLETE 2026-02-25, Step 7 (MT repo creation) marked READY |

**Score:** 7/7 truths verified (1 with a test hygiene gap against truth #3)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/live/bus/server.py` | Starlette app, /api/register /api/deregister /api/check, Unix socket, fail-open | VERIFIED | 122 lines, all 3 routes present, GovernorDaemon injection, fail-open on DuckDB error |
| `src/pipeline/live/bus/schema.py` | bus_sessions + governance_signals DDL, idempotent create_bus_schema() | VERIFIED | 39 lines, bus_sessions with status CHECK constraint, governance_signals with boundary_dependency CHECK constraint |
| `src/pipeline/live/stream/state_machine.py` | SessionState enum, SessionStateMachine with TENTATIVE_END/CONFIRMED_END, MID_EPISODE_TYPES guard | VERIFIED | 101 lines, MID_EPISODE_TYPES = frozenset({"X_ASK"}), guard checked before all transition logic |
| `src/pipeline/live/stream/signals.py` | EVENT_LEVEL_SIGNAL_TYPES, EPISODE_LEVEL_SIGNAL_TYPES, classify_boundary_dependency() | VERIFIED | 36 lines, 3 event_level types, 3 episode_level types, conservative default for unknown |
| `src/pipeline/live/governor/daemon.py` | GovernorDaemon, get_briefing(), reads constraints.json | VERIFIED | 71 lines, get_briefing() calls _load_active_constraints(), filters retired/superseded, fail-open on missing file |
| `src/pipeline/live/hooks/premise_gate.py` | _call_bus_check(), ope_constraint_count, fails open | VERIFIED | 574 lines, _call_bus_check() at lines 60-80, ope_constraint_count at line 556, exception handler returns empty dict |
| `src/pipeline/live/hooks/session_start.py` | main(), _post_json(), /api/register + /api/check, constraint briefing to stdout | VERIFIED | 77 lines, _post_json() with Unix socket, /api/register call line 45, /api/check call line 48, stdout print lines 57-68 |
| `docs/architecture/BUILDER-OPERATOR-BOUNDARY.md` | OPE_RUN_ID injection, bus read-channel enforcement, Skills Pack authorship protocol | VERIFIED | 174 lines, all three boundaries documented with validation evidence links |
| `tests/test_bus_integration.py` | cross-session run_id grouping test, passes | VERIFIED | 252 lines, 9 tests, all 9 PASS including critical test_two_sessions_same_run_id_grouped_in_db |
| `.planning/PROGRAM-SEQUENCE.md` | Phase 19 COMPLETE, Phases 13.3-18 COMPLETE | VERIFIED | Status Log table has Phase 19 row marked COMPLETE 2026-02-25 |
| `src/pipeline/cli/bus.py` | bus start + status commands | VERIFIED | 78 lines, bus_group Click group, start uses uvicorn with uds=socket, status checks socket existence |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `premise_gate.py` | `/api/check` on Unix socket | `_call_bus_check()` using http.client + AF_UNIX socket | WIRED | Lines 60-80: socket created, /api/check POST, response parsed, exception returns empty dict |
| `session_start.py` | `/api/register` on Unix socket | `_post_json()` | WIRED | Line 45: _post_json("/api/register", ...) called in main() |
| `server.py` | `GovernorDaemon.get_briefing()` | `/api/check` handler calls `_daemon.get_briefing()` | WIRED | Line 107: briefing = _daemon.get_briefing(session_id, run_id) |
| `GovernorDaemon` | `data/constraints.json` | `_load_active_constraints()` | WIRED | Line 64: path.read_text() + json.loads, filters active constraints |
| `StreamProcessor` | `SessionStateMachine` | `_state_machine.transition()` in process_event() | WIRED | Line 74: `_new_state, boundary_confirmed = self._state_machine.transition(event_type, now)` |
| `bus_sessions` table | `run_id` grouping | INSERT OR REPLACE with run_id from register body | WIRED | Server.py line 70-74: INSERT with run_id parameter; test verifies two sessions appear under same run_id |

---

### Requirements Coverage

| Requirement | Status | Notes |
|-------------|--------|-------|
| LIVE-01 PreToolUse hook (constraint delivery) | SATISFIED | PAG hook calls /api/check, receives constraint list, emits ope_constraint_count |
| LIVE-02 PostToolUse hook | SATISFIED (deferred scope) | Phase 19 CONTEXT.md confirms PostToolUse not in Phase 19 scope; SessionStart is the session-level hook |
| LIVE-04 Inter-session coordination bus (Unix socket) | SATISFIED | bus/server.py, bus/schema.py, CLI, all tests pass |
| LIVE-05 Governing daemon | SATISFIED | governor/daemon.py: GovernorDaemon reads constraints.json, generates ConstraintBriefing |
| run-id-dissolves-repo-boundary violation | SATISFIED (architecture) | bus_sessions table records run_id per session; two-session test confirms grouping; OpenClaw injection deferred to post-installation |
| identity-firewall x bootstrap-circularity violation | SATISFIED (architecture) | Bus API exposes no write endpoint; BUILDER-OPERATOR-BOUNDARY.md documents structural separation |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/pipeline/live/stream/processor.py` | 103-110 | `_detect_signals()` returns `[]` unconditionally | Info | Intentional extension point per plan: "governing daemon (Plan 03) wires real detectors via dependency injection." Documented in SUMMARY 19-02. Not a blocker — the routing logic (event_level vs episode_level) is fully implemented around this hook. |
| `src/pipeline/live/governor/briefing.py` | 24 | `interventions: list = []  # DDF co-pilot stubs (LIVE-06 deferred)` | Info | LIVE-06 (DDF co-pilot) explicitly deferred to post-OpenClaw-installation. Documented in docstring. Not a blocker. |
| `tests/pipeline/live/hooks/test_premise_gate.py` | 727 | `test_no_warnings_no_output` asserts empty stdout but PAG now always emits hookSpecificOutput JSON | Warning | Phase 19 intentionally changed PAG to always emit JSON (decision documented in SUMMARY 19-04). Test not updated to match. 1 test FAILS. Not a blocker for the goal (bus integration is functional), but creates noise in test suite. |

---

### Human Verification Required

#### 1. SessionStart Hook In Settings

**Test:** Verify `.claude/settings.local.json` on disk contains the SessionStart hook entry pointing to `session_start.py`.
**Expected:** The file should have a `hooks.SessionStart` entry that invokes `src/pipeline/live/hooks/session_start.py`.
**Why human:** `settings.local.json` is in the global gitignore and cannot be read by file system inspection via test. The SUMMARY confirms it was written to disk but the file is not tracked.

#### 2. Bus Operational End-to-End

**Test:** Start the bus with `python -m src.pipeline.cli bus start`, then in a second terminal run `curl --unix-socket /tmp/ope-governance-bus.sock http://localhost/api/check -d '{"session_id":"test","run_id":"test"}' -H "Content-Type: application/json"`.
**Expected:** Response with `{"constraints": [...], "interventions": []}` structure.
**Why human:** Bus requires uvicorn to be running; cannot be verified by grep-based analysis.

---

### Gaps Summary

One gap was found: a test hygiene regression in the PAG hook test suite.

**What happened:** Phase 19 Plan 04 intentionally changed the PAG hook to always emit JSON with `ope_constraint_count` in the response (even when no warnings exist). This was a documented architectural decision: "PAG response JSON is now always emitted to ensure ope_constraint_count is always present." However, `test_no_warnings_no_output` in `tests/pipeline/live/hooks/test_premise_gate.py` was not updated to match this new behavior. The test asserts `captured.getvalue() == ""` but the hook now produces `{"hookSpecificOutput": {"ope_constraint_count": 0}}`.

**What this does NOT affect:** The functional goal is fully achieved. The bus is wired, fail-open behavior is correct, the constraint count is being reported. The gap is entirely in test expectation alignment, not in behavior.

**Fix required:** Update `test_no_warnings_no_output` to expect the JSON output rather than empty string. This is a one-line test fix.

**The two segmenter failures** (`test_multiple_sequential_episodes`, `test_x_ask_outcome`) are pre-existing failures from commit 30e45dc, which predates all Phase 19 commits by approximately 350 commits. Phase 19 did not introduce these failures.

---

*Verified: 2026-02-25T20:00:00Z*
*Verifier: Claude (gsd-verifier)*
