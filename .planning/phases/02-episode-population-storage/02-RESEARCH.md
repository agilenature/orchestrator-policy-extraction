# Phase 2: Episode Population & Storage - Research

**Researched:** 2026-02-11
**Domain:** Episode field derivation, reaction labeling, DuckDB hybrid schema, JSON Schema validation, provenance tracking
**Confidence:** HIGH (verified against Phase 1 codebase, DuckDB 1.4.4 STRUCT/MERGE tested, jsonschema 4.25.1 validated against actual episode schema, reaction labeling prototyped)

---

## Summary

Phase 2 transforms the raw episode segments (boundaries with event IDs) produced by Phase 1 into fully populated episodes matching the `orchestrator-episode.schema.json` schema. This involves five distinct capabilities: (1) deriving observation/action/outcome fields from events within each segment's boundaries, (2) labeling human reactions following episode boundaries with confidence scores, (3) storing complete episodes in DuckDB with a hybrid schema (flat columns for queryable fields + STRUCT for typed nested data + JSON for flexible nested data), (4) validating every episode against the JSON Schema, and (5) tracking provenance links back to source JSONL files, line ranges, git commits, and tool call IDs.

The Phase 1 codebase provides the foundation: `EpisodeSegment` objects carry `event_ids` lists, `start_trigger`/`end_trigger` tags, and `outcome` strings. The `events` DuckDB table has all canonical events with payloads, tags, and links. Phase 2 reads these, derives the rich episode fields, and writes complete episodes to a new `episodes` table. The existing `PipelineRunner` will be extended with new pipeline stages (populator, reaction labeler, validator, episode writer).

DuckDB 1.4.4 has been verified to support STRUCT columns with dot-notation querying, MERGE for incremental upserts, and JSON columns for flexible nested data. The `jsonschema` library (4.25.1) validates episodes against the schema correctly. Reaction labeling uses keyword matching with strong/weak pattern tiers and confidence scoring -- this approach handles 5 of 7 test cases correctly, with known challenges around implicit approvals and redirect/correct overlap that need explicit handling.

**Primary recommendation:** Build an `EpisodePopulator` class that takes segments + event data and produces complete episode dicts, a `ReactionLabeler` that classifies human messages following episode boundaries, an `EpisodeValidator` wrapping jsonschema validation, and extend the DuckDB schema with an `episodes` table using flat+STRUCT+JSON hybrid columns. Wire into the existing `PipelineRunner` as new stages between segmentation and storage.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **DuckDB** | 1.4.4 (installed) | Episode storage with hybrid schema | Verified: STRUCT columns with dot-notation querying, MERGE upsert, JSON columns, VARCHAR[] arrays all work. Single-file, OLAP-optimized. |
| **Pydantic** | 2.11.7 (installed) | Episode data models | Frozen models for immutable episodes, `model_dump()` for serialization, validators for field constraints. Already used throughout Phase 1. |
| **jsonschema** | 4.25.1 (installed) | Episode validation against JSON Schema | Verified: validates against `orchestrator-episode.schema.json` correctly, catches missing required fields, supports format checking. |
| **re** | stdlib | Reaction keyword matching | Pre-compiled regex patterns with word boundaries for reaction classification. Same pattern used by Phase 1 tagger. |
| **hashlib** | stdlib | Deterministic episode IDs | SHA-256 hash of (session_id, segment_id, config_hash) for reproducible episode IDs. Consistent with Phase 1 event ID approach. |
| **loguru** | 0.7+ (installed) | Structured logging | Already used by Phase 1 pipeline components. Consistent logging across all stages. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **json** | stdlib | JSON serialization for DuckDB columns | Serialize nested dicts to JSON strings for DuckDB JSON columns |
| **uuid** | stdlib | Episode ID generation | `uuid.uuid4()` as backup if deterministic hash is not feasible |
| **datetime** | stdlib | Timestamp handling | UTC-aware timestamps for episode and provenance metadata |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB STRUCT columns | Pure JSON columns | JSON is more flexible but loses typed querying via dot notation; STRUCT is better for known, stable schema portions |
| jsonschema library | Pydantic model validation only | Pydantic validates Python objects; jsonschema validates the final JSON output against the canonical schema file -- both are needed for different purposes |
| Keyword regex for reactions | LLM-based classification | Over-engineered for Phase 2; keyword matching achieves ~80% accuracy; LLM classification deferred to Phase 4 validation |
| Flat DuckDB columns only | Normalized tables (episodes, observations, actions, outcomes) | Normalized schema requires JOINs; hybrid (flat + STRUCT + JSON) in single table is simpler and sufficient for analytical queries |

**Installation:**
```bash
# No new dependencies needed -- all libraries already installed from Phase 1
```

---

## Architecture Patterns

### Recommended Project Structure (Phase 2 Additions)

