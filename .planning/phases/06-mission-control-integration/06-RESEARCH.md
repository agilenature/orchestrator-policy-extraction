# Phase 6: Mission Control Integration - Research

**Researched:** 2026-02-11
**Domain:** Next.js dashboard integration, SQLite episode storage, real-time event capture, WebSocket tool provenance, review UI, DuckDB-SQLite bridging
**Confidence:** MEDIUM (Mission Control repo structure verified via GitHub; OpenClaw Gateway API internals are NOT publicly documented at protocol level; DuckDB SQLite extension verified; Next.js 15 + SSE patterns well-established)

---

## Summary

Phase 6 shifts episode capture from batch post-hoc JSONL parsing (Phases 1-5) to real-time structured capture within Mission Control. Mission Control is a Next.js 15 + SQLite dashboard at `github.com/crshdn/mission-control` that manages AI agent tasks through a lifecycle (PLANNING -> INBOX -> ASSIGNED -> IN PROGRESS -> TESTING -> REVIEW -> DONE), dispatches to agents via OpenClaw Gateway over WebSocket (port 18789), and already has a real-time SSE infrastructure for broadcasting events to connected clients.

The integration requires four capabilities: (1) real-time episode capture from the task lifecycle, (2) tool provenance streaming from the OpenClaw Gateway WebSocket connection, (3) a review widget for reaction labeling with inline constraint extraction, and (4) SQLite tables for episode storage that the existing Python analytics pipeline can query via DuckDB's SQLite extension. The existing Python pipeline (Phases 1-5) stores episodes in DuckDB with a hybrid flat+STRUCT+JSON schema; the bridge between SQLite (Next.js writes) and DuckDB (Python reads) is DuckDB's native SQLite extension, which supports bidirectional read/write via `ATTACH 'mission-control.db' (TYPE sqlite)`.

The largest technical uncertainty is the OpenClaw Gateway WebSocket API. The Gateway runs on port 18789 and communicates via JSON messages over WebSocket, but the exact RPC method names, message schemas for tool call streaming, and subscription mechanisms are NOT publicly documented. The Gateway stores session transcripts as JSONL files in `~/.openclaw/agents/*/sessions/*.jsonl` with fields like `type` (human/assistant/tool), `content`, `tool_name`, `tool_input`, `tool_result`. Mission Control already has a WebSocket client (`src/lib/openclaw/client`) that connects to the Gateway -- the integration should extend this existing client rather than building a new one.

**Primary recommendation:** Work inside Mission Control's existing Next.js 15 codebase. Add SQLite tables for episodes/events/constraints/approvals/commit_links. Extend the existing OpenClaw Gateway WebSocket client to capture tool provenance events. Build the review widget as a React component using Next.js 15 Server Actions. Use DuckDB's SQLite extension for the Python pipeline to read Mission Control's SQLite database directly, eliminating the need for data synchronization.

---

## Standard Stack

### Core (Mission Control Side -- TypeScript/Next.js)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | 15 (already in MC) | Full-stack framework: React UI + API routes + Server Actions | Already the foundation of Mission Control |
| better-sqlite3 | latest (already in MC) | Synchronous SQLite access from Node.js for episode tables | Already used by Mission Control for task storage; WAL mode for concurrent reads |
| React | 19 (already in MC) | Review widget UI, live episode stream components | Already in Mission Control; useActionState for form handling |
| Tailwind CSS | latest (already in MC) | Styling for review widget and episode dashboard | Already in Mission Control |
| ws | latest (already in MC) | WebSocket client for OpenClaw Gateway | Already used by Mission Control's `src/lib/openclaw/client` |
| EventSource/SSE | built-in | Real-time broadcast of episode events to dashboard clients | Already implemented in MC at `/api/events/stream` |

### Core (Python Pipeline Side -- Analytics Bridge)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.4.4 (installed) | Query Mission Control's SQLite via `ATTACH ... (TYPE sqlite)` | Already the project database; SQLite extension enables cross-database queries |
| pydantic | 2.11.7 (installed) | Episode model validation when importing from SQLite | Already used throughout pipeline |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| zod | latest (likely in MC) | TypeScript schema validation for episode/review payloads | All API route input validation |
| uuid | built-in (Node.js) | Generate episode_id, event_id, constraint_id | All entity creation |
| lucide-react | latest (likely in MC) | Icons for reaction buttons in review widget | Review widget UI |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB SQLite extension | Explicit sync (export SQLite -> import DuckDB) | Sync adds complexity, delay, and failure modes; ATTACH is transparent and real-time |
| SSE for live updates | WebSocket from MC to browser | MC already uses SSE with 30s keep-alive; adding WS would be redundant infrastructure |
| better-sqlite3 | Prisma/Drizzle ORM | ORM adds abstraction layer over simple table operations; MC already uses raw better-sqlite3 |
| Server Actions for review | Traditional API routes (POST /api/episodes/review) | Server Actions are idiomatic Next.js 15 and handle form state, loading, and error natively |
| SQLite for episode storage | Keep DuckDB only, write from Next.js | DuckDB has no stable Node.js driver for concurrent writes from a web server; SQLite is MC's native DB |

