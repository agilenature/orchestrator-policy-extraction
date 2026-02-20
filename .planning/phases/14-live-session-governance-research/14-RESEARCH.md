# Phase 14: Live Session Governance Research

**Researched:** 2026-02-20
**Domain:** Claude Code hooks, real-time JSONL processing, inter-process communication, governing session orchestration
**Confidence:** HIGH

## Summary

Phase 14 is a research-only phase that produces architectural design documents for a live governance layer. The key technical insight from this research is that **Claude Code's hook system already provides the exact interception points needed** -- PreToolUse for blocking/warning tool calls, SessionStart for constraint briefings, PostToolUse for monitoring, and SessionEnd for cleanup. The hook protocol is well-documented with precise JSON schemas for stdin/stdout, and the user already has working hooks in `~/.claude/settings.json` demonstrating both patterns (SessionStart for context injection, PreToolUse for tool blocking).

The architecture divides into two independent concerns: (1) **hook-based governance** (PreToolUse constraint checking, SessionStart briefings) which operates synchronously within a single session via shell scripts calling Python, and (2) **cross-session coordination** (shared bus, governing session) which requires a persistent local service. For the bus, a Unix domain socket with an asyncio HTTP server (using the already-installed `uvicorn` + `starlette` stack) gives sub-millisecond IPC on macOS -- well within the 200ms budget. For JSONL tailing, the `watchdog` library using macOS FSEvents provides low-latency file change notifications without polling.

**Primary recommendation:** Design the architecture in two waves -- Wave 1 designs the single-session hooks (PreToolUse checker, SessionStart briefing, JSONL stream processor) which can be implemented independently; Wave 2 designs the multi-session bus and governing session pattern which depends on Wave 1's event format.

## Standard Stack

### Core (Already in Project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.11+ | 3.13.5 installed | Runtime | Project standard |
| Click | >=8.0.0 | CLI commands | Project standard |
| Pydantic v2 | >=2.0.0 | Data models, validation | Project standard |
| DuckDB | >=1.0.0 | Persistent storage for governance events | Project standard |
| loguru | >=0.7 | Structured logging | Project standard |

### New Dependencies for Live Governance
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| watchdog | 6.0.0 | File system monitoring (FSEvents on macOS) | JSONL tailing for LIVE-03 stream processor |
| uvicorn | 0.40.0 (installed) | ASGI server | Inter-session bus HTTP service (LIVE-04) |
| starlette | 0.52.1 (installed) | ASGI framework | Bus API routes and middleware (LIVE-04) |
| httpx | 0.28.1 (installed) | Async HTTP client | Hook scripts calling the bus (LIVE-01, LIVE-02) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| watchdog (FSEvents) | Polling with `os.stat()` | watchdog gives ~10ms latency vs 100-500ms polling; polling is zero-dependency but misses rapid writes |
| uvicorn+starlette | Raw `asyncio.start_unix_server` | Raw asyncio is zero-dependency but requires hand-rolling HTTP protocol; uvicorn+starlette already installed |
| Unix socket | TCP localhost | Unix socket avoids TCP overhead, ~0.1ms vs ~1ms; TCP is more debuggable with curl |
| httpx (async client) | subprocess curl | httpx is already installed and Pythonic; curl adds shell overhead but works from bash hooks |

**Installation:**
```bash
pip install watchdog>=6.0.0
# uvicorn, starlette, httpx already installed
```

## Architecture Patterns

### Overall System Architecture
```
Claude Code Session(s)
    |
    |-- PreToolUse hook --> governance-check.py --> PolicyViolationChecker
    |                           |
    |                           +--> [optional] HTTP call to bus for cross-session state
    |
    |-- SessionStart hook --> constraint-briefing.py --> ConstraintStore + DurabilityScores
    |
    |-- PostToolUse hook (async) --> log-event.py --> bus event stream
    |
    |-- JSONL file grows on disk
            |
            +--> watchdog FSEvents --> stream-processor.py
                    |
                    +--> EscalationDetector (per-event)
                    +--> AmnesiaDetector (per-event)
                    +--> Governance signal emitter --> bus
                            |
Governance Bus (Unix socket + starlette)
    |
    |-- /api/constraints       GET active constraints
    |-- /api/check             POST tool_name + tool_input, returns allow/warn/deny
    |-- /api/sessions          GET active sessions, POST register/deregister
    |-- /api/events            POST governance events (escalations, amnesia)
    |-- /api/broadcast         POST governance signals to all sessions
    |
    +--> Governing Session (optional LIVE-05)
            |
            +--> Monitors bus events
            +--> Maintains authoritative constraint store
            +--> Broadcasts blocks/briefings
```