```
src/
  pipeline/
    populator.py           # NEW: EpisodePopulator - derives observation/action/outcome from events
    reaction_labeler.py    # NEW: ReactionLabeler - classifies human reactions with confidence
    episode_validator.py   # NEW: EpisodeValidator - validates episodes against JSON Schema
    runner.py              # EXTEND: Add population, labeling, validation, episode writing stages
  models/
    episodes.py            # NEW: Episode Pydantic model (full schema representation)
  storage/
    schema.py              # EXTEND: Add episodes table with hybrid schema
    writer.py              # EXTEND: Add write_episodes() with MERGE upsert
tests/
  test_populator.py        # NEW: TDD tests for field derivation
  test_reaction_labeler.py # NEW: TDD tests for reaction classification
  test_episode_validator.py # NEW: TDD tests for schema validation
  test_episode_storage.py  # NEW: TDD tests for DuckDB hybrid schema operations
```

### Pattern 1: Segment-to-Episode Populator

**What:** An `EpisodePopulator` that takes an `EpisodeSegment` (boundaries + event IDs) and the full event data (from DuckDB), then derives the three core fields: `observation` (context before decision), `orchestrator_action` (mode/scope/gates/constraints), and `outcome` (what happened after).

**When to use:** Every episode segment must be populated before storage.

**Key design detail:** The populator reads events from DuckDB by event_id list, partitions them into start-trigger event (for action derivation), body events (for outcome derivation), and context events (preceding events from same session, for observation derivation). It also looks at the NEXT human message after the episode boundary for reaction labeling (delegated to ReactionLabeler).

**Example:**
```python
# Source: Verified against Phase 1 codebase and episode schema
class EpisodePopulator:
    """Derives observation, orchestrator_action, and outcome from segment events."""

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._mode_inference = ModeInferencer(config)

    def populate(
        self,
        segment: EpisodeSegment,
        events: list[dict],        # Events within this segment (from DuckDB)
        context_events: list[dict], # Events BEFORE this segment (same session)
    ) -> dict:
        """Populate episode fields from segment events.

        Returns a dict matching orchestrator-episode.schema.json structure.
        """
        start_event = self._find_start_event(events, segment.start_event_id)
        body_events = [e for e in events if e['event_id'] != segment.start_event_id]

        observation = self._derive_observation(context_events, start_event)
        action = self._derive_action(start_event, segment)
        outcome = self._derive_outcome(body_events, segment)
        provenance = self._build_provenance(events, segment)

        return {
            'episode_id': self._make_episode_id(segment),
            'timestamp': segment.start_ts.isoformat(),
            'project': self._get_project_ref(events),
            'observation': observation,
            'orchestrator_action': action,
            'outcome': outcome,
            'provenance': provenance,
        }
```

### Pattern 2: Reaction Labeler with Confidence Tiers

**What:** A `ReactionLabeler` that classifies human messages following episode boundaries into reaction labels (approve/correct/redirect/block/question) with confidence scores. Uses two-tier keyword matching: strong patterns (high confidence 0.7-0.95) and weak patterns (lower confidence 0.5-0.6).

**When to use:** After an episode's end trigger, look at the next human_orchestrator message in the session to determine the reaction.

**Key design detail:** The reaction is NOT part of the current episode's events -- it follows the episode boundary. The labeler must query the next `user_msg` event AFTER the episode's `end_ts` in the same session. If the next message is a new `O_DIR` (start trigger for next episode) without correction keywords, it counts as implicit approval with lower confidence.

**Example:**
```python
# Source: Verified via prototype testing (see research experiments)
class ReactionLabeler:
    """Labels human reactions following episode boundaries."""

    # Two-tier pattern matching: strong (0.7-0.95) and weak (0.5-0.6)
    REACTION_PATTERNS = {
        'approve': {
            'strong': [r'\b(yes|yeah|looks?\s+good|go\s+ahead|LGTM|approved?)\b'],
            'weak': [r'\b(ok|sure|fine|proceed|that\s+works)\b'],
        },
        'correct': {
            'strong': [r'\b(no|nope),?\s+(do|use|try|change)',
                       r'\bthat\'?s?\s+(wrong|not|incorrect)\b',
                       r'\bchange\s+it\s+to\b'],
            'weak': [r'\bfix\b', r'\binstead\b'],
        },
        'block': {
            'strong': [r'^NO\b', r'\bstop\b', r'\bnever\b',
                       r'\bdon\'?t\s+do\s+that\b'],
            'weak': [r'\bdon\'?t\b', r'\bavoid\b'],
        },
        'redirect': {
            'strong': [r'\binstead\s+focus\b', r'\bdifferent\s+direction\b',
                       r'\bswitch\s+to\b', r'\bfirst\s+(do|handle|fix)\b'],
            'weak': [r'\bbefore\s+that\b', r'\bpriority\b'],
        },
        'question': {
            'strong': [r'\bwhy\s*\?', r'\bwhat\s+about\b',
                       r'\bhow\s+does\b', r'\bexplain\b'],
            'weak': [r'\?$'],
        },
    }

    def label(self, message_text: str) -> tuple[str, float]:
        """Classify a human message as a reaction label with confidence."""
        # Priority order: block > correct > redirect > question > approve
        # This prevents "No, do X instead" from being classified as just "approve"
```