**Installation (Mission Control side):**
```bash
# No new dependencies needed -- all libraries already in Mission Control
# The review widget and episode tables are new CODE, not new LIBRARIES
```

**Installation (Python pipeline side):**
```bash
# DuckDB SQLite extension auto-loads on ATTACH
# No new Python packages needed
```

---

## Architecture Patterns

### Recommended Project Structure (Changes to Mission Control)

```
mission-control/
  src/
    app/
      api/
        episodes/              # NEW: Episode CRUD + streaming
          route.ts             # GET (list), POST (create from task lifecycle)
          [id]/
            route.ts           # GET (single), PATCH (update with reaction)
            events/
              route.ts         # GET (episode events), POST (append event)
          stream/
            route.ts           # SSE endpoint for live episode events
        constraints/           # NEW: Constraint management
          route.ts             # GET (list), POST (extract from review)
      components/
        ReviewWidget.tsx       # NEW: Reaction labeling + constraint extraction
        EpisodeCard.tsx        # NEW: Episode summary card
        EpisodeTimeline.tsx    # NEW: Live event stream view
        ConstraintForm.tsx     # NEW: Inline constraint extraction form
    lib/
      db/
        episodes.ts            # NEW: Episode SQLite operations
        constraints.ts         # NEW: Constraint SQLite operations
        schema-episodes.ts     # NEW: CREATE TABLE statements for episode tables
      openclaw/
        provenance.ts          # NEW: Tool provenance capture from Gateway WS
      episodes/
        builder.ts             # NEW: Build episodes from task lifecycle events
        mapper.ts              # NEW: Map MC task fields to episode schema
  data/
    mission-control.db         # EXISTING: Add new tables alongside existing task tables
```

### Pattern 1: Task Lifecycle -> Episode Capture (Event Sourcing)

**What:** Each task lifecycle transition in Mission Control produces an episode event. The task lifecycle IS the episode boundary structure -- no post-hoc segmentation needed.

**When to use:** For MC-01 (real-time episode capture from structured tasks).

**Mapping:**

| MC Task State Transition | Episode Event | Episode Boundary |
|--------------------------|---------------|------------------|
| Task CREATED | Episode created with observation (initial context) | Episode START |
| PLANNING -> INBOX | Planning output attached as orchestrator_action | -- |
| INBOX -> ASSIGNED | Agent assignment recorded | -- |
| ASSIGNED -> IN PROGRESS | Execution begins; tool provenance streaming starts | -- |
| IN PROGRESS -> TESTING | Test results captured as outcome.quality | -- |
| TESTING -> REVIEW | Episode outcome populated; awaiting reaction | Decision BOUNDARY |
| REVIEW -> DONE (approve) | Reaction label = "approve" | Episode END |
| REVIEW -> corrections | Reaction label = "correct"/"redirect"/"block" + constraint extraction | Episode END |

```typescript
// Source: Derived from MC task lifecycle + AUTHORITATIVE_DESIGN.md Part 6
interface EpisodeFromTask {
  episode_id: string;           // UUID generated at task creation
  task_id: string;              // MC task ID (the stable join key)
  timestamp: string;            // ISO 8601

  // Populated at PLANNING -> INBOX
  observation: {
    repo_state: { changed_files: string[]; diff_stat: DiffStat };
    quality_state: { tests_status: string; lint_status: string };
    context: { recent_summary: string; open_questions: string[]; constraints_in_force: string[] };
  };

  // Populated at PLANNING output
  orchestrator_action: {
    mode: 'Explore' | 'Plan' | 'Implement' | 'Verify' | 'Integrate' | 'Triage' | 'Refactor';
    goal: string;
    scope: { paths: string[]; avoid: string[] };
    executor_instruction: string;
    gates: Gate[];
    risk: 'low' | 'medium' | 'high' | 'critical';
  };

  // Populated during IN PROGRESS (streaming) and at TESTING
  outcome: {
    executor_effects: { tool_calls_count: number; files_touched: string[]; commands_ran: string[]; git_events: GitEvent[] };
    quality: { tests_status: string; lint_status: string; diff_stat: DiffStat };
    reaction: { label: string; message: string; confidence: number } | null;
    reward_signals: { objective: ObjectiveRewards };
  };

  // Populated at REVIEW if correct/block
  constraints_extracted: ConstraintRef[];
}
```

### Pattern 2: DuckDB SQLite Bridge (Zero-Copy Analytics)

**What:** The Python pipeline reads Mission Control's SQLite database directly via DuckDB's SQLite extension. No data export, no sync, no message queues.

**When to use:** For MC-04 (dashboard integration) and connecting Phase 5 RAG/shadow mode to real-time episodes.

