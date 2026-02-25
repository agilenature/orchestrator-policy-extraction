# Builder-Operator Boundary Specification

**Layer:** 1 (Canon)
**Source:** Phase 19 CONTEXT.md boundary resolutions
**CCD axis:** identity-firewall (generator and validator must be structurally separated)

---

## 1. The Two Roles

The OPE governance architecture distinguishes two structurally separated roles
for Claude Code sessions. The separation is not a convention enforced by
session discipline -- it is an architectural invariant enforced by the bus API
design and the OPE_RUN_ID injection mechanism.

### Builder-Role

The builder-role designs governance infrastructure, authors Skills Packs, and
sets constraint policy. Builder-role sessions operate before operator sessions
start. They produce the artifacts that govern operator sessions:

- `data/constraints.json` (the ConstraintStore source of truth)
- `.claude/skills/` files (Skills Pack -- behavioral constraints)
- Bus infrastructure code (server, stream processor, governing daemon)

Builder-role sessions do not have `OPE_RUN_ID` set by OpenClaw. They may have
a builder-designated run_id or no run_id at all. The bus will not register
them as participant operator sessions.

### Operator-Role

The operator-role is a dispatched session running under governance. Operator
sessions read constraints from the bus but cannot modify them. They are
dispatched by OpenClaw's Control Plane with `OPE_RUN_ID` injected into their
environment at process start time.

An operator session's lifecycle:
1. OpenClaw dispatches the session with `OPE_RUN_ID` set in environment
2. SessionStart hook reads `OPE_RUN_ID` from `os.environ` and registers with the bus
3. PAG hook calls `/api/check` on each PreToolUse event to receive active constraints
4. Session deregisters on exit

### The Structural Separation

The key invariant: the entity that designs the constraints is never the same
entity that is governed by them in the same session context. Builder sessions
cannot register as operator sessions because they lack the OpenClaw-injected
`OPE_RUN_ID`. Operator sessions cannot modify constraints because the bus
exposes no write endpoint.

---

## 2. OPE_RUN_ID Injection Mechanism

`OPE_RUN_ID` is the environment variable through which OpenClaw's Control Plane
links operator sessions to their dispatching work unit. The injection contract:

**Writer:** OpenClaw (platform-core) sets `OPE_RUN_ID` in the session
environment at dispatch time via `run.iteration`. Only the dispatching
orchestrator writes this value.

**Reader:** Operator sessions read `OPE_RUN_ID` from `os.environ`. The
SessionStart hook and PAG hook both read -- never generate -- this value.

**Non-reflexivity:** An operator session cannot inject its own `OPE_RUN_ID`
because it reads from environ, and the only writer of that environ is the
dispatching orchestrator. The session process inherits the environment set
by the parent process (OpenClaw's session dispatch).

**Pre-OpenClaw-installation fallback:** When `OPE_RUN_ID` is absent from the
environment (because OpenClaw is not yet installed), the SessionStart hook
falls back to using the session_id as the run_id. This means each session is
an isolated epistemological island -- no cross-session grouping occurs. The
architectural invariant (sessions read, they do not generate) holds even in
fallback mode: the session is not generating a cross-session run_id, it is
using its own session_id as a degenerate single-session run_id.

**Post-OpenClaw-installation:** `OPE_RUN_ID` spans all sessions dispatched for
the same work unit across any number of repos. OPE's DuckDB can join
`bus_sessions` with `episodes` by `run_id` to reconstruct the cross-session
causal chain. The bus registration protocol does not change -- only the
injection source changes (from absent/session_id fallback to OpenClaw-injected).

---

## 3. Bus Read-Channel Enforcement

The OPE Governance Bus exposes three session-facing endpoints, all read-channel:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/register` | POST | Announce session start with session_id + run_id |
| `/api/deregister` | POST | Announce session end |
| `/api/check` | POST | Submit premise data, receive constraint briefing |

There is no `/api/constraints` write endpoint. Sessions cannot modify the
constraint store through the bus. The constraint store (`data/constraints.json`)
is owned exclusively by the builder-role.

Governor-internal operations (signal receive from stream processor, constraint
policy updates) are method calls within the governing daemon process. They are
not exposed on the Unix socket. Sessions communicating over the socket cannot
reach governor internals.

The asymmetry is structural, not advisory: the Starlette router has exactly
three routes. A POST to `/api/constraints` returns 404 because the route does
not exist -- not because a permission check rejects it.

---

## 4. Skills Pack Authorship Protocol (Deferred)

**Status:** Deferred to post-OpenClaw-installation. The protocol is defined
here; the enforcement mechanism requires OpenClaw's session dispatch
infrastructure.

Skills Packs (`.claude/skills/` files) are governance artifacts authored by
the builder-role. They define the behavioral constraints that govern operator
sessions. The authorship protocol:

**Authorship firewall:** Builder-role sessions that author Skills Pack files
do not have `OPE_RUN_ID` set. They cannot register as operator sessions with
the bus. The authored files are static artifacts in the OpenClaw workspace;
operator sessions receive them as read-only context loaded at skill invocation
time by OpenClaw.

**Validation separation:** The `behavior.verify` skill (post-installation)
validates Skills Pack files against a test environment. The authoring session
cannot be its own validator because `behavior.verify` runs as a separate
OpenClaw skill invocation -- structurally isolated from the authoring session
that wrote the files. This enforces the identity-firewall CCD axis: the
generator and validator are structurally separated.

**Phase 19 scope:** Do not author Skills Pack files until OpenClaw is
installed and `behavior.verify` can validate them. The protocol definition
in this document is the Phase 19 deliverable for this boundary.

---

## 5. Validation Evidence

Each boundary is verified structurally by tests in the integration test suite.

**Run_id grouping (Boundary 1):**
`test_two_sessions_same_run_id_grouped_in_db` -- registers Session A and
Session B with the same run_id; verifies both appear in `bus_sessions` under
that run_id in DuckDB. This is the Phase 19 validation criterion.

**Run_id fallback (Boundary 1, pre-OpenClaw):**
`test_run_id_fallback_when_not_provided` -- registers a session without
run_id; verifies session_id is used as fallback run_id. Confirms degenerate
single-session behavior when OpenClaw is absent.

**Read-channel enforcement (Boundary 2):**
`test_sessions_cannot_write_constraints_via_bus` -- POSTs to
`/api/constraints`; verifies 404 response. Confirms no write endpoint exists.

**Cross-session constraint delivery (Boundary 2):**
`test_cross_session_constraint_delivery` -- both sessions under same run_id
receive the same constraint list from `/api/check`. Confirms the read-only
briefing path delivers shared constraints.

**Fail-open behavior:**
`test_deregister_unknown_session_returns_200` and
`test_check_with_no_constraints_file_returns_empty` -- confirm the bus never
blocks sessions, even on missing data or unknown sessions.

**Skills Pack authorship (Boundary 3):**
Deferred to post-OpenClaw-installation. No test exists because the
enforcement mechanism (OpenClaw session dispatch) is not yet installed.

---

*Created: 2026-02-25 | Phase 19-05 | Grounded in: 19-CONTEXT.md boundary resolutions*
