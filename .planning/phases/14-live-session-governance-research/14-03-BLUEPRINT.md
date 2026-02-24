# Phase 15: Live Session Governance Implementation Blueprint

**Synthesized from:** 14-01-DESIGN.md (LIVE-01, LIVE-02, LIVE-03) + 14-02-DESIGN.md (LIVE-04, LIVE-05, LIVE-06)
**Purpose:** Serve as the primary input for Phase 15 `/gsd:plan-phase` -- every plan, file target, API contract, and test scenario derives from this document.
**Date:** 2026-02-24

---

## 0. Phase 15 Overview

### 0.1 Phase Summary

| Field | Value |
|-------|-------|
| **Phase name** | Live Session Governance Implementation |
| **Goal** | Implement the live governance layer designed in Phase 14: hook scripts (PreToolUse + SessionStart), JSONL stream processor, inter-session coordination bus, and governing session daemon |
| **Depends on** | Phase 14 (design complete: 14-01 + 14-02), Phase 13 (PolicyViolationChecker + ConstraintStore ready) |
| **Requirements** | LIVE-01 through LIVE-05 (same as Phase 14 research, now implemented) |
| **Estimated plans** | 9 plans across 5 waves |
| **Estimated duration** | ~5.5 hours total execution time |
| **New dependency** | `pip install watchdog>=6.0.0` (FSEvents-based JSONL file monitoring) |

### 0.2 Module Structure

All new code lives under `src/pipeline/live/`. Test mirrors live under `tests/pipeline/live/`.

```
src/pipeline/live/
  __init__.py                          # Package init; exports key classes
  hooks/
    __init__.py                        # Hooks subpackage init
    models.py                          # HookInput, GovernanceDecision, AxisGroup, ConstraintBriefing, GovernanceSignal Pydantic models
    governance_check.py                # LIVE-01: PreToolUse hook handler (stdin JSON -> stdout JSON)
    constraint_briefing.py             # LIVE-02: SessionStart hook handler (stdin JSON -> stdout briefing)
    log_event.py                       # PostToolUse async event logger (future; placeholder)
  stream/
    __init__.py                        # Stream subpackage init
    adapters.py                        # LiveEvent dataclass + LiveEventAdapter (raw JSONL -> LiveEvent)
    incremental.py                     # IncrementalEscalationAdapter, IncrementalAmnesiaAdapter, IncrementalPolicyCheckAdapter
    processor.py                       # StreamProcessor: watchdog Observer + event loop + signal emission
  bus/
    __init__.py                        # Bus subpackage init
    models.py                          # Bus-specific request/response Pydantic models (CheckRequest, RegisterRequest, etc.)
    state.py                           # SharedState, SessionRecord, ProjectState, BroadcastMessage dataclasses
    server.py                          # Starlette ASGI app with 10 API routes + uvicorn runner
    client.py                          # BusClient: sync + async httpx wrappers for Unix socket
  governor/
    __init__.py                        # Governor subpackage init
    daemon.py                          # GovernorDaemon: async background tasks on bus event loop
    decisions.py                       # Decision matrix logic (signal -> action mapping)
    broadcaster.py                     # Broadcast message delivery (queuing + drain on /api/check)
```

**Test file structure:**

```
tests/pipeline/live/
  __init__.py
  hooks/
    __init__.py
    test_models.py                     # HookInput/GovernanceDecision validation, serialization
    test_governance_check.py           # PreToolUse hook: stdin/stdout, decision logic, fallback
    test_constraint_briefing.py        # SessionStart hook: scope filtering, briefing format, truncation
  stream/
    __init__.py
    test_adapters.py                   # LiveEventAdapter: JSONL conversion, tag inference rules
    test_incremental.py                # All 3 incremental adapters: event processing, buffering, flush
    test_processor.py                  # StreamProcessor: watchdog integration, position tracking, signal emission
  bus/
    __init__.py
    test_models.py                     # Bus request/response model validation
    test_state.py                      # SharedState: session registry, constraint cache, staleness
    test_server.py                     # All 10 API routes via httpx.AsyncClient(app=app)
    test_client.py                     # BusClient: connectivity, check, fallback
  governor/
    __init__.py
    test_daemon.py                     # GovernorDaemon: start/stop, event consumption
    test_decisions.py                  # Decision matrix: all signal types, graduation logic
    test_broadcaster.py                # Broadcast delivery: queuing, drain, block flag
  test_integration.py                  # End-to-end: bus + hooks + governor + stream processor
  test_hook_protocol.py                # JSON protocol compliance for Claude Code hook contract
```

**File counts:** 18 source files + 15 test files = 33 total new files.

---

## 1. Wave Definitions

### Wave 1: Core Hook Scripts (LIVE-01 + LIVE-02)

**Scope:** Standalone hook scripts that work without the bus. Direct file-based constraint loading via ConstraintStore.

**Files created:**

| Source File | Purpose |
|-------------|---------|
| `src/pipeline/live/__init__.py` | Package init |
| `src/pipeline/live/hooks/__init__.py` | Hooks subpackage init |
| `src/pipeline/live/hooks/models.py` | HookInput, GovernanceDecision, AxisGroup, ConstraintBriefing, GovernanceSignal Pydantic v2 models |
| `src/pipeline/live/hooks/governance_check.py` | PreToolUse handler: parse stdin, extract text, check constraints, emit stdout JSON |
| `src/pipeline/live/hooks/constraint_briefing.py` | SessionStart handler: load constraints, filter by scope, group by CCD axis, emit briefing |

| Test File | Purpose |
|-----------|---------|
| `tests/pipeline/live/__init__.py` | Test package init |
| `tests/pipeline/live/hooks/__init__.py` | Test subpackage init |
| `tests/pipeline/live/hooks/test_models.py` | Model validation, frozen immutability, field defaults |
| `tests/pipeline/live/hooks/test_governance_check.py` | Decision logic, text extraction per tool, fallback behavior |
| `tests/pipeline/live/hooks/test_constraint_briefing.py` | Scope filtering, axis grouping, durability classification, truncation |

**API contracts:** See Section 3.1, Wave 1.

**Dependencies on existing code:**
- `src/pipeline/constraint_store.py` -- `ConstraintStore(path, schema_path)`, `.get_active_constraints() -> list[dict]`
- `src/pipeline/feedback/checker.py` -- `PolicyViolationChecker(constraint_store)`, `.check(text) -> (bool, dict | None)`
- `src/pipeline/utils.py` -- `scopes_overlap(paths_a, paths_b) -> bool`

**Estimated plans:** 2
- Plan 15-01: Hook models + governance_check.py (2 tasks, ~30 min)
- Plan 15-02: constraint_briefing.py + hook protocol tests (2 tasks, ~30 min)

**Success criteria:**
1. `echo '{"session_id":"test","cwd":"/tmp","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | PYTHONDONTWRITEBYTECODE=1 python3 src/pipeline/live/hooks/governance_check.py` produces valid deny/warn/allow JSON on stdout.
2. `echo '{"session_id":"test","cwd":"/Users/david/projects/orchestrator-policy-extraction","hook_event_name":"SessionStart"}' | PYTHONDONTWRITEBYTECODE=1 python3 src/pipeline/live/hooks/constraint_briefing.py` produces JSON with `hookSpecificOutput.additionalContext` containing GOVERNANCE BRIEFING text.
3. All hook failures (missing file, parse error, import error) result in exit code 0 with no stdout (fail-open).
4. Total hook latency: <200ms for PreToolUse, <500ms for SessionStart.

---

### Wave 2: JSONL Stream Processor (LIVE-03)