```python
# Source: DuckDB SQLite extension docs (https://duckdb.org/docs/stable/core_extensions/sqlite.html)
import duckdb

def query_mc_episodes(mc_db_path: str, ope_db_path: str = "data/ope.db"):
    """Query Mission Control episodes from the Python analytics pipeline."""
    conn = duckdb.connect(ope_db_path)

    # Attach Mission Control's SQLite database
    conn.execute(f"ATTACH '{mc_db_path}' AS mc (TYPE sqlite)")

    # Query episodes directly -- DuckDB handles SQLite JSON columns
    episodes = conn.execute("""
        SELECT
            e.episode_id,
            e.task_id,
            e.mode,
            e.risk,
            e.reaction_label,
            e.observation,       -- JSON column, queryable via json_extract
            e.orchestrator_action,
            e.outcome
        FROM mc.episodes e
        WHERE e.reaction_label IS NOT NULL
        ORDER BY e.created_at DESC
    """).fetchall()

    # Can also INSERT INTO the main DuckDB episodes table
    conn.execute("""
        INSERT INTO episodes
        SELECT ... FROM mc.episodes WHERE ...
    """)

    return episodes
```

### Pattern 3: OpenClaw Gateway Provenance Capture

**What:** Extend Mission Control's existing OpenClaw WebSocket client to capture tool provenance events during task execution and store them as episode_events.

**When to use:** For MC-02 (tool provenance streaming).

```typescript
// Source: MC architecture (src/lib/openclaw/client) + OpenClaw session JSONL format
// IMPORTANT: Gateway API internals are not fully documented.
// This pattern is based on the known JSONL session format and MC's existing WS client.

interface ToolProvenanceEvent {
  event_id: string;
  episode_id: string;
  timestamp: string;
  event_type: 'tool_call' | 'tool_result' | 'file_touch' | 'command_run' | 'test_result' | 'git_event';
  payload: {
    tool_name?: string;       // Read, Edit, Bash, Write, Grep, Glob
    tool_input?: Record<string, unknown>;
    tool_result?: string;
    files_touched?: string[];
    command?: string;
    exit_code?: number;
    git_ref?: string;
  };
}

// Extend the existing MC OpenClaw client to capture provenance
class ProvenanceCapture {
  private db: Database;
  private currentEpisodeId: string | null = null;

  onGatewayMessage(message: GatewayMessage): void {
    // Filter for tool-related messages from the agent session
    if (message.type === 'assistant' && message.content) {
      // Extract tool_use blocks from assistant content
      for (const block of message.content) {
        if (block.type === 'tool_use') {
          this.recordToolCall(block.name, block.input);
        }
      }
    }

    if (message.type === 'tool' || (message.type === 'user' && message.tool_result)) {
      // Tool result -- capture outcome
      this.recordToolResult(message.tool_name, message.tool_result);
    }
  }

  private recordToolCall(toolName: string, toolInput: unknown): void {
    if (!this.currentEpisodeId) return;

    const event: ToolProvenanceEvent = {
      event_id: crypto.randomUUID(),
      episode_id: this.currentEpisodeId,
      timestamp: new Date().toISOString(),
      event_type: 'tool_call',
      payload: { tool_name: toolName, tool_input: toolInput as Record<string, unknown> },
    };

    this.db.prepare(`
      INSERT INTO episode_events (event_id, episode_id, timestamp, event_type, payload)
      VALUES (?, ?, ?, ?, ?)
    `).run(event.event_id, event.episode_id, event.timestamp, event.event_type, JSON.stringify(event.payload));
  }
}
```

### Pattern 4: Review Widget with Reaction + Constraint Extraction

**What:** A React component in Mission Control's REVIEW stage that captures structured reaction labels and optionally extracts constraints from corrections/blocks.

**When to use:** For MC-03 (review widget).

```tsx
// Source: Next.js 15 Server Actions + project episode schema
// This is the core UI component for human-in-the-loop feedback

'use client';

import { useState } from 'react';

const REACTION_LABELS = ['approve', 'correct', 'redirect', 'block', 'question'] as const;
type ReactionLabel = typeof REACTION_LABELS[number];

interface ReviewWidgetProps {
  episodeId: string;
  taskId: string;
  episodeSummary: {
    mode: string;
    goal: string;
    filesChanged: number;
    testsStatus: string;
    lintStatus: string;
  };
}

export function ReviewWidget({ episodeId, taskId, episodeSummary }: ReviewWidgetProps) {
  const [reaction, setReaction] = useState<ReactionLabel | null>(null);
  const [message, setMessage] = useState('');
  const [showConstraintForm, setShowConstraintForm] = useState(false);
  const [constraint, setConstraint] = useState({
    text: '',
    severity: 'warning' as 'warning' | 'requires_approval' | 'forbidden',
    scopePaths: [] as string[],
    detectionHints: [] as string[],
  });

  const needsConstraint = reaction === 'correct' || reaction === 'block';

  async function handleSubmit() {
    const payload = {
      episode_id: episodeId,
      task_id: taskId,
      reaction: { label: reaction, message, confidence: 1.0 },
      constraint: showConstraintForm ? constraint : null,
    };

    await fetch('/api/episodes/' + episodeId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    // SSE broadcast handled server-side
  }

  return (
    <div className="p-6 border rounded-lg space-y-4">
      <div className="flex gap-2">
        {REACTION_LABELS.map(label => (
          <button
            key={label}
            onClick={() => { setReaction(label); setShowConstraintForm(false); }}
            className={`px-4 py-2 rounded ${reaction === label ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}
          >
            {label.charAt(0).toUpperCase() + label.slice(1)}
          </button>
        ))}
      </div>

      <textarea
        value={message}
        onChange={e => setMessage(e.target.value)}
        placeholder="Optional feedback message..."
        className="w-full p-2 border rounded"
      />

      {needsConstraint && !showConstraintForm && (
        <button onClick={() => setShowConstraintForm(true)} className="text-blue-600 underline">
          Extract a constraint from this correction?
        </button>
      )}

      {showConstraintForm && (
        <ConstraintExtractionForm constraint={constraint} onChange={setConstraint} />
      )}

      <button onClick={handleSubmit} disabled={!reaction} className="px-6 py-2 bg-green-600 text-white rounded">
        Submit Review
      </button>
    </div>
  );
}
```

### Pattern 5: SSE Broadcast for Live Episode Events

**What:** Extend Mission Control's existing SSE endpoint (`/api/events/stream`) to broadcast episode lifecycle events (creation, provenance updates, review submissions) to connected dashboard clients.

**When to use:** For real-time dashboard updates as episodes are captured.

```typescript
// Source: MC's existing REALTIME_IMPLEMENTATION_SUMMARY.md pattern
// MC already has SSE at /api/events/stream with 30s keep-alive
// Extend with episode-specific event types