### Recommended Project Structure for Phase 15 Implementation
```
src/
  pipeline/
    live/                    # New module for live governance
      __init__.py
      hooks/                 # Hook handler scripts
        governance_check.py  # PreToolUse: constraint check
        constraint_briefing.py # SessionStart: briefing
        log_event.py         # PostToolUse (async): event logging
      stream/                # JSONL stream processor
        processor.py         # FSEvents watcher + event processor
        adapters.py          # Raw JSONL -> CanonicalEvent adapters
      bus/                   # Inter-session coordination bus
        server.py            # Starlette ASGI app
        client.py            # httpx client wrapper
        models.py            # Bus message Pydantic models
        state.py             # In-memory shared state
      governor/              # Governing session logic
        monitor.py           # Bus event consumer
        broadcaster.py       # Governance signal broadcaster
```

### Pattern 1: PreToolUse Hook as Governance Gate (LIVE-01)

**What:** A shell script invoked by Claude Code's PreToolUse hook that calls a Python checker, returning allow/warn/deny JSON on stdout.

**When to use:** Every state-changing tool call (Write, Edit, Bash) should be checked against active constraints.

**Critical design constraint:** The hook must complete within the default 600-second timeout, but for UX the target is <200ms. The PolicyViolationChecker uses pre-compiled regex and runs in microseconds. The bottleneck is Python startup time (~50-100ms) and optional bus HTTP call (~1-5ms on Unix socket).

**Example (governance-check.py):**
```python
#!/usr/bin/env python3
"""PreToolUse hook: check proposed tool call against active constraints.

Reads JSON from stdin (Claude Code hook protocol), runs PolicyViolationChecker,
returns hookSpecificOutput JSON on stdout.

Source: Claude Code hooks reference (https://code.claude.com/docs/en/hooks)
"""
import json
import sys

from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.feedback.checker import PolicyViolationChecker


def main():
    hook_input = json.load(sys.stdin)
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Build searchable text from tool input
    text_parts = []
    if tool_name == "Bash":
        text_parts.append(tool_input.get("command", ""))
    elif tool_name in ("Write", "Edit"):
        text_parts.append(tool_input.get("file_path", ""))
        text_parts.append(tool_input.get("content", "")[:500])  # Cap for perf
    search_text = " ".join(text_parts)

    if not search_text.strip():
        sys.exit(0)  # Nothing to check

    store = ConstraintStore()
    checker = PolicyViolationChecker(store)
    should_suppress, matched = checker.check(search_text)

    if matched is None:
        sys.exit(0)  # No match, allow

    severity = matched.get("severity", "warning")
    constraint_text = matched.get("text", "Unknown constraint")
    constraint_id = matched.get("constraint_id", "unknown")

    if should_suppress:
        # forbidden or requires_approval -> deny
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"GOVERNANCE: Blocked by constraint {constraint_id}: "
                    f"{constraint_text}"
                ),
            }
        }
    else:
        # warning -> allow with context
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    f"GOVERNANCE WARNING: Constraint {constraint_id} "
                    f"({severity}): {constraint_text}"
                ),
            }
        }

    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
```

**Hook configuration (project .claude/settings.json):**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/src/pipeline/live/hooks/governance_check.py",
            "timeout": 5,
            "statusMessage": "Checking governance constraints..."
          }
        ]
      }
    ]
  }
}
```

### Pattern 2: SessionStart Hook as Constraint Briefing (LIVE-02)

**What:** A SessionStart hook that loads active constraints, filters by project scope, ranks by durability score, and injects a briefing into Claude's context via `additionalContext`.

**When to use:** Every new session and resume. Use the matcher to fire on `startup` and `resume`.

**Example output (JSON on stdout):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "GOVERNANCE BRIEFING: 12 active constraints for this project.\n\nCRITICAL (low durability, frequently violated):\n- [bbd376a2] \"Let's think about why didn't you catch the errors that you fixed?\" (3% durability, violated 37/38 sessions)\n- [a1b2c3d4] \"Do not modify schema without explicit approval\" (forbidden)\n\nACTIVE CONSTRAINTS:\n- [e5f6g7h8] \"Always run tests after code changes\" (warning, 85% durability)\n..."
  }
}
```