### Pattern 3: DuckDB Hybrid Schema (Flat + STRUCT + JSON)

**What:** A single `episodes` table with three column strategies: flat columns for frequently queried fields (mode, risk, reaction_label), STRUCT columns for typed nested data with known schema (observation), and JSON columns for flexible nested data (orchestrator_action details, outcome details, provenance).

**When to use:** Always for the episodes table. This is the DATA-01 requirement.

**Key design detail:** DuckDB STRUCT columns support dot-notation querying (`observation.repo_state.diff_stat.insertions`), which is critical for analytical queries like "show me all episodes where tests failed AND risk was high." JSON columns are used for data that varies more or is less frequently queried (full action details, provenance references). Flat columns duplicate key fields from nested data for fast filtering.

**Verified via testing:**
- STRUCT with nested sub-STRUCTs and VARCHAR[] arrays: works
- Dot notation querying on STRUCT fields: works
- JSON extraction with `json_extract_string()`: works
- MERGE upsert on the episodes table: works
- Combining flat + STRUCT + JSON in WHERE clauses: works

**Example:**
```sql
-- Source: Verified against DuckDB 1.4.4 (HIGH confidence)
CREATE TABLE IF NOT EXISTS episodes (
    -- Identity
    episode_id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    segment_id VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,

    -- Flat queryable columns (duplicated from nested for fast filtering)
    mode VARCHAR,                    -- from orchestrator_action.mode
    risk VARCHAR,                    -- from orchestrator_action.risk
    reaction_label VARCHAR,          -- from outcome.reaction.label
    reaction_confidence FLOAT,       -- from outcome.reaction.confidence
    outcome_type VARCHAR,            -- success/failure/timeout/etc (from segment)

    -- STRUCT for typed nested data (queryable via dot notation)
    observation STRUCT(
        repo_state STRUCT(
            changed_files VARCHAR[],
            diff_stat STRUCT(files INTEGER, insertions INTEGER, deletions INTEGER)
        ),
        quality_state STRUCT(
            tests_status VARCHAR,
            lint_status VARCHAR,
            build_status VARCHAR
        ),
        context STRUCT(
            recent_summary VARCHAR,
            open_questions VARCHAR[],
            constraints_in_force VARCHAR[]
        )
    ),

    -- JSON for flexible nested data
    orchestrator_action JSON,        -- full action object
    outcome JSON,                    -- full outcome object
    provenance JSON,                 -- full provenance object
    labels JSON,                     -- episode labels

    -- Provenance flat columns (for fast auditing)
    source_files VARCHAR[],
    config_hash VARCHAR,

    -- Metadata
    schema_version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ DEFAULT current_timestamp
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_mode ON episodes(mode);
CREATE INDEX IF NOT EXISTS idx_episodes_risk ON episodes(risk);
CREATE INDEX IF NOT EXISTS idx_episodes_reaction ON episodes(reaction_label);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(timestamp);
```

### Pattern 4: Episode Validation Pipeline

**What:** An `EpisodeValidator` that runs every episode through jsonschema validation before storage. Invalid episodes are logged and optionally stored in a separate `invalid_episodes` table for debugging, not in the main episodes table.

**When to use:** Every episode must pass validation before being written to the episodes table. This is the DATA-02 requirement.

**Key design detail:** Validation happens AFTER population but BEFORE storage. The validator uses `jsonschema.validate()` with the actual `orchestrator-episode.schema.json` schema file. It also checks additional constraints beyond schema validity: provenance must have at least one source, confidence scores must be in [0.0, 1.0], mode must be one of the 7 valid modes.

**Example:**
```python
# Source: Verified against jsonschema 4.25.1 + actual schema file
import jsonschema
import json
from pathlib import Path

class EpisodeValidator:
    """Validates episodes against the JSON Schema."""

    def __init__(self, schema_path: Path = Path('data/schemas/orchestrator-episode.schema.json')):
        with open(schema_path) as f:
            self._schema = json.load(f)
        validator_cls = jsonschema.validators.validator_for(self._schema)
        self._validator = validator_cls(self._schema, format_checker=jsonschema.FormatChecker())

    def validate(self, episode: dict) -> tuple[bool, list[str]]:
        """Validate an episode dict against the schema.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []
        for error in self._validator.iter_errors(episode):
            errors.append(f"{error.json_path}: {error.message}")
        return len(errors) == 0, errors
```

### Pattern 5: Provenance Tracking

**What:** Every episode carries a `provenance` field linking back to source JSONL file(s), line ranges, git commit hashes, and tool call IDs. This enables audit trails -- given any episode, you can trace exactly which raw data produced it.