type EpisodeSSEEvent =
  | { type: 'episode_created'; episodeId: string; taskId: string; mode: string }
  | { type: 'episode_provenance'; episodeId: string; toolName: string; eventType: string }
  | { type: 'episode_reviewed'; episodeId: string; reactionLabel: string }
  | { type: 'constraint_extracted'; constraintId: string; text: string; severity: string };

// Client-side hook (extends MC's existing useSSE)
function useEpisodeStream() {
  const [episodes, setEpisodes] = useState<Map<string, Episode>>(new Map());

  useEffect(() => {
    const source = new EventSource('/api/events/stream');
    source.addEventListener('episode_created', (e) => { /* ... */ });
    source.addEventListener('episode_provenance', (e) => { /* ... */ });
    source.addEventListener('episode_reviewed', (e) => { /* ... */ });
    return () => source.close();
  }, []);

  return episodes;
}
```

### Anti-Patterns to Avoid

- **Dual-write to SQLite AND DuckDB:** Do NOT write episodes to both databases. Write to SQLite (Mission Control's DB) and read from DuckDB via the SQLite extension. This eliminates sync bugs and data divergence.
- **Polling for provenance:** Do NOT poll the Gateway for tool call status. Use the existing WebSocket connection to capture events as they stream. Mission Control already maintains this connection.
- **Custom WebSocket server for dashboard:** Do NOT add a WebSocket server to MC for live updates. MC already uses SSE with proven 100ms propagation latency and 50+ concurrent connections. Extend SSE, don't replace it.
- **Parsing JSONL files for real-time episodes:** The entire point of Phase 6 is to STOP parsing JSONL. Episodes are created structurally from task lifecycle events. JSONL remains only for batch pipeline (Phases 1-5) processing historical data.
- **Designing episode schema independent of existing Pydantic models:** The SQLite episode schema MUST map to the existing Python Episode Pydantic model (363 lines in `src/pipeline/models/episodes.py`). Use the same field names, same nesting structure serialized as JSON columns, same enum values.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQLite <-> DuckDB data sync | Custom export/import scripts, message queues, or CDC | DuckDB SQLite extension (`ATTACH ... TYPE sqlite`) | Transparent bidirectional access; zero sync overhead; verified working in DuckDB 1.4.4 |
| Real-time dashboard updates | Custom WebSocket server for browser clients | Mission Control's existing SSE infrastructure (`/api/events/stream`) | Already proven at 100ms latency, 50+ clients, with auto-reconnection and keep-alive |
| Task lifecycle state machine | Custom state machine for episode boundaries | Mission Control's existing task workflow (PLANNING -> ... -> REVIEW -> DONE) | Task states ARE the episode boundaries; don't duplicate logic |
| Constraint storage format | New constraint database schema | Reuse the existing `data/schemas/constraint.schema.json` and ConstraintStore format | Phase 3 already defined the constraint schema; Mission Control should produce compatible output |
| Episode model validation | Custom TypeScript validation | Zod schema generated from the existing JSON Schema (`orchestrator-episode.schema.json`) | Single source of truth for episode structure; TypeScript and Python both validate against it |
| Tool provenance parsing | Custom parser for Gateway messages | Extend MC's existing `src/lib/openclaw/client` WebSocket handler | MC already connects to Gateway; extend, don't rewrite |

**Key insight:** Phase 6 is primarily an INTEGRATION phase, not a greenfield build. Mission Control already has: SQLite, WebSocket to Gateway, SSE to browser, task lifecycle, and a React UI. The work is adding episode tables, provenance capture, review widget, and the DuckDB bridge -- all within MC's existing architecture.

---

## Common Pitfalls

### Pitfall 1: Schema Divergence Between SQLite and DuckDB Episode Models
**What goes wrong:** SQLite episode records don't match the Pydantic Episode model, causing import failures or silent data corruption when the Python pipeline queries via DuckDB.
**Why it happens:** TypeScript and Python teams evolve schemas independently; JSON column nesting differs; enum values drift.
**How to avoid:** Generate both the Zod (TypeScript) and Pydantic (Python) models from the SAME source: `data/schemas/orchestrator-episode.schema.json`. Run a cross-validation test that creates an episode in SQLite, reads it via DuckDB, and validates against the Pydantic model.
**Warning signs:** DuckDB `json_extract` returns NULL on fields that exist in SQLite; Pydantic validation errors when reading MC episodes; field name mismatches (camelCase vs snake_case).

### Pitfall 2: OpenClaw Gateway API Changes / Undocumented Behavior
**What goes wrong:** The provenance capture code breaks because the Gateway changes its WebSocket message format, or the message format differs from what was assumed.
**Why it happens:** The Gateway API is not publicly documented at the protocol level. The JSONL session format (type/content/tool_name/tool_input/tool_result) is inferred from analysis and community sources, not official specification.
**How to avoid:** Build the provenance capture as a thin adapter layer with explicit message parsing. Log ALL unrecognized message types. Include a "raw message" fallback that stores unparsed Gateway messages for later analysis. Version the adapter so it can be updated when Gateway API becomes documented.
**Warning signs:** Provenance capture records 0 events during execution; unrecognized message type warnings in logs; Gateway connection drops without events.

### Pitfall 3: SQLite Write Contention During High-Activity Periods
**What goes wrong:** Multiple provenance events arrive simultaneously from the Gateway while the user is also submitting a review, causing SQLite "database is locked" errors.
**Why it happens:** SQLite allows only one writer at a time. Under WAL mode, readers don't block writers, but concurrent writes queue up. If the queue time exceeds the busy timeout, writes fail.
**How to avoid:** (1) Enable WAL mode (`PRAGMA journal_mode=WAL`). (2) Use a single write coordinator (e.g., a serialized write queue in the Node.js process). (3) Batch provenance events (buffer 100ms of events, write in a single transaction). (4) Set a generous busy timeout (`PRAGMA busy_timeout=5000`).
**Warning signs:** "SQLITE_BUSY" errors in logs; missing provenance events; review submissions failing intermittently.

### Pitfall 4: Review Widget Captures Reaction But Misses Constraint
**What goes wrong:** Users click "Correct" or "Block" but skip the constraint extraction step, resulting in reaction labels without durable constraints -- exactly the ephemeral feedback the system is designed to prevent.
**Why it happens:** The constraint extraction form is optional or hidden behind a click; users are in a hurry.
**How to avoid:** When reaction is "correct" or "block", show the constraint extraction form INLINE (not behind a modal or extra click). Pre-populate the constraint text from the user's correction message. Make severity default to "requires_approval" for correct and "forbidden" for block. Allow skip only with an explicit "Skip constraint extraction" button.
**Warning signs:** High ratio of correct/block reactions with 0 constraints extracted; constraint store stops growing despite ongoing corrections.

### Pitfall 5: Episode Timestamps Out of Order Due to Async Provenance
**What goes wrong:** Episode events arrive out of chronological order because WebSocket messages from the Gateway have variable latency, causing the episode timeline to be non-monotonic.
**Why it happens:** Network latency between Gateway and MC; batched message delivery; tool calls that take varying time to complete.
**How to avoid:** Use the Gateway's event timestamp (from the JSONL record), NOT the MC receive timestamp, as the canonical `ts_utc`. Store both: `gateway_ts` (from Gateway) and `received_ts` (local). Sort by `gateway_ts` for display and analytics.
**Warning signs:** Episode event timelines show out-of-order tool calls; "Bash command completed before it started" in the timeline view.

### Pitfall 6: DuckDB ATTACH Locks Mission Control's SQLite
**What goes wrong:** The Python pipeline attaches MC's SQLite database via DuckDB and holds a read lock, preventing MC from writing new episodes or provenance events.
**Why it happens:** DuckDB's SQLite extension acquires locks during query execution. Long-running analytical queries can hold the lock for seconds or more.
**How to avoid:** (1) Run Python analytics during off-peak times (not during active task execution). (2) Use short-lived DuckDB connections (connect, query, close) rather than persistent connections. (3) For heavy analytics, copy the SQLite file first (`cp mission-control.db mc-snapshot.db`) and query the copy. (4) Consider a periodic sync job that imports MC episodes into the main DuckDB database.
**Warning signs:** MC dashboard shows "database locked" errors during Python pipeline runs; slow task state transitions when analytics are running.

---

## Code Examples

### SQLite Schema for Episode Tables (MC-04)

```sql
-- Source: Derived from existing DuckDB schema (src/pipeline/storage/schema.py)
-- and AUTHORITATIVE_DESIGN.md Part 6.2E

