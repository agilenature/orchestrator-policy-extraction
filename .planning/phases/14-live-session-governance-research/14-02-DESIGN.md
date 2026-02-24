# Phase 14 Plan 02: Multi-Session Coordination Layer Design

**Phase:** 14-live-session-governance-research
**Plan:** 02
**Components:** LIVE-04 (Inter-Session Coordination Bus), LIVE-05 (Governing Session Pattern), LIVE-06 (DDF Co-Pilot Architecture)
**Depends on:** 14-01-PLAN.md (GovernanceSignal model, HookInput, GovernanceDecision, hook contracts)
**Created:** 2026-02-24

---

## 1. Inter-Session Coordination Bus (LIVE-04)

### 1.1 Bus Architecture Overview

**Purpose:** A lightweight local HTTP service that provides shared constraint state, session registry, and governance event distribution across parallel Claude Code sessions. When multiple sessions run against the same project, the bus eliminates redundant constraint file loading, enables cross-session signal aggregation, and provides the transport layer for governing session decisions.

**Transport:** Unix domain socket at `/tmp/ope-governance-bus.sock`.

Rationale:
- No port conflicts with other local services (TCP localhost would require port selection/collision handling)
- Sub-millisecond IPC latency (~0.1ms round-trip on macOS), well within the 200ms PreToolUse budget
- Automatic cleanup on process exit (kernel removes socket on process termination for clean shutdowns)
- Not accessible from network (security: local-only by design)

**Server stack:** uvicorn 0.40.0 ASGI server + starlette 0.52.1 framework.

Rationale:
- Both already installed in the project environment (zero new dependencies for the bus itself)
- Production-quality async framework with native Unix socket support via uvicorn's `--uds` flag
- Starlette provides routing, request parsing, JSON responses, SSE support, and middleware -- no hand-rolling HTTP protocol
- Single event loop (async) eliminates thread safety concerns for shared in-memory state

**Client stack:** httpx 0.28.1.

- Synchronous: `httpx.Client(transport=httpx.HTTPTransport(uds="/tmp/ope-governance-bus.sock"), base_url="http://localhost")` for hook scripts (PreToolUse, SessionStart)
- Asynchronous: `httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds="/tmp/ope-governance-bus.sock"), base_url="http://localhost")` for stream processor and governor internals

**Startup:**

```python
# src/pipeline/live/bus/server.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.pipeline.live.bus.server:app",
        uds="/tmp/ope-governance-bus.sock",
        log_level="info",
        access_log=False,  # Suppress per-request logs for hook calls (too noisy)
    )
```

Or via CLI: `python -m src.pipeline.cli govern bus start` (wraps the above with PID file management, stale socket detection, and daemonization).

**Shutdown:** Graceful shutdown on SIGINT/SIGTERM. The shutdown handler must:
1. Stop accepting new connections
2. Complete in-flight requests (uvicorn handles this via `shutdown_timeout`)
3. Deregister all sessions from in-memory registry
4. Remove socket file at `/tmp/ope-governance-bus.sock`
5. Remove PID file at `/tmp/ope-governance-bus.pid`

**Stale socket detection:** On startup, if the socket file already exists:
1. Attempt to connect to it with a 100ms timeout
2. If connection succeeds -- another bus is already running. Log error and exit (do not start a second bus)
3. If connection refused or timeout -- stale socket from a crashed process. Unlink the file and proceed with normal startup

### 1.2 Bus API Routes

All routes use JSON request/response bodies. Content-Type is `application/json` for all non-SSE routes. Routes are prefixed with `/api/` for namespacing.

#### a) `GET /api/health`

Health check endpoint. No request body.

**Response (200):**
```json
{
  "status": "ok",
  "uptime_seconds": 3612.5,
  "session_count": 3,
  "constraint_count": 208,
  "projects": ["orchestrator-policy-extraction", "modernizing-tool"]
}
```

**Error responses:** None. This endpoint always returns 200 if the bus is running.

**Behavior:** Returns current bus state summary. Used by `govern bus status` CLI command and by hooks to verify bus availability.

---

#### b) `POST /api/check`

Constraint check called by PreToolUse hook scripts. This is the bus-optimized version of what the hook does directly (load ConstraintStore + PolicyViolationChecker) when the bus is unavailable.

**Request body:**
```json
{
  "tool_name": "Bash",
  "tool_input": {"command": "rm -rf /tmp/build"},
  "session_id": "abc123",
  "project_dir": "/Users/david/projects/orchestrator-policy-extraction"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool_name` | string | Yes | Tool being invoked (Bash, Write, Edit, Read, Glob, Grep) |
| `tool_input` | object | Yes | Tool-specific input parameters |
| `session_id` | string | Yes | Calling session's ID |
| `project_dir` | string | Yes | Project directory for constraint scoping |

**Response (200):**
```json
{
  "decision": "deny",
  "constraint_id": "bbd376a2",
  "reason": "GOVERNANCE: Blocked by constraint bbd376a2: Do not modify schema without explicit approval",
  "severity": "forbidden",
  "ccd_axis": "destructive_irreversible_operations",
  "pending_broadcasts": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `"allow" \| "warn" \| "deny"` | Governance decision |
| `constraint_id` | string or null | ID of the matched constraint (null if no match) |
| `reason` | string or null | Human-readable reason for the decision |
| `severity` | string or null | Constraint severity level |
| `ccd_axis` | string or null | CCD axis of the matched constraint (for briefing context) |
| `pending_broadcasts` | array | Any pending broadcast messages for this session (piggy-backed on check response) |

**Error responses:**
- 400: Missing required fields
- 404: Project not registered (no constraint store loaded for this project_dir)

**Behavior:**
1. Look up the ProjectState for `project_dir`
2. Build searchable text from `tool_name` + `tool_input` (same extraction logic as PreToolUse hook: Bash -> command, Write/Edit -> file_path + content[:500])
3. Run `ProjectState.checker.check(text)` against the in-memory pre-compiled constraint patterns
4. Map the checker result to a GovernanceDecision: `(True, constraint)` -> deny, `(False, constraint)` -> warn, `(False, None)` -> allow
5. Update `session.last_seen` timestamp (implicit heartbeat)
6. Include any pending broadcast messages for this session in the response (drains the broadcast queue)

**Latency target:** <5ms (in-memory regex check, no disk I/O).

---

#### c) `GET /api/constraints`

Get active constraints for a project.

**Query parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_dir` | string | Yes | Project directory to scope constraints |
| `scope` | string | No | Optional path prefix filter within the project |

**Response (200):**
```json
{
  "constraints": [
    {
      "constraint_id": "bbd376a2",
      "text": "Do not modify schema without explicit approval",
      "severity": "forbidden",
      "ccd_axis": "destructive_irreversible_operations",
      "epistemological_origin": "reactive",
      "detection_hints": ["schema", "migration"],
      "status": "active"
    }
  ],
  "count": 208,
  "cached_at": "2026-02-24T01:15:04Z"
}
```

**Error responses:**
- 404: Project not registered

**Behavior:** Returns constraints from the in-memory cache for the specified project. Does NOT read from disk. The `scope` parameter applies additional path prefix filtering if provided.

---

#### d) `POST /api/constraints/reload`

Force constraint reload from disk for a specific project.

**Request body:**
```json
{
  "project_dir": "/Users/david/projects/orchestrator-policy-extraction"
}
```

**Response (200):**
```json
{
  "reloaded": 210,
  "previous_count": 208
}
```

**Error responses:**
- 404: Project not registered
- 500: Failed to load constraints file (parse error, missing file)

**Behavior:**
1. Re-read `{project_dir}/data/constraints.json`
2. Create a new `ConstraintStore` instance
3. Rebuild `PolicyViolationChecker` with the new constraint patterns
4. Replace the in-memory cache atomically (swap reference, not mutate in place)
5. Log the reload event with old and new constraint counts

Used after `govern ingest` adds new constraints to ensure enforcement picks up changes immediately.

---

#### e) `POST /api/sessions/register`

Register a Claude Code session with the bus.

