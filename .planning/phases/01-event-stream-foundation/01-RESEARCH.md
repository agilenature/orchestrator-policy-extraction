# Phase 1: Event Stream Foundation - Research

**Researched:** 2026-02-10
**Domain:** JSONL log parsing, event stream normalization, rule-based classification, trigger-based segmentation, DuckDB storage
**Confidence:** HIGH (verified against actual Claude Code JSONL files, DuckDB 1.4.4 tested, Pydantic v2 validated, all locked decisions grounded in project design docs)

---

## Summary

Phase 1 transforms raw Claude Code session logs (JSONL files) and git history into a unified, tagged event stream segmented into decision-point episode boundaries. The implementation is a pure Python batch pipeline with three stages: (A) normalize heterogeneous sources into canonical events, (B) classify events with semantic tags via config-driven rules, and (C) segment the tagged stream into episodes using a trigger-based state machine. Configuration loads from YAML and drives all classification and segmentation behavior.

The JSONL format has been reverse-engineered from actual session files. Each line is a JSON object with a `type` field (`user`, `assistant`, `progress`, `system`, `file-history-snapshot`, `queue-operation`). Assistant messages contain `content` blocks of type `thinking`, `text`, or `tool_use`. Tool results appear as `user` messages with `tool_result` content blocks and a `toolUseResult` field containing stdout/stderr. Git commit results **do** contain commit hashes in the stdout text (e.g., `[main ccd6533] Initial commit...`), confirming link-based temporal alignment is feasible. Every message carries `timestamp`, `sessionId`, `uuid`, and `parentUuid` for causal chain reconstruction.

**Primary recommendation:** Build a streaming line-by-line parser (not bulk load) using `orjson` + Pydantic v2 models, with a multi-pass tagger (tool pass, executor pass, orchestrator pass) and a trigger-based state machine segmenter. Store results in DuckDB with deterministic event IDs for idempotent re-ingestion.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Temporal Alignment:** Hybrid approach - use explicit links (commit hash in JSONL) when available, fall back to +/-2 second causal windowing. Mark link confidence (explicit=1.0, windowing=0.8, no-link=0.0).
2. **Episode Boundaries:** Fail-fast segmentation - end on ANY T_TEST, T_RISKY, next O_GATE/O_CORR/O_DIR, or 30s timeout. Tag outcome: success/failure/timeout.
3. **Event Classification:** Config-driven rules with confidence scoring. Primary label (one per event, highest confidence) + secondary labels (additive). Store alternatives as metadata.
4. **Payload Structure:** JSON with payload.common (normalized: text, reasoning, tool_name, duration_ms, error_message, files_touched) + payload.details (tool-specific nested).
5. **Risk Model:** Dual-layer (risky_tools + protected_paths) for binary T_RISKY. Risk scoring (0.0-1.0) for continuous assessment. Threshold >=0.7 triggers T_RISKY.
6. **X_PROPOSE/X_ASK Semantics:** Stakeholder-provided operational definitions with canonical examples and non-examples. X_PROPOSE = executor presents candidate next steps with normative stance affecting orchestrator degrees of freedom. X_ASK = executor requests missing information necessary to proceed without speculation.
7. **Deduplication:** Deterministic event_id = hash(source_system, session_id, turn_id, ts_utc, actor, type). Idempotent ingestion with ON CONFLICT IGNORE.
8. **Error Handling:** Multi-level (reject/degrade/alternative/log/metrics). Abort session if >10% invalid events. Configurable strictness (strict/permissive).
9. **Lint Treatment:** T_LINT is observation, not episode end trigger (unless lint prevents execution).
10. **Nested Decisions:** Flat episodes with metadata (interruption_count, context_switches, complexity: simple|complex).
11. **Timeout:** 30 seconds configurable via episode_timeout_seconds in config.yaml.
12. **O_CORR Detection:** Keyword matching ("No", "Wrong", "Stop", "Fix", "Error", "Don't", "That's not"). Context: if previous event was T_TEST failure or T_RISKY and user responds immediately, default to O_CORR.
13. **Multi-label Resolution:** Highest confidence wins primary. Tied scores use precedence (O_CORR > O_DIR > O_GATE). Minimum 0.5 confidence for any label.
14. **False Positives:** Tolerate for Phase 1 (aggressive detection, <20% acceptable rate).
15. **Risk Combination:** max(risk_factors) >= 0.7 for binary T_RISKY; weighted_average for continuous risk_score.
16. **Reasoning Field:** Optional payload.common.reasoning. Store full text, no truncation. Don't use in classification rules for Phase 1.
17. **Ingestion Metadata:** Track first_seen, last_seen, ingestion_count.
18. **Duplicate Logging:** DEBUG level for individual duplicates; WARNING if >5% duplicate rate.
19. **Validation Modes:** strict (reject on warning) | permissive (log warnings, continue). Configurable in config.yaml.
20. **Temporal Anomalies:** Tolerate + flag. Add deterministic microsecond noise for duplicate timestamps. Prefer causal links over timestamp order.
21. **Configuration:** Single config.yaml for Phase 1 (no overlays).

### Claude's Discretion