-- Core episode table
CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT,
    timestamp TEXT NOT NULL,           -- ISO 8601

    -- Flat queryable columns (mirrors DuckDB schema)
    mode TEXT CHECK (mode IN ('Explore','Plan','Implement','Verify','Integrate','Triage','Refactor')),
    risk TEXT CHECK (risk IN ('low','medium','high','critical')),
    reaction_label TEXT CHECK (reaction_label IN ('approve','correct','redirect','block','question')),
    reaction_confidence REAL,
    status TEXT DEFAULT 'in_progress' CHECK (status IN ('pending','in_progress','review','completed')),

    -- JSON columns for nested structures (matches Pydantic Episode model)
    observation TEXT,                   -- JSON: {repo_state, quality_state, context}
    orchestrator_action TEXT,           -- JSON: {mode, goal, scope, executor_instruction, gates, risk}
    outcome TEXT,                       -- JSON: {executor_effects, quality, reaction, reward_signals}
    provenance TEXT,                    -- JSON: {sources: [{type, ref}]}
    constraints_extracted TEXT,         -- JSON: [{constraint_id, text, severity, scope, detection_hints}]
    labels TEXT,                        -- JSON: {episode_type, notes}

    -- Metadata
    project_repo_path TEXT,
    project_branch TEXT,
    project_commit_head TEXT,
    phase TEXT,
    schema_version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_episodes_task ON episodes(task_id);