**Request body:**
```json
{
  "session_id": "abc123",
  "project_dir": "/Users/david/projects/orchestrator-policy-extraction",
  "transcript_path": "/Users/david/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/session.jsonl",
  "started_at": "2026-02-24T01:15:04Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Claude Code session ID |
| `project_dir` | string | Yes | Project working directory |
| `transcript_path` | string | Yes | Path to the session's JSONL file |
| `started_at` | string (ISO 8601) | Yes | Session start timestamp |

**Response (200):**
```json
{
  "ok": true,
  "session_count": 3
}
```

**Error responses:**
- 400: Missing required fields
- 409: Session already registered (idempotent -- returns success with current count)

**Behavior:**
1. If `project_dir` not yet known, create a new ProjectState: load `{project_dir}/data/constraints.json`, initialize ConstraintStore + PolicyViolationChecker, add to `projects` dict
2. Add session to the project's session registry
3. Set `session.last_seen = now()`
4. If the stream processor is running, notify it to watch the new `transcript_path`

---

#### f) `POST /api/sessions/deregister`

Deregister a session from the bus.

**Request body:**
```json
{
  "session_id": "abc123"
}
```

**Response (200):**
```json
{
  "ok": true,
  "session_count": 2
}
```

**Error responses:**
- 404: Session not found (idempotent -- returns success)

**Behavior:**
1. Remove session from the project's session registry
2. Clear any pending broadcast messages for this session
3. If this was the last session for a project, keep the ProjectState loaded (constraints remain cached for quick re-registration)
4. Log the deregistration event

---

#### g) `GET /api/sessions`

List all active sessions across all projects.

**Query parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_dir` | string | No | Filter to sessions for this project only |