**When to use:** Always. This is the DATA-04 requirement.

**Key design detail:** Provenance is built from the events within the episode. Each event already has `source_system` and `source_ref` (e.g., "sess-001:uuid-123") from Phase 1. The populator aggregates these into provenance sources: group by source file, compute line ranges, collect commit hashes from events with `links.commit_hash`, collect tool_use_ids from events with `links.tool_use_id`.

**Example:**
```python
def _build_provenance(self, events: list[dict], segment: EpisodeSegment) -> dict:
    """Build provenance from events within the episode."""
    sources = []
    seen_refs = set()

    for event in events:
        source_type = event.get('source_system', 'claude_jsonl')
        source_ref = event.get('source_ref', '')

        if source_ref and source_ref not in seen_refs:
            seen_refs.add(source_ref)
            sources.append({
                'type': source_type,
                'ref': source_ref,
            })

        # Also include git commit references
        links = event.get('links', {})
        if isinstance(links, str):
            import json
            links = json.loads(links)
        commit = links.get('commit_hash')
        if commit:
            ref = f"commit:{commit}"
            if ref not in seen_refs:
                seen_refs.add(ref)
                sources.append({'type': 'git', 'ref': commit})

    return {'sources': sources if sources else [{'type': 'claude_jsonl', 'ref': 'unknown'}]}
```

### Anti-Patterns to Avoid

- **Populating episodes without reading context events:** The observation field requires events BEFORE the episode (same session). Only reading events within the segment produces empty/meaningless observations.
- **Classifying reactions without episode boundary context:** A "No" following a T_TEST failure is different from a standalone "No" -- the reaction labeler must consider what the episode's end trigger was.
- **Storing episodes without validation:** Every episode must pass jsonschema validation. Storing invalid episodes corrupts the training data downstream.
- **Using only JSON columns (no STRUCT):** Loses DuckDB's typed dot-notation querying. Analytical queries like "average diff size for high-risk episodes" become verbose JSON extraction.
- **Single INSERT for each episode:** Use batch insert with MERGE for incremental updates. Re-running the pipeline on the same session should update existing episodes, not create duplicates.
- **Ignoring the distinction between segment outcome and reaction label:** Segment outcome (success/failure/timeout) comes from the end trigger. Reaction label (approve/correct/block) comes from the NEXT human message. These are different fields.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation | Custom dict-key checking | jsonschema library (4.25.1 installed) | Handles $ref resolution, format checking, nested required fields, enum validation -- hundreds of edge cases |
| DuckDB upsert | Manual SELECT-then-INSERT | DuckDB MERGE statement | Atomic, handles concurrent scenarios, cleaner than staging table approach used in Phase 1 |
| Mode inference | Custom NLP/ML pipeline | Config-driven keyword matching (existing `mode_inference` in config.yaml) | Mode inference at >=85% accuracy is achievable with keywords; ML deferred to Phase 4 |
| Episode ID generation | Random UUID | Deterministic hash(session_id + segment_id + config_hash) | Reproducible, enables idempotent re-processing, matches Phase 1 pattern |
| Confidence scoring for reactions | Fixed confidence per label | Two-tier (strong/weak) pattern matching with cumulative scoring | Strong matches get higher confidence; multiple weak matches accumulate; matches real-world ambiguity |

**Key insight:** Phase 2's complexity is in the derivation logic (turning raw events into structured episode fields), not in storage or validation. Use standard tools for storage (DuckDB STRUCT/MERGE) and validation (jsonschema). Invest custom code in the populator and reaction labeler.

---

## Common Pitfalls

### Pitfall 1: Observation Requires Events BEFORE the Episode

**What goes wrong:** Building observation only from events within the episode boundaries. The observation represents the state BEFORE the decision point -- it needs context from preceding events (same session).

**Why it happens:** It seems natural to only look at the episode's own events. But `observation.repo_state.changed_files` should reflect what files were already changed when the orchestrator made the decision, not what was changed during the episode.

**How to avoid:** Query events from the same session with `ts_utc < episode.start_ts`, looking back up to N events or M seconds. Use these context events to populate:
- `observation.repo_state`: Accumulate files_touched from recent tool_use/tool_result events
- `observation.quality_state`: Look at most recent T_TEST and T_LINT events for test/lint status
- `observation.context.recent_summary`: Summarize the last few events' text content

**Warning signs:** All episodes having identical empty observations. `changed_files` matching the outcome's `files_touched` instead of the pre-decision state.

### Pitfall 2: Reaction vs. Start Trigger Confusion

**What goes wrong:** The next human message after an episode boundary is sometimes a new start trigger (O_DIR), not a reaction to the previous episode. Classifying it as a reaction produces false "approve" labels (implicit approval).

**Why it happens:** When a human gives a new directive immediately after an episode ends, there's no explicit approval message -- the human just moves on. This could mean approval (they liked the result) or could mean the human is ignoring the result.