### Pattern 3: JSONL Stream Processor with FSEvents (LIVE-03)

**What:** A long-running Python process that uses `watchdog` to monitor Claude Code JSONL files for modifications, reads new lines as they're appended, converts them to lightweight event representations, and runs EscalationDetector + AmnesiaDetector incrementally.

**When to use:** Runs as a background daemon alongside Claude Code sessions. Started by the governance bus or manually.

**Key design consideration:** The existing EscalationDetector and AmnesiaDetector operate on lists of TaggedEvent objects. For live use, they need an incremental adapter:
- EscalationDetector: maintains pending windows in memory, feeds events one at a time
- AmnesiaDetector: currently requires batch eval results; for live, needs a per-event constraint check adapter

```python
# Conceptual pattern for stream processing
from watchdog.observers import Observer
from watchdog.events import FileModifiedEvent, FileSystemEventHandler

class SessionFileHandler(FileSystemEventHandler):
    def __init__(self, session_id: str, processor):
        self.session_id = session_id
        self.processor = processor
        self.last_position = 0  # Track file read position

    def on_modified(self, event: FileModifiedEvent):
        if not event.src_path.endswith('.jsonl'):
            return
        # Read only new lines since last position
        with open(event.src_path, 'r') as f:
            f.seek(self.last_position)
            new_lines = f.readlines()
            self.last_position = f.tell()
        for line in new_lines:
            self.processor.process_event(line, self.session_id)
```

### Pattern 4: Inter-Session Bus (LIVE-04)

**What:** A lightweight local HTTP service on a Unix domain socket that provides shared state across parallel Claude Code sessions.

**When to use:** When multiple Claude Code sessions need to share constraint state, coordinate governance decisions, or broadcast alerts.

**Key design decisions:**
- Unix domain socket at `/tmp/ope-governance-bus.sock` (fast, no port conflicts)
- Starlette ASGI app served by uvicorn
- In-memory state with optional DuckDB persistence
- Sessions register on start, deregister on end (SessionStart/SessionEnd hooks)

```python
# Conceptual bus server pattern
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# In-memory shared state
state = {
    "sessions": {},        # session_id -> {registered_at, project_dir, ...}
    "constraints": [],     # Active constraints cache
    "events": [],          # Recent governance events (ring buffer)
}

async def check_constraint(request: Request):
    body = await request.json()
    # Run PolicyViolationChecker against shared constraint state
    # Return allow/warn/deny
    return JSONResponse({"decision": "allow", "matched": None})

async def register_session(request: Request):
    body = await request.json()
    state["sessions"][body["session_id"]] = body
    return JSONResponse({"ok": True})

app = Starlette(routes=[
    Route("/api/check", check_constraint, methods=["POST"]),
    Route("/api/sessions", register_session, methods=["POST"]),
])

# Run with: uvicorn bus.server:app --uds /tmp/ope-governance-bus.sock
```

### Pattern 5: Governing Session (LIVE-05)

**What:** A dedicated Claude Code instance (started with `claude --agent governor`) that monitors all other active sessions via the bus, maintains the authoritative constraint store, and can broadcast blocks or briefings.

**When to use:** When running multiple parallel sessions that need centralized governance oversight.

**Key insight from agent teams research:** Claude Code's experimental agent teams feature already provides inter-session communication via shared task lists and mailboxes. However, for governance, a simpler model works better: one long-running session with hooks that consume bus events. The governing session does NOT need to be a team lead -- it just needs to:
1. Register itself as the governor on the bus
2. Poll/subscribe to governance events from the bus
3. React to escalation and amnesia signals
4. Broadcast governance decisions to active sessions

### Anti-Patterns to Avoid