**Scope:** Background daemon that tails session JSONL files using watchdog FSEvents, processes events through incremental detector adapters, and emits GovernanceSignal objects.

**Files created:**

| Source File | Purpose |
|-------------|---------|
| `src/pipeline/live/stream/__init__.py` | Stream subpackage init |
| `src/pipeline/live/stream/adapters.py` | LiveEvent dataclass + LiveEventAdapter with 8 pre-compiled tag inference rules |
| `src/pipeline/live/stream/incremental.py` | IncrementalEscalationAdapter, IncrementalAmnesiaAdapter, IncrementalPolicyCheckAdapter |
| `src/pipeline/live/stream/processor.py` | StreamProcessor: watchdog Observer, position tracking, partial line handling, signal emission |

| Test File | Purpose |
|-----------|---------|
| `tests/pipeline/live/stream/__init__.py` | Test subpackage init |
| `tests/pipeline/live/stream/test_adapters.py` | LiveEventAdapter: each event type, each tag inference rule, multi-tool-use assistant messages |
| `tests/pipeline/live/stream/test_incremental.py` | All 3 adapters: window management, buffering, flush, discard |
| `tests/pipeline/live/stream/test_processor.py` | File watching, position tracking, partial lines, signal routing |

**API contracts:** See Section 3.1, Wave 2.

**Dependencies:**
- Wave 1 models: `GovernanceSignal`, `LiveEvent` (from `hooks/models.py`)
- Existing: `EscalationDetector` algorithm (replicated incrementally), `PolicyViolationChecker`
- NEW external: `watchdog>=6.0.0` (`pip install watchdog`)

**Estimated plans:** 2
- Plan 15-03: LiveEventAdapter + incremental detector adapters (2 tasks, ~40 min)
- Plan 15-04: StreamProcessor with watchdog (2 tasks, ~40 min)

**Success criteria:**
1. StreamProcessor detects a new event appended to a test JSONL file within 200ms.
2. IncrementalEscalationAdapter detects a block-then-bypass sequence across per-event calls.
3. IncrementalAmnesiaAdapter buffers candidates and only emits on `flush_pending()` (episode_level dispatch).
4. IncrementalPolicyCheckAdapter emits immediately on constraint match (event_level dispatch).
5. Partial line handling: incomplete JSON line buffered, completed on next append.

---

### Wave 3: Inter-Session Bus (LIVE-04)

**Scope:** HTTP service on Unix domain socket providing shared constraint state, session registry, and governance event distribution across parallel Claude Code sessions.

**Files created:**

| Source File | Purpose |
|-------------|---------|
| `src/pipeline/live/bus/__init__.py` | Bus subpackage init |
| `src/pipeline/live/bus/models.py` | Bus Pydantic models: CheckRequest, RegisterRequest, DeregisterRequest, BroadcastRequest, etc. |
| `src/pipeline/live/bus/state.py` | SharedState, SessionRecord, ProjectState, BroadcastMessage dataclasses |
| `src/pipeline/live/bus/server.py` | Starlette ASGI app with 10 routes + uvicorn startup + shutdown handlers |
| `src/pipeline/live/bus/client.py` | BusClient: sync/async httpx wrappers, socket discovery, timeout fallback |

| Test File | Purpose |
|-----------|---------|
| `tests/pipeline/live/bus/__init__.py` | Test subpackage init |
| `tests/pipeline/live/bus/test_models.py` | Request/response model validation |
| `tests/pipeline/live/bus/test_state.py` | Session add/remove, constraint cache, staleness detection, multi-project |
| `tests/pipeline/live/bus/test_server.py` | All 10 routes via httpx.AsyncClient(app=app, transport=...) |
| `tests/pipeline/live/bus/test_client.py` | BusClient: is_available(), check(), fallback behavior |

**API contracts:** See Section 3.1, Wave 3.

**Dependencies:**
- Wave 1 models: `GovernanceDecision`, `GovernanceSignal`
- Existing: `ConstraintStore`, `PolicyViolationChecker`
- Existing (already installed): `starlette>=0.52.1`, `uvicorn>=0.40.0`, `httpx>=0.28.1`

**Estimated plans:** 2
- Plan 15-05: Bus models + SharedState + server routes (3 tasks, ~45 min)
- Plan 15-06: BusClient + bus integration tests (2 tasks, ~30 min)

**Success criteria:**
1. Bus starts on Unix socket at `/tmp/ope-governance-bus.sock`.
2. `GET /api/health` returns 200 with session_count and constraint_count.
3. `POST /api/check` returns correct deny/warn/allow decision for a given tool call.
4. `POST /api/sessions/register` adds a session; `POST /api/sessions/deregister` removes it.
5. Stale socket detection: bus handles orphaned socket from crashed process.
6. Constraint cache reload: `POST /api/constraints/reload` replaces in-memory cache atomically.

---

### Wave 4: Governor Daemon (LIVE-05)

**Scope:** Async background tasks co-located in the bus process that monitor governance signals, apply the decision matrix, and broadcast blocks/warnings to sessions.

**Files created:**

| Source File | Purpose |
|-------------|---------|
| `src/pipeline/live/governor/__init__.py` | Governor subpackage init |
| `src/pipeline/live/governor/daemon.py` | GovernorDaemon: async task runner consuming events from SharedState ring buffer |
| `src/pipeline/live/governor/decisions.py` | Decision matrix: signal_type + condition -> autonomous action |
| `src/pipeline/live/governor/broadcaster.py` | Broadcast message queuing, drain on /api/check, block flag management |

| Test File | Purpose |
|-----------|---------|
| `tests/pipeline/live/governor/__init__.py` | Test subpackage init |
| `tests/pipeline/live/governor/test_daemon.py` | Start/stop lifecycle, event consumption, graceful shutdown |
| `tests/pipeline/live/governor/test_decisions.py` | All 10 signal types in decision matrix, graduation logic |
| `tests/pipeline/live/governor/test_broadcaster.py` | Queue management, drain on check, block/unblock |

**API contracts:** See Section 3.1, Wave 4.

**Dependencies:**
- Wave 3: SharedState (direct access, not HTTP), server routes for broadcast delivery
- Wave 2: Stream processor signals (GovernanceSignal)
- Wave 1: GovernanceDecision model

**Estimated plans:** 2
- Plan 15-07: Governor daemon + decisions + broadcaster (2-3 tasks, ~45 min)

**Success criteria:**
1. GovernorDaemon starts as an async task within the bus event loop.
2. Decision matrix correctly maps `constraint_violated` (severity=forbidden) to broadcast `block`.
3. Decision matrix correctly maps `escalation_detected` to broadcast `warn`.
4. Broadcast messages are delivered to the target session's next `/api/check` response.
5. Block flag: once set, ALL subsequent `/api/check` calls for that session return `deny`.

---

### Wave 5: Integration + Hook Registration

**Scope:** Wire everything together, register hooks in `.claude/settings.json`, add CLI commands for bus management, and run end-to-end integration tests.

**Files created/modified:**

| File | Action | Purpose |
|------|--------|---------|
| `.claude/settings.json` | Modified | Add PreToolUse and SessionStart hook configurations |
| `src/pipeline/cli/govern.py` | Modified | Add `bus start`, `bus stop`, `bus status` subcommands |
| `src/pipeline/live/hooks/governance_check.py` | Modified | Add bus fallback: try bus first, fall back to direct |
| `src/pipeline/live/hooks/constraint_briefing.py` | Modified | Add bus session registration on SessionStart |
| `tests/pipeline/live/test_integration.py` | Created | End-to-end: bus + hooks + governor + stream processor |
| `tests/pipeline/live/test_hook_protocol.py` | Created | JSON protocol compliance for Claude Code hook contract |