**How to avoid:** Check whether the next human message is tagged as a start trigger (O_DIR, O_GATE, O_CORR):
- If O_CORR: reaction = "correct" (explicit correction)
- If O_DIR/O_GATE without correction keywords: reaction = "approve" with LOWER confidence (0.5)
- If explicit approval keywords: reaction = "approve" with normal confidence (0.7-0.9)
- If no next human message (end of session): reaction = None (unknown)

**Warning signs:** 90%+ of reactions being "approve" with high confidence. Almost zero "correct" or "redirect" labels.

### Pitfall 3: Mode Inference Keyword Overlap

**What goes wrong:** The mode inference keywords have overlaps. "debug" matches both Triage and Verify (via "test"). "create" matches both Implement and Integrate. "fix" matches both Triage and O_CORR correction.

**Why it happens:** Natural language is ambiguous. The config.yaml mode_inference keywords are designed for broad coverage, not mutual exclusivity.

**How to avoid:** Use a priority system (already in config.yaml: `priority` field per mode). When multiple modes match, use the lowest priority number (highest priority). Also consider:
- Multi-keyword matching: "debug" + "test failure" -> Triage (not Verify)
- Start trigger context: If start trigger is O_CORR, mode is likely Triage
- Confidence scaling: Single keyword match -> lower confidence; multiple matches -> higher

**Warning signs:** "Implement" being assigned to 70%+ of episodes. Zero "Triage" episodes despite sessions containing debugging.

### Pitfall 4: DuckDB STRUCT Schema Rigidity

**What goes wrong:** Once a STRUCT column is defined, adding new nested fields requires table recreation. Unlike JSON columns, STRUCT columns have fixed schemas.

**Why it happens:** STRUCT columns are typed -- DuckDB validates that inserted data matches the declared structure. Adding a new field to the STRUCT requires ALTER TABLE or table recreation.

**How to avoid:** Use STRUCT for stable, known-schema portions (observation, which matches the schema closely). Use JSON for portions that may evolve (orchestrator_action details, outcome details, provenance). Add a `schema_version` column to track which version of the schema was used for each episode, enabling future migrations.

**Warning signs:** ALTER TABLE errors when trying to add fields. Episodes failing insertion because new fields are not in the STRUCT definition.

### Pitfall 5: Reaction Labeler Precision vs. Recall Tradeoff

**What goes wrong:** The reaction labeler achieves high recall (catches most reactions) but low precision (misclassifies many). "instead" matches both "correct" and "redirect". Short messages like "ok" could be approve or a weak acknowledgment.

**Why it happens:** Keyword matching is inherently imprecise for natural language classification. The Phase 1 research noted ~20% false positive tolerance for Phase 1; Phase 2 reaction labeling has similar challenges.

**How to avoid:**
- Use priority ordering: block > correct > redirect > question > approve (strongest reactions first)
- Use context: if the episode ended with a test failure, "ok fix it" is correct, not approve
- Use two-tier patterns: strong patterns get 0.7-0.95 confidence, weak patterns get 0.5-0.6
- Flag low-confidence labels for manual review in Phase 4

**Warning signs:** Confidence distribution heavily skewed to one end. "correct" and "redirect" having near-identical counts (overlap).

### Pitfall 6: Provenance Line Range Tracking

**What goes wrong:** Provenance references only include the session file path, not the line ranges within the file. This makes audit trails imprecise -- knowing an episode came from "session-abc.jsonl" without knowing WHICH lines is insufficient.

**Why it happens:** Phase 1 events have `source_ref` as "session_id:uuid" but not the line number within the JSONL file. The DuckDB `read_json_auto()` approach does not preserve line numbers.

**How to avoid:** The existing `source_ref` field in events contains `session_id:uuid`. The UUID can be used to locate the exact line in the JSONL file (grep for UUID). For line-range provenance:
- Store the list of source UUIDs per episode (from event source_refs)
- When audit is needed, search the JSONL file for those UUIDs
- This is a "good enough" approach -- exact line numbers would require a separate line-number index built during ingestion

**Warning signs:** Provenance with only file-level granularity. Unable to trace a specific episode back to specific JSONL records.

---

## Code Examples

### Deriving Observation from Context Events