- **DO NOT put heavy computation in PreToolUse hooks.** The hook blocks the tool call. Keep it under 200ms. If analysis is needed, use PostToolUse async hooks for non-blocking work and PreToolUse only for fast constraint checks.
- **DO NOT re-parse the entire JSONL file on each modification event.** Track file position and only read new lines. JSONL files grow to 14MB+.
- **DO NOT use TCP localhost when Unix sockets are available.** Unix sockets eliminate TCP overhead and port conflict issues.
- **DO NOT load constraints from disk on every hook invocation.** Cache them in the bus or use a long-running daemon. Python startup + JSON parse takes ~50ms; cached check takes <1ms.
- **DO NOT try to use Claude Code agent teams for the governing session.** Agent teams are experimental, designed for parallel development work, and add massive token overhead. A simple dedicated session with custom hooks is better.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File system monitoring | Custom FSEvents bindings or polling loops | watchdog 6.0.0 | Handles platform detection, event coalescing, thread management; macOS FSEvents is ~10ms latency |
| HTTP IPC server | Raw socket protocol or custom TCP server | uvicorn + starlette (already installed) | Production-quality ASGI server with Unix socket support, routing, middleware |
| HTTP client for hooks | subprocess curl or raw socket | httpx (already installed) | Async support, connection pooling, Unix socket transport via `httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds="/tmp/sock"))` |
| JSON schema validation | Manual dict checking | Pydantic v2 models | Already project standard; provides serialization, validation, and type hints |
| Constraint checking | New regex engine for hooks | PolicyViolationChecker (already built) | Pre-compiled regex, handles severity levels, already tested |
| Escalation detection | New pattern matcher | EscalationDetector (already built) | Sliding window algorithm, exempt tools, bypass patterns all implemented |

**Key insight:** The existing pipeline components (PolicyViolationChecker, EscalationDetector, AmnesiaDetector, ConstraintStore) are all designed as pure-function classes that take inputs and return results. They need thin adapters for live use, not rewrites.

## Common Pitfalls

### Pitfall 1: Python Startup Time in Hook Scripts
**What goes wrong:** Each PreToolUse hook invocation spawns a new Python process. Python 3.13 cold start is 50-100ms. With imports (Pydantic, DuckDB, etc.), it can reach 200-500ms.
**Why it happens:** Claude Code hooks are shell commands, not persistent processes.
**How to avoid:** Three strategies, in order of preference:
1. **Minimize imports:** The hook script should import only what's needed. PolicyViolationChecker + ConstraintStore + json + sys is ~30ms.
2. **Pre-warm with bus:** If the bus is running, the hook calls `httpx.get("http+unix:///tmp/ope-governance-bus.sock/api/check")` which is ~5ms. The bus keeps the checker in memory.
3. **Use a compiled shim:** A small Go/Rust binary that does the HTTP call and returns JSON. Eliminates Python startup entirely for the common path.
**Warning signs:** PreToolUse hook taking >200ms visible in `claude --debug` output.

### Pitfall 2: JSONL File Locking and Partial Writes
**What goes wrong:** Reading the JSONL file while Claude Code is writing to it can yield partial JSON lines (truncated at the last `\n`).
**Why it happens:** Claude Code appends events line-by-line. The tail reader may see a line before the full `\n` is written.
**How to avoid:** Always read complete lines (ending with `\n`). Buffer incomplete trailing content and retry on next modification event. Use `readline()` which naturally handles this.
**Warning signs:** `json.JSONDecodeError` on the last line of a read batch.

### Pitfall 3: Hook JSON Output Contamination
**What goes wrong:** Claude Code fails to parse hook output because non-JSON text is mixed into stdout (e.g., from Python warnings, loguru output, or shell profile messages).
**Why it happens:** The hook protocol requires stdout to contain ONLY the JSON object. Any other text causes a parse failure.
**How to avoid:** Redirect all logging to stderr. Set `PYTHONDONTWRITEBYTECODE=1`. Suppress loguru stdout sinks. Test hooks with `echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 hook.py` and verify stdout is pure JSON.
**Warning signs:** Hook appears to run but has no effect; `claude --debug` shows "JSON validation failed."

### Pitfall 4: Stale State After Constraint Updates
**What goes wrong:** The hook script loads constraints at startup and never refreshes. New constraints added via `govern ingest` are not enforced.
**Why it happens:** Each hook invocation is independent -- it loads `data/constraints.json` fresh. But if a bus cache is used, the cache goes stale.
**How to avoid:** The bus should reload constraints when `data/constraints.json` changes (use watchdog on that file too). For non-bus mode, fresh loading on each invocation is correct but slow.
**Warning signs:** New constraints not being enforced; stale constraint count in briefings.

### Pitfall 5: FSEvents Coalescing on macOS
**What goes wrong:** macOS FSEvents coalesces rapid file modifications into a single event. If Claude Code writes 10 events in quick succession, the watcher may only fire once.
**Why it happens:** FSEvents is designed for efficiency, not per-write notifications.
**How to avoid:** On each notification, read ALL new content from the tracked file position to current end. Don't assume one notification = one new line.
**Warning signs:** Missing events in the stream processor; event count lower than expected.