**Dependencies:** All previous waves.

**Estimated plans:** 2
- Plan 15-08: CLI commands + hook registration (2 tasks, ~30 min)
- Plan 15-09: End-to-end integration tests (2 tasks, ~30 min)

**Success criteria:**
1. `python -m src.pipeline.cli govern bus start` starts the governance bus daemon.
2. `python -m src.pipeline.cli govern bus status` reports bus health.
3. `python -m src.pipeline.cli govern bus stop` gracefully shuts down the bus.
4. `.claude/settings.json` contains PreToolUse and SessionStart hook configurations.
5. PreToolUse hook tries bus first (POST /api/check), falls back to direct file load on failure.
6. SessionStart hook registers the session with the bus (POST /api/sessions/register) when available.
7. End-to-end test: start bus -> register session -> check constraint -> detect escalation -> broadcast warning -> verify delivery.

---

## 2. Wave Dependency Graph

```
Wave 1: Core Hook Scripts (LIVE-01 + LIVE-02)
    |  provides: HookInput, GovernanceDecision, GovernanceSignal models
    |  provides: governance_check.py, constraint_briefing.py (standalone mode)
    v
Wave 2: JSONL Stream Processor (LIVE-03)
    |  consumes: GovernanceSignal, LiveEvent models from Wave 1
    |  provides: IncrementalEscalationAdapter, IncrementalAmnesiaAdapter, StreamProcessor
    v
Wave 3: Inter-Session Bus (LIVE-04)
    |  consumes: GovernanceDecision from Wave 1
    |  provides: SharedState, BusClient, 10 API routes
    v
Wave 4: Governor Daemon (LIVE-05)
    |  consumes: SharedState from Wave 3, GovernanceSignal from Wave 2
    |  provides: GovernorDaemon, decision matrix, broadcast protocol
    v
Wave 5: Integration + Hook Registration
    |  consumes: All previous waves
    |  provides: CLI commands, hook registration, end-to-end wiring
```

**Note:** Waves 2 and 3 are technically independent of each other (both depend on Wave 1, neither depends on the other). They could be implemented in parallel. However, the plan mapping sequences them 2-then-3 because the stream processor's bus emission path requires the BusClient (Wave 3). The standalone emission paths (stdout, DuckDB) work without the bus.

---

## 3. Technical Specifications

### 3.1 API Contract Summary

All signatures use Python 3.13 type hints. Pydantic v2 `BaseModel` with `frozen=True` for immutable data models.

#### Wave 1: Hook Models + Scripts

**models.py -- Pydantic Models**

```python
class HookInput(BaseModel, frozen=True):
    """Parsed hook input from Claude Code stdin."""
    session_id: str
    transcript_path: str = ""
    cwd: str
    permission_mode: str = "default"
    hook_event_name: Literal["PreToolUse", "SessionStart", "PostToolUse", "SessionEnd"]
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_use_id: str | None = None

class GovernanceDecision(BaseModel, frozen=True):
    """Result of checking a tool call against active constraints."""
    decision: Literal["allow", "warn", "deny"]
    constraint_id: str | None = None
    constraint_text: str | None = None
    reason: str | None = None
    severity: Literal["warning", "requires_approval", "forbidden"] | None = None
    ccd_axis: str | None = None
    epistemological_origin: Literal["reactive", "principled", "inductive"] | None = None

class AxisGroup(BaseModel, frozen=True):
    """A group of constraints sharing a CCD axis."""
    ccd_axis: str
    principle_statement: str
    constraint_count: int
    constraint_ids: list[str]
    severities: list[str]
    lowest_durability: float | None = None
    lowest_durability_constraint_id: str | None = None

class ConstraintBriefing(BaseModel, frozen=True):
    """Structured briefing for SessionStart hook output."""
    total_constraints: int
    critical_groups: list[AxisGroup]
    active_groups: list[AxisGroup]
    ungrouped_constraints: list[dict]
    project_scope: str
    generated_at: str

class GovernanceSignal(BaseModel, frozen=True):
    """Signal emitted by stream processor or detectors."""
    signal_type: Literal[
        "escalation_detected", "amnesia_detected",
        "constraint_violated", "constraint_graduated"
    ]
    session_id: str
    timestamp: str
    details: dict[str, Any]
    boundary_dependency: Literal["event_level", "episode_level"]
    constraint_id: str | None = None
    ccd_axis: str | None = None
    episode_id: str | None = None

class LiveEvent(BaseModel, frozen=True):
    """Lightweight tagged representation of a raw JSONL event."""
    event_type: Literal["user", "assistant", "tool_use", "tool_result", "system", "unknown"]
    timestamp: str
    session_id: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    text_content: str = ""
    file_path: str | None = None
    inferred_tag: Literal[
        "O_DIR", "O_GATE", "O_CORR", "O_ESC",
        "X_ASK", "X_PROPOSE",
        "T_TEST", "T_RISKY", "T_GIT_COMMIT",
        None
    ] = None
    raw_event_type: str = ""
```

**governance_check.py -- PreToolUse Hook**

```python
def build_search_text(tool_name: str, tool_input: dict) -> str:
    """Extract searchable text from tool input based on tool name.

    Truncates content fields to 500 chars. Joins with spaces.
    """

def run_check(hook_input: HookInput) -> GovernanceDecision:
    """Run constraint check against the tool call.

    Loads ConstraintStore + PolicyViolationChecker (or calls bus).
    Returns GovernanceDecision with decision, reason, constraint details.
    """

def format_output(decision: GovernanceDecision, hook_input: HookInput) -> str | None:
    """Format GovernanceDecision into Claude Code hook JSON output.

    Returns JSON string for deny/warn, None for silent allow.
    Deny: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}
    Warn: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "..."}}
    Allow: None (no output)
    """

def main() -> None:
    """Entry point: read stdin, check constraints, write stdout, exit 0."""
```

**constraint_briefing.py -- SessionStart Hook**

```python
def load_scoped_constraints(cwd: str) -> list[dict]:
    """Load active constraints filtered by cwd scope via scopes_overlap()."""

def group_by_axis(constraints: list[dict]) -> tuple[list[AxisGroup], list[AxisGroup], list[dict]]:
    """Group constraints by ccd_axis into critical, active, and ungrouped.

    Critical: contains forbidden severity or durability < 0.3.
    Active: remaining axis-grouped constraints.
    Ungrouped: constraints with ccd_axis = null.
    Returns (critical_groups, active_groups, ungrouped_constraints).
    """

def format_briefing(briefing: ConstraintBriefing) -> str:
    """Format ConstraintBriefing into human-readable text.

    Sections: CRITICAL, ACTIVE, UNGROUPED.
    Truncates to 2000 chars if needed (CRITICAL never truncated).
    """

def format_output(briefing_text: str) -> str:
    """Format briefing text into SessionStart hook JSON output.

    Returns: {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
    """

def main() -> None:
    """Entry point: read stdin, build briefing, write stdout, exit 0."""
```

#### Wave 2: Stream Processor

**adapters.py -- LiveEventAdapter**

```python
class LiveEventAdapter:
    """Convert raw JSONL event dicts into LiveEvent objects.

    Pre-compiles 8 tag inference regex patterns at __init__.
    """

    def __init__(self) -> None:
        """Initialize with pre-compiled tag inference patterns."""

    def adapt(self, raw_event: dict) -> list[LiveEvent]:
        """Convert a raw JSONL dict to one or more LiveEvent objects.

        Returns empty list for system/progress events.
        Returns multiple LiveEvents for assistant messages with multiple tool_use blocks.
        """
```

**incremental.py -- Incremental Adapters**