- Internal code organization and module boundaries
- Test strategy and coverage targets
- Logging framework choice
- CLI interface design
- Intermediate data representations between pipeline stages

### Deferred Ideas (OUT OF SCOPE)

- Configuration overlays/profiles (defer to implementation)
- Sentiment analysis for O_CORR detection (keyword matching sufficient)
- Reasoning-based classification rules (store reasoning but don't use it)
- Hierarchical episode grouping (flat episodes only)
</user_constraints>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **orjson** | >=3.11 | JSONL line parsing | 3-5x faster than stdlib json; Rust-based; handles bytes natively; critical for processing multi-MB session files without memory issues. **Not yet installed -- must add to dependencies.** |
| **Pydantic** | 2.11.7 (installed) | Data model validation | Rust-backed v2 core; `@field_validator` decorators; frozen models for immutability; generates JSON Schema; discriminated unions for polymorphic event types. Already installed. |
| **DuckDB** | 1.4.4 (installed) | Event and episode storage | Verified: JSON columns, MERGE (upsert), Parquet export all work on installed version. Single-file deployment. OLAP-optimized for analytical queries. |
| **PyYAML** | 6.0.2 (installed) | Config loading | Standard YAML parser for data/config.yaml. Already installed. |
| **hashlib** | stdlib | Deterministic event_id | SHA-256 truncated to 16 hex chars. Zero dependencies. Verified: same input always produces same hash. |
| **re** | stdlib | Pattern matching for classification | Compiled regex for keyword matching, command detection. Microsecond-level performance per event. |
| **datetime** | stdlib | Timestamp normalization | ISO 8601 parsing, UTC conversion, timezone-aware comparison. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **jsonschema** | 4.24.0 (installed) | Config validation | Validate config.yaml structure against JSON Schema at startup |
| **click** | 8.3.1 (installed) | CLI framework | Entry point for `scripts/extract-events.py` pipeline runner |
| **tqdm** | 4.67.1 (installed) | Progress bars | Session processing progress (processing N sessions) |
| **loguru** | >=0.7 | Structured logging | Better than stdlib logging for pipeline debugging. Structured JSON output. **Not yet installed -- must add.** |
| **pytest** | >=8.0 | Testing | Test each pipeline stage independently. **Not yet installed globally -- add to dev deps.** |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| orjson | stdlib json | 3-5x slower; acceptable for <100 sessions; use if orjson causes Rust compilation issues |
| orjson | msgspec | Faster for schema-aware parsing; worse error messages; less ecosystem adoption |
| Pydantic | dataclasses + manual validation | Lighter weight; no auto-validation; lose JSON Schema generation |
| loguru | stdlib logging | Zero-dependency; verbose setup; no structured output by default |
| DuckDB JSON columns | DuckDB STRUCT columns | STRUCT gives typed access; JSON gives flexibility; JSON better for Phase 1 where schema is evolving |

**Installation (Phase 1 additions):**
```bash
pip install orjson>=3.11 loguru>=0.7
# Already installed: duckdb pydantic pyyaml jsonschema click tqdm
```

---

## Architecture Patterns

### Recommended Project Structure (Phase 1 Scope)

```
src/
  pipeline/
    __init__.py
    adapters/
      __init__.py
      claude_jsonl.py      # Parse Claude Code JSONL -> raw events
      git_history.py       # Parse git log -> raw events
    normalizer.py          # Stage A: merge + sort + deduplicate -> canonical events
    tagger.py              # Stage B: classify events with semantic tags
    segmenter.py           # Stage C: segment into episode boundaries
    runner.py              # Pipeline orchestration: session -> tagged segments
  models/
    __init__.py
    events.py              # CanonicalEvent, TaggedEvent, RawEvent dataclasses
    config.py              # Configuration loading + validation
    segments.py            # EpisodeSegment, EpisodeBoundary dataclasses
  storage/
    __init__.py
    schema.py              # DuckDB table definitions (events, segments)
    writer.py              # Write events/segments to DuckDB
  cli/
    __init__.py
    extract.py             # CLI entry point: process sessions -> DuckDB
tests/
  test_adapters/
    test_claude_jsonl.py
    test_git_history.py
  test_normalizer.py
  test_tagger.py
  test_segmenter.py
  test_models.py
  conftest.py              # Shared fixtures (sample events, config)
```

### Pattern 1: Source Adapter Pattern (Normalization)

**What:** Each data source (Claude JSONL, git history) has a dedicated adapter that transforms source-specific format into `RawEvent` objects. The normalizer merges, sorts, and deduplicates them into `CanonicalEvent` objects. The rest of the pipeline only sees canonical events.

**When to use:** Always. This decouples JSONL format changes from pipeline logic.

**Key design detail:** The Claude Code JSONL format produces multiple canonical events per JSONL line in some cases. An assistant message with `[thinking, text, tool_use]` content blocks should yield up to 3 raw events (one per block). Tool results arrive as separate `user` lines with `tool_result` content and `sourceToolAssistantUUID` linking back to the tool_use.

**Example:**
```python
# Source: Verified against actual JSONL files (HIGH confidence)
@dataclass(frozen=True)
class RawEvent:
    """Pre-normalization event from a source adapter."""
    source_system: str           # "claude_jsonl" | "git"
    source_ref: str              # file:line_number or commit_hash
    ts_utc: datetime             # Already UTC-normalized
    session_id: str
    actor: str                   # "human_orchestrator" | "executor" | "tool" | "system"
    event_type: str              # "user_msg" | "assistant_text" | "assistant_thinking" |
                                 # "tool_use" | "tool_result" | "git_commit" | etc.
    payload: dict                # Source-specific content
    uuid: str                    # Original UUID from source
    parent_uuid: str | None      # For causal chain reconstruction
    links: dict                  # Cross-references (tool_use_id, commit_hash)

class ClaudeJSONLAdapter:
    """Parse Claude Code JSONL session file into RawEvents."""

    def parse_file(self, filepath: Path, session_id: str) -> Iterator[RawEvent]:
        with open(filepath, 'rb') as f:
            for line_num, line in enumerate(f, 1):
                record = orjson.loads(line)
                yield from self._parse_record(record, filepath, line_num, session_id)

    def _parse_record(self, record: dict, filepath: Path, line_num: int,
                      session_id: str) -> Iterator[RawEvent]:
        rec_type = record.get('type')
        if rec_type == 'assistant':
            yield from self._parse_assistant(record, filepath, line_num, session_id)
        elif rec_type == 'user':
            yield from self._parse_user(record, filepath, line_num, session_id)
        elif rec_type == 'system':
            yield from self._parse_system(record, filepath, line_num, session_id)
        # Skip: file-history-snapshot, progress, queue-operation
```

### Pattern 2: Multi-Pass Tagger (Classification)

**What:** Three sequential tagging passes, each responsible for a category: (1) Tool tagger detects T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY from tool_use/tool_result events. (2) Executor tagger detects X_PROPOSE, X_ASK from assistant text events. (3) Orchestrator tagger detects O_DIR, O_GATE, O_CORR from user message events.

**When to use:** Always. Separating passes by category makes rules independently testable and configurable.

**Why three passes:** Tool events are classified from structured data (tool name, command string) with HIGH confidence. Executor events require text pattern matching on assistant messages with MEDIUM confidence. Orchestrator events require keyword matching on user messages with variable confidence. Different data, different rules, different confidence levels.

**Example:**
```python
# Source: Design spec + verified classification decisions
class EventTagger:
    """Multi-pass event classifier."""

    def __init__(self, config: TaggingConfig):
        self.tool_tagger = ToolTagger(config)
        self.executor_tagger = ExecutorTagger(config)
        self.orchestrator_tagger = OrchestratorTagger(config)

    def tag(self, events: list[CanonicalEvent]) -> list[TaggedEvent]:
        tagged = []
        for i, event in enumerate(events):
            classifications = []

            # Pass 1: Tool classification (structured data, high confidence)
            if event.event_type in ('tool_use', 'tool_result'):
                classifications.extend(self.tool_tagger.classify(event))

            # Pass 2: Executor classification (text patterns, medium confidence)
            if event.actor == 'executor' and event.event_type == 'assistant_text':
                classifications.extend(self.executor_tagger.classify(event))

            # Pass 3: Orchestrator classification (keywords, variable confidence)
            if event.actor == 'human_orchestrator' and event.event_type == 'user_msg':
                context = events[max(0, i-3):i]  # Previous 3 events for context
                classifications.extend(self.orchestrator_tagger.classify(event, context))

            # Resolve: highest confidence = primary, rest = secondary
            primary, secondaries = self._resolve_labels(classifications)
            tagged.append(TaggedEvent(event=event, primary=primary,
                                     secondaries=secondaries,
                                     all_classifications=classifications))
        return tagged
```

### Pattern 3: Trigger-Based State Machine (Segmentation)

**What:** A state machine that walks the tagged event stream, opening episodes on start triggers (O_DIR, O_GATE) and closing them on end triggers (X_PROPOSE, X_ASK, T_TEST, T_RISKY, T_GIT_COMMIT, next O_DIR/O_GATE/O_CORR, 30s timeout). This is NOT a sliding window.

**When to use:** Always for decision-point segmentation. Sliding windows split atomic decisions arbitrarily.

**Key design detail from locked decisions:** Episode ends on ANY T_TEST (fail-fast), not just on test failure. Lint (T_LINT) is NOT an end trigger. Timeout is 30 seconds (not 30 minutes -- note the requirements doc says 30min but CLARIFICATIONS-ANSWERED says 30s; the answered clarification supersedes).

**Example:**
```python
class EpisodeSegmenter:
    """Trigger-based state machine for episode boundary detection."""

    START_TRIGGERS = {'O_DIR', 'O_GATE'}
    END_TRIGGERS = {'X_PROPOSE', 'X_ASK', 'T_TEST', 'T_RISKY',
                    'T_GIT_COMMIT', 'O_DIR', 'O_GATE', 'O_CORR'}

    def __init__(self, config: SegmentationConfig):
        self.timeout_seconds = config.episode_timeout_seconds  # 30

    def segment(self, tagged_events: list[TaggedEvent]) -> list[EpisodeSegment]:
        episodes = []
        current: EpisodeSegment | None = None

        for event in tagged_events:
            primary_tag = event.primary.label if event.primary else None

            # Check timeout
            if current and self._timed_out(current, event):
                current.close(event.event.ts_utc, outcome='timeout')
                episodes.append(current)
                current = None

            # Start trigger: open new episode (close previous if open)
            if primary_tag in self.START_TRIGGERS:
                if current:
                    current.close(event.event.ts_utc, outcome='superseded')
                    episodes.append(current)
                current = EpisodeSegment(start_event=event)

            # Add event to current episode
            if current:
                current.add_event(event)

            # End trigger: close current episode
            if current and primary_tag in self.END_TRIGGERS:
                if primary_tag in self.START_TRIGGERS:
                    # This event starts a new episode (already opened above)
                    # The previous episode was closed with 'superseded'
                    pass
                else:
                    outcome = self._determine_outcome(event)
                    current.close(event.event.ts_utc, outcome=outcome)
                    episodes.append(current)
                    current = None

        # Handle unclosed episode at end of stream
        if current:
            current.close(tagged_events[-1].event.ts_utc, outcome='stream_end')
            episodes.append(current)

        return episodes
```

### Pattern 4: Deterministic Event ID (Deduplication)

**What:** Generate event_id as a deterministic hash of (source_system, session_id, turn_id, ts_utc, actor, type). This ensures idempotent re-ingestion: processing the same JSONL file twice produces the same events with the same IDs.

**When to use:** Always. This is a locked decision.

**Implementation detail:** Use the `uuid` field from the JSONL record as the `turn_id` component, since it is unique per record within a session. For git events, use the commit hash as source_id.

```python
import hashlib

def make_event_id(source_system: str, session_id: str, turn_id: str,
                  ts_utc: str, actor: str, event_type: str) -> str:
    key = f'{source_system}:{session_id}:{turn_id}:{ts_utc}:{actor}:{event_type}'
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### Anti-Patterns to Avoid

- **Loading full JSONL into memory:** Session files can be multi-MB. Stream line-by-line with orjson, never `json.load(file)`.
- **Single-pass classification:** Mixing tool, executor, and orchestrator classification in one function makes rules untestable and undebuggable. Use separate passes.
- **Sliding window segmentation:** Fixed time/count windows split atomic decisions. Use trigger-based state machine.
- **Mutable event objects:** Events must be immutable (frozen dataclasses or Pydantic frozen models) so pipeline stages cannot corrupt upstream data.
- **Hardcoded classification rules:** All keywords, patterns, and thresholds must come from config.yaml. Hardcoded rules make re-tuning require code changes.
- **Treating tool_result as standalone events without linking to tool_use:** The `tool_use_id` field in tool results must be linked to the originating tool_use event. The `sourceToolAssistantUUID` field in tool_result records provides this link.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSONL parsing | Custom line splitter + json.loads | orjson.loads on raw bytes | Handles encoding, malformed lines, memory efficiently |
| Data validation | Manual if/else checks on dict fields | Pydantic v2 BaseModel with @field_validator | Automatic type coercion, clear error messages, JSON Schema generation |
| Config validation | Manual YAML key checking | jsonschema validation of loaded YAML | Declarative schema, catches missing/wrong-typed fields, version-aware |
| Timestamp parsing | strptime with manual timezone handling | datetime.fromisoformat() (Python 3.11+) | Handles ISO 8601 with timezone correctly; stdlib since 3.11 |
| UUID generation | Custom random ID generators | hashlib.sha256 deterministic hash | Reproducible, idempotent, debuggable; same input = same ID |
| Progress reporting | Custom print statements with line counts | tqdm with total=line_count | Rate estimation, ETA, clean terminal output |
| DuckDB schema migrations | Manual ALTER TABLE scripts | DuckDB schema_version column + migration functions | Tracks which version each row was written at; enables gradual migration |

**Key insight:** The pipeline's complexity is in the classification rules and segmentation logic, not in parsing or storage. Use standard tools for I/O and validation; invest custom code in the tagger and segmenter.

---

## Common Pitfalls

### Pitfall 1: Misidentifying Actor from JSONL Message Type

**What goes wrong:** Treating all `type: "user"` JSONL records as human orchestrator messages. Many `type: "user"` records are actually tool results (with `tool_result` content blocks) or system-injected meta messages (with `isMeta: true`).

**Why it happens:** The JSONL format uses `type: "user"` for three different things: (a) actual human messages, (b) tool results being fed back to the model, (c) system meta-messages.

**How to avoid:**
- `type: "user"` + `isMeta: false` + no `tool_result` content blocks = human orchestrator message (actor: "human_orchestrator")
- `type: "user"` + content contains `tool_result` blocks = tool result (actor: "tool")
- `type: "user"` + `isMeta: true` = system-injected context (actor: "system" -- skip or tag as metadata)
- `type: "assistant"` = executor message (actor: "executor")

**Warning signs:** O_DIR tags appearing on tool result events. Episode boundaries triggering on tool output instead of human input. Actor distribution showing 100% "human_orchestrator" with no "tool" entries.

### Pitfall 2: Missing the parentUuid Causal Chain

**What goes wrong:** Events are sorted purely by timestamp, losing the causal ordering. A thinking block at T=1.0, a text block at T=1.1, and a tool_use at T=1.2 are all part of the same assistant turn but appear as independent events.

**Why it happens:** Claude Code emits content blocks as separate JSONL lines with their own UUIDs, but they share the same `message.id` and are linked by `parentUuid`. Without reconstructing this chain, a single assistant response looks like multiple independent events.

**How to avoid:**
- Group assistant content blocks by `message.id` (shared across thinking + text + tool_use blocks from the same response)
- Use `parentUuid` to reconstruct the causal chain within a turn
- Use `sourceToolAssistantUUID` on tool_result records to link results back to tool_use events
- Sort within a turn by line order (not timestamp, which may have sub-second resolution issues)

**Warning signs:** Episode segments containing orphaned tool_result events with no preceding tool_use. Thinking blocks classified as standalone executor events rather than attached to their tool_use.

### Pitfall 3: Timeout Unit Confusion (30 seconds vs 30 minutes)

**What goes wrong:** The requirements doc (ROADMAP.md, AUTHORITATIVE_DESIGN.md) says "30 minutes" timeout, but CLARIFICATIONS-ANSWERED.md (Q4) explicitly decides "30 seconds" as the episode timeout. Using 30 minutes produces episodes that never timeout and span entire sessions.

**Why it happens:** The clarification process changed the timeout from 30 minutes to 30 seconds. The locked decision in CLARIFICATIONS-ANSWERED supersedes the earlier 30-minute default in design docs.

**How to avoid:** Use `config.yaml` value `episode_timeout_seconds: 30`. Always read timeout from config, never hardcode. The planner must use 30 seconds per the locked decision.

**Warning signs:** Zero timeout-terminated episodes in test runs. Episodes spanning 10+ minutes with no activity.

### Pitfall 4: Git Commit Hash Extraction Regex Failure

**What goes wrong:** The regex to extract commit hashes from git command output fails on edge cases: amended commits, merge commits, commits with long messages that wrap, or non-English locale output.

**Why it happens:** Git output format varies by version, locale, and command flags. The standard `git commit` output is `[branch hash] message` but this can vary.

**How to avoid:**
- Parse the known format: `[branch_name hash_prefix] message_first_line`
- Regex: `\[[\w/.-]+\s+([0-9a-f]{7,40})\]`
- Also check `toolUseResult.stdout` which contains the raw output
- Fallback: if commit hash extraction fails, fall back to timestamp-based windowing (confidence=0.8) instead of failing

**Warning signs:** Large number of git events with `link_confidence: 0.0` when they should have explicit links. Empty `links.commit_hash` on events that are clearly git commits.

### Pitfall 5: Classification Rule Ordering and Precedence

**What goes wrong:** An event matches multiple classification rules with similar confidence, and the system picks the wrong primary label because rule ordering is not deterministic.

**Why it happens:** Natural language is ambiguous. A message like "No, run the tests first" matches both O_CORR ("No") and O_GATE ("run the tests first"). Without explicit precedence, the result depends on iteration order.

**How to avoid:** Implement the locked precedence order for tied scores: O_CORR > O_DIR > O_GATE. When confidence scores are equal, the higher-precedence label wins. This is defined in CLARIFICATIONS-ANSWERED Q9.

**Warning signs:** Classification distribution that doesn't match expectations (e.g., zero O_CORR when sessions clearly contain corrections). Flapping labels when rules are reordered.

### Pitfall 6: DuckDB Single-Writer Violation

**What goes wrong:** Running two extraction processes simultaneously against the same DuckDB file causes lock errors or data corruption.

**Why it happens:** DuckDB is designed for single-writer access (OLAP, not OLTP). Concurrent writes from multiple processes are not supported.

**How to avoid:** Use file-level locking or process-level coordination. Never run parallel extraction jobs writing to the same `ope.db`. Process sessions sequentially within a single process. If parallelism is needed, process sessions independently and merge into DuckDB in a single-writer final step.

**Warning signs:** `IOError` or lock-related exceptions during extraction. Duplicate events after parallel runs.

---

## Code Examples

### Claude Code JSONL Record Types (Verified)

The following types were observed in actual session files (HIGH confidence):

```python
# Source: Direct inspection of ~/.claude/projects/ JSONL files (2026-02-10)

# JSONL record types and their relevance to the pipeline:
RECORD_TYPES = {
    'user': {
        'subtypes': [
            'human_message',      # isMeta=False, no tool_result -> actor: human_orchestrator
            'tool_result',        # content contains tool_result blocks -> actor: tool
            'system_meta',        # isMeta=True -> actor: system (usually skip)
        ],
        'fields': ['parentUuid', 'isSidechain', 'userType', 'cwd', 'sessionId',
                   'version', 'gitBranch', 'type', 'message', 'uuid', 'timestamp',
                   'isMeta', 'toolUseResult', 'sourceToolAssistantUUID']
    },
    'assistant': {
        'content_block_types': ['thinking', 'text', 'tool_use'],
        'fields': ['parentUuid', 'isSidechain', 'userType', 'cwd', 'sessionId',
                   'version', 'gitBranch', 'message', 'requestId', 'type', 'uuid',
                   'timestamp'],
        'message_fields': ['model', 'id', 'type', 'role', 'content',
                          'stop_reason', 'stop_sequence', 'usage']
    },
    'system': {
        'subtypes': ['turn_duration', 'compact_boundary'],
        'fields': ['parentUuid', 'sessionId', 'type', 'subtype', 'durationMs',
                   'timestamp', 'uuid']
    },
    'progress': 'Hook execution events -- skip in pipeline',
    'file-history-snapshot': 'File backup snapshots -- skip in pipeline',
    'queue-operation': 'Message queue operations -- skip in pipeline',
}
```

### Tool Use and Tool Result Linking (Verified)

```python
# Source: Direct inspection of JSONL files

# Assistant tool_use message:
# {
#   "type": "assistant",
#   "message": {
#     "content": [{
#       "type": "tool_use",
#       "id": "toolu_01FBkLmk9Yq65qxRYhYT5JU1",  # <-- tool_use_id
#       "name": "Bash",
#       "input": {"command": "git status", "description": "Show working tree status"}
#     }]
#   },
#   "uuid": "51212053-01bd-4b84-92d0-c753fc90eeb7",  # <-- assistant event UUID
#   "timestamp": "2026-02-10T23:29:13.335Z"
# }

# Corresponding tool_result (appears as type: "user"):
# {
#   "type": "user",
#   "message": {
#     "content": [{
#       "tool_use_id": "toolu_01FBkLmk9Yq65qxRYhYT5JU1",  # matches tool_use.id
#       "type": "tool_result",
#       "content": "On branch main...",
#       "is_error": false
#     }]
#   },
#   "toolUseResult": {
#     "stdout": "On branch main...",
#     "stderr": "",
#     "interrupted": false,
#     "isImage": false
#   },
#   "sourceToolAssistantUUID": "51212053-01bd-4b84-92d0-c753fc90eeb7",  # matches assistant UUID
#   "uuid": "7b9e684b-d09b-4491-9d9b-c502c574e612",
#   "timestamp": "2026-02-10T23:29:13.506Z"
# }
```

### Git Commit Hash Extraction from Tool Results (Verified)

```python
# Source: Direct inspection of JSONL tool results containing git commit output

import re

GIT_COMMIT_PATTERN = re.compile(r'\[[\w/.-]+\s+([0-9a-f]{7,40})\]')

def extract_commit_hash(tool_result_content: str) -> str | None:
    """Extract commit hash from git commit output.

    Example input: "[main ccd6533] Initial commit: Phase 0 data infrastructure"
    Returns: "ccd6533"
    """
    match = GIT_COMMIT_PATTERN.search(tool_result_content)
    return match.group(1) if match else None

# Verified against actual JSONL output:
# "[main (root-commit) ccd6533] Initial commit: Phase 0 data infrastructure"
# Also handles: "[main abc1234] feat: add feature"
# Also handles: "[feature/auth def5678] fix: auth bug"
```

### DuckDB Events Table Schema (Phase 1)

```sql
-- Source: Locked decisions + DuckDB 1.4.4 verified features

-- Events table: stores normalized canonical events
CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,     -- deterministic hash
    ts_utc TIMESTAMPTZ NOT NULL,
    session_id VARCHAR NOT NULL,
    actor VARCHAR NOT NULL,           -- human_orchestrator | executor | tool | system
    event_type VARCHAR NOT NULL,      -- user_msg | assistant_text | tool_use | tool_result | git_commit
    primary_tag VARCHAR,              -- O_DIR | O_GATE | O_CORR | X_PROPOSE | X_ASK | T_TEST | T_LINT | T_GIT_COMMIT | T_RISKY
    primary_tag_confidence FLOAT,
    secondary_tags JSON,              -- [{label, confidence}]
    payload JSON,                     -- {common: {...}, details: {...}}
    links JSON,                       -- {parent_uuid, tool_use_id, commit_hash, ...}
    risk_score FLOAT,                 -- 0.0-1.0 continuous risk assessment
    risk_factors JSON,                -- [{factor, weight, matched}]
    -- Ingestion metadata
    first_seen TIMESTAMPTZ DEFAULT current_timestamp,
    last_seen TIMESTAMPTZ DEFAULT current_timestamp,
    ingestion_count INTEGER DEFAULT 1,
    -- Source tracking
    source_system VARCHAR NOT NULL,   -- claude_jsonl | git
    source_ref VARCHAR NOT NULL       -- file:line_number or commit_hash
);