### Pitfall 6: Multiple Sessions Writing to Same Governance State
**What goes wrong:** Two sessions both modify `data/constraints.json` or the DuckDB database simultaneously, causing corruption or lost writes.
**Why it happens:** No locking mechanism between independent Claude Code sessions.
**How to avoid:** This is the entire reason for the governance bus (LIVE-04). All state mutations go through the bus, which serializes them. Direct file access is read-only from sessions.
**Warning signs:** Duplicate constraint IDs, missing governance events, DuckDB lock errors.

## Code Examples

### Claude Code Hook Input/Output Protocol

Source: https://code.claude.com/docs/en/hooks (verified 2026-02-20)

**PreToolUse input (stdin):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "cwd": "/Users/david/projects/orchestrator-policy-extraction",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "rm -rf /tmp/build"
  },
  "tool_use_id": "toolu_01ABC123..."
}
```

**PreToolUse output - deny (stdout):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Blocked by governance constraint: reason here"
  }
}
```

**PreToolUse output - allow with warning (stdout):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "GOVERNANCE WARNING: Constraint X applies. Proceed with caution."
  }
}
```

**PreToolUse output - allow (exit 0, no stdout):**
```bash
exit 0  # No output needed, tool call proceeds normally
```

**SessionStart output - briefing (stdout):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "GOVERNANCE BRIEFING: 12 active constraints..."
  }
}
```

### JSONL Session File Event Types

Source: Empirical analysis of `~/.claude/projects/` JSONL files

Each line is a JSON object with a `type` field. Key types observed:
```
file-history-snapshot  # File state snapshot at session start
progress               # Hook execution progress events
user                   # User messages (contains .message.content)
assistant              # Claude responses and tool calls (contains .message.content[])
                       # Tool calls have content items with type: "tool_use"
```

Tool call events in `assistant` type have this structure:
```json
{
  "type": "assistant",
  "sessionId": "uuid",
  "message": {
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_...",
        "name": "Write",
        "input": { "file_path": "...", "content": "..." }
      }
    ]
  },
  "timestamp": "2026-02-17T21:15:03.123Z"
}
```

### User's Existing Hook Implementations

Source: `~/.claude/settings.json` (verified on disk)

The user already has two hooks configured:
1. **SessionStart:** `gsd-check-update.js` -- Spawns a background process, exits immediately (non-blocking pattern)
2. **PreToolUse (WebSearch):** `redirect-to-perplexity.sh` -- Reads stdin with `cat`, extracts with `jq`, returns deny JSON with `jq -n`

The redirect-to-perplexity.sh is the exact pattern needed for governance:
```bash
#!/bin/bash
INPUT=$(cat)
QUERY=$(echo "$INPUT" | jq -r '.tool_input.query // empty')
# ... process ...
jq -n --arg reason "blocked" '{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": $reason
  }
}'
```

### httpx Unix Socket Client

Source: httpx documentation (training data, MEDIUM confidence)

```python
import httpx

# Synchronous client for hook scripts
transport = httpx.HTTPTransport(uds="/tmp/ope-governance-bus.sock")
with httpx.Client(transport=transport, base_url="http://localhost") as client:
    response = client.post("/api/check", json={
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /tmp"}
    })
    result = response.json()
    # {"decision": "deny", "constraint_id": "abc123", "reason": "..."}

# Async client for bus internals
async_transport = httpx.AsyncHTTPTransport(uds="/tmp/ope-governance-bus.sock")
async with httpx.AsyncClient(transport=async_transport, base_url="http://localhost") as client:
    response = await client.post("/api/check", json={...})
```

### uvicorn Unix Domain Socket Server

Source: uvicorn documentation (verified: uvicorn 0.40.0 installed)