```python
class IncrementalEscalationAdapter:
    """Incremental wrapper for escalation detection algorithm."""

    def __init__(self, config: PipelineConfig) -> None:
        """Initialize with pipeline config for escalation settings."""

    def process_event(self, event: LiveEvent) -> list[EscalationCandidate]:
        """Process a single event; return any escalation candidates detected."""

    def reset(self) -> None:
        """Clear all pending windows (e.g., on session end)."""

class IncrementalAmnesiaAdapter:
    """Per-event constraint checking with episode-level signal buffering."""

    def __init__(self, checker: PolicyViolationChecker) -> None:
        """Initialize with a pre-loaded PolicyViolationChecker."""

    def process_event(self, event: LiveEvent) -> None:
        """Check event against constraints; buffer matches (no return)."""

    def flush_pending(self, episode_id: str) -> list[GovernanceSignal]:
        """Flush buffered amnesia signals at CONFIRMED_END. Attach episode_id."""

    def discard_pending(self) -> int:
        """Discard buffered signals on REOPENED. Return count discarded."""

class IncrementalPolicyCheckAdapter:
    """Post-execution constraint checking for JSONL events."""

    def __init__(self, checker: PolicyViolationChecker) -> None:
        """Initialize with a pre-loaded PolicyViolationChecker."""

    def process_event(self, event: LiveEvent) -> GovernanceSignal | None:
        """Check event against constraints; return signal if violation found (event_level)."""
```

**processor.py -- StreamProcessor**

```python
class StreamProcessor:
    """Monitors JSONL session files and runs incremental detectors.

    Uses watchdog Observer for FSEvents-based file monitoring.
    Maintains per-file position tracking and partial line buffers.
    """

    def __init__(self, project_dir: str, bus_client: BusClient | None = None) -> None:
        """Initialize processor for a project directory.

        Resolves JSONL session directory from project_dir.
        Creates detector adapters and watchdog observer.
        """

    def start(self) -> None:
        """Start watching for JSONL file changes. Non-blocking."""

    def stop(self) -> None:
        """Stop the watchdog observer and clean up state."""

    def process_event(self, session_id: str, raw_event: dict) -> list[GovernanceSignal]:
        """Process a single raw JSONL event through all adapters.

        Returns list of event_level signals emitted immediately.
        Episode_level signals are buffered internally.
        """
```

#### Wave 3: Inter-Session Bus

**models.py -- Bus Request/Response Models**

```python
class CheckRequest(BaseModel):
    """POST /api/check request body."""
    tool_name: str
    tool_input: dict[str, Any]
    session_id: str
    project_dir: str

class CheckResponse(BaseModel):
    """POST /api/check response body."""
    decision: Literal["allow", "warn", "deny"]
    constraint_id: str | None = None
    reason: str | None = None
    severity: str | None = None
    ccd_axis: str | None = None
    pending_broadcasts: list[dict] = []

class RegisterRequest(BaseModel):
    """POST /api/sessions/register request body."""
    session_id: str
    project_dir: str
    transcript_path: str
    started_at: str

class DeregisterRequest(BaseModel):
    """POST /api/sessions/deregister request body."""
    session_id: str

class BroadcastRequest(BaseModel):
    """POST /api/broadcast request body."""
    message_type: Literal["block", "warn", "briefing"]
    target_sessions: list[str] | Literal["all"]
    content: str
    source: str | None = None
    constraint_id: str | None = None

class ReloadRequest(BaseModel):
    """POST /api/constraints/reload request body."""
    project_dir: str
```

**state.py -- Shared State**

```python
@dataclass
class SessionRecord:
    """Registered session record in the bus."""
    session_id: str
    project_dir: str
    transcript_path: str
    registered_at: datetime
    last_seen: datetime
    stale: bool = False
    blocked: bool = False
    blocked_reason: str | None = None

@dataclass
class ProjectState:
    """Per-project state: constraint store, checker, and session registry."""
    project_dir: str
    constraint_store: ConstraintStore
    checker: PolicyViolationChecker
    sessions: dict[str, SessionRecord]
    constraints_loaded_at: datetime
    constraint_count: int

@dataclass
class BroadcastMessage:
    """Pending broadcast message for a session."""
    message_type: str
    content: str
    source: str | None
    constraint_id: str | None
    created_at: datetime

class SharedState:
    """Central bus state manager. Single-threaded async access."""

    def __init__(self) -> None: ...

    def add_session(self, request: RegisterRequest) -> int:
        """Register a session. Returns updated session count."""

    def remove_session(self, session_id: str) -> int:
        """Deregister a session. Returns updated session count."""

    def get_project_state(self, project_dir: str) -> ProjectState | None:
        """Get state for a project, or None if not registered."""

    def check_constraint(self, request: CheckRequest) -> CheckResponse:
        """Run constraint check for a tool call. Updates last_seen."""

    def add_event(self, signal: GovernanceSignal) -> str:
        """Add an event to the ring buffer. Returns event_id."""

    def get_sessions(self, project_dir: str | None = None) -> list[dict]:
        """List sessions, optionally filtered by project."""

    def reload_constraints(self, project_dir: str) -> tuple[int, int]:
        """Reload constraints from disk. Returns (new_count, old_count)."""

    def queue_broadcast(self, request: BroadcastRequest) -> dict:
        """Queue broadcast messages for target sessions. Returns delivery report."""

    def drain_broadcasts(self, session_id: str) -> list[dict]:
        """Drain pending broadcasts for a session. Called by /api/check."""
```

**server.py -- Route Handlers**

```python
# Starlette route handler signatures (all async)

async def health(request: Request) -> JSONResponse:
    """GET /api/health -- bus health and summary stats."""

async def check_constraint(request: Request) -> JSONResponse:
    """POST /api/check -- constraint check for PreToolUse hook."""

async def get_constraints(request: Request) -> JSONResponse:
    """GET /api/constraints -- active constraints for a project."""

async def reload_constraints(request: Request) -> JSONResponse:
    """POST /api/constraints/reload -- force constraint reload from disk."""

async def register_session(request: Request) -> JSONResponse:
    """POST /api/sessions/register -- register a session."""

async def deregister_session(request: Request) -> JSONResponse:
    """POST /api/sessions/deregister -- deregister a session."""

async def list_sessions(request: Request) -> JSONResponse:
    """GET /api/sessions -- list active sessions."""

async def post_event(request: Request) -> JSONResponse:
    """POST /api/events -- submit a governance event."""

async def event_stream(request: Request) -> EventSourceResponse:
    """GET /api/events/stream -- SSE stream of governance events."""

async def broadcast(request: Request) -> JSONResponse:
    """POST /api/broadcast -- broadcast message to sessions."""

def create_app(state: SharedState) -> Starlette:
    """Create the Starlette ASGI app with all routes mounted."""
```

**client.py -- BusClient**

```python
class BusClient:
    """Client for the governance bus Unix socket API."""

    def __init__(self, socket_path: str = "/tmp/ope-governance-bus.sock") -> None:
        """Initialize with socket path."""

    def is_available(self) -> bool:
        """Test if bus is running (check socket exists + GET /api/health)."""

    def check(self, tool_name: str, tool_input: dict, session_id: str, project_dir: str) -> CheckResponse | None:
        """POST /api/check. Returns None on failure (caller falls back to direct)."""

    def register_session(self, session_id: str, project_dir: str, transcript_path: str, started_at: str) -> bool:
        """POST /api/sessions/register. Returns True on success."""

    def deregister_session(self, session_id: str) -> bool:
        """POST /api/sessions/deregister. Returns True on success."""

    def post_event(self, signal: GovernanceSignal) -> str | None:
        """POST /api/events. Returns event_id on success, None on failure."""

    def health(self) -> dict | None:
        """GET /api/health. Returns health dict on success, None on failure."""
```