**Response (200):**
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "project_dir": "/Users/david/projects/orchestrator-policy-extraction",
      "registered_at": "2026-02-24T01:15:04Z",
      "last_heartbeat": "2026-02-24T01:20:30Z",
      "stale": false
    }
  ],
  "count": 3
}
```

**Error responses:** None.

**Behavior:** Returns all registered sessions. A session is marked `stale: true` if `last_heartbeat` is older than 5 minutes.

---

#### h) `POST /api/events`

Submit a governance event from the stream processor, detectors, or co-pilot.

**Request body:** GovernanceSignal model (as defined in 14-01-PLAN.md section 1.3):
```json
{
  "signal_type": "escalation_detected",
  "session_id": "abc123",
  "timestamp": "2026-02-24T01:18:22Z",
  "details": {
    "tool_name": "Bash",
    "command": "rm -rf /tmp/build",
    "constraint_id": null,
    "candidate_text": "Unapproved destructive command"
  },
  "boundary_dependency": "event_level"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `signal_type` | string | Yes | One of: `escalation_detected`, `amnesia_detected`, `constraint_violated`, `constraint_graduated`, `ddf_intervention`, `fringe_drift` |
| `session_id` | string | Yes | Source session ID |
| `timestamp` | string (ISO 8601) | Yes | Event timestamp |
| `details` | object | Yes | Signal-specific details |
| `boundary_dependency` | `"event_level" \| "episode_level"` | Yes | Dispatch timing classification |

**Response (200):**
```json
{
  "received": true,
  "event_id": "evt_20260224T011822_abc123_001"
}
```

**Error responses:**
- 400: Invalid signal_type or missing required fields

**Behavior:**
1. Assign a unique event_id (timestamp + session_id + sequence number)
2. Append to the events ring buffer (in-memory, max 1000 entries)
3. Notify SSE subscribers (push to all connected /api/events/stream clients)
4. Forward to the governor's decision engine (section 2) for autonomous response
5. Persist to DuckDB `governance_signals` table (async, non-blocking)

---

#### i) `GET /api/events/stream`

Server-Sent Events (SSE) stream of governance events. Used by the governing session (section 2) and monitoring tools to watch events in real time.

**Query parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_dir` | string | No | Filter to events for this project only |
| `signal_types` | string | No | Comma-separated list of signal types to filter |

**Response:** `text/event-stream` (SSE)

```
event: governance_signal
data: {"signal_type": "escalation_detected", "session_id": "abc123", "timestamp": "2026-02-24T01:18:22Z", "details": {...}, "event_id": "evt_001"}

event: governance_signal
data: {"signal_type": "constraint_violated", "session_id": "def456", ...}

event: heartbeat
data: {"timestamp": "2026-02-24T01:19:00Z"}
```

**Behavior:**
1. On connection, send a heartbeat event immediately (confirms stream is active)
2. Send heartbeat events every 30 seconds (keeps connection alive, detects stale clients)
3. On each new GovernanceSignal received by the bus, push to all connected SSE clients (filtered by `project_dir` and `signal_types` if specified)
4. Client disconnect is detected by broken pipe; clean up subscriber registration

---

#### j) `POST /api/broadcast`

Broadcast a governance message to one or more active sessions. Used by the governor to block, warn, or brief sessions.

**Request body:**
```json
{
  "message_type": "block",
  "target_sessions": ["abc123"],
  "content": "GOVERNANCE BLOCK: Constraint bbd376a2 violated. Stop modifying schema files until reviewed.",
  "source": "governor",
  "constraint_id": "bbd376a2"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message_type` | `"block" \| "warn" \| "briefing"` | Yes | Message category |
| `target_sessions` | array of strings or `"all"` | Yes | Target session IDs |
| `content` | string | Yes | Message content |
| `source` | string | No | Message source identifier |
| `constraint_id` | string | No | Related constraint ID |

**Response (200):**
```json
{
  "delivered_to": ["abc123"],
  "failed": [],
  "queued": 1
}
```

**Error responses:**
- 400: Invalid message_type or missing fields

**Behavior:**
1. Resolve target sessions: if `"all"`, expand to all registered session IDs
2. For each target session:
   - Append the broadcast message to `broadcasts[session_id]` queue
   - For `"block"` type: also set a `blocked` flag on the session record that the `/api/check` endpoint reads
3. Messages are delivered on the target session's next `/api/check` call (piggy-backed on the check response). This is pull-based delivery -- the bus does not push to hooks directly.
4. For `"block"` messages: the next `/api/check` call from the blocked session will return `deny` regardless of the tool being checked, with the broadcast content as the reason. The block persists until explicitly cleared via a subsequent broadcast with `message_type: "warn"` or manual intervention.
5. For `"warn"` and `"briefing"` messages: delivered as `pending_broadcasts` in the next `/api/check` response. The hook script includes them in `additionalContext`.

### 1.3 Shared State Model

The bus maintains all state in-memory. The async event loop (single-threaded) eliminates the need for locks or mutexes.

**In-memory state structure:**

```python
@dataclass
class SessionRecord:
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
    project_dir: str
    constraint_store: ConstraintStore
    checker: PolicyViolationChecker
    sessions: dict[str, SessionRecord]       # session_id -> SessionRecord
    constraints_loaded_at: datetime
    constraint_count: int

@dataclass
class BroadcastMessage:
    message_type: str                        # "block" | "warn" | "briefing"
    content: str
    source: str | None
    constraint_id: str | None
    created_at: datetime

class BusState:
    projects: dict[str, ProjectState]         # project_dir -> ProjectState
    events: deque[GovernanceSignal]            # ring buffer, maxlen=1000
    broadcasts: dict[str, list[BroadcastMessage]]  # session_id -> pending messages
    sse_subscribers: list[asyncio.Queue]       # SSE client queues
    started_at: datetime

    # Governor state (section 2) -- co-located in same process
    governor: GovernorState | None
```

**Design assumptions:**
- Starlette is async (single event loop). All route handlers are `async def`. Shared state access is safe without locks because no two handlers execute concurrently within the same event loop iteration.
- State mutations are atomic at the Python object level (dict assignment, list append). No multi-step transactions are needed.
- If a future need arises for thread-safe access (e.g., background tasks on a thread pool), the solution is `asyncio.Lock`, not threading.Lock.

**Constraint cache invalidation:**

Two mechanisms, both supported:

1. **File watcher (automatic):** Use `watchdog` to monitor `{project_dir}/data/constraints.json` for each registered project. On file modification, auto-reload the ConstraintStore and rebuild the PolicyViolationChecker. This handles the case where `govern ingest` writes new constraints.

2. **Manual reload (explicit):** `POST /api/constraints/reload` triggers an immediate reload. This is the reliable path -- watchdog may coalesce events or miss rapid writes.

The reload process is atomic: create a new ConstraintStore and PolicyViolationChecker, then swap the references in ProjectState. In-flight `/api/check` calls that started before the swap continue with the old checker (safe -- the old objects remain valid until garbage collected).

**Session staleness detection:**

- A session's `last_seen` timestamp is updated on every `/api/check` call (implicit heartbeat from PreToolUse hook).
- A background async task runs every 60 seconds:
  - Sessions with `last_seen` older than 5 minutes are marked `stale=True`
  - Sessions with `last_seen` older than 30 minutes are auto-deregistered (removed from registry)
  - Stale session cleanup is logged for audit

### 1.4 Session Discovery Protocol

**How hooks find the bus:**

Hook scripts (PreToolUse, SessionStart) use the following discovery protocol:

1. Check if `/tmp/ope-governance-bus.sock` exists on the filesystem
2. If it does not exist: bus is not running. Fall back to **standalone mode** (direct file-based constraint loading)
3. If it exists: attempt an HTTP connection with a 100ms timeout
4. If connection succeeds: bus is available. Use the bus for all constraint operations
5. If connection refused or times out: stale socket from a crashed bus. Fall back to standalone mode. Log a warning to stderr.

**Standalone mode fallback:**

When the bus is unavailable, each hook invocation is self-contained:
- PreToolUse: loads `ConstraintStore(path=Path("data/constraints.json"))`, creates `PolicyViolationChecker(store)`, runs `checker.check(text)` inline. Total latency: ~70-110ms (within budget).
- SessionStart: loads ConstraintStore, generates briefing from the constraint list directly. No durability scores available without bus (those require DuckDB access which is too slow for inline loading).

The bus is an optimization layer, not a requirement. Single-session governance (LIVE-01, LIVE-02) works without the bus. Multi-session coordination (LIVE-04, LIVE-05) requires the bus.

**Session registration lifecycle:**

| Event | Hook | Bus Action | Fallback (no bus) |
|-------|------|------------|-------------------|
| Session starts | SessionStart | `POST /api/sessions/register` | Skip registration |
| Tool call | PreToolUse | `POST /api/check` (implicit heartbeat) | Direct constraint check |
| Session ends | SessionEnd | `POST /api/sessions/deregister` | Skip (staleness handles cleanup) |
| Session crashes | (none) | Detected by staleness timer (5 min mark stale, 30 min deregister) | No cleanup needed |

**Heartbeat mechanism:**

The PreToolUse hook's `/api/check` call doubles as a heartbeat. Every tool call (which in Claude Code happens frequently -- multiple per minute during active work) updates the session's `last_seen` timestamp. No explicit heartbeat endpoint or keepalive mechanism is needed.

### 1.5 Bus Startup and Lifecycle

**CLI integration:**

| Command | Action |
|---------|--------|
| `python -m src.pipeline.cli govern bus start` | Start bus daemon. Write PID to `/tmp/ope-governance-bus.pid`. Detach from terminal (daemonize) |
| `python -m src.pipeline.cli govern bus stop` | Read PID from file, send SIGTERM, wait for graceful shutdown (5s timeout), then SIGKILL if needed |
| `python -m src.pipeline.cli govern bus status` | HTTP GET to `/api/health` via Unix socket. Print status summary or "Bus not running" |
| `python -m src.pipeline.cli govern bus restart` | Stop then start |

**PID file management:**

- PID file location: `/tmp/ope-governance-bus.pid`
- Written immediately after successful startup (socket bound, server listening)
- Contains only the numeric PID as text
- Removed during graceful shutdown (step 5 of shutdown sequence)
- On startup, if PID file exists: check if the PID is still running (`os.kill(pid, 0)`). If running, refuse to start (another bus instance is active). If not running, remove stale PID file and proceed.

**Logging:**

- All bus logs go to stderr (never stdout -- the bus is a server, not a hook)
- Log format: `[TIMESTAMP] [LEVEL] [COMPONENT] message` using loguru
- Log levels: INFO for session register/deregister and constraint reloads; WARNING for stale socket detection and session staleness; ERROR for constraint load failures; DEBUG for individual `/api/check` calls (disabled by default for performance)
- Optional log file: `--log-file /tmp/ope-governance-bus.log` CLI flag for persistent logging

**Graceful shutdown sequence:**

1. SIGINT or SIGTERM received
2. Set shutdown flag -- stop accepting new connections
3. Wait for in-flight requests to complete (uvicorn's `shutdown_timeout`, default 10s)
4. Cancel background tasks (staleness checker, file watchers)
5. Deregister all sessions from in-memory registry (cleanup)
6. Remove socket file: `os.unlink("/tmp/ope-governance-bus.sock")`
7. Remove PID file: `os.unlink("/tmp/ope-governance-bus.pid")`
8. Flush any pending DuckDB writes
9. Exit with code 0

---

## 2. Governing Session Pattern (LIVE-05)

### 2.1 Governing Session Architecture

**Key architectural decision:** The governor is a **Python daemon process**, NOT a Claude Code session.

Rationale:
- Claude Code sessions have limited context windows and terminate when idle or when context fills. A governor must run indefinitely.
- Claude Code sessions consume LLM tokens on every interaction. Routine monitoring (constraint checking, signal aggregation, staleness detection) requires zero LLM reasoning -- it is purely algorithmic.
- A Python daemon can run for weeks, consuming only CPU/memory for event processing, and optionally invoke Claude Code on-demand for decisions requiring LLM reasoning.
- The daemon shares in-memory state with the bus directly (no IPC overhead) because it runs in the same process.

**Co-location with the bus:**

The governor is NOT a separate process. It is an additional set of async tasks running in the same Python process as the bus server. This design means:
- The governor has direct read/write access to `BusState` (no HTTP calls to itself)
- The governor subscribes to the event ring buffer directly (no SSE overhead for internal consumption)
- A single `govern bus start` command starts both the HTTP bus and the governor logic
- The governor's decision engine is an async background task that processes events from the ring buffer

**On-demand Claude Code session (Phase 15 Wave 4+ -- advanced, not Wave 1):**

When the daemon detects a situation requiring human-like judgment (e.g., a novel constraint violation pattern that matches no existing CCD axis, or a complex escalation that requires reading code context), it can optionally spawn a Claude Code session with a specific prompt:

```bash
claude --print --prompt "Review this governance event and recommend action: {event_json}" 2>/dev/null
```

This is an advanced feature. Wave 1 implementation handles all governor decisions algorithmically. The on-demand LLM path is designed here but deferred to Wave 4+.

### 2.2 Governor Responsibilities

The governor performs five core functions:

**1. Event Stream Monitoring**

The governor consumes events from the bus's in-memory ring buffer. It processes each GovernanceSignal and applies the decision matrix (below).

**2. Authoritative Constraint Store**

The governor's in-memory ConstraintStore is the single source of truth for all sessions. When hook scripts call `/api/check`, they get constraints from the governor's cache. Direct file reads by standalone hooks are a fallback path only.

**3. Signal Aggregation and Deduplication**

Multiple sessions may generate similar signals (e.g., two sessions both detect the same escalation pattern). The governor deduplicates:
- Dedup key: `(signal_type, constraint_id, time_window)`
- Time window: 5 minutes
- Within the dedup window, only the first signal is processed; subsequent duplicates are logged but suppressed
- Signals with no `constraint_id` (e.g., novel patterns) are deduped by content hash of `details`

**4. Decision Matrix**

For each signal type, the governor takes autonomous action:

| Signal Type | Condition | Autonomous Action | Requires LLM? | DuckDB Write |
|-------------|-----------|-------------------|----------------|--------------|
| `constraint_violated` | severity=forbidden | Broadcast `block` to source session | No | governance_decisions |
| `constraint_violated` | severity=warning | Log + add to next session briefing | No | governance_signals |
| `constraint_violated` | severity=requires_approval | Broadcast `warn` + flag for human review | No | governance_decisions |
| `escalation_detected` | unapproved (no matching constraint allows it) | Broadcast `warn` to source session + log | No | governance_decisions |
| `escalation_detected` | approved (matching constraint approves it) | Update constraint activation count | No | governance_signals |
| `amnesia_detected` | any | Add to session briefing for next session, flag in DuckDB | No | governance_signals + amnesia_events |
| `novel_pattern` | no matching constraint | Queue for human review (emit `pending_review` signal) | Optional (Wave 4+) | governance_signals |
| `constraint_graduated` | violation_rate < threshold over N sessions | Emit graduation candidate; propose promotion to project_wisdom | No | governance_decisions |
| `ddf_intervention` | any (from co-pilot) | Log; no governor action needed (co-pilot handles directly) | No | governance_signals |
| `fringe_drift` | unresolved fringe signal | Log as Fringe Drift event for Phase 16 metrics | No | governance_signals |

**5. Broadcast Protocol**

When the governor decides to block or warn a session:
1. Call `POST /api/broadcast` internally (direct function call, not HTTP -- co-located)
2. The broadcast message is queued for the target session
3. The target session's next PreToolUse hook call to `/api/check` receives the broadcast via `pending_broadcasts` in the response
4. For `block` messages: the session's `blocked` flag is set; ALL subsequent `/api/check` calls return `deny` until the block is cleared
5. Block clearing: the governor or human operator sends a new broadcast with `message_type: "warn"` containing "BLOCK CLEARED" to reset the `blocked` flag

**Policy Automatization Detector (Desktop -> Library transition):**

This is the compounding mechanism per 14-CONTEXT.md Section 2. The governor tracks constraint usage patterns and proposes graduation when constraints have been internalized.

**Tracking mechanism:**

For each constraint, the governor maintains:
```python
@dataclass
class ConstraintUsageStats:
    constraint_id: str
    ccd_axis: str | None
    epistemological_origin: str                # "reactive" | "principled" | "inductive"
    activation_count: int = 0                  # Times the constraint was checked (activated)
    violation_count: int = 0                   # Times the constraint was actually violated
    session_window: list[SessionViolationRate] = field(default_factory=list)

@dataclass
class SessionViolationRate:
    session_id: str
    activations: int
    violations: int
    violation_rate: float                      # violations / activations
    timestamp: datetime
```

- `activation_count` increments every time `/api/check` runs a constraint against a tool call (even if no match)
- `violation_count` increments every time a constraint matches (deny or warn)
- Per-session rates are recorded at session deregistration time

**Graduation criteria:**

A constraint becomes a graduation candidate when:

```
violation_rate = violations / activations < graduation_threshold
```

sustained over `graduation_window` consecutive sessions.

**Epistemological origin differentiation:**

| Origin | Graduation Threshold | Graduation Window | Rationale |
|--------|---------------------|-------------------|-----------|
| `principled` | < 0.01 (1%) | 10 sessions | Principled constraints generalize earlier -- they have been valued (integrated into the affect system per MAS). A principle with near-zero violations over 10 sessions is genuinely internalized. |
| `inductive` | < 0.02 (2%) | 15 sessions | Inductive constraints (derived from pattern recognition) need moderate evidence -- they generalize across similar domains but may not hold in novel contexts. |
| `reactive` | < 0.02 (2%) | 20 sessions | Reactive constraints (derived from single corrections) require the most evidence -- their scope is narrower, and they fire on exact-match patterns. More sessions needed to confirm true internalization vs. accidental non-activation. |

**Graduation process:**

1. Governor detects that a constraint meets graduation criteria
2. Emit `constraint_graduated` GovernanceSignal with constraint details and usage stats
3. The signal is logged to DuckDB `governance_decisions` table with `decision_type: "graduation_candidate"`
4. **Human review required:** The constraint is NOT automatically promoted. The `constraint_graduated` signal is queued for human review (visible in `govern status` CLI output and in the Phase 16 review workflow)
5. On human approval: constraint's `status` changes from `active` to `graduated`; a new `project_wisdom` entry is created with `wisdom_type: "automatized_constraint"` carrying the original constraint's `ccd_axis`, `scope_rule`, and usage evidence
6. On human rejection: constraint remains `active`; graduation window resets

**The compounding effect:**

- Session N: 12 active constraints on the governance Desktop. Each PreToolUse check runs against 12 principles.
- Session N+100: 3 constraints graduated (internalized). 9 active constraints on Desktop. 3 freed slots.
- The freed Desktop capacity is used by higher-order principles surfaced by the DDF co-pilot (section 3). The system gets smarter without getting more expensive.
- The graduation rate is the system's learning velocity: `graduated_constraints / total_sessions` measures how quickly the AI + human collaboration internalizes governance principles.

### 2.3 Governor State Management

**Persistent state (DuckDB):**

Two new tables for governance persistence:

```sql
-- Governance signals: append-only log of all signals received
CREATE TABLE IF NOT EXISTS governance_signals (
    event_id        VARCHAR PRIMARY KEY,
    signal_type     VARCHAR NOT NULL,
    session_id      VARCHAR NOT NULL,
    project_dir     VARCHAR NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    details         JSON NOT NULL,
    boundary_dependency VARCHAR NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Governance decisions: governor's autonomous responses
CREATE TABLE IF NOT EXISTS governance_decisions (
    decision_id     VARCHAR PRIMARY KEY,
    event_id        VARCHAR NOT NULL,             -- FK to governance_signals
    decision_type   VARCHAR NOT NULL,             -- "block" | "warn" | "allow" | "graduation_candidate" | "pending_review"
    target_sessions JSON,                         -- Array of session IDs affected
    action_taken    TEXT NOT NULL,                 -- Description of the action
    constraint_id   VARCHAR,                      -- Related constraint (if any)
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Constraint usage stats: per-constraint per-session violation rates
CREATE TABLE IF NOT EXISTS constraint_usage_stats (
    stat_id         VARCHAR PRIMARY KEY,
    constraint_id   VARCHAR NOT NULL,
    session_id      VARCHAR NOT NULL,
    project_dir     VARCHAR NOT NULL,
    activations     INTEGER NOT NULL DEFAULT 0,
    violations      INTEGER NOT NULL DEFAULT 0,
    violation_rate  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (constraint_id, session_id)
);
```

**In-memory state (BusState.governor):**

```python
@dataclass
class GovernorState:
    usage_stats: dict[str, ConstraintUsageStats]  # constraint_id -> stats
    dedup_window: dict[str, datetime]              # dedup_key -> first_seen
    pending_reviews: list[GovernanceSignal]         # Signals awaiting human review
    graduation_candidates: list[str]               # constraint_ids proposed for graduation
```

**Recovery after restart:**

On bus/governor startup:
1. Reload constraints from `{project_dir}/data/constraints.json` for each known project
2. Rebuild PolicyViolationChecker for each project
3. Load constraint_usage_stats from DuckDB to rebuild `GovernorState.usage_stats` (graduation tracking survives restart)
4. Session registry starts empty -- sessions will re-register on their next hook call
5. Events ring buffer starts empty (ephemeral -- historical events are in DuckDB)
6. Pending broadcasts are lost on restart (acceptable -- they would be stale anyway)

### 2.4 Governor Monitoring Dashboard (Design Only)

The governor exposes a JSON data endpoint for monitoring:

**`GET /api/dashboard`**

**Response (200):**
```json
{
  "uptime_seconds": 3612.5,
  "sessions": {
    "active": 3,
    "stale": 1,
    "total_registered_today": 7,
    "list": [
      {"session_id": "abc123", "project": "ope", "last_heartbeat": "30s ago", "stale": false},
      {"session_id": "def456", "project": "ope", "last_heartbeat": "8m ago", "stale": true}
    ]
  },
  "constraints": {
    "total": 208,
    "active": 195,
    "graduated": 13,
    "by_project": {"orchestrator-policy-extraction": 208}
  },
  "enforcement": {
    "checks_total": 1547,
    "checks_per_minute": 12.3,
    "blocks_total": 23,
    "warnings_total": 89,
    "blocks_per_hour": 1.2
  },
  "governance": {
    "signals_received_today": 45,
    "decisions_made_today": 12,
    "pending_reviews": 3,
    "graduation_candidates": 2,
    "recent_signals": [
      {"event_id": "evt_001", "signal_type": "escalation_detected", "session_id": "abc123", "ago": "2m"}
    ]
  }
}
```

This is a data endpoint, not a UI. A future Phase could add a terminal dashboard (`rich` library) or web UI that consumes this JSON.

### 2.5 Multi-Project Support

The bus supports multiple projects simultaneously. This is essential for a developer working on OPE and modernizing tool in parallel sessions.

**Design:**

- Sessions register with their `project_dir`
- The bus maintains a `dict[str, ProjectState]` mapping project directories to their state
- Each ProjectState holds its own: ConstraintStore, PolicyViolationChecker, session list, constraint usage stats
- Constraint loading is lazy: ProjectState is created on first session registration for that project

**Project isolation:**

- `/api/check` calls are scoped by `project_dir` in the request body -- a session's tool calls are checked against its own project's constraints only
- Governance signals carry `project_dir` -- signals from project A are not visible to project B's sessions
- The SSE stream (`/api/events/stream`) can be filtered by `project_dir`
- The governor's decision matrix operates per-project (a block in project A does not affect project B)
- Constraint graduation tracking is per-project (a constraint may be graduated in OPE but still active in modernizing tool if both projects share it)

**Cross-project future (Phase 18 / run-id-dissolves-repo-boundary CCD):**

The current design isolates projects. A future enhancement (governed by the `run_id` axis from MEMORY.md) would allow the governing orchestrator to assign a shared `run_id` spanning multiple projects, enabling cross-project causal chain attribution. The bus architecture supports this -- the `project_dir` isolation is a routing decision, not a structural constraint. Adding a `run_id` field to GovernanceSignal and keying some state by `run_id` instead of `project_dir` would enable cross-project coordination without architectural change.

### 2.6 Security Considerations

**Acceptable for the threat model (solo developer on local machine):**

- The Unix socket is accessible to any local process running as the same user. On macOS, this means any process in the user's login session can read/write the socket.
- No authentication on bus API routes. The bus is local-only (Unix socket, not TCP). There is no network attack surface.
- No encryption needed. All data flows over local IPC within the same machine. No secrets traverse the bus (constraint text and tool inputs are not secrets in this context).
- Constraint mutations (reload, broadcast) are not authenticated but are logged with timestamp and source session_id for audit trail.

**Known limitations documented for transparency:**

- Any local process can register as a session, submit events, or broadcast messages. There is no session identity verification.
- A malicious local process could flood the event stream, exhaust the ring buffer, or broadcast spurious block messages. Mitigation: rate limiting per source (not implemented in Wave 1; acceptable risk for solo developer).
- The PID file has no ownership verification. A local process could overwrite it. Mitigation: PID file is informational, not a security boundary.

### 2.7 Failure Modes and Recovery

**Failure 1: Bus crashes**

- **Impact:** Sessions lose shared constraint state and cross-session coordination.
- **Detection:** Hook scripts get connection refused on next `/api/check` call.
- **Recovery:** Hooks fall back to standalone mode (direct file-based constraint checking). No governance gap for LIVE-01/LIVE-02 -- they work without the bus, just slower (~100ms instead of ~60ms) and without cross-session features.
- **Restart:** `govern bus start` starts a fresh bus. Sessions re-register on their next hook call. Constraint usage stats are recovered from DuckDB.

**Failure 2: Bus overloaded (slow response)**

- **Impact:** PreToolUse hook exceeds its latency budget, slowing down Claude Code tool calls.
- **Detection:** `/api/check` response time exceeds 100ms.
- **Recovery:** Hook scripts use a 100ms timeout on the bus HTTP call:
  ```python
  try:
      response = client.post("/api/check", json=payload, timeout=0.1)
  except (httpx.TimeoutException, httpx.ConnectError):
      # Fall back to direct constraint checking
      return direct_constraint_check(tool_name, tool_input)
  ```
- **Root cause mitigation:** The bus should never be slow -- constraint checking is in-memory regex matching (<1ms). If the bus is slow, it indicates a bug (e.g., blocking I/O in the event loop) that should be diagnosed, not worked around.

**Failure 3: Orphaned socket**

- **Impact:** Next bus startup fails because the socket file already exists.
- **Detection:** Socket file exists but no process is listening.
- **Recovery:** Startup stale socket detection (section 1.1): attempt connect, if refused, unlink and re-create. Also: PID file cross-check -- if PID file exists and the PID is not running, remove both PID file and socket file.

**Failure 4: DuckDB write failure**

- **Impact:** Governance decisions and signals are not persisted.
- **Detection:** DuckDB raises an exception on write.
- **Recovery:** Log the error. Continue operating with in-memory state only. The bus does not crash on DuckDB failures -- persistence is best-effort for the governor, not a requirement for constraint checking. On next successful DuckDB connection, batch-write any buffered signals.

**Failure 5: Constraint file corruption**

- **Impact:** `data/constraints.json` is malformed, preventing constraint reload.
- **Detection:** JSON parse error during reload.
- **Recovery:** Keep the existing in-memory constraint cache. Log the error. Do NOT replace a working constraint cache with an empty one. The next successful file parse will update the cache.

---

## 3. DDF Co-Pilot Architecture (LIVE-06)

### 3.1 DDF Co-Pilot Overview

**Purpose:** Detect conceptual breakthroughs as they occur in a live session, prompt the human to name new axes before they drift back into implicit knowledge (Fringe Drift prevention), and deposit insights into `memory_candidates` immediately (write-on-detect).

**Governing constraint (deposit-not-detect CCD axis):** The co-pilot exists to DEPOSIT to `memory_candidates`, not merely to detect. Detection (DDF markers, structural signals, affective heuristics) is instrumental. Deposit (a `memory_candidates` row written to DuckDB) is terminal. Any co-pilot component that only detects and never produces a candidate is instrumentation noise.

**Architectural position:** The co-pilot is a component of the bus/governor daemon (section 2). It runs as an async task that monitors the real-time event stream (via the stream processor's governance signals and direct JSONL event access) and fires intervention prompts via `additionalContext` injection.

**What the co-pilot is NOT:**

- It is NOT an observer of intelligence growth. It participates in the recursive climb by extracting filing keys from the human's Crow (Values -> axis identification) that the AI cannot generate itself (structural asymmetry: AI has no retrieval cost function, per MEMORY.md `raven-cost-function-absent` CCD axis).
- It is NOT a passive logger. Every intervention aims to produce a `memory_candidates` entry. Interventions that do not produce entries are tracked as Fringe Drift events for metric purposes.
- It is NOT a replacement for human judgment. The co-pilot prompts; the human names. The co-pilot records; the human reviews (Phase 16).

### 3.2 Three Co-Pilot Intervention Types

#### Type 1: O_AXS Intervention (Axis Shift)

**Fires:** AFTER an Axis Shift event is detected -- the human has named a new concept. This is the highest-confidence intervention because the naming has already occurred.

**Trigger condition:**
- O_AXS episode mode detected by the stream processor's tagger
- Instruction granularity drops sharply (prior 3 prompts averaged > 50 words per user prompt; current prompt < 20 words) AND a new unifying concept is introduced in the same prompt
- The new concept is identified by: a noun phrase appearing for the first time in the session transcript that is referenced again in the next 2 user prompts (persistence indicates it is a concept being formed, not a one-off mention)

**Detection heuristics (pre-compiled at co-pilot init):**

```python
# Granularity drop detector
class GranularityTracker:
    window: deque[int]          # word counts of last 3 user prompts
    threshold_ratio: float = 0.4  # current / average must be < 0.4

# Novel concept detector
class NovelConceptTracker:
    session_vocabulary: set[str]  # all noun phrases seen in session
    recent_concepts: deque[tuple[str, int]]  # (concept, prompt_index) for last 5 prompts
    persistence_threshold: int = 2  # must appear in N subsequent prompts
```

**Intervention prompt (injected via `additionalContext` on the next PreToolUse call):**

```
AXIS SHIFT DETECTED -- you appear to have named a new organizing concept: "{detected_concept}".

Please formalize it:
1. Name it as a CCD axis (the concept, not an example)
2. State the scope rule (what counts as an instance)
3. Give a flood example (one concrete case that this axis explains)

I will record this as a memory candidate for review.
```

**Write-on-detect mechanism:**

On receiving the human's formal naming response (detected by: user prompt following the intervention that contains structured content with axis/scope/example patterns, or simply the next user prompt if it contains a clear concept name):

1. Extract `ccd_axis`, `scope_rule`, `flood_example` from the human's response (regex patterns for common formats: "axis: ...", "scope: ...", numbered lists, dash-prefixed items)
2. Write ONE entry to `memory_candidates` DuckDB table:

```python
{
    "id": f"mc_{session_id}_{uuid4().hex[:8]}",
    "source_instance_id": None,           # No identification instance -- direct human input
    "ccd_axis": extracted_axis,
    "scope_rule": extracted_scope_rule,
    "flood_example": extracted_flood_example,
    "pipeline_component": "ddf_copilot_oaxs",
    "heuristic_description": "O_AXS intervention: axis shift detected at granularity drop",
    "status": "pending",
    # Extended fields (co-pilot additions to existing schema):
    # session_id, subject, origin, confidence -- see section 3.3
}
```

3. Emit a `ddf_intervention` GovernanceSignal to the bus (for logging and governor awareness)
4. If extraction fails (human response is ambiguous or does not contain structured content): do NOT write a partial entry. Log as a `fringe_drift` event (intervention fired but did not produce a deposit).

**This deposit is the TERMINAL act.** The detection is instrumental. Phase 16 adds the review workflow; the first deposit happens here in Phase 15.

---

#### Type 2: Fringe Intervention (Negative Vague Phenomenological Language)

**Fires:** BEFORE naming (pre-Level-4). Negative vague language indicates Fringe awareness before the human can articulate the concept. This intervention combats Fringe Drift -- the phenomenon where an insight sensed at the periphery of awareness vanishes before it can be named.

**Trigger condition:**
- Negative valence + vague epistemic markers in a user prompt
- WITHOUT a named concept in the same prompt (if a named concept is present, this is Level 4+ and O_AXS handles it)

**Detection heuristics (keyword/regex patterns, pre-compiled at init):**

```python
# Negative vague phenomenological markers
FRINGE_PATTERNS: list[re.Pattern] = [
    re.compile(r"something\s+feels?\s+off", re.IGNORECASE),
    re.compile(r"this\s+doesn'?t\s+sit\s+right", re.IGNORECASE),
    re.compile(r"something'?s?\s+wrong\s+with", re.IGNORECASE),
    re.compile(r"i'?m?\s+not\s+sure\s+why\s+but", re.IGNORECASE),
    re.compile(r"there'?s?\s+something\s+about", re.IGNORECASE),
    re.compile(r"something\s+bothers?\s+me", re.IGNORECASE),
    re.compile(r"can'?t\s+quite\s+put\s+my\s+finger", re.IGNORECASE),
    re.compile(r"this\s+seems?\s+wrong\s+somehow", re.IGNORECASE),
    re.compile(r"i\s+feel\s+like\s+we'?re?\s+missing", re.IGNORECASE),
    re.compile(r"i\s+have\s+a\s+nagging", re.IGNORECASE),
    re.compile(r"something\s+is\s+off\s+here", re.IGNORECASE),
]

# Named concept exclusion (if any of these are present, suppress Fringe intervention)
NAMED_CONCEPT_INDICATORS: list[re.Pattern] = [
    re.compile(r"the\s+principle\s+is", re.IGNORECASE),
    re.compile(r"the\s+axis\s+is", re.IGNORECASE),
    re.compile(r"this\s+is\s+a\s+case\s+of", re.IGNORECASE),
    re.compile(r"the\s+concept\s+here\s+is", re.IGNORECASE),
    re.compile(r"ccd[_-]?axis", re.IGNORECASE),
    re.compile(r"scope[_\s]rule", re.IGNORECASE),
]
```

**Intervention prompt:**

```
FRINGE SIGNAL -- you are sensing something without yet naming it.

Before we continue: what specifically feels wrong? Can you describe
the concern in one sentence without examples?

(This prevents Fringe Drift -- the insight will vanish if we do not
name it now.)
```

**Write-on-detect mechanism:**

Monitor the next 2 user prompts from the session after intervention:

- **If human responds with a named principle** (detected by: presence of a clear concept name, definitional language, or structured axis/scope/example content):
  - Write to `memory_candidates` with:
    - `origin`: `"reactive"` (Fringe-derived -- identified a problem but not yet valued)
    - `confidence`: `0.6` (lower confidence -- Fringe signals may not produce axis-quality concepts; the naming was prompted, not spontaneous)
    - `pipeline_component`: `"ddf_copilot_fringe"`
  - Emit `ddf_intervention` GovernanceSignal (successful capture)

- **If human responds with "not sure yet", "I don't know", or equivalent** (no clear naming):
  - Do NOT write to `memory_candidates` (no forced deposit of unresolved concepts -- a non-concept entry is worse than no entry)
  - Emit `fringe_drift` GovernanceSignal (concept lost to Basement without capture)
  - Log the Fringe Drift event for the Phase 16 metric (section 3.6)

- **If no relevant response within 2 prompts** (human moved on to other work):
  - Treat as Fringe Drift (same as above)

---

#### Type 3: Affect Spike Intervention (Positive Valence Shift Pre-Naming)

**Fires:** BEFORE naming. Positive affective shift indicates a Value Node activation before the human has articulated the breakthrough. This is the symmetric positive counterpart to the Fringe Intervention: both fire pre-naming, both combat Drift, both deposit to `memory_candidates` on successful capture.

Per 14-CONTEXT.md Section 5 (MAS integration): the Affect Spike occurs at the moment a Value Node activates -- before the human has articulated the connection. It is as vulnerable to Drift as the negative Fringe signal.

**Trigger condition:**
- Positive valence spike + sudden certainty increase in a user prompt
- WITHOUT a named concept immediately preceding (if naming already occurred, O_AXS handles it)

**Detection heuristics (keyword/regex patterns, pre-compiled at init):**

```python
# Positive valence spike markers
AFFECT_SPIKE_PATTERNS: list[re.Pattern] = [
    re.compile(r"that'?s?\s+it!", re.IGNORECASE),
    re.compile(r"exactly!", re.IGNORECASE),
    re.compile(r"this\s+is\s+the\s+key", re.IGNORECASE),
    re.compile(r"yes\s*[-—]\s*that'?s?\s+why", re.IGNORECASE),
    re.compile(r"now\s+it\s+makes\s+sense", re.IGNORECASE),
    re.compile(r"this\s+explains\s+everything", re.IGNORECASE),
    re.compile(r"that'?s?\s+exactly\s+(what|why|how)", re.IGNORECASE),
    re.compile(r"oh!\s+", re.IGNORECASE),
    re.compile(r"aha!", re.IGNORECASE),
    re.compile(r"holy\s+shit", re.IGNORECASE),
    re.compile(r"this\s+changes\s+everything", re.IGNORECASE),
    re.compile(r"i\s+just\s+realized", re.IGNORECASE),
]

# Certainty acceleration detector
class CertaintyAccelerationTracker:
    """Detects sequences of 3+ prompts with increasing assertion strength."""
    hedge_patterns: list[re.Pattern]  # "maybe", "perhaps", "I think", "possibly"
    declarative_patterns: list[re.Pattern]  # "this is", "the answer is", "it must be"

    def check(self, recent_prompts: list[str]) -> bool:
        """Returns True if hedge_ratio is decreasing over last 3 prompts."""
        ...

# Statement acceleration detector
class StatementLengthTracker:
    """Detects enthusiasm-driven text expansion."""
    window: deque[int]  # word counts of last 3 user prompts
    spike_ratio: float = 2.0  # current / average must be > 2.0 to fire
```

**Exclusion rule:** Suppress if the same prompt contains a named concept (checked by `NAMED_CONCEPT_INDICATORS` from Fringe patterns). If naming has already happened, O_AXS intervention is appropriate, not Affect Spike.

**Intervention prompt:**

```
BREAKTHROUGH MOMENT -- something just clicked for you.

Before we continue: what specifically clicked? Can you state the
principle in one sentence?

(This prevents the Aha! from drifting back to Basement before it
becomes a named concept.)
```

**Write-on-detect mechanism:**

Monitor the next 2 user prompts from the session after intervention:

- **If human responds with a named principle:**
  - Write to `memory_candidates` with:
    - `origin`: `"inductive"` (derived from pattern recognition -- the Aha! moment is inductive reasoning crystallizing into a named concept)
    - `confidence`: `0.75` (moderate-high -- Affect Spike produces Level 5-6 quality concepts when captured, because the affective weight indicates the concept has been valued)
    - `pipeline_component`: `"ddf_copilot_affect_spike"`
  - Emit `ddf_intervention` GovernanceSignal (successful capture)

- **If no clear naming within 2 prompts:**
  - Emit `fringe_drift` GovernanceSignal (the Aha! drifted before capture)
  - Same Fringe Drift tracking as Type 2

**This intervention is EQUALLY LOAD-BEARING to the Fringe Intervention.** Both combat the same Drift mechanism. The Fringe fires on negative phenomenological language (sensing a problem); the Affect Spike fires on positive phenomenological language (sensing a solution). Both are pre-naming and therefore vulnerable to the same Drift failure mode.

### 3.3 memory_candidates Entry Schema

The `memory_candidates` table already exists (created in Phase 13.3, defined in `src/pipeline/review/schema.py`). The current schema:

```sql
CREATE TABLE IF NOT EXISTS memory_candidates (
    id                    VARCHAR PRIMARY KEY,
    source_instance_id    VARCHAR,
    ccd_axis              TEXT NOT NULL,
    scope_rule            TEXT NOT NULL,
    flood_example         TEXT NOT NULL,
    pipeline_component    VARCHAR,
    heuristic_description TEXT,
    status                VARCHAR NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'validated', 'suspended', 'rejected', 'split_required')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at           TIMESTAMPTZ,
    CHECK (LENGTH(TRIM(ccd_axis)) > 0),
    CHECK (LENGTH(TRIM(scope_rule)) > 0),
    CHECK (LENGTH(TRIM(flood_example)) > 0)
);
```

**Co-pilot writes entries conforming to this schema.** The CCD format constraint (non-empty `ccd_axis`, `scope_rule`, `flood_example`) enforces the Snippet-Not-Chunk CCD axis structurally.

**Extended fields needed for co-pilot deposits (Phase 15 schema migration):**

The existing schema lacks fields that the co-pilot needs. Phase 15 implementation must add:

```sql
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS session_id VARCHAR;
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS subject VARCHAR DEFAULT 'human'
    CHECK (subject IN ('human', 'ai'));
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS origin VARCHAR DEFAULT 'reactive'
    CHECK (origin IN ('reactive', 'principled', 'inductive'));
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 0.5
    CHECK (confidence >= 0.0 AND confidence <= 1.0);
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS perception_pointer TEXT;
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `session_id` | VARCHAR | null | Source session that produced this candidate |
| `subject` | VARCHAR | `"human"` | Who produced the insight: `"human"` (human named it) or `"ai"` (AI generated it) |
| `origin` | VARCHAR | `"reactive"` | Epistemological origin: `"reactive"` (single correction), `"principled"` (Level 6 flood), `"inductive"` (pattern recognition / Affect Spike) |
| `confidence` | DOUBLE | 0.5 | Confidence score: 0.0-1.0. Set by the co-pilot based on intervention type (O_AXS: 0.8, Affect Spike: 0.75, Fringe: 0.6) |
| `perception_pointer` | TEXT | null | Ground-truth pointer per `ground-truth-pointer` CCD axis: `"{session_id}:{prompt_number}"` or `"{transcript_path}:{line_range}"` |

**Entry schema per intervention type:**

| Field | O_AXS (Type 1) | Fringe (Type 2) | Affect Spike (Type 3) |
|-------|-----------------|------------------|----------------------|
| `pipeline_component` | `ddf_copilot_oaxs` | `ddf_copilot_fringe` | `ddf_copilot_affect_spike` |
| `subject` | `human` | `human` | `human` |
| `origin` | `principled` | `reactive` | `inductive` |
| `confidence` | 0.8 | 0.6 | 0.75 |
| `status` | `pending` | `pending` | `pending` |
| `heuristic_description` | "O_AXS: axis shift at granularity drop" | "Fringe: negative vague language captured" | "Affect Spike: positive valence captured" |

### 3.4 AI-Side DDF Detection (Phase 15 scope, designed here)

The AI's own responses are also monitored for DDF markers. When the AI spontaneously exhibits higher-order reasoning, these are captured as `ai_flame_events`.

**What is monitored:**

The co-pilot monitors `assistant`-type JSONL events in the stream processor for DDF level indicators in the AI's text output.

**DDF level detection heuristics (AI-side, simplified for real-time):**

| DDF Level | Detection Signal | Heuristic |
|-----------|-----------------|-----------|
| Level 2: Piles -> Files (Axis Shift) | AI introduces a new CCD or named abstraction not present in the human's prior prompts | New noun phrase introduced by AI, referenced by AI again in next response, not previously used by human |
| Level 3: Causal Isolation | AI performs Method of Difference reasoning rather than symptom-matching | Presence of contrastive reasoning patterns: "X differs from Y in that...", "When Z is removed...", "The distinguishing property is..." |
| Level 4: The Algebra | AI moves from concrete examples to variable-level principles | Generalization patterns: "In general...", "The principle here is...", "This generalizes to..." |
| Level 6: Concretization Flood | AI spontaneously applies a principle to multiple novel domains without prompting | AI response contains 3+ distinct concrete examples of the same principle applied to different domains, unprompted by the human |

**DuckDB schema for ai_flame_events (Phase 15 implementation):**

```sql
CREATE TABLE IF NOT EXISTS ai_flame_events (
    event_id        VARCHAR PRIMARY KEY,
    session_id      VARCHAR NOT NULL,
    ddf_level       INTEGER NOT NULL CHECK (ddf_level BETWEEN 1 AND 7),
    subject         VARCHAR NOT NULL DEFAULT 'ai' CHECK (subject IN ('human', 'ai')),
    trigger_text    TEXT NOT NULL,              -- The AI text that triggered detection
    detected_axis   VARCHAR,                    -- CCD axis detected (if Level 2+)
    confidence      DOUBLE PRECISION NOT NULL,
    perception_pointer TEXT NOT NULL,           -- "{transcript_path}:{line_number}"
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Co-pilot's role for AI-side detection:**

1. Monitor assistant-type JSONL events from the stream processor
2. Run DDF level heuristics on AI response text
3. When Level 2+ detected: write to `ai_flame_events` table
4. When Level 6 AI flood detected: ALSO write to `memory_candidates` (write-on-detect, same terminal act as human side) with `subject: "ai"`, `origin: "inductive"`, `confidence: 0.7`
5. AI-side deposits have lower confidence (0.7) than human-side O_AXS deposits (0.8) because the AI's "naming" may be surface-similarity retrieval rather than genuine axis identification (per `raven-cost-function-absent` CCD axis). Human review in Phase 16 is essential for AI-generated candidates.

### 3.5 Integration with Bus/Governor

**Architectural position:**

The co-pilot runs as an async task within the bus daemon process, alongside the governor. It has direct access to:
- The stream processor's event feed (via internal subscription, not SSE)
- The bus's broadcast mechanism (direct function call to queue messages)
- DuckDB connection for `memory_candidates` and `ai_flame_events` writes

**Event processing flow:**

```
JSONL file grows
    |
    v
Stream processor reads new events
    |
    v
LiveEventAdapter converts to LiveEvent
    |
    +---> Detectors (escalation, amnesia, policy) --> GovernanceSignal --> Bus events
    |
    +---> Co-pilot DDF analysis
              |
              +---> Human prompt analysis (Fringe patterns, Affect patterns, Granularity tracking)
              |         |
              |         +---> Intervention trigger? --> POST /api/broadcast (intervention prompt)
              |
              +---> AI response analysis (DDF level heuristics)
              |         |
              |         +---> Level 2+? --> Write ai_flame_events
              |         +---> Level 6?  --> Also write memory_candidates
              |
              +---> Response capture (monitors next 2 human prompts after intervention)
                        |
                        +---> Named concept extracted? --> Write memory_candidates
                        +---> No naming within 2 prompts? --> Emit fringe_drift signal
```

**Intervention delivery mechanism:**

When the co-pilot detects an intervention trigger:
1. Call the bus's broadcast function (internal, not HTTP) with:
   - `message_type: "briefing"` (not "block" -- interventions are prompts, not restrictions)
   - `target_sessions: [session_id]` (only the session that produced the trigger)
   - `content`: the intervention prompt text
2. The intervention prompt is queued as a pending broadcast for the target session
3. On the session's next PreToolUse hook call, the `/api/check` response includes the intervention prompt in `pending_broadcasts`
4. The hook script includes the intervention text in `additionalContext`, where Claude reads it and can relay it to the human

**Response capture mechanism:**

After broadcasting an intervention, the co-pilot enters a "capture window" for the target session:

```python
@dataclass
class CaptureWindow:
    session_id: str
    intervention_type: str          # "oaxs" | "fringe" | "affect_spike"
    triggered_at: datetime
    remaining_prompts: int = 2      # Monitor next N user prompts
    intervention_text: str          # For audit trail
```

- The co-pilot monitors user-type events from the session
- For each user prompt within the capture window: run concept extraction (look for axis/scope/example patterns, named principles, definitional language)
- If a concept is extracted: write to `memory_candidates`, close the capture window
- If `remaining_prompts` reaches 0 without extraction: emit `fringe_drift`, close the capture window
- Only ONE capture window per session at a time (new intervention triggers are suppressed while a window is active)

**Intervention rate limiting:**

To avoid overwhelming the human:
- Maximum 1 intervention per 10 user prompts per session
- After an intervention, the co-pilot suppresses further triggers for at least 5 minutes or 10 prompts (whichever comes first)
- O_AXS interventions (post-naming, highest value) override the cooldown
- The rate limit is tracked per session

### 3.6 Fringe Drift Rate Metric

**Definition:** The proportion of detected Fringe and Affect Spike signals (Types 2 and 3) that failed to produce a named concept within 2 prompts of the intervention.

**Formula:**

```
fringe_drift_rate = unresolved_interventions / total_pre_naming_interventions
```

Where:
- `total_pre_naming_interventions` = count of Fringe (Type 2) + Affect Spike (Type 3) interventions fired
- `unresolved_interventions` = count of those that did NOT produce a `memory_candidates` entry within the capture window

Note: O_AXS (Type 1) interventions are excluded from this metric because they fire post-naming -- Drift has already been prevented by the human's spontaneous naming act.

**Target:** < 20% per session aggregate. Most Fringe and Affect Spike signals should produce named concepts when intercepted by the co-pilot.

**Measurement granularity:**
- Per session: `session_fringe_drift_rate`
- Per intervention type: separate rates for Fringe vs. Affect Spike (they may have different resolution rates)
- Rolling average: computed over a configurable window (default: last 10 sessions)

**DuckDB persistence (for Phase 16 Sacred Fire Intelligence System):**

```sql
CREATE TABLE IF NOT EXISTS copilot_interventions (
    intervention_id     VARCHAR PRIMARY KEY,
    session_id          VARCHAR NOT NULL,
    intervention_type   VARCHAR NOT NULL CHECK (intervention_type IN ('oaxs', 'fringe', 'affect_spike')),
    trigger_text        TEXT NOT NULL,         -- The user text that triggered the intervention
    intervention_prompt TEXT NOT NULL,          -- The prompt that was broadcast
    triggered_at        TIMESTAMPTZ NOT NULL,
    resolved            BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_type     VARCHAR,               -- "named_concept" | "fringe_drift" | "timeout"
    memory_candidate_id VARCHAR,               -- FK to memory_candidates (if resolved)
    resolved_at         TIMESTAMPTZ,
    perception_pointer  TEXT NOT NULL           -- "{transcript_path}:{line_number}"
);
```

This table is the Phase 16 data source for Fringe Drift rate computation, intervention effectiveness analysis, and co-pilot calibration.

---

## 4. Cross-References

### To 14-01-PLAN.md (Single-Session Layer)

| 14-02 Component | 14-01 Component | Relationship |
|-----------------|-----------------|--------------|
| Bus `/api/check` | PreToolUse hook contract | Bus provides optimized version of the same constraint check; hook falls back to direct mode when bus unavailable |
| Bus `/api/events` | Stream processor GovernanceSignal | Stream processor emits signals that the bus receives and distributes to governor and SSE subscribers |
| Governor broadcast | PreToolUse `additionalContext` | Governor messages are delivered to sessions via the PreToolUse hook's `pending_broadcasts` mechanism |
| Governor constraint authority | SessionStart briefing | SessionStart hook gets authoritative constraints from bus when available; direct file load as fallback |
| Co-pilot interventions | PreToolUse `additionalContext` | Co-pilot intervention prompts are delivered as `additionalContext` via the broadcast mechanism |
| Episode boundary state machine | Stream processor TENTATIVE_END/CONFIRMED_END | Co-pilot respects episode boundaries -- episode_level signals deferred to CONFIRMED_END per 14-01 design |

### To Existing Codebase

| 14-02 Component | Existing Code | Usage |
|-----------------|---------------|-------|
| Bus constraint checking | `PolicyViolationChecker` (`src/pipeline/feedback/checker.py`) | Bus wraps the checker in-memory; same `check(text)` interface |
| Bus constraint loading | `ConstraintStore` (`src/pipeline/constraint_store.py`) | Bus creates ConstraintStore instances per project; uses `get_active_constraints()` |
| Co-pilot memory deposits | `memory_candidates` table (`src/pipeline/review/schema.py`) | Co-pilot writes to existing table; Phase 15 adds columns for session_id, subject, origin, confidence |
| Governor usage tracking | `constraint_usage_stats` (new table) | New DuckDB table for graduation tracking |

### To MEMORY.md CCD Axes

| CCD Axis | Relevant Design Decision |
|----------|------------------------|
| `deposit-not-detect` | Co-pilot design prioritizes memory_candidates writes (terminal) over detection machinery (instrumental) |
| `raven-cost-function-absent` | AI-side DDF deposits have lower confidence (0.7) than human-side (0.8) because AI cannot distinguish axis-quality from surface-similarity |
| `terminal-vs-instrumental` | Governor decision matrix classifies each signal by whether it produces a deposit or only a detection |
| `ground-truth-pointer` | All memory_candidates entries carry `perception_pointer` linking to source session/line |
| `snippet-not-chunk` | CCD format constraint on memory_candidates enforces structured entries, not magnitude-level "remember X" |
| `identity-firewall` | Co-pilot generates candidates; human reviews in Phase 16. Generator and validator are structurally separated |
| `temporal-closure-dependency` | Episode-level signals (amnesia) deferred to CONFIRMED_END; event-level signals (escalation) fire immediately |
| `bootstrap-circularity` | memory_candidates reviewed against DuckDB artifacts + MEMORY.md, not by the deficient AI session |

---

## 5. Implementation Phasing

This design document specifies LIVE-04, LIVE-05, and LIVE-06 for Phase 15 implementation. The recommended implementation order within Phase 15:

| Wave | Component | Deliverable |
|------|-----------|-------------|
| Wave 3 | Bus server + API routes | `src/pipeline/live/bus/server.py`, `state.py`, `models.py`, `client.py` |
| Wave 3 | Hook bus integration | Update hooks to call bus when available, fall back to direct mode |
| Wave 4 | Governor async tasks | Decision matrix, signal processing, broadcast protocol |
| Wave 4 | Policy Automatization Detector | Usage tracking, graduation criteria, graduation signals |
| Wave 4 | DDF co-pilot (Type 1: O_AXS) | Post-naming intervention, memory_candidates deposit |
| Wave 5 | DDF co-pilot (Types 2+3) | Fringe + Affect Spike interventions, capture windows |
| Wave 5 | AI-side DDF detection | ai_flame_events table, Level 2+ detection heuristics |
| Wave 6 | Fringe Drift metrics | copilot_interventions table, rate computation |
| Wave 6 | Governor dashboard | `/api/dashboard` endpoint |