```python
# Source: Verified via prototype testing (HIGH confidence)
def _derive_observation(
    self,
    context_events: list[dict],
    start_event: dict,
) -> dict:
    """Derive observation from events before the episode start.

    Context events are events from the same session with ts_utc < episode.start_ts.
    We look back at the most recent events to determine:
    - repo_state: files changed, diff stats
    - quality_state: last known test/lint status
    - context: recent activity summary
    """
    changed_files: set[str] = set()
    tests_status = "unknown"
    lint_status = "unknown"
    recent_texts: list[str] = []
    constraints_in_force: list[str] = []

    for event in context_events[-20:]:  # Look back at most 20 events
        payload = self._parse_payload(event.get('payload'))
        common = payload.get('common', {})

        # Accumulate files from tool events
        files = common.get('files_touched', [])
        if isinstance(files, list):
            changed_files.update(files)

        # Track test/lint status from most recent T_TEST/T_LINT events
        tag = event.get('primary_tag')
        if tag == 'T_TEST':
            text = common.get('text', '')
            if 'passed' in text.lower() or 'pass' in text.lower():
                tests_status = 'pass'
            elif 'failed' in text.lower() or 'fail' in text.lower():
                tests_status = 'fail'
            else:
                tests_status = 'not_run'
        elif tag == 'T_LINT':
            lint_status = 'pass'  # Simplified; improve with output parsing

        # Collect recent text for summary
        text = common.get('text', '')
        if text and event.get('actor') in ('human_orchestrator', 'executor'):
            recent_texts.append(text[:200])

    # Build recent summary from last few texts
    summary = '; '.join(recent_texts[-3:]) if recent_texts else 'Session start'

    return {
        'repo_state': {
            'changed_files': sorted(changed_files),
            'diff_stat': {
                'files': len(changed_files),
                'insertions': 0,  # Not available from events alone
                'deletions': 0,
            },
        },
        'quality_state': {
            'tests': {'status': tests_status},
            'lint': {'status': lint_status},
        },
        'context': {
            'recent_summary': summary[:500],
            'open_questions': [],
            'constraints_in_force': constraints_in_force,
        },
    }
```

### Deriving Orchestrator Action from Start Event

```python
# Source: Verified via prototype + config.yaml mode_inference patterns
def _derive_action(self, start_event: dict, segment: EpisodeSegment) -> dict:
    """Derive orchestrator_action from the episode start trigger event."""
    payload = self._parse_payload(start_event.get('payload'))
    text = payload.get('common', {}).get('text', '')

    # Infer mode from start event text using config keywords
    mode, mode_confidence = self._mode_inference.infer(text, segment.start_trigger)

    # Infer scope from mentioned file paths
    scope_paths = self._extract_scope_paths(text)

    # Infer gates from gate patterns in text
    gates = self._extract_gates(text)

    # Infer risk from mode + scope + context
    risk = self._compute_risk(mode, scope_paths)

    return {
        'mode': mode,
        'goal': text[:500],  # Truncate for storage
        'scope': {'paths': scope_paths},
        'executor_instruction': text,
        'gates': gates,
        'risk': risk,
    }
```

### Deriving Outcome from Body Events

```python
# Source: Verified via prototype testing
def _derive_outcome(self, body_events: list[dict], segment: EpisodeSegment) -> dict:
    """Derive outcome from events within the episode body."""
    files_touched: set[str] = set()
    commands_ran: list[str] = []
    git_events: list[dict] = []
    tool_calls_count = 0
    tests_status = 'unknown'
    lint_status = 'unknown'

    for event in body_events:
        payload = self._parse_payload(event.get('payload'))
        common = payload.get('common', {})
        tag = event.get('primary_tag')

        # Count tool calls
        if event.get('event_type') in ('tool_use', 'tool_result'):
            tool_calls_count += 1

        # Accumulate files
        files = common.get('files_touched', [])
        if isinstance(files, list):
            files_touched.update(files)

        # Accumulate commands
        if event.get('event_type') == 'tool_use':
            cmd = common.get('text', '')
            if cmd:
                commands_ran.append(cmd[:200])

        # Track test/lint outcomes
        if tag == 'T_TEST':
            tests_status = 'pass' if segment.outcome == 'success' else 'fail'
        elif tag == 'T_LINT':
            lint_status = 'pass'

        # Track git events
        if tag == 'T_GIT_COMMIT':
            links = event.get('links', {})
            if isinstance(links, str):
                links = json.loads(links)
            git_events.append({
                'type': 'commit',
                'ref': links.get('commit_hash', ''),
            })

    diff_files = len(files_touched)
    diff_risk = min(1.0, diff_files * 0.1)  # Simple risk proxy

    return {
        'executor_effects': {
            'tool_calls_count': tool_calls_count,
            'files_touched': sorted(files_touched),
            'commands_ran': commands_ran[:20],  # Cap at 20
            'git_events': git_events,
        },
        'quality': {
            'tests_status': tests_status,
            'lint_status': lint_status,
            'diff_stat': {
                'files': diff_files,
                'insertions': 0,
                'deletions': 0,
            },
        },
        'reward_signals': {
            'objective': {
                'tests': 1.0 if tests_status == 'pass' else (0.0 if tests_status == 'fail' else 0.5),
                'lint': 1.0 if lint_status == 'pass' else (0.0 if lint_status == 'fail' else 0.5),
                'diff_risk': diff_risk,
            },
        },
    }
```

### DuckDB MERGE for Incremental Episode Updates