#### Wave 4: Governor Daemon

**daemon.py -- GovernorDaemon**

```python
class GovernorDaemon:
    """Async background tasks for governance monitoring and decision-making.

    Co-located in the bus process. Consumes events from SharedState ring buffer.
    """

    def __init__(self, state: SharedState) -> None:
        """Initialize with direct access to SharedState."""

    async def start(self) -> None:
        """Start background tasks: event consumer, staleness checker."""

    async def stop(self) -> None:
        """Cancel background tasks gracefully."""

    async def _consume_events(self) -> None:
        """Main loop: consume events, apply decision matrix, emit actions."""

    async def _check_staleness(self) -> None:
        """Periodic task: mark stale sessions, auto-deregister after 30 min."""
```

**decisions.py -- Decision Matrix**

```python
@dataclass
class GovernanceAction:
    """Action taken by the governor in response to a signal."""
    action_type: Literal["block", "warn", "log", "graduate", "pending_review"]
    target_sessions: list[str] | Literal["all"]
    message: str
    constraint_id: str | None = None

def decide(signal: GovernanceSignal, state: SharedState) -> GovernanceAction | None:
    """Apply decision matrix to a governance signal.

    Returns GovernanceAction for signals requiring response, None for log-only.
    """
```

**broadcaster.py -- Broadcast Delivery**

```python
def queue_broadcast(state: SharedState, action: GovernanceAction) -> dict:
    """Queue a governance action as a broadcast message.

    Converts GovernanceAction to BroadcastRequest and queues via SharedState.
    For 'block' actions: sets session blocked flag.
    Returns delivery report.
    """

def clear_block(state: SharedState, session_id: str) -> bool:
    """Clear a session's blocked flag. Returns True if session was blocked."""
```

---

### 3.2 Test Strategy

#### Wave 1 Tests (~25 tests)

**Categories:** Unit (models, decision logic), Protocol (JSON schema compliance)

**Test infrastructure:** `io.StringIO` for stdin/stdout capture; subprocess for full hook invocation tests.

**Scenarios:**

| # | Test | Category | Description |
|---|------|----------|-------------|
| 1 | `test_hook_input_valid_pretooluse` | Unit | Parse valid PreToolUse JSON into HookInput |
| 2 | `test_hook_input_valid_sessionstart` | Unit | Parse valid SessionStart JSON (no tool fields) |
| 3 | `test_hook_input_missing_required_field` | Unit | Raise ValidationError on missing session_id |
| 4 | `test_governance_decision_frozen` | Unit | Verify frozen immutability |
| 5 | `test_governance_signal_boundary_dependency` | Unit | Verify event_level vs episode_level classification |
| 6 | `test_build_search_text_bash` | Unit | Extract command field, truncate to 500 chars |
| 7 | `test_build_search_text_write` | Unit | Extract file_path + content[:500] |
| 8 | `test_build_search_text_edit` | Unit | Extract file_path + old_string[:500] + new_string[:500] |
| 9 | `test_build_search_text_read` | Unit | Extract file_path only |
| 10 | `test_build_search_text_unknown_tool` | Unit | Fall back to str(tool_input)[:500] |
| 11 | `test_governance_check_deny_forbidden` | Unit | PolicyViolationChecker returns (True, constraint) with severity=forbidden |
| 12 | `test_governance_check_warn` | Unit | Checker returns (False, constraint) with severity=warning |
| 13 | `test_governance_check_allow` | Unit | Checker returns (False, None) -> silent allow |
| 14 | `test_governance_check_parse_error_failopen` | Unit | Invalid stdin JSON -> exit 0, no stdout |
| 15 | `test_governance_check_missing_constraints_failopen` | Unit | Missing constraints.json -> exit 0, no stdout |
| 16 | `test_governance_check_subprocess_deny` | Protocol | Run hook as subprocess, verify deny JSON output format |
| 17 | `test_governance_check_subprocess_allow` | Protocol | Run hook as subprocess, verify empty stdout |
| 18 | `test_constraint_briefing_scope_filter` | Unit | Only constraints matching cwd are included |
| 19 | `test_constraint_briefing_axis_grouping` | Unit | Constraints grouped by ccd_axis |
| 20 | `test_constraint_briefing_critical_forbidden` | Unit | Forbidden severity -> CRITICAL section |
| 21 | `test_constraint_briefing_critical_low_durability` | Unit | Durability < 0.3 -> CRITICAL section |
| 22 | `test_constraint_briefing_ungrouped` | Unit | Null ccd_axis -> UNGROUPED section |
| 23 | `test_constraint_briefing_truncation` | Unit | Briefing exceeds 2000 chars -> truncated |
| 24 | `test_constraint_briefing_zero_constraints` | Unit | No matching constraints -> minimal briefing |
| 25 | `test_constraint_briefing_output_format` | Protocol | Verify hookSpecificOutput JSON schema compliance |

#### Wave 2 Tests (~30 tests)

**Categories:** Unit (adapter logic), Integration (file watching + adapter pipeline)

**Test infrastructure:** `tempfile.NamedTemporaryFile` for JSONL files; controlled append with `flush()` + `time.sleep()` for timing tests.

**Scenarios:**

| # | Test | Category | Description |
|---|------|----------|-------------|
| 1 | `test_adapt_user_message` | Unit | Raw user JSONL -> LiveEvent with event_type="user" |
| 2 | `test_adapt_assistant_text` | Unit | Assistant text-only -> LiveEvent with event_type="assistant" |
| 3 | `test_adapt_tool_use_bash` | Unit | Assistant tool_use Bash -> LiveEvent with tool_name, tool_input |
| 4 | `test_adapt_multi_tool_use` | Unit | Assistant with 3 tool_use blocks -> 3 LiveEvents |
| 5 | `test_adapt_system_event_skipped` | Unit | Progress/file-history events -> empty list |
| 6 | `test_tag_inference_git_commit` | Unit | Bash "git commit" -> T_GIT_COMMIT (priority 1) |
| 7 | `test_tag_inference_test` | Unit | Bash "pytest" -> T_TEST (priority 2) |
| 8 | `test_tag_inference_risky_bash` | Unit | Bash "rm -rf" -> T_RISKY (priority 3) |
| 9 | `test_tag_inference_risky_write` | Unit | Write tool -> T_RISKY (priority 4) |
| 10 | `test_tag_inference_user_approval` | Unit | "yes, go ahead" -> X_ASK (priority 5) |
| 11 | `test_tag_inference_slash_command` | Unit | "/gsd" -> O_DIR (priority 6) |
| 12 | `test_tag_inference_priority_order` | Unit | "git commit" matches both T_GIT_COMMIT and T_RISKY -> T_GIT_COMMIT |
| 13 | `test_escalation_adapter_block_then_bypass` | Unit | O_GATE event then T_RISKY -> EscalationCandidate |
| 14 | `test_escalation_adapter_reset_on_approval` | Unit | O_GATE then X_ASK -> window cleared, no candidate |
| 15 | `test_escalation_adapter_window_expiry` | Unit | O_GATE then N non-exempt events -> window expired |
| 16 | `test_escalation_adapter_exempt_tools` | Unit | Read/Glob/Grep events skip turn counting |
| 17 | `test_escalation_adapter_reset` | Unit | reset() clears all pending windows |
| 18 | `test_amnesia_adapter_buffers_candidate` | Unit | Tool_use matching constraint -> pending signal, not returned |
| 19 | `test_amnesia_adapter_flush_pending` | Unit | flush_pending() returns signals with episode_id attached |
| 20 | `test_amnesia_adapter_discard_pending` | Unit | discard_pending() clears buffer, returns count |
| 21 | `test_amnesia_adapter_skip_non_tool_use` | Unit | User/assistant events are ignored |
| 22 | `test_policy_check_adapter_violation` | Unit | Tool_use matching constraint -> GovernanceSignal returned immediately |
| 23 | `test_policy_check_adapter_no_match` | Unit | No constraint match -> None |
| 24 | `test_policy_check_adapter_warning` | Unit | Warning severity -> signal with severity="warning" |
| 25 | `test_processor_file_position_tracking` | Integration | Process 3 events, verify position advances |
| 26 | `test_processor_partial_line_handling` | Integration | Append half a line, then complete it -> 1 event processed |
| 27 | `test_processor_new_file_detection` | Integration | Create new JSONL file -> processor starts tracking |
| 28 | `test_processor_signal_emission_stdout` | Integration | Constraint violation -> signal on stdout |
| 29 | `test_processor_signal_deduplication` | Integration | Same event processed twice -> signal emitted once |
| 30 | `test_processor_start_stop_lifecycle` | Integration | Start, process events, stop cleanly |