-- Episode segments table: stores boundary detection results
CREATE TABLE IF NOT EXISTS episode_segments (
    segment_id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    start_event_id VARCHAR NOT NULL REFERENCES events(event_id),
    end_event_id VARCHAR REFERENCES events(event_id),
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ,
    start_trigger VARCHAR NOT NULL,    -- O_DIR | O_GATE
    end_trigger VARCHAR,               -- X_PROPOSE | X_ASK | T_TEST | T_RISKY | T_GIT_COMMIT | timeout | superseded
    outcome VARCHAR,                   -- success | failure | timeout | superseded | stream_end
    event_count INTEGER NOT NULL,
    event_ids JSON NOT NULL,           -- [event_id, ...]
    -- Episode metadata
    complexity VARCHAR DEFAULT 'simple',  -- simple | complex
    interruption_count INTEGER DEFAULT 0,
    context_switches INTEGER DEFAULT 0,
    config_hash VARCHAR,               -- hash of config used for this segmentation
    created_at TIMESTAMPTZ DEFAULT current_timestamp
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_tag ON events(primary_tag);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_segments_session ON episode_segments(session_id);
```

### Config Loading and Validation

```python
# Source: Locked config structure from CLARIFICATIONS-ANSWERED

import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional

class TemporalConfig(BaseModel):
    causal_window_seconds: int = 2
    link_confidence: dict = Field(default_factory=lambda: {
        'explicit': 1.0, 'windowing': 0.8, 'none': 0.0
    })

class RiskModelConfig(BaseModel):
    threshold: float = 0.7
    combination_mode: dict = Field(default_factory=lambda: {
        'classification': 'max', 'scoring': 'weighted_average'
    })
    risky_tools: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)