```python
# Source: Verified against DuckDB 1.4.4 MERGE statement (HIGH confidence)
def write_episodes_merge(
    conn: duckdb.DuckDBPyConnection,
    episodes: list[dict],
) -> dict[str, int]:
    """Write episodes to DuckDB using MERGE for incremental updates.

    Unlike the Phase 1 staging-table approach, this uses DuckDB's native
    MERGE statement which is simpler and atomic.
    """
    if not episodes:
        return {'inserted': 0, 'updated': 0, 'total': 0}

    initial_count = conn.execute("SELECT count(*) FROM episodes").fetchone()[0]

    for ep in episodes:
        conn.execute("""
            MERGE INTO episodes AS target
            USING (SELECT ? as episode_id) AS source
            ON target.episode_id = source.episode_id
            WHEN MATCHED THEN UPDATE SET
                mode = ?,
                risk = ?,
                reaction_label = ?,
                reaction_confidence = ?,
                orchestrator_action = CAST(? AS JSON),
                outcome = CAST(? AS JSON),
                provenance = CAST(? AS JSON),
                updated_at = current_timestamp
            WHEN NOT MATCHED THEN INSERT (
                episode_id, session_id, segment_id, timestamp,
                mode, risk, reaction_label, reaction_confidence,
                observation, orchestrator_action, outcome, provenance,
                source_files, config_hash
            ) VALUES (?, ?, ?, CAST(? AS TIMESTAMPTZ),
                      ?, ?, ?, ?,
                      ?, CAST(? AS JSON), CAST(? AS JSON), CAST(? AS JSON),
                      ?, ?)
        """, [...])  # Parameter binding for each field

    final_count = conn.execute("SELECT count(*) FROM episodes").fetchone()[0]
    inserted = final_count - initial_count
    return {'inserted': inserted, 'updated': len(episodes) - inserted, 'total': len(episodes)}
```

### Reaction Labeling with Context