#### Wave 3 Tests (~35 tests)

**Categories:** Unit (models, state), Integration (server routes via in-process httpx)

**Test infrastructure:** `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` for in-process server testing. No actual Unix socket needed for unit/integration tests.

**Scenarios:**

| # | Test | Category | Description |
|---|------|----------|-------------|
| 1-5 | `test_*_model_validation` | Unit | Validate all bus request/response Pydantic models |
| 6 | `test_state_add_session` | Unit | Add session, verify count increases |
| 7 | `test_state_remove_session` | Unit | Remove session, verify count decreases |
| 8 | `test_state_session_staleness` | Unit | Session with old last_seen marked stale |
| 9 | `test_state_auto_deregister_30min` | Unit | Session stale > 30 min auto-deregistered |
| 10 | `test_state_project_state_creation` | Unit | First session for project creates ProjectState with constraints |
| 11 | `test_state_constraint_reload_atomic` | Unit | Reload replaces cache; in-flight checks use old cache |
| 12 | `test_state_multi_project` | Unit | Two projects with independent constraint caches |
| 13 | `test_state_broadcast_queue` | Unit | Queue message, drain on check, verify delivery |
| 14 | `test_state_block_flag` | Unit | Block broadcast sets flag; all checks return deny |
| 15 | `test_state_event_ring_buffer` | Unit | Events beyond 1000 evict oldest |
| 16 | `test_route_health` | Integration | GET /api/health -> 200 with uptime, session_count |
| 17 | `test_route_check_deny` | Integration | POST /api/check with forbidden constraint -> deny response |
| 18 | `test_route_check_allow` | Integration | POST /api/check with no matching constraint -> allow |
| 19 | `test_route_check_missing_project` | Integration | POST /api/check for unknown project -> 404 |
| 20 | `test_route_get_constraints` | Integration | GET /api/constraints -> list of active constraints |
| 21 | `test_route_reload_constraints` | Integration | POST /api/constraints/reload -> updated count |
| 22 | `test_route_register_session` | Integration | POST /api/sessions/register -> ok=true |
| 23 | `test_route_register_duplicate` | Integration | Register same session twice -> 409 but idempotent |
| 24 | `test_route_deregister_session` | Integration | POST /api/sessions/deregister -> ok=true |
| 25 | `test_route_deregister_unknown` | Integration | Deregister unknown session -> still ok (idempotent) |
| 26 | `test_route_list_sessions` | Integration | GET /api/sessions -> session list |
| 27 | `test_route_list_sessions_filter` | Integration | GET /api/sessions?project_dir=X -> filtered list |
| 28 | `test_route_post_event` | Integration | POST /api/events -> received=true with event_id |
| 29 | `test_route_post_event_invalid` | Integration | POST /api/events with bad signal_type -> 400 |
| 30 | `test_route_broadcast_block` | Integration | POST /api/broadcast block -> delivered to target |
| 31 | `test_route_broadcast_all` | Integration | POST /api/broadcast with "all" -> delivered to all sessions |
| 32 | `test_route_broadcast_warn` | Integration | POST /api/broadcast warn -> queued, delivered on check |
| 33 | `test_client_is_available_true` | Integration | BusClient.is_available() when bus running |
| 34 | `test_client_is_available_false` | Integration | BusClient.is_available() when no bus |
| 35 | `test_client_check_fallback` | Integration | BusClient.check() fails -> returns None |

#### Wave 4 Tests (~20 tests)

**Categories:** Unit (decision matrix), Integration (daemon lifecycle)

**Test infrastructure:** Mock SharedState for decision testing; real async event loop for daemon tests.

**Scenarios:**

| # | Test | Category | Description |
|---|------|----------|-------------|
| 1 | `test_decide_constraint_violated_forbidden` | Unit | severity=forbidden -> block action |
| 2 | `test_decide_constraint_violated_warning` | Unit | severity=warning -> log-only |
| 3 | `test_decide_constraint_violated_requires_approval` | Unit | severity=requires_approval -> warn action |
| 4 | `test_decide_escalation_unapproved` | Unit | Unapproved escalation -> warn action |
| 5 | `test_decide_escalation_approved` | Unit | Approved escalation -> update count |
| 6 | `test_decide_amnesia` | Unit | Amnesia detected -> briefing update |
| 7 | `test_decide_constraint_graduated` | Unit | Graduation candidate -> pending_review |
| 8 | `test_decide_novel_pattern` | Unit | Unknown signal type -> pending_review |
| 9 | `test_decide_deduplication` | Unit | Same signal within 5 min -> suppressed |
| 10 | `test_decide_deduplication_window_expired` | Unit | Same signal after 5 min -> processed |
| 11 | `test_queue_broadcast_block` | Unit | Block action -> broadcast queued + blocked flag |
| 12 | `test_queue_broadcast_warn` | Unit | Warn action -> broadcast queued, no flag |
| 13 | `test_clear_block` | Unit | Clear block -> blocked=False |
| 14 | `test_drain_broadcasts` | Unit | Drain returns pending, clears queue |
| 15 | `test_drain_broadcasts_empty` | Unit | No pending -> empty list |
| 16 | `test_daemon_start_stop` | Integration | Start daemon, verify tasks created, stop cleanly |
| 17 | `test_daemon_event_consumption` | Integration | Add event to ring buffer, daemon processes it |
| 18 | `test_daemon_staleness_check` | Integration | Stale session detected and flagged |
| 19 | `test_daemon_block_on_forbidden` | Integration | Forbidden violation -> session blocked |
| 20 | `test_daemon_concurrent_requests` | Integration | Bus serves requests while daemon processes events |

#### Wave 5 Tests (~15 tests)

**Categories:** Integration (full system), Protocol (hook contract compliance)

**Test infrastructure:** Real Unix socket (temp path), real JSONL file, subprocess-launched hooks, and bus process. Use `pytest-asyncio` for async test support.

**Scenarios:**