class ValidationConfig(BaseModel):
    mode: str = 'strict'  # strict | permissive
    invalid_event_abort_threshold: float = 0.10
    abort_scope: str = 'per_session'

class PipelineConfig(BaseModel):
    episode_timeout_seconds: int = 30
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    risk_model: RiskModelConfig = Field(default_factory=RiskModelConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    # ... classification rules, reaction_keywords, etc.

def load_config(path: Path = Path('data/config.yaml')) -> PipelineConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return PipelineConfig(**raw)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `@validator` | Pydantic v2 `@field_validator` | Pydantic 2.0 (2023) | Must use v2 patterns; v1 is deprecated |
| `json.loads()` for JSONL | `orjson.loads()` for performance | orjson 3.x (2020+) | 3-5x faster parsing, critical for large files |
| DuckDB without MERGE | DuckDB 1.4.0+ with MERGE (upsert) | Sept 2025 | Enables idempotent re-ingestion natively |
| Python `datetime.strptime` for ISO 8601 | `datetime.fromisoformat()` | Python 3.11 (2022) | Handles timezone offsets correctly |
| `dataclasses` for models | Pydantic `BaseModel` (frozen) | Pydantic 2.x | Auto-validation, JSON Schema, serialization |

**Deprecated/outdated:**
- Pydantic v1 patterns: `@validator` is now `@field_validator`, `class Config` is now `model_config`
- `jsonlines` library: The project has this in requirements.txt but orjson + line iteration is faster and simpler
- `pandas` for JSONL processing: Eager evaluation; unnecessary for line-by-line streaming

---

## Claude Code JSONL Format Reference

This section documents the JSONL format as reverse-engineered from actual session files. This is critical knowledge for the Claude JSONL adapter.

### Session File Location and Naming

- **Location:** `~/.claude/projects/{encoded-project-path}/`
- **Naming:** `{session-uuid}.jsonl` (e.g., `071c8eb8-905b-40a0-82aa-b2831f675d24.jsonl`)
- **Session ID:** The UUID filename IS the session ID (matches `sessionId` field in records)
- **Encoding:** UTF-8, one JSON object per line

### Common Fields (Present on Most Records)

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Record type: `user`, `assistant`, `system`, `progress`, `file-history-snapshot`, `queue-operation` |
| `uuid` | string | Unique ID for this record |
| `parentUuid` | string/null | UUID of the parent record in the causal chain |
| `timestamp` | string | ISO 8601 UTC timestamp (e.g., `2026-02-10T23:29:13.335Z`) |
| `sessionId` | string | Session UUID (matches filename) |
| `cwd` | string | Working directory at time of event |
| `version` | string | Claude Code version (e.g., `2.1.38`) |
| `gitBranch` | string | Current git branch |
| `isSidechain` | boolean | Whether this is a sidechain/subagent conversation |
| `userType` | string | `external` for normal usage |

### Record Type Details

**`type: "assistant"`** - Contains `message.content` as array of content blocks:
- `{type: "thinking", thinking: "...", signature: "..."}` - Extended thinking
- `{type: "text", text: "..."}` - Visible text response
- `{type: "tool_use", id: "toolu_...", name: "...", input: {...}}` - Tool invocation
- Additional fields: `message.model`, `message.id` (shared across blocks of same response), `message.usage`, `requestId`

**`type: "user"` (human message)** - `isMeta: false`, no `tool_result` blocks:
- `message.content` is a string (the user's text)
- `message.role: "user"`

**`type: "user"` (tool result)** - Contains `tool_result` content blocks:
- `message.content[].tool_use_id` links to originating `tool_use.id`
- `toolUseResult.stdout` / `toolUseResult.stderr` contain raw output
- `sourceToolAssistantUUID` links to the assistant event that issued the tool call
- `is_error` indicates whether the tool call failed

**`type: "user"` (system meta)** - `isMeta: true`:
- System-injected context (slash command payloads, local command caveats)
- Generally skip in pipeline or tag as system metadata

**`type: "system"`** - System events:
- `subtype: "turn_duration"` with `durationMs` field - marks end of a turn
- `subtype: "compact_boundary"` - marks context compaction events

### Event Counts (Observed Distribution)

From 9 session files (2080 total lines):
- `file-history-snapshot`: 86 (4%) -- skip
- `progress`: 822 (40%) -- skip
- `user`: 410 (20%) -- parse (human msgs + tool results + system meta)
- `assistant`: 730 (35%) -- parse (thinking + text + tool_use)
- `system`: 27 (1%) -- parse turn_duration for timing data
- `queue-operation`: 5 (<1%) -- skip

**Note:** `progress` events (hook execution) are the most frequent but are irrelevant to the pipeline. The adapter should skip them efficiently.

---

## Open Questions

1. **Subagent/sidechain handling**
   - What we know: JSONL records have `isSidechain` field. Some sessions have companion directories (same UUID without .jsonl extension).
   - What's unclear: Whether sidechain events should be included in the parent session's event stream or tracked separately.
   - Recommendation: For Phase 1, skip events where `isSidechain: true`. Track as a potential enhancement for later phases. The locked decisions don't address subagents.

2. **Content block ordering within a single assistant response**
   - What we know: A single assistant response produces multiple JSONL lines (thinking, text, tool_use) with slightly different timestamps but the same `message.id`.
   - What's unclear: Whether the JSONL line order is guaranteed to match the logical order (thinking before text before tool_use).
   - Recommendation: Sort content blocks within the same `message.id` by: thinking first, then text, then tool_use. This matches the API contract. Verify against more sessions if ordering issues arise.

3. **`slug` field on some records**
   - What we know: Some records have a `slug` field (e.g., `"serialized-chasing-kite"`). Appears on some user and system records.
   - What's unclear: What this field represents and whether it carries semantic meaning.
   - Recommendation: Preserve in raw payload but don't use for classification. LOW confidence that it matters.

4. **Existing config.yaml gap with locked decisions**
   - What we know: The existing `data/config.yaml` has `idle_timeout_minutes: 30` (30 minutes), but the locked decision is `episode_timeout_seconds: 30` (30 seconds). The config also lacks the full structure defined in CLARIFICATIONS-ANSWERED.
   - What's unclear: Whether to update config.yaml to match locked decisions during Phase 1, or create a new config file.
   - Recommendation: Update the existing `data/config.yaml` to match the complete config structure from CLARIFICATIONS-ANSWERED. This is a prerequisite task before implementing the pipeline.

---

## Sources

### Primary (HIGH confidence)

- **Direct JSONL inspection:** `~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/*.jsonl` - 9 session files, 2080 total records. All format details verified against actual files.
- **DuckDB 1.4.4 verification:** JSON columns, MERGE (upsert), Python API all tested on installed version.
- **Pydantic 2.11.7 verification:** `@field_validator`, frozen models, `model_dump_json()` all tested.
- **Python 3.13.5 verification:** `datetime.fromisoformat()`, `hashlib.sha256`, all stdlib features confirmed.
- **Project design docs (canonical):**
  - `docs/design/AUTHORITATIVE_DESIGN.md` - Episode schema, pipeline stages, tag taxonomy
  - `.planning/phases/01-event-stream-foundation/01-CONTEXT.md` - Gray areas and proposed decisions
  - `.planning/phases/01-event-stream-foundation/CLARIFICATIONS-ANSWERED.md` - 21 locked decisions
  - `data/config.yaml` - Existing configuration (needs update)
  - `data/schemas/orchestrator-episode.schema.json` - Episode JSON Schema
  - `.planning/research/ARCHITECTURE.md` - Pipeline architecture patterns
  - `.planning/research/STACK.md` - Technology stack recommendations
  - `.planning/research/PITFALLS.md` - Common mistakes and prevention

### Secondary (MEDIUM confidence)

- **Stack research:** Library versions verified against installed packages and PyPI. orjson and loguru need installation.
- **Perplexity search on JSONL format:** Confirmed location and basic structure, but lacked detailed schema (reverse-engineering from actual files was necessary).

### Tertiary (LOW confidence)

- **Subagent/sidechain behavior:** Observed `isSidechain` field and companion directories but did not inspect sidechain content. Handling strategy is a recommendation, not verified.
- **`slug` field semantics:** Observed in some records, purpose unknown. Recommendation is speculative.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All core libraries verified installed and tested (except orjson and loguru which need pip install)
- Architecture: HIGH - Patterns derived from project design docs and verified against actual JSONL format
- JSONL format: HIGH - Reverse-engineered from 9 actual session files with 2080 records
- Pitfalls: HIGH - Grounded in actual JSONL format quirks (isMeta, tool_result as user type, parentUuid chains)
- Classification rules: MEDIUM - Rules are well-defined in locked decisions but untested against real data

**Research date:** 2026-02-10
**Valid until:** 2026-03-10 (stable -- JSONL format may change with Claude Code updates, but core patterns are unlikely to change)