```python
# Start the bus server on a Unix domain socket
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.pipeline.live.bus.server:app",
        uds="/tmp/ope-governance-bus.sock",
        log_level="info",
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Exit code only hook decisions | JSON `hookSpecificOutput` with `permissionDecision` | Claude Code hooks reference (current) | Richer control: allow/deny/ask instead of just block/allow |
| Top-level `decision`/`reason` in PreToolUse | `hookSpecificOutput.permissionDecision` | Current (old format deprecated) | Must use new format; old `"approve"`/`"block"` values mapped to `"allow"`/`"deny"` |
| Polling-based file watching | FSEvents via watchdog | watchdog 6.0.0 (Nov 2024) | ~10ms notification latency vs 100-500ms polling |
| Batch pipeline processing | Hook-based real-time interception | Claude Code hooks feature | Transforms from post-hoc analysis to prospective governance |
| Agent teams for coordination | Custom hooks + shared bus | Architecture decision | Agent teams too heavyweight (experimental, high token cost) for governance |

**Deprecated/outdated:**
- PreToolUse `decision: "block"/"approve"` format is deprecated; use `hookSpecificOutput.permissionDecision: "deny"/"allow"` instead
- `CGIHTTPRequestHandler` for HTTP serving is deprecated; use ASGI (starlette+uvicorn)

## Claude Code Hooks Deep Reference

### All Hook Events Relevant to Governance

| Event | Governance Use | Can Block? | Latency Budget |
|-------|---------------|------------|----------------|
| `SessionStart` (matcher: `startup\|resume`) | Constraint briefing (LIVE-02) | No | <500ms (runs once) |
| `PreToolUse` (matcher: `Bash\|Write\|Edit`) | Constraint enforcement (LIVE-01) | YES: `permissionDecision: "deny"` | <200ms target |
| `PostToolUse` (async, matcher: `Bash\|Write\|Edit`) | Event logging to bus | No (async) | No limit (background) |
| `SessionEnd` | Deregister from bus, cleanup | No | <1s (cleanup) |
| `SubagentStart` | Inject governance context into subagents | No | <200ms |
| `Stop` | Final governance check before session ends | YES | <500ms |

### Hook Configuration Locations (Priority Order)

1. `~/.claude/settings.json` -- Global, all projects (user already has hooks here)
2. `.claude/settings.json` -- Project-specific, committable
3. `.claude/settings.local.json` -- Project-specific, gitignored (user already has permissions here)

**Recommendation:** Governance hooks should go in `.claude/settings.json` (committable, project-scoped) so they travel with the project. The bus server address can be configured via environment variable in `.claude/settings.local.json`.

### Key Constraints from Hook Protocol

1. **Hooks are shell commands.** Python scripts must be invokable as `python3 script.py`. The script receives JSON on stdin, returns JSON on stdout.
2. **Exit code semantics are fixed.** Exit 0 = success (parse stdout JSON). Exit 2 = blocking error (stderr fed to Claude). Any other exit = non-blocking error (ignored).
3. **Hooks snapshot at startup.** Changes to hook configuration during a session require `/hooks` menu review. This means governance hook updates need a session restart or explicit user approval.
4. **Multiple hooks run in parallel.** If both a governance hook and the existing redirect-to-perplexity hook match, they run simultaneously. Design for this.
5. **Default timeout is 600 seconds** for command hooks. Set explicit short timeouts (5-10s) for governance hooks to fail fast.
6. **async hooks cannot block.** Only synchronous PreToolUse hooks can deny tool calls. PostToolUse async hooks are fire-and-forget.
7. **additionalContext is the primary feedback channel.** For SessionStart and non-blocking PreToolUse, inject governance information via `additionalContext` which goes into Claude's context.

## Latency Budget Analysis

For LIVE-01 (PreToolUse constraint check, <200ms target):

| Component | Estimated Latency | Notes |
|-----------|------------------|-------|
| Shell spawn + Python startup | 50-80ms | Python 3.13, minimal imports |
| stdin JSON parse | <1ms | Small payload |
| ConstraintStore load (JSON file) | 10-20ms | 208 constraints, ~100KB |
| PolicyViolationChecker init (regex compile) | 5-10ms | Pre-compiled patterns |
| PolicyViolationChecker.check() | <1ms | Regex matching |
| stdout JSON serialize | <1ms | Small response |
| **Total (direct file mode)** | **~70-110ms** | **Within 200ms budget** |

Alternative with bus:

| Component | Estimated Latency | Notes |
|-----------|------------------|-------|
| Shell spawn + Python startup | 50-80ms | Minimal imports (just httpx + json) |
| httpx Unix socket POST | 1-5ms | Local IPC, no network |
| Bus constraint check (in-memory) | <1ms | Pre-loaded, pre-compiled |
| **Total (bus mode)** | **~55-90ms** | **Well within budget** |

Further optimization (if needed):
- **Compiled shim:** Replace Python with a Go/Rust binary that does the HTTP call. Startup: <5ms. Total: ~10ms.
- **Bash-only hook:** Use `curl --unix-socket` directly. No Python startup. Total: ~15ms.

## Open Questions

1. **Hook script vs bus-first architecture?**
   - What we know: Direct file-based checking works within latency budget (~100ms). Bus-based checking is faster for repeated calls (~60ms) but requires the bus to be running.
   - What's unclear: Should the hook script work standalone (load constraints from file) with optional bus enhancement? Or should it require the bus?
   - Recommendation: Design for standalone-first with bus as optimization. The hook should load from file if bus is unreachable, call bus if available.

2. **EscalationDetector incremental adapter complexity?**
   - What we know: EscalationDetector maintains pending windows and walks events in order. It currently takes a full list of TaggedEvents.
   - What's unclear: Can the sliding window state be cleanly maintained across stream processor invocations? What happens when a session is resumed after a gap?
   - Recommendation: Create an `IncrementalEscalationDetector` wrapper that holds `_PendingWindow` state and accepts one event at a time. On session resume, replay last N events to rebuild window state.

3. **JSONL event-to-TaggedEvent conversion for live use?**
   - What we know: The batch pipeline converts raw JSONL -> CanonicalEvent -> TaggedEvent through a multi-pass tagger. This is too heavy for real-time.
   - What's unclear: What subset of tagging is needed for live governance? Can we tag incrementally?
   - Recommendation: Create a lightweight `LiveEventAdapter` that converts raw JSONL directly to a minimal tagged representation (tool_name, command_text, file_path, basic tag inference). Full batch tagging remains for post-hoc analysis.

4. **Governing session lifecycle management?**
   - What we know: Claude Code sessions end when the user exits or context fills. A governing session would need to be long-lived.
   - What's unclear: How to keep a governing session alive? Should it auto-restart? Should it use `--resume`?
   - Recommendation: The governor should be a Python daemon process, not a Claude Code session. It monitors the bus, runs detectors, and takes autonomous action. A Claude Code "governing session" can be started on-demand to review governance state and make decisions that require LLM reasoning.

5. **Constraint scope filtering for briefings?**
   - What we know: Constraints have `scope_paths` fields. The SessionStart hook receives `cwd` in its input.
   - What's unclear: How precise should scope matching be? Exact path prefix? Glob matching?
   - Recommendation: Use path prefix matching (`cwd.startswith(scope_path)`) for v1. Log unmatched constraints for gap analysis.

## Sources

### Primary (HIGH confidence)
- Claude Code hooks reference: https://code.claude.com/docs/en/hooks -- Complete hook protocol, all event types, JSON schemas, decision control
- Claude Code agent teams: https://code.claude.com/docs/en/agent-teams -- Team architecture, limitations, communication model
- User's existing hooks: `~/.claude/settings.json` -- Working PreToolUse (deny) and SessionStart (background) implementations
- User's existing JSONL files: `~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/*.jsonl` -- Verified event structure
- Existing codebase: `src/pipeline/feedback/checker.py`, `src/pipeline/escalation/detector.py`, `src/pipeline/durability/amnesia.py`, `src/pipeline/constraint_store.py` -- All verified on disk

### Secondary (MEDIUM confidence)
- watchdog 6.0.0: https://github.com/gorakhargosh/watchdog -- Version, FSEvents support on macOS, API pattern
- httpx Unix socket support -- From installed package (0.28.1) and training data
- uvicorn Unix socket support -- From installed package (0.40.0), `--uds` flag
- starlette routing -- From installed package (0.52.1)

### Tertiary (LOW confidence)
- Python 3.13 startup time estimates (~50-80ms) -- From training data, not benchmarked
- FSEvents coalescing behavior -- From watchdog docs + training data, not empirically tested on this project
- httpx `AsyncHTTPTransport(uds=...)` API -- From training data, should be verified with installed version

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Verified installed packages, verified existing codebase components, verified hook protocol from official docs
- Architecture: HIGH -- Based on verified hook protocol, verified existing components, and verified IPC libraries already installed
- Pitfalls: MEDIUM -- Based on combination of official docs (hook protocol issues) and training data (Python startup, FSEvents coalescing)
- Latency estimates: LOW -- Estimates from training data, not benchmarked; should be validated in Phase 15

**Research date:** 2026-02-20
**Valid until:** 2026-04-20 (stable domain -- Claude Code hooks protocol unlikely to change drastically)