| # | Test | Category | Description |
|---|------|----------|-------------|
| 1 | `test_hook_protocol_pretooluse_deny_schema` | Protocol | Deny output matches Claude Code JSON schema exactly |
| 2 | `test_hook_protocol_pretooluse_warn_schema` | Protocol | Warn output matches schema |
| 3 | `test_hook_protocol_pretooluse_allow_empty` | Protocol | Allow = no stdout, exit 0 |
| 4 | `test_hook_protocol_sessionstart_schema` | Protocol | SessionStart output matches schema |
| 5 | `test_hook_protocol_exit_codes` | Protocol | All paths exit 0 (never non-zero) |
| 6 | `test_integration_bus_start_stop` | Integration | CLI start, verify socket, CLI stop, verify cleanup |
| 7 | `test_integration_hook_with_bus` | Integration | Start bus, run PreToolUse hook, verify bus-mediated check |
| 8 | `test_integration_hook_without_bus` | Integration | No bus running, hook falls back to direct check |
| 9 | `test_integration_session_registration` | Integration | SessionStart hook registers with bus |
| 10 | `test_integration_constraint_enforcement` | Integration | Forbidden constraint -> deny on tool call |
| 11 | `test_integration_escalation_broadcast` | Integration | Escalation signal -> governor broadcasts warn |
| 12 | `test_integration_end_to_end` | Integration | Full lifecycle: bus start -> register -> check -> escalation -> broadcast -> delivery |
| 13 | `test_integration_multi_session` | Integration | Two sessions, one blocked, other continues normally |
| 14 | `test_integration_constraint_reload` | Integration | Add constraint, reload, verify enforcement |
| 15 | `test_integration_graceful_shutdown` | Integration | Bus shutdown completes in-flight requests |

**Total test estimate: ~125 new tests**

---

### 3.3 Phase 15 Requirements (LIVE-01 through LIVE-05)

Each requirement is restated with implementation-level acceptance criteria.

#### LIVE-01: PreToolUse Constraint Enforcement

**Requirement:** On every state-changing tool call, check the proposed action against active constraints and return allow, warn, or deny within 200ms.

**Implementation:** `src/pipeline/live/hooks/governance_check.py`

**Acceptance criteria:**
1. Hook reads JSON from stdin matching the PreToolUseHookInput schema.
2. Hook extracts searchable text per tool type (Bash: command, Write: file_path+content, Edit: file_path+old+new, Read: file_path, Glob/Grep: pattern+path, Other: str(input)).
3. Content fields truncated to 500 characters before check.
4. `PolicyViolationChecker.check(text)` results mapped to hook output: `(True, constraint)` -> deny JSON, `(False, constraint)` -> warn JSON, `(False, None)` -> no output.
5. All failure modes (parse error, missing file, import error, checker exception) result in exit code 0 with no stdout.
6. **Latency test:** `time echo '{"session_id":"t","cwd":"/tmp","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 src/pipeline/live/hooks/governance_check.py` completes in <200ms.

#### LIVE-02: SessionStart Constraint Briefing

**Requirement:** At session startup, inject a CCD-axis-grouped briefing of active constraints into Claude's context.

**Implementation:** `src/pipeline/live/hooks/constraint_briefing.py`