CREATE INDEX IF NOT EXISTS idx_episodes_mode ON episodes(mode);
CREATE INDEX IF NOT EXISTS idx_episodes_risk ON episodes(risk);
CREATE INDEX IF NOT EXISTS idx_episodes_reaction ON episodes(reaction_label);
CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);

-- Episode events (tool provenance)
CREATE TABLE IF NOT EXISTS episode_events (
    event_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,            -- Gateway timestamp (canonical)
    received_at TEXT NOT NULL,          -- MC receive timestamp
    event_type TEXT NOT NULL CHECK (event_type IN (
        'tool_call','tool_result','file_touch','command_run',
        'test_result','git_event','lint_result','build_result',
        'lifecycle'                     -- task state transitions
    )),
    payload TEXT NOT NULL,              -- JSON: tool-specific details

    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_events_episode ON episode_events(episode_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON episode_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts ON episode_events(timestamp);

-- Constraints (mirrors data/schemas/constraint.schema.json)
CREATE TABLE IF NOT EXISTS constraints (
    constraint_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning','requires_approval','forbidden')),
    scope_paths TEXT NOT NULL,          -- JSON array of paths
    detection_hints TEXT,               -- JSON array of patterns
    source_episode_id TEXT,
    source_reaction_label TEXT,
    examples TEXT,                      -- JSON array of {episode_id, context}
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (source_episode_id) REFERENCES episodes(episode_id)
);

-- Approvals (gate decisions during workflow)
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    gate_type TEXT NOT NULL,            -- e.g., 'run_tests', 'require_human_approval'
    decision TEXT NOT NULL CHECK (decision IN ('approved','rejected','waived')),
    decided_by TEXT DEFAULT 'human',
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_approvals_episode ON approvals(episode_id);

-- Commit links (validation layer: connect episodes to deliverables)
CREATE TABLE IF NOT EXISTS commit_links (
    link_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    branch TEXT,
    commit_message TEXT,
    files_changed TEXT,                 -- JSON array
    link_confidence REAL DEFAULT 1.0,   -- 1.0 for deterministic (task_id stamped), lower for heuristic
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_commits_episode ON commit_links(episode_id);
CREATE INDEX IF NOT EXISTS idx_commits_sha ON commit_links(commit_sha);
```

### DuckDB Bridge: Read MC Episodes from Python Pipeline

```python
# Source: DuckDB SQLite extension (https://duckdb.org/docs/stable/core_extensions/sqlite.html)
# Verified: DuckDB 1.4.4 SQLite extension supports ATTACH with read/write

import json
from pathlib import Path
import duckdb
from src.pipeline.models.episodes import Episode

def import_mc_episodes(
    mc_db_path: str,
    ope_conn: duckdb.DuckDBPyConnection,
) -> list[Episode]:
    """Import episodes from Mission Control SQLite into the analytics pipeline.

    Uses DuckDB's SQLite extension for zero-copy cross-database queries.
    Validates each imported episode against the Pydantic Episode model.
    """
    ope_conn.execute(f"ATTACH '{mc_db_path}' AS mc (TYPE sqlite)")

    rows = ope_conn.execute("""
        SELECT
            episode_id, task_id, session_id, timestamp,
            mode, risk, reaction_label, reaction_confidence,
            observation, orchestrator_action, outcome,
            provenance, constraints_extracted, labels,
            project_repo_path, project_branch, project_commit_head,
            phase
        FROM mc.episodes
        WHERE status = 'completed'
          AND reaction_label IS NOT NULL
    """).fetchall()

    episodes = []
    for row in rows:
        # Parse JSON columns back into dicts
        obs = json.loads(row[8]) if row[8] else None
        action = json.loads(row[9]) if row[9] else None
        outcome_data = json.loads(row[10]) if row[10] else None
        prov = json.loads(row[11]) if row[11] else None
        constraints = json.loads(row[12]) if row[12] else []
        lbls = json.loads(row[13]) if row[13] else None

        # Validate against Pydantic model
        ep = Episode(
            episode_id=row[0],
            timestamp=row[3],
            project={"repo_path": row[14] or "", "branch": row[15], "commit_head": row[16]},
            observation=obs,
            orchestrator_action=action,
            outcome=outcome_data,
            provenance=prov or {"sources": [{"type": "mission_control", "ref": row[1]}]},
            task_id=row[1],
            phase=row[17],
            constraints_extracted=constraints,
            labels=lbls,
        )
        episodes.append(ep)

    ope_conn.execute("DETACH mc")
    return episodes
```

### Task-to-Episode Mapper

```typescript
// Source: AUTHORITATIVE_DESIGN.md Part 6.2 + MC task lifecycle

interface MCTask {
  id: string;
  title: string;
  description: string;
  status: string;
  planning_output?: string;         // JSON from AI planning Q&A
  agent_id?: string;
  created_at: string;
  updated_at: string;
}

function taskToEpisodeObservation(task: MCTask, repoState: RepoState): Observation {
  return {
    repo_state: repoState,
    quality_state: {
      tests: { status: 'unknown', last_command: null, failing: [] },
      lint: { status: 'unknown', last_command: null, issues_count: null },
      build: null,
    },
    context: {
      recent_summary: `Task: ${task.title}. ${task.description}`,
      open_questions: [],
      constraints_in_force: [], // Load from constraint store
    },
  };
}

function planningOutputToAction(planningOutput: string): OrchestratorAction {
  // Parse the structured planning output
  // MC's AI planning Q&A should be modified to emit structured JSON
  const plan = JSON.parse(planningOutput);
  return {
    mode: plan.mode || 'Explore',
    goal: plan.goal || '',
    scope: { paths: plan.scope_paths || [], avoid: plan.scope_avoid || [] },
    executor_instruction: plan.executor_instruction || '',
    gates: plan.gates || [],
    risk: plan.risk || 'medium',
  };
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Post-hoc JSONL parsing for episodes | Real-time structured capture at task lifecycle events | Phase 6 (this phase) | Eliminates correlation uncertainty; episodes are precise by construction |
| Separate analytics DB (DuckDB only) | DuckDB reads SQLite directly via extension | DuckDB 0.10+ (2024), stable in 1.4.4 | Single source of truth in SQLite; no sync infrastructure |
| Polling-based dashboard updates | SSE with 100ms propagation, 30s keep-alive | Already in MC (REALTIME_IMPLEMENTATION_SUMMARY.md) | Live episode timeline without additional infrastructure |
| Free-text review comments | Structured reaction labels + constraint extraction | Phase 6 (this phase) | Every correction becomes a durable, enforceable constraint |
| Manual episode-to-commit correlation | task_id as deterministic join key stamped in branch/commit | Phase 6 (this phase) | Correlation becomes deterministic, not probabilistic |

**Deprecated/outdated:**
- Post-hoc JSONL parsing for ongoing sessions: Only needed for historical data (Phases 1-5); real-time capture is the target for all new sessions
- Probabilistic session-commit correlation: task_id provides a deterministic join key, making heuristic matching obsolete for MC-captured episodes

---

## Open Questions

1. **OpenClaw Gateway WebSocket Protocol Specification**
   - What we know: Gateway runs on port 18789, communicates via JSON over WebSocket, stores sessions as JSONL with type/content/tool_name/tool_input/tool_result fields. MC already has a client at `src/lib/openclaw/client`.
   - What's unclear: Exact RPC method names for subscribing to agent execution events; message schemas for tool call streaming; whether provenance events are pushed automatically or require subscription; how to distinguish tool calls from different concurrent agent sessions.
   - Recommendation: When MC repo access is available, READ the existing `src/lib/openclaw/client` code to understand the current WebSocket protocol. Build provenance capture as a thin adapter that can be updated. Log unrecognized messages rather than failing. This is the HIGHEST RISK area of Phase 6.

2. **Mission Control Database Schema Compatibility**
   - What we know: MC uses SQLite (`mission-control.db`) with `better-sqlite3`. It has existing tables for tasks, agents, task_activities, task_deliverables, openclaw_sessions.
   - What's unclear: Exact current table schemas; whether there are foreign key constraints that affect our new tables; whether MC uses migrations or raw SQL for schema changes; WAL mode status.
   - Recommendation: When MC repo access is available, READ `src/lib/db/` to understand the existing schema. Design episode tables to reference existing `tasks` table via foreign key. Follow MC's existing schema management pattern (migrations vs. raw DDL).

3. **Planning Q&A Output Structure**
   - What we know: MC has "AI-guided planning Q&A" that currently produces natural language plans. Phase 6 requires structured orchestrator action output (mode, goal, scope, constraints, gates, risk, executor_instruction).
   - What's unclear: How the planning Q&A is implemented (LLM prompt? structured form?); how invasive the change from prose to structured JSON output would be; whether users would accept the rigidity.
   - Recommendation: Start with a HYBRID approach: keep the natural language planning output, but add a POST-PROCESSING step that extracts structured fields (mode, scope, risk) from the prose. Over time, migrate to structured-first planning where the Q&A workflow outputs JSON directly.

4. **Constraint Store Synchronization**
   - What we know: The existing Python pipeline stores constraints in `data/constraints.json` via ConstraintStore. MC will extract constraints during review and store them in SQLite.
   - What's unclear: Should MC write to `constraints.json` directly? Should there be one constraint store (SQLite) or two (SQLite + JSON)? How to handle constraint deduplication across both sources?
   - Recommendation: MC writes constraints to its SQLite `constraints` table. The Python pipeline reads MC constraints via DuckDB SQLite extension AND reads `constraints.json` for historically-extracted constraints. A merge utility combines both sources, using the existing ConstraintStore deduplication (SHA-256 of text + scope). Over time, MC SQLite becomes the primary store.

5. **Task ID Stamping in Commits and Branches**
   - What we know: AUTHORITATIVE_DESIGN.md specifies task_id as the deterministic join key, stamped into branch names, commit trailers, PR titles, or `.mc/task.json`.
   - What's unclear: Which stamping mechanism to implement; whether OpenClaw agents can be instructed to include task_id in commits; whether this requires Gateway API support or just prompt engineering.
   - Recommendation: Start with commit trailers (`Task-ID: <task_id>`) since the existing pipeline already parses commit messages. Add `.mc/task.json` in the working directory during task execution. Branch naming (`mc/<task_id>/<description>`) is a nice-to-have.

6. **Scope of MC Codebase Changes**
   - What we know: MC is a Next.js 15 app with ~15 source directories (app/api, components, lib/db, lib/openclaw, lib/store).
   - What's unclear: The full extent of the codebase; how modular it is; whether the task lifecycle state machine is easily extensible; whether the OpenClaw proxy endpoints need modification.
   - Recommendation: This question is resolved by READING the MC codebase once access is available. Plan for a discovery sprint (1-2 days) at the start of Phase 6 to map the codebase before committing to implementation plans.

---

## Sources

### Primary (HIGH confidence)
- `src/pipeline/models/episodes.py` -- Episode Pydantic model (363 lines): defines the episode structure that SQLite tables must be compatible with
- `src/pipeline/storage/schema.py` -- DuckDB schema (266 lines): existing table structure that the bridge must query
- `src/pipeline/constraint_store.py` -- ConstraintStore (193 lines): existing constraint format that MC must produce
- `data/schemas/orchestrator-episode.schema.json` -- JSON Schema: canonical episode structure
- `data/schemas/constraint.schema.json` -- JSON Schema: canonical constraint structure
- `data/config.yaml` -- Pipeline configuration (310 lines): risk model, protected paths, mode inference
- `docs/design/AUTHORITATIVE_DESIGN.md` -- Part 6: Mission Control Integration specification
- `docs/design/Mission Control - supervisory control layer.md` -- Full integration strategy document
- `docs/VISION.md` -- Month 5-6 Mission Control UI mockups and workflow
- `.planning/REQUIREMENTS.md` -- MC-01 through MC-04 requirement definitions
- `.planning/ROADMAP.md` -- Phase 6 success criteria and dependencies
- DuckDB SQLite extension docs (https://duckdb.org/docs/stable/core_extensions/sqlite.html) -- Verified bidirectional read/write via ATTACH

### Secondary (MEDIUM confidence)
- `github.com/crshdn/mission-control` -- README and repo structure (viewed via GitHub web)
- `REALTIME_IMPLEMENTATION_SUMMARY.md` (MC repo) -- SSE architecture, task_activities/deliverables tables, 100ms latency
- `.env.example` (MC repo) -- Configuration variables: DATABASE_PATH, OPENCLAW_GATEWAY_URL, OPENCLAW_GATEWAY_TOKEN
- Perplexity research: Next.js 15 + better-sqlite3 + SSE dashboard patterns
- Perplexity research: DuckDB-SQLite integration patterns and limitations
- Perplexity research: OpenClaw Gateway architecture (WebSocket on port 18789, JSON messages, JSONL sessions)

### Tertiary (LOW confidence)
- OpenClaw Gateway WebSocket protocol: Message format inferred from session JSONL structure and community analysis; NOT verified against official specification or source code. **This is the highest-risk knowledge gap.**
- MC internal architecture: Inferred from repo file listing and README; actual code not reviewed. Specific patterns (how planning Q&A works, how task state transitions are implemented) are UNKNOWN.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Mission Control's existing tech stack (Next.js 15, SQLite, SSE, WebSocket) is well-documented and stable; no new libraries required
- Architecture (DuckDB-SQLite bridge): HIGH - DuckDB SQLite extension is documented and verified working in DuckDB 1.4.4
- Architecture (MC integration): MEDIUM - Inferred from repo README and docs; actual codebase not reviewed (requires repo access)
- OpenClaw Gateway API: LOW - Protocol internals not publicly documented; provenance capture design based on inferred message format
- Review widget: HIGH - Standard Next.js 15 pattern with Server Actions; well-established in React ecosystem
- SQLite schema: HIGH - Directly derived from existing DuckDB schema and Episode Pydantic model
- Pitfalls: HIGH - SQLite concurrency, schema divergence, and Gateway API instability are well-known issues in this architecture class

**External blocker:** Mission Control repository access is required before implementation planning can proceed. The MC codebase needs a discovery sprint to validate assumptions about:
- Existing database schema and migration approach
- OpenClaw client WebSocket protocol
- Task lifecycle state machine extensibility
- Planning Q&A implementation

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (stable domain for Next.js/SQLite/DuckDB; Gateway API may evolve)