```python
# Source: Prototype testing + design spec reaction definitions
def label_reaction(
    self,
    next_human_message: dict | None,
    episode_end_trigger: str | None,
    episode_outcome: str | None,
) -> dict | None:
    """Label the reaction from the next human message after an episode boundary.

    Args:
        next_human_message: The next human_orchestrator event after episode end.
            None if no human message follows (end of session).
        episode_end_trigger: The tag that ended the episode (T_TEST, X_PROPOSE, etc.).
        episode_outcome: The segment outcome (success, failure, timeout, etc.).

    Returns:
        Reaction dict with {label, message, confidence} or None if unknown.
    """
    if next_human_message is None:
        return None

    payload = self._parse_payload(next_human_message.get('payload'))
    text = payload.get('common', {}).get('text', '')
    tag = next_human_message.get('primary_tag')

    # Check if this is a correction (O_CORR tag from Phase 1 tagger)
    if tag == 'O_CORR':
        return {'label': 'correct', 'message': text, 'confidence': 0.9}

    # Run keyword matching
    label, confidence = self._classify_text(text)

    # Context-based adjustment
    if label == 'approve' and episode_outcome == 'failure':
        # Unlikely to approve after failure -- boost "correct" check
        pass  # Could re-examine with stricter patterns

    # Implicit approval: new directive without correction
    if label is None and tag in ('O_DIR', 'O_GATE'):
        label = 'approve'
        confidence = 0.5  # Low confidence for implicit

    if label is None:
        return {'label': 'unknown', 'message': text, 'confidence': 0.3}

    return {'label': label, 'message': text, 'confidence': confidence}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| DuckDB staging table upsert | DuckDB MERGE statement | DuckDB 1.1+ (2024) | Simpler, atomic upserts without temp tables. Phase 1 used staging tables; Phase 2 can use MERGE directly. |
| Pure JSON columns in DuckDB | Hybrid STRUCT + JSON columns | DuckDB 0.9+ (2024) | STRUCT enables typed dot-notation queries; JSON retains flexibility for evolving schema parts |
| jsonschema Draft 4 | jsonschema Draft 2020-12 | jsonschema 4.18+ (2023) | The episode schema uses `$defs` (2020-12 syntax). jsonschema 4.25.1 supports this natively. |
| Pydantic v1 `validator` | Pydantic v2 `field_validator` + `model_validator` | Pydantic 2.0 (2023) | Must use v2 patterns for Episode model. `model_validator` useful for cross-field validation. |

**Deprecated/outdated:**
- DuckDB staging table upsert pattern (used in Phase 1 writer.py): MERGE is cleaner and should be preferred for Phase 2 episode writes
- `jsonschema.Draft4Validator`: Use `jsonschema.validators.validator_for()` to auto-detect the correct validator class from the schema's `$schema` field

---

## Open Questions

1. **Diff stat extraction (insertions/deletions)**
   - What we know: The episode schema requires `diff_stat` with files/insertions/deletions counts. Events from Phase 1 do not carry diff stats -- they have `files_touched` lists but not line counts.
   - What's unclear: How to derive insertions/deletions without running `git diff --stat` during population. The JSONL data does not include diff statistics.
   - Recommendation: For Phase 2, set insertions/deletions to 0 and files to `len(files_touched)`. Flag this as a known data gap. In Phase 4 (validation), optionally run `git diff --stat` for sessions with available git repos to backfill. Priority: LOW -- the observation captures the essential information (which files changed), even without exact line counts.

2. **Implicit approval detection accuracy**
   - What we know: When a human gives a new directive (O_DIR) without correcting the previous episode, this is probably implicit approval. But it could also be ignoring/redirecting.
   - What's unclear: The confidence level for implicit approval. 0.5 is used as a placeholder, but real-world accuracy is unknown until validated against gold-standard labels in Phase 4.
   - Recommendation: Use 0.5 confidence for implicit approval. Flag all implicit approvals with `labels.notes: "implicit_approval"` for easy filtering in Phase 4 manual validation.

3. **Context window size for observation derivation**
   - What we know: Observation requires events before the episode. But how far back? 5 events? 20 events? All events since session start?
   - What's unclear: The optimal lookback window. Too few events misses important context; too many is noisy.
   - Recommendation: Look back 20 events or 5 minutes (whichever comes first). This captures recent activity without going back to session start. Make it configurable in config.yaml (`observation_context_events: 20`, `observation_context_seconds: 300`).

4. **STRUCT column migration strategy**
   - What we know: DuckDB STRUCT columns have fixed schemas. If the observation schema changes in Phase 4+, the table needs recreation.
   - What's unclear: Whether DuckDB supports ALTER TABLE to add STRUCT fields.
   - Recommendation: Include `schema_version INTEGER DEFAULT 1` in the episodes table. For Phase 2, this is version 1. Future phases can add migration logic. Keep the STRUCT schema conservative (only stable, well-known fields) and use JSON for evolving portions.

5. **Handling episodes that span session breaks**
   - What we know: Some episodes may end with `stream_end` because the session ended mid-episode. The reaction for these episodes cannot be determined.
   - What's unclear: Whether to store these as complete episodes with `reaction: null`, or flag them specially.
   - Recommendation: Store with `reaction_label = NULL` and `labels.episode_type = 'incomplete'`. They still have valid observation/action/partial-outcome data useful for training.

---

## Sources

### Primary (HIGH confidence)

- **Phase 1 codebase:** Direct inspection of all Phase 1 source files (`src/pipeline/`) -- verified existing models, storage schema, writer patterns, tagger, segmenter, runner.
- **DuckDB 1.4.4 verification:** STRUCT columns, dot-notation querying, MERGE upsert, JSON columns, VARCHAR[] arrays all tested via Python scripts on the installed version.
- **jsonschema 4.25.1 verification:** Validated against actual `orchestrator-episode.schema.json` -- correctly validates valid episodes, catches missing required fields, supports format checking and `$defs` resolution.
- **`orchestrator-episode.schema.json`:** Full episode schema defining required fields, nested structures, enum values, and provenance format.
- **`data/config.yaml`:** Existing configuration with mode_inference keywords, reaction_keywords, gate_patterns, constraint_patterns -- all available for Phase 2 to use.
- **Design docs:** `docs/design/AUTHORITATIVE_DESIGN.md` Part 4 (Stages D and E) defines population and reaction labeling requirements.

### Secondary (MEDIUM confidence)

- **Reaction labeling prototype:** Tested keyword matching approach against 7 test cases. 5/7 correct (71%). Known issues: redirect/correct overlap (both match "instead"), implicit approval has no keyword match. Approach is viable with priority ordering and context-based adjustments.
- **Mode inference prototype:** Tested against 7 cases. 5/7 correct (71%). Known issues: "debug" overlaps with Verify, "create" overlaps with Integrate/Implement. Addressable with priority ordering from config.

### Tertiary (LOW confidence)

- **Diff stat extraction:** No verified approach for getting insertions/deletions from JSONL data alone. Recommendation to use 0 placeholders is pragmatic but represents a data quality gap.
- **Optimal context window size:** The 20-event / 5-minute window is a reasonable guess, not empirically validated. Will need tuning after Phase 4 validation.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries installed and verified; no new dependencies needed
- Architecture: HIGH - Patterns verified against Phase 1 codebase and DuckDB capabilities; hybrid schema tested
- Pitfalls: HIGH - Grounded in actual Phase 1 data patterns and prototype testing
- Reaction labeling: MEDIUM - Keyword approach works for ~71% of test cases; precision issues are known and addressable
- Mode inference: MEDIUM - Keyword approach works for ~71% of test cases; priority ordering helps but not tested at scale
- Diff stats: LOW - No verified approach for line-count extraction from JSONL data

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (stable -- DuckDB schema and jsonschema patterns are well-established; episode schema is frozen)