**Acceptance criteria:**
1. Hook reads JSON from stdin matching the SessionStartHookInput schema.
2. Constraints filtered by `scopes_overlap(constraint.scope.paths, [cwd])`.
3. Constraints grouped by `ccd_axis`: CRITICAL (forbidden or durability < 0.3), ACTIVE (remaining with axis), UNGROUPED (null axis).
4. Briefing format matches the section layout from 14-01-DESIGN.md (CRITICAL, ACTIVE, UNGROUPED sections).
5. Briefing truncated to 2000 characters if necessary (CRITICAL section never truncated).
6. Output JSON matches SessionStart hook schema: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`.
7. **Compression test:** 332 active constraints produce a briefing with ~12-15 axis groups, not 332 flat entries.

#### LIVE-03: Real-Time JSONL Stream Processing

**Requirement:** Detect governance events (escalation, amnesia, constraint violation) in real time as JSONL events are written.

**Implementation:** `src/pipeline/live/stream/processor.py` + `adapters.py` + `incremental.py`

**Acceptance criteria:**
1. StreamProcessor discovers session JSONL directory from `project_dir`.
2. watchdog Observer detects new and modified JSONL files.
3. Position tracking: processor reads only new content from each file.
4. Partial line handling: incomplete JSON lines buffered until complete.
5. LiveEventAdapter converts raw JSONL events to LiveEvent objects with correct inferred tags.
6. IncrementalEscalationAdapter detects block-then-bypass sequences.
7. IncrementalPolicyCheckAdapter emits event_level GovernanceSignal on constraint match.
8. IncrementalAmnesiaAdapter buffers episode_level signals until CONFIRMED_END.
9. **Latency test:** Append event to JSONL file, assert GovernanceSignal emitted within 200ms.

#### LIVE-04: Inter-Session Coordination Bus

**Requirement:** Provide shared constraint state, session registry, and event distribution across parallel sessions via a local HTTP service.

**Implementation:** `src/pipeline/live/bus/server.py` + `state.py` + `models.py` + `client.py`

**Acceptance criteria:**
1. Bus starts on Unix domain socket at `/tmp/ope-governance-bus.sock`.
2. All 10 API routes respond correctly (see Section 3.1 Wave 3 for signatures).
3. Constraint cache: loaded once per project on first session registration, served from memory on `/api/check`.
4. Session registry: register/deregister/list with staleness detection (5 min mark stale, 30 min auto-deregister).
5. `POST /api/check` latency: <5ms (in-memory regex check).
6. Stale socket detection: orphaned socket from crashed process is cleaned up on startup.
7. PID file management: written on start, checked on re-start, removed on stop.
8. **Multi-project test:** Two projects with independent constraint caches both operational.

#### LIVE-05: Governor Daemon

**Requirement:** Autonomous governance monitoring with decision matrix and broadcast protocol.

**Implementation:** `src/pipeline/live/governor/daemon.py` + `decisions.py` + `broadcaster.py`

**Acceptance criteria:**
1. GovernorDaemon runs as async tasks co-located in the bus process.
2. Decision matrix handles all signal types from 14-02-DESIGN.md table (constraint_violated, escalation_detected, amnesia_detected, etc.).
3. `constraint_violated` (severity=forbidden) -> broadcast `block` to source session.
4. `escalation_detected` (unapproved) -> broadcast `warn` to source session.
5. Signal deduplication: same (signal_type, constraint_id) within 5 min -> suppressed.
6. Block flag: once set on a session, all `/api/check` calls return deny until cleared.
7. **Integration test:** Emit escalation signal -> verify governor broadcasts warning to registered session.

---

### 3.4 Phase 15 Success Criteria

Phase 15 is complete when all of the following are true:

1. **All 5 requirements** (LIVE-01 through LIVE-05) have passing acceptance tests.
2. **~125 new tests** passing with zero regressions on the existing test suite.
3. **CLI operational:** `python -m src.pipeline.cli govern bus start` starts the governance bus; `bus stop` shuts it down; `bus status` reports health.
4. **Hook registration:** `.claude/settings.json` contains PreToolUse and SessionStart hook configurations matching the format in 14-01-DESIGN.md Appendix A.
5. **Standalone mode:** Single-session governance (LIVE-01 + LIVE-02) works without the bus running.
6. **Coordinated mode:** Multi-session governance (LIVE-04 + LIVE-05) works with the bus running.
7. **End-to-end proof:** Start bus -> register session -> check constraint -> detect escalation -> broadcast warning -> verify warning delivered on next check.
8. **Latency compliance:** PreToolUse hook <200ms, SessionStart <500ms, bus /api/check <5ms, stream processor event-to-signal <200ms.
9. **Fail-open verified:** All hook failure paths tested and confirmed to exit 0 with no stdout.

---

### 3.5 Risks and Mitigations

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | Python startup time exceeds 200ms budget for PreToolUse hook | Hook slows every tool call | Medium | Measure in Plan 15-01 (first task). If too slow: minimize imports (lazy load ConstraintStore), or implement bus-first path so most calls go through fast httpx instead of fresh Python init |
| 2 | watchdog FSEvents behavior differs on macOS (coalescing, delays) | Stream processor misses or delays events | Low | Integration test in Plan 15-04 with real file appends on macOS. Fallback: polling-based watcher (watchdog.observers.polling.PollingObserver) |
| 3 | httpx Unix socket API differs from documented behavior | BusClient cannot connect to bus | Low | Verify `httpx.HTTPTransport(uds=...)` API in Plan 15-06 first test. Adapt if needed (e.g., use urllib3 Unix socket adapter) |
| 4 | Starlette SSE (Server-Sent Events) implementation is complex | `/api/events/stream` endpoint delays Wave 3 | Medium | Start with polling-based event consumption (client polls `/api/events/recent`). Upgrade to true SSE in Wave 5 if needed |
| 5 | Governor async tasks conflict with bus request handling | Bus becomes unresponsive during governor processing | Low | Use `asyncio.create_task()` with proper cancellation. Test concurrent request + governor processing in Wave 4 |
| 6 | Constraint classification by CCD axis not yet done | SessionStart briefing shows mostly UNGROUPED constraints | Medium | This is expected -- axis classification is a future task. Briefing degrades gracefully: UNGROUPED section lists constraints individually |
| 7 | DuckDB concurrent access from bus + stream processor | Write conflicts on governance_signals table | Low | Bus process owns all DuckDB writes (single writer). Stream processor writes via bus API (POST /api/events), not directly. |

---

### 3.6 Phase 15 Plan Mapping

Mapping waves to GSD plans for `/gsd:plan-phase` Phase 15 input.

| Plan | Wave | Name | Tasks | Est. Duration | Key Outputs |
|------|------|------|-------|---------------|-------------|
| 15-01 | 1a | Hook models + governance_check.py | 2 | ~30 min | `hooks/models.py`, `hooks/governance_check.py`, `test_models.py`, `test_governance_check.py` |
| 15-02 | 1b | constraint_briefing.py + hook protocol | 2 | ~30 min | `hooks/constraint_briefing.py`, `test_constraint_briefing.py` |
| 15-03 | 2a | LiveEventAdapter + incremental adapters | 2 | ~40 min | `stream/adapters.py`, `stream/incremental.py`, `test_adapters.py`, `test_incremental.py` |
| 15-04 | 2b | StreamProcessor with watchdog | 2 | ~40 min | `stream/processor.py`, `test_processor.py` |
| 15-05 | 3a | Bus models + SharedState + server | 3 | ~45 min | `bus/models.py`, `bus/state.py`, `bus/server.py`, `test_models.py`, `test_state.py`, `test_server.py` |
| 15-06 | 3b | BusClient + bus integration | 2 | ~30 min | `bus/client.py`, `test_client.py` |
| 15-07 | 4 | Governor daemon + decisions + broadcaster | 3 | ~45 min | `governor/daemon.py`, `governor/decisions.py`, `governor/broadcaster.py`, `test_daemon.py`, `test_decisions.py`, `test_broadcaster.py` |
| 15-08 | 5a | CLI commands + hook registration | 2 | ~30 min | `cli/govern.py` (modified), `.claude/settings.json` (modified) |
| 15-09 | 5b | End-to-end integration tests | 2 | ~30 min | `test_integration.py`, `test_hook_protocol.py` |

**Total:** 9 plans, 20 tasks, ~5.5 hours estimated execution time.

**Sequencing constraints:**
- 15-01 must complete before all others (provides shared models)
- 15-02 depends on 15-01 (uses HookInput, GovernanceDecision)
- 15-03 depends on 15-01 (uses LiveEvent, GovernanceSignal models)
- 15-04 depends on 15-03 (uses LiveEventAdapter, incremental adapters)
- 15-05 depends on 15-01 (uses GovernanceDecision, GovernanceSignal)
- 15-06 depends on 15-05 (tests against running server)
- 15-07 depends on 15-05 (uses SharedState)
- 15-08 depends on 15-05 + 15-06 (wires CLI to bus)
- 15-09 depends on all previous (end-to-end)

---

## 4. Cross-References

### 4.1 Design Document Mapping

| Blueprint Section | 14-01-DESIGN.md Section | 14-02-DESIGN.md Section |
|-------------------|------------------------|------------------------|
| Wave 1 (hooks) | 1.1 PreToolUse, 1.2 SessionStart, 1.3 Models, 1.4 CCD Decision | -- |
| Wave 2 (stream) | 2.1-2.7 Stream Processor | -- |
| Wave 3 (bus) | -- | 1.1-1.5 Bus Architecture, API Routes, State Model |
| Wave 4 (governor) | -- | 2.1-2.7 Governor, Decision Matrix, Broadcast Protocol |
| Wave 5 (integration) | Appendix A (hook config) | 1.4 Session Discovery Protocol |

### 4.2 Existing Code Dependencies

| Existing Component | Path | Used By | Interface |
|-------------------|------|---------|-----------|
| PolicyViolationChecker | `src/pipeline/feedback/checker.py` | Wave 1 (hooks), Wave 2 (adapters), Wave 3 (bus) | `__init__(store)`, `check(text) -> (bool, dict\|None)` |
| ConstraintStore | `src/pipeline/constraint_store.py` | Wave 1 (hooks), Wave 3 (bus) | `__init__(path, schema_path)`, `get_active_constraints() -> list[dict]` |
| scopes_overlap | `src/pipeline/utils.py` | Wave 1 (briefing) | `scopes_overlap(paths_a, paths_b) -> bool` |
| EscalationDetector | `src/pipeline/escalation/detector.py` | Wave 2 (adapter replicates algorithm) | Algorithm reference only; not called directly |
| PipelineConfig | `src/pipeline/models/config.py` | Wave 2 (escalation settings) | `load_config(path) -> PipelineConfig` |
| govern_group | `src/pipeline/cli/govern.py` | Wave 5 (add bus subcommands) | Click group with `ingest` and `check-stability` commands |

### 4.3 MEMORY.md CCD Axis Alignment

| CCD Axis | Blueprint Component | Implementation |
|----------|-------------------|----------------|
| `deposit-not-detect` | Not in scope (Phase 15 Waves 1-5 are LIVE-01 through LIVE-05; DDF co-pilot is LIVE-06, Phase 15 Wave 6+) | Deferred to Phase 15 Wave 6+ or Phase 16 |
| `temporal-closure-dependency` | Wave 2 episode boundary state machine | TENTATIVE_END / CONFIRMED_END in stream processor |
| `identity-firewall` | Wave 1 PolicyViolationChecker generates; Wave 4 Governor validates | Generator (hook check) structurally separate from validator (governor decision) |
| `ground-truth-pointer` | Wave 2 LiveEvent carries transcript_path reference | Each signal traces back to source JSONL line |

### 4.4 Scope Boundary

**In scope for Phase 15 (this blueprint):**
- LIVE-01: PreToolUse hook
- LIVE-02: SessionStart hook
- LIVE-03: JSONL stream processor
- LIVE-04: Inter-session bus
- LIVE-05: Governor daemon

**Out of scope (deferred to Phase 15 Wave 6+ or Phase 16):**
- LIVE-06: DDF co-pilot (all 3 intervention types)
- AI-side DDF detection (ai_flame_events)
- Fringe Drift metrics (copilot_interventions table)
- Policy Automatization Detector (graduation tracking)
- memory_candidates schema extensions (session_id, subject, origin, confidence, perception_pointer)
- Governor monitoring dashboard (/api/dashboard)

These are designed in 14-02-DESIGN.md but deferred because they depend on LIVE-01 through LIVE-05 being operational. The blueprint focuses on the core governance infrastructure that the DDF co-pilot and assessment layers will build on.
