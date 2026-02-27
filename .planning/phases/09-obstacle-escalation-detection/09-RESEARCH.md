# Phase 9: Obstacle Escalation Detection - Research

**Researched:** 2026-02-19
**Domain:** Rule-based sequence detection on tagged event streams, constraint auto-generation, DuckDB schema evolution
**Confidence:** HIGH

## Summary

Phase 9 adds a new detection layer to the existing multi-pass event tagger pipeline: recognizing when an agent is blocked (via O_GATE rejection or O_CORR correction) and subsequently takes an unauthorized alternative path (T_RISKY tool call without intervening X_ASK/X_PROPOSE). This is a **post-tagger sequence analysis** problem -- the individual events are already tagged by the existing three-pass tagger (Phases 1-3); Phase 9 adds a fourth pass that scans the tagged event stream for specific multi-event patterns within a configurable turn window.

The implementation touches five existing components: (1) a new `EscalationDetector` class that consumes `TaggedEvent` sequences and produces `O_ESC` detections, (2) schema extensions to `episodes` DuckDB table and Pydantic models for escalation-specific fields, (3) an `EscalationConstraintGenerator` that produces constraint candidates from detected escalations, (4) integration into `PipelineRunner.run_session()` as a post-segmentation step, and (5) new metrics in `ShadowReporter`. The existing tagger, segmenter, and constraint store are not modified -- Phase 9 composes with them.

The critical architectural insight is that O_ESC is NOT a classification label on a single event (like O_DIR or T_RISKY). It is a **multi-event sequence pattern** detected across 2+ events within a turn window. This means it cannot be added as a fourth tagger pass in the existing `EventTagger.tag()` pipeline. Instead, it runs as a separate detection step after tagging and segmentation, consuming the fully tagged event stream.

**Primary recommendation:** Implement `EscalationDetector` as a standalone class that takes `list[TaggedEvent]` and produces `list[EscalationCandidate]`, wired into `PipelineRunner` between segmentation (Step 7) and episode population (Step 9). Use the existing staging-table UPSERT pattern for DuckDB writes with content-derived stable IDs.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Q1: Detection Semantics (Blocking)**
- Block = `O_GATE` event with negative/reject outcome OR `O_CORR` event
- Bypass = any `T_RISKY`, `T_GIT_COMMIT`, `T_TEST`, Write, Edit, or Bash tool call within N=5 turns without an intervening `X_PROPOSE` or `X_ASK` event
- No message text parsing required -- pure event-type detection
- N=5 turns configurable as `escalation_window_turns` in config.yaml, default 5
- O_CORR counts as block trigger (YES)

**Q2: Bypass Exemptions (Blocking)**
- Exempt tools (never count as bypass): Read, Glob, Grep, WebFetch, WebSearch, Task
- Always-bypass tools (regardless): Bash with `rm`, `chmod`, `chown`, `sudo`, `curl -X DELETE`, `drop table`
- X_ASK or X_PROPOSE after rejection resets the O_ESC candidate window entirely
- Exempt tool list stored as `escalation_exempt_tools` in config.yaml

**Q3: Constraint Linking (Blocking)**
- If existing constraint matches (SHA-256 text+scope or embedding similarity >0.85): set `bypassed_constraint_id = <existing_id>`
- If no match: auto-create constraint candidate with `status=candidate`, `source=inferred_from_escalation`
- Both `bypassed_constraint_id` and `bypassed_event_ref` stored as separate nullable fields
- Candidate constraints use same SHA-256 ID generation as existing ConstraintStore
- Candidates held for batch review (NOT immediately visible in Mission Control)

**Q4: Auto-Forbidden Constraint Generation (Blocking)**
- O_ESC + subsequent O_CORR/negative reaction -> generate `forbidden` constraint candidate
- O_ESC + silence (no reaction) -> generate `requires_approval` candidate only (NOT forbidden)
- O_ESC + APPROVE reaction -> no auto-constraint; mark `approval_status=APPROVED`
- All auto-generated constraints start `status=candidate`; never enforced immediately
- Constraint text template: "Forbid [tool_category] performing [operation_type] on [resource_path_prefix] without prior approval following a rejected [O_GATE|O_CORR] gate"
- Promotion workflow (candidate -> active) OUT OF SCOPE for Phase 9

**Q5: Episode Schema (Important)**
- Add nullable escalation columns to existing `episodes` DuckDB table:
  - `escalate_block_event_ref` (str, nullable)
  - `escalate_bypass_event_ref` (str, nullable)
  - `escalate_bypassed_constraint_id` (str, nullable)
  - `escalate_approval_status` (str, nullable: PENDING | APPROVED | UNAPPROVED)
  - `escalate_confidence` (float, nullable)
  - `escalate_detector_version` (str, nullable)
- `orchestrator_action.mode` enum extended with `ESCALATE`
- Content-derived stable ID: `hash(session_id, block_event_ref, bypass_event_ref)`

**Q6: Escalation Metrics (Important)**
- `escalation_count_per_session = count(O_ESC) / count(sessions)`
- `rejection_adherence_rate = 1 - (count(O_ESC) / count(O_GATE_reject + O_CORR))`
- `unapproved_escalation_rate = count(O_ESC where status=UNAPPROVED) / count(O_ESC)` -- headline gate metric
- Target: `unapproved_escalation_rate = 0.0`
- Added to existing ShadowReporter as new metrics block; aggregate only

**Q7: Test Cases (Important)**
- 30 labeled JSONL fixture files in `tests/fixtures/escalation/`
- 15 positive (O_ESC expected): blatant (5), delayed within window (5), indirect bypass (5)
- 15 negative (no O_ESC): read-only post-rejection (5), X_ASK resets window (5), window expired (5)
- Each fixture: minimal session slice (10-15 events) + `.expected.json` sidecar
- Mixed: mine objectivism sessions first, synthetic for edge cases

**Q8: Idempotency (Auto-solved)**
- `o_esc_id = SHA256(session_id + block_event_ref + bypass_event_ref)`
- `constraint_id = SHA256(o_esc_id + constraint_target_signature)`
- UPSERT (not INSERT) on both episode and constraint tables
- Full `escalate_detector_version` stored for audit

### Claude's Discretion

No explicit "Claude's Discretion" sections in the CONTEXT.md. The following areas are implied as implementation-detail choices:
- Internal class design and method signatures for the EscalationDetector
- How to wire the detector into the existing PipelineRunner flow
- How to structure the 30 test fixtures internally (exact event content)
- Whether to extend existing models in-place vs. add new model classes
- Error handling strategy for edge cases (missing events, orphaned windows)

### Deferred Ideas (OUT OF SCOPE)

- Text-based heuristic layer for detection (OpenAI approach -- only if recall insufficient)
- Embedding-based constraint matching (>0.85 cosine similarity) -- simplified to SHA-256 text+scope matching for Phase 9
- Constraint promotion workflow (candidate -> active)
- Mission Control real-time escalation display
- Per-project segmentation of escalation metrics
- FSM-based detection architecture (Perplexity approach)
</user_constraints>

---

## Standard Stack

### Core

This phase uses no new external libraries. All implementation builds on the existing stack.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | v2 (existing) | Data models for EscalationCandidate, config extensions | Already in use for all models |
| duckdb | (existing) | Storage for escalation episodes, metrics queries | Already the primary data store |
| loguru | (existing) | Structured logging for detector decisions | Already used throughout pipeline |
| pytest | (existing) | TDD for escalation detector and integration tests | Already the test framework |
| jsonschema | (existing) | Validation of auto-generated constraints | Already used by ConstraintStore |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hashlib (stdlib) | -- | SHA-256 for deterministic IDs | ID generation for O_ESC episodes and constraints |
| re (stdlib) | -- | Bash command pattern matching for always-bypass tools | Detecting `rm`, `chmod`, etc. in Bash commands |

### Alternatives Considered

None -- this phase adds application logic on the existing stack. No new dependencies needed.

---

## Architecture Patterns

### Recommended Project Structure

```
src/pipeline/
    escalation/
        __init__.py          # Exports: EscalationDetector, EscalationConstraintGenerator
        detector.py          # EscalationDetector class (sequence pattern matching)
        constraint_gen.py    # EscalationConstraintGenerator (auto-constraint from O_ESC)
        models.py            # EscalationCandidate, EscalationConfig dataclasses
    models/
        config.py            # Extended with EscalationConfig sub-model
        events.py            # Classification.label validator extended to include O_ESC
        episodes.py          # OrchestratorAction.mode extended with ESCALATE
    storage/
        schema.py            # ALTER TABLE episodes ADD COLUMN for escalation fields
        writer.py            # write_escalation_episodes() or extend write_episodes()
    shadow/
        reporter.py          # Extended with escalation metrics
    tagger.py                # NOT MODIFIED (O_ESC is not a single-event tag)
    segmenter.py             # NOT MODIFIED (O_ESC is post-segmentation)
    runner.py                # Extended: add escalation detection step

tests/
    fixtures/
        escalation/          # 30 JSONL fixtures + .expected.json sidecars
    test_escalation_detector.py
    test_escalation_constraint_gen.py
    test_escalation_integration.py

data/
    config.yaml              # Extended with escalation section
```

**Rationale for `src/pipeline/escalation/` package:** The escalation detector is a self-contained subsystem with its own models, detection logic, and constraint generation. Placing it in a sub-package avoids bloating existing modules (tagger.py, constraint_extractor.py) which have different responsibilities. The detector consumes TaggedEvent output from the tagger but does not modify the tagger.

### Pattern 1: Sliding Window Sequence Detector

**What:** Walk the tagged event stream maintaining a "pending escalation" state. When a block event (O_GATE/O_CORR) is seen, open a window of N turns. Within that window, if a bypass-eligible tool call appears without an intervening X_ASK/X_PROPOSE, emit an EscalationCandidate.

**When to use:** Always -- this is the core detection algorithm.

**Example:**

```python
# Source: CONTEXT.md Q1 locked decision + existing tagger.py pattern

from dataclasses import dataclass, field
from src.pipeline.models.events import TaggedEvent

@dataclass
class EscalationCandidate:
    """A detected escalation sequence."""
    session_id: str
    block_event_id: str      # The O_GATE/O_CORR event
    block_event_tag: str     # "O_GATE" or "O_CORR"
    bypass_event_id: str     # The T_RISKY/etc. event
    bypass_tool_name: str    # Tool name from the bypass event
    bypass_command: str      # Command text (for constraint template)
    window_turns_used: int   # How many turns between block and bypass
    confidence: float        # Detection confidence
    detector_version: str    # e.g. "1.0.0"


class EscalationDetector:
    """Detects O_ESC patterns in a tagged event stream.

    Algorithm:
    1. Walk events in order
    2. On O_GATE or O_CORR: open escalation window (N events ahead)
    3. On exempt tool (Read, Glob, etc.): skip, do not close window
    4. On X_ASK or X_PROPOSE: close/reset the window (approval sought)
    5. On bypass-eligible tool within window: emit EscalationCandidate
    6. On window expiry (N events passed): discard window
    """

    def __init__(self, config):
        self._window_size = config.escalation.window_turns  # default 5
        self._exempt_tools = set(config.escalation.exempt_tools)
        self._always_bypass_patterns = config.escalation.always_bypass_patterns
        self._version = "1.0.0"

    def detect(self, tagged_events: list[TaggedEvent]) -> list[EscalationCandidate]:
        candidates = []
        pending_blocks: list[dict] = []  # Active escalation windows

        for i, event in enumerate(tagged_events):
            tag = event.primary.label if event.primary else None

            # Step 2: Open window on block event
            if tag in ("O_GATE", "O_CORR"):
                pending_blocks.append({
                    "block_event": event,
                    "block_index": i,
                    "turns_remaining": self._window_size,
                })
                continue

            # Process pending windows
            still_pending = []
            for window in pending_blocks:
                window["turns_remaining"] -= 1

                # Step 4: X_ASK/X_PROPOSE resets window
                if tag in ("X_ASK", "X_PROPOSE"):
                    continue  # Drop this window

                # Step 6: Window expired
                if window["turns_remaining"] <= 0:
                    continue  # Drop expired window

                # Step 3: Exempt tool -- keep window, skip event
                tool_name = self._extract_tool_name(event)
                if tool_name in self._exempt_tools:
                    still_pending.append(window)
                    continue

                # Step 5: Bypass-eligible tool within window
                if self._is_bypass_eligible(event, tag, tool_name):
                    candidates.append(self._build_candidate(
                        window["block_event"], event, window
                    ))
                    continue  # Window consumed

                still_pending.append(window)

            pending_blocks = still_pending

        return candidates
```

### Pattern 2: Constraint Auto-Generation from Escalation

**What:** After detection, generate constraint candidates based on the bypass action's tool class, target resource, and the triggering event type. Severity depends on the subsequent human reaction.

**When to use:** After escalation detection, before episode write.

**Example:**

```python
# Source: CONTEXT.md Q4 locked decision + existing constraint_extractor.py pattern

class EscalationConstraintGenerator:
    """Generates constraint candidates from detected escalations.

    Three-tier logic:
    1. O_ESC + O_CORR/block reaction -> 'forbidden' candidate
    2. O_ESC + silence (no reaction) -> 'requires_approval' candidate
    3. O_ESC + approve reaction -> no constraint; mark APPROVED
    """

    CONSTRAINT_TEMPLATE = (
        "Forbid {tool_category} performing {operation_type} on "
        "{resource_path_prefix} without prior approval following a "
        "rejected {gate_type} gate"
    )

    def generate(
        self,
        candidate: EscalationCandidate,
        reaction_label: str | None,  # from ReactionLabeler
        constraint_store: ConstraintStore,
    ) -> dict | None:
        """Generate a constraint candidate, or None if APPROVED."""
        if reaction_label == "approve":
            return None  # No constraint; approval_status=APPROVED

        severity = "forbidden" if reaction_label in ("correct", "block") else "requires_approval"

        text = self.CONSTRAINT_TEMPLATE.format(
            tool_category=candidate.bypass_tool_name,
            operation_type=self._infer_operation_type(candidate),
            resource_path_prefix=self._infer_resource_prefix(candidate),
            gate_type=candidate.block_event_tag,
        )

        constraint_id = self._make_constraint_id(candidate, text)

        return {
            "constraint_id": constraint_id,
            "text": text,
            "severity": severity,
            "scope": {"paths": self._infer_scope_paths(candidate)},
            "detection_hints": [candidate.bypass_tool_name],
            "source_episode_id": "",  # Filled after episode creation
            "status": "candidate",
            "source": "inferred_from_escalation",
            "created_at": "",  # Filled with current timestamp
        }
```

### Pattern 3: DuckDB Schema Evolution with ADD COLUMN

**What:** Extend the existing `episodes` table with nullable escalation-specific columns using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. This is backward-compatible -- existing episodes have NULL in these columns.

**When to use:** In `create_schema()` after the existing table creation.

**Example:**

```python
# Source: existing schema.py pattern + CONTEXT.md Q5 decision

# Add to create_schema() function:
escalation_columns = [
    ("escalate_block_event_ref", "VARCHAR"),
    ("escalate_bypass_event_ref", "VARCHAR"),
    ("escalate_bypassed_constraint_id", "VARCHAR"),
    ("escalate_approval_status", "VARCHAR"),  # PENDING | APPROVED | UNAPPROVED
    ("escalate_confidence", "FLOAT"),
    ("escalate_detector_version", "VARCHAR"),
]

for col_name, col_type in escalation_columns:
    try:
        conn.execute(
            f"ALTER TABLE episodes ADD COLUMN {col_name} {col_type}"
        )
    except Exception:
        pass  # Column already exists (idempotent)
```

### Pattern 4: Content-Derived Stable IDs (Existing Pattern)

**What:** Generate deterministic episode IDs from content hashes so re-processing the same data produces the same IDs, enabling idempotent UPSERT.

**When to use:** Always for escalation episode IDs and auto-generated constraint IDs.

**Example:**

```python
# Source: existing patterns in populator.py, constraint_extractor.py

import hashlib

def make_escalation_episode_id(session_id: str, block_event_ref: str, bypass_event_ref: str) -> str:
    """SHA-256(session_id + block_event_ref + bypass_event_ref) truncated to 16 hex."""
    key = f"{session_id}:{block_event_ref}:{bypass_event_ref}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def make_escalation_constraint_id(o_esc_id: str, constraint_target_signature: str) -> str:
    """SHA-256(o_esc_id + constraint_target_signature) truncated to 16 hex."""
    key = f"{o_esc_id}:{constraint_target_signature}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### Anti-Patterns to Avoid

- **Modifying the existing EventTagger for O_ESC:** O_ESC is a multi-event sequence, not a single-event classification. Adding it to the three-pass tagger would violate the tagger's contract (one event in, one label out). Keep the EscalationDetector as a separate post-tagger step.

- **Making O_ESC a Classification.label validator value:** The `Classification` model's `label_valid` validator only allows single-event tags. O_ESC is a composite detection across multiple events. If O_ESC must appear in the label vocabulary for downstream consumers, add it carefully with a different `source` value (e.g., `source="escalation_detector"`) to distinguish it from single-event classifications.

- **Modifying the EpisodeSegmenter to handle O_ESC boundaries:** O_ESC episodes are not segmented by the normal start/end trigger mechanism. They are detected post-segmentation as cross-episode patterns. Keep the segmenter unchanged.

- **Storing escalation data only in JSON columns:** The escalation fields (`escalate_block_event_ref`, `escalate_approval_status`, etc.) should be flat DuckDB columns for fast SQL filtering and indexing, not buried in JSON blobs. The existing episodes table uses this hybrid pattern (flat for queryable, JSON for nested).

- **Auto-generating `forbidden` constraints on silence:** Per Q4 decision, silence means "it worked" in these sessions. Only generate `requires_approval` on silence. Generating `forbidden` on silence would poison the constraint store.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deterministic IDs | Custom UUID generation | SHA-256 content hashing (existing pattern) | Consistent with pipeline idempotency guarantees |
| Constraint validation | Custom validation logic | Existing `ConstraintStore._load_validator()` with JSON Schema | Schema validation already handles all constraint fields |
| DuckDB upsert | Raw INSERT/UPDATE SQL | Existing staging table pattern from `writer.py` | Handles DuckDB's limitations with ON CONFLICT |
| Reaction classification | Re-implement reaction detection | Existing `ReactionLabeler.label()` output | Reaction labels are already computed per episode |
| Tool name extraction | Parse event payloads manually | Existing `ToolTagger._extract_tool_name()` pattern | Payload structure is well-established |

**Key insight:** Phase 9 composes with, rather than modifies, existing pipeline components. The escalation detector consumes output from the tagger and reaction labeler, and feeds into the constraint store. All integration points already exist.

---

## Common Pitfalls

### Pitfall 1: Turn Window Counting with Exempt Tools

**What goes wrong:** If exempt tools (Read, Glob, Grep) decrement the turn window counter, many legitimate escalation sequences will have their window expire before the bypass tool is reached. Real sessions have many read-only tool calls between events.

**Why it happens:** A naive implementation counts ALL events toward the window, not just non-exempt events. A 5-turn window might span only 1 significant event if surrounded by Read/Glob calls.

**How to avoid:** The turn window should count only **non-exempt** events. Exempt tool calls should be completely transparent to the window counter -- they neither decrement the counter nor reset the window.

**Warning signs:** Test cases where the bypass happens within 5 significant turns but >5 total events fail to detect O_ESC.

### Pitfall 2: Multiple Pending Windows from Sequential Blocks

**What goes wrong:** If the agent gets blocked twice in sequence (O_GATE then O_CORR), two windows are open simultaneously. A single bypass tool call could match both windows, producing duplicate escalation candidates.

**Why it happens:** The detector maintains a list of pending windows. Without deduplication, the same bypass event can close multiple windows.

**How to avoid:** When a bypass event matches a window, consume only the **oldest** pending window (the first block that started the sequence). Alternatively, deduplicate candidates by `(session_id, bypass_event_id)` after detection.

**Warning signs:** Test cases with sequential O_GATE + O_CORR produce 2 O_ESC candidates instead of 1.

### Pitfall 3: Constraint Schema Extension Without Migration

**What goes wrong:** Adding a `status` field to constraints (required for `candidate` vs `active` tracking) but the existing `constraint.schema.json` does not include `status`. The ConstraintStore's JSON Schema validation would reject auto-generated constraints.

**Why it happens:** The existing constraint schema has `additionalProperties: false` and does not define `status` or `source` fields.

**How to avoid:** Extend `data/schemas/constraint.schema.json` to add optional `status` (enum: `candidate`, `active`, `retired`) and `source` (string) fields BEFORE adding constraints with these fields. Alternatively, use the existing schema's `detection_hints` or add these via the `examples` array metadata.

**Warning signs:** Constraint validation fails silently; auto-generated constraints are dropped by `ConstraintStore.add()`.

### Pitfall 4: OrchestratorAction.mode Enum Extension Breaking Validation

**What goes wrong:** Adding `ESCALATE` to the mode enum in the Pydantic model but not updating the JSON Schema (`orchestrator-episode.schema.json`) and the business rule validator (`EpisodeValidator._check_business_rules()`). Escalation episodes fail validation and are silently dropped.

**Why it happens:** Three separate places define the valid mode enum: (1) Pydantic `OrchestratorAction.mode` Literal type, (2) JSON Schema `OrchestratorAction.mode.enum` array, (3) `EpisodeValidator._check_business_rules()` `valid_modes` set. All three must be updated in sync.

**How to avoid:** Update all three in a single plan task. Test that an episode with `mode=ESCALATE` passes validation end-to-end.

**Warning signs:** `episode_invalid_count` increases after Phase 9; escalation episodes appear in detection logs but not in the `episodes` DuckDB table.

### Pitfall 5: Bypass Tool Detection for Write/Edit/Bash Without Tags

**What goes wrong:** The Q1 decision states "Write, Edit, or Bash tool call" counts as a bypass. But Write/Edit/Bash calls may not have a T_RISKY tag if they don't match risky_tools or protected_paths. The detector should check tool names directly, not only rely on T_RISKY tags.

**Why it happens:** The existing ToolTagger only assigns T_RISKY when the risk threshold (0.7) is met. A simple `Edit` call to a non-protected path has no tag at all. But per Q1, any Write/Edit/Bash within the window constitutes a bypass.

**How to avoid:** The bypass-eligibility check must use a two-layer approach: (1) check for T_RISKY/T_GIT_COMMIT/T_TEST tags, AND (2) check tool name against bypass-eligible tools (Write, Edit, Bash). Either condition triggers bypass detection.

**Warning signs:** Test cases where Bash (non-risky) or Edit (non-protected-path) after rejection do not produce O_ESC.

### Pitfall 6: config.yaml Extension Without PipelineConfig Model Update

**What goes wrong:** Adding `escalation` section to `data/config.yaml` but not adding the corresponding Pydantic sub-model to `PipelineConfig`. The YAML data loads but is silently ignored (Pydantic v2 ignores extra fields by default).

**Why it happens:** PipelineConfig uses Pydantic v2 which ignores extra keys unless `model_config = ConfigDict(extra='forbid')` is set -- and the existing model does NOT set `extra='forbid'`.

**How to avoid:** Add an `EscalationConfig` sub-model with `Field(default_factory=...)` to `PipelineConfig`, following the same pattern as `RiskModelConfig`, `ClassificationConfig`, etc.

**Warning signs:** EscalationDetector gets default config values instead of YAML-specified values; `window_turns` is always 5 even when config says 3.

---

## Code Examples

Verified patterns from the existing codebase:

### Event Extraction Helpers (existing pattern from tagger.py)

```python
# Source: src/pipeline/tagger.py lines 168-183

def _extract_tool_name(event: CanonicalEvent) -> str:
    """Extract tool name from event payload."""
    common = event.payload.get("common", {})
    return common.get("tool_name", "")

def _extract_command_text(event: CanonicalEvent) -> str:
    """Extract command text from event payload."""
    common = event.payload.get("common", {})
    return common.get("text", "")
```

### Staging Table UPSERT Pattern (existing pattern from writer.py)

```python
# Source: src/pipeline/storage/writer.py lines 137-218

def _batch_upsert(conn, rows):
    """
    1. CREATE TEMPORARY TABLE _staging_xxx (...)
    2. INSERT INTO _staging_xxx VALUES (?, ?, ...)
    3. UPDATE main_table SET ... WHERE id IN (SELECT id FROM _staging_xxx)
    4. INSERT INTO main_table SELECT ... FROM _staging_xxx WHERE id NOT IN (SELECT id FROM main_table)
    5. DROP TABLE IF EXISTS _staging_xxx
    """
```

### Configuration Sub-Model Pattern (existing pattern from config.py)

```python
# Source: src/pipeline/models/config.py

class EscalationConfig(BaseModel):
    """Escalation detection settings (Phase 9)."""
    window_turns: int = 5
    exempt_tools: list[str] = Field(default_factory=lambda: [
        "Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task",
    ])
    always_bypass_patterns: list[str] = Field(default_factory=lambda: [
        "rm ", "rm -", "chmod", "chown", "sudo", "curl -X DELETE", "drop table",
    ])
    detector_version: str = "1.0.0"

# Added to PipelineConfig:
class PipelineConfig(BaseModel):
    # ... existing fields ...
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
```

### Test Fixture Pattern (existing pattern from conftest.py)

```python
# Source: tests/conftest.py

# Each escalation test fixture is a minimal JSONL event sequence.
# Use make_event() and make_tagged_event() from conftest.py to build sequences.
# Positive fixture example (O_ESC expected):

from tests.conftest import make_event, make_tagged_event
from datetime import datetime, timedelta, timezone

def make_escalation_sequence_positive():
    """Block (O_GATE) -> Bash (T_RISKY) within 3 turns, no X_ASK."""
    t0 = datetime(2026, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        make_tagged_event(
            make_event(
                actor="human_orchestrator", event_type="user_msg",
                payload={"common": {"text": "No, don't push to main"}},
                ts_utc=t0, event_id="evt-001",
            ),
            primary_label="O_GATE", confidence=0.7,
        ),
        make_tagged_event(
            make_event(
                actor="tool", event_type="tool_use",
                payload={"common": {"tool_name": "Read", "text": "Read src/main.py"}},
                ts_utc=t0 + timedelta(seconds=5), event_id="evt-002",
            ),
            primary_label=None,  # Read is exempt
        ),
        make_tagged_event(
            make_event(
                actor="tool", event_type="tool_use",
                payload={"common": {"tool_name": "Bash", "text": "git push origin main"}},
                ts_utc=t0 + timedelta(seconds=10), event_id="evt-003",
            ),
            primary_label="T_RISKY", confidence=0.8,
        ),
    ]
    return events  # Expected: 1 EscalationCandidate
```

### Schema Validation Pattern (existing from episode_validator.py)

```python
# Source: src/pipeline/episode_validator.py lines 146-155

# The business rule validator checks mode against a hardcoded set.
# Phase 9 MUST add "ESCALATE" to this set:
valid_modes = {
    "Explore", "Plan", "Implement", "Verify",
    "Integrate", "Triage", "Refactor",
    "ESCALATE",  # Phase 9 addition
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-event classification only | Multi-event sequence detection (Phase 9) | Phase 9 | Enables detection of behavioral patterns across events, not just per-event labels |
| Constraints only from human corrections | Constraints also from detected escalations | Phase 9 | Expands the constraint extraction surface; catches policies that were never explicitly stated |
| Binary episode types (decision points) | Decision points + escalation episodes | Phase 9 | Richer episode taxonomy for training signal |

**Not deprecated:**
- The existing three-pass tagger is NOT being replaced. Phase 9 adds a post-tagger detection step that consumes tagger output.
- The existing ConstraintExtractor is NOT being modified. A new EscalationConstraintGenerator handles escalation-specific constraint creation.

---

## Open Questions

1. **Tool Name Extraction Reliability**
   - What we know: The existing `ToolTagger._extract_tool_name()` reads `payload.common.tool_name`. Events from `claude_jsonl` adapter populate this field.
   - What's unclear: Whether ALL tool_use events have `tool_name` populated, or if some events only have the tool name in the `text` field. Edge case: Bash tool calls might have `tool_name="Bash"` or might have no `tool_name` at all.
   - Recommendation: During implementation, verify by querying existing DuckDB events: `SELECT DISTINCT payload->>'common'->>'tool_name' FROM events WHERE event_type='tool_use'`. Fall back to extracting from text if tool_name is unreliable.

2. **Constraint Matching for `bypassed_constraint_id`**
   - What we know: Q3 decision says "If existing constraint matches (SHA-256 text+scope)." The SHA-256 match requires the constraint text to be identical, which is unlikely for auto-generated templates vs. human-written corrections.
   - What's unclear: How to match a templated constraint ("Forbid Bash performing push on main...") to an existing human-written constraint ("Don't push to main without approval"). Pure SHA-256 won't match.
   - Recommendation: For Phase 9, use a simpler heuristic: match on `detection_hints` overlap (both constraints mention the same tool/path). If no match, link to `bypassed_event_ref` only and create a new candidate. Embedding-based matching (>0.85 cosine) is deferred per CONTEXT.md.

3. **Turn Window vs. Event Window**
   - What we know: Q1 says "within N=5 turns." The word "turns" in the CONTEXT is ambiguous -- does it mean 5 events, or 5 actor-transitions (human->assistant->tool = 1 turn)?
   - What's unclear: Whether exempt tools count toward the turn count.
   - Recommendation: Count non-exempt events only. 5 non-exempt events after the block event constitutes the window. This provides the most useful detection window and avoids the exempt-tool inflation pitfall.

---

## Critical Integration Points

These are the exact code locations and data contracts the planner must coordinate changes across:

### 1. Classification Label Validation (`events.py` line 39-53)

The `Classification.label_valid` validator uses a hardcoded set of valid labels. If escalation detections produce `TaggedEvent`-like objects with label `O_ESC`, this set MUST be extended. **However**: the recommended approach is NOT to produce Classification objects for O_ESC (since it's multi-event), but to use the `EscalationCandidate` model directly. If the planner decides O_ESC should appear as a tag on events for downstream consumers, extend the validator.

### 2. OrchestratorAction.mode Literal (`episodes.py` line 151-153)

The `mode` field is `Literal["Explore", "Plan", "Implement", "Verify", "Integrate", "Triage", "Refactor"]`. Must add `"ESCALATE"`. The episodes.py model is frozen; this is a type change only.

### 3. JSON Schema mode enum (`orchestrator-episode.schema.json` line 229-231)

The `OrchestratorAction.mode.enum` array must add `"ESCALATE"`.

### 4. EpisodeValidator valid_modes (`episode_validator.py` line 148-151)

The `valid_modes` set in `_check_business_rules()` must add `"ESCALATE"`.

### 5. DuckDB episodes table (`schema.py` line 122-169)

Six new nullable columns must be added via ALTER TABLE in `create_schema()`.

### 6. PipelineRunner.run_session() (`runner.py` line 102-468)

A new step must be inserted between Step 7 (segmentation) and Step 9 (episode population). The escalation detector runs on the full tagged event stream, produces candidates, and the constraint generator creates constraint candidates. Results are stored alongside normal episodes.

### 7. PipelineConfig (`config.py` line 186-213)

A new `escalation: EscalationConfig` field must be added.

### 8. data/config.yaml (line 310+)

A new `escalation:` YAML section with `window_turns`, `exempt_tools`, `always_bypass_patterns`, `detector_version`.

### 9. ShadowReporter (`reporter.py` line 17-210)

Three new escalation metrics must be added to `compute_report()` and `format_report()`.

### 10. ConstraintStore / constraint.schema.json

The constraint schema may need optional `status` and `source` fields. Alternatively, store these in the `examples` metadata or use `x_extensions` on the episode.

---

## Sources

### Primary (HIGH confidence)

- **Existing codebase** -- All architectural patterns, data models, and integration points verified by direct code reading of the following files:
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/tagger.py` -- Three-pass tagger architecture
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/models/events.py` -- CanonicalEvent, Classification, TaggedEvent models
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/models/episodes.py` -- Episode model with OrchestratorAction.mode enum
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/models/config.py` -- PipelineConfig sub-model pattern
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/segmenter.py` -- Start/end trigger patterns
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/constraint_store.py` -- ConstraintStore add/save/dedup pattern
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/constraint_extractor.py` -- Constraint extraction and ID generation
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/storage/schema.py` -- DuckDB schema creation pattern
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/storage/writer.py` -- Staging table UPSERT pattern
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/runner.py` -- Pipeline runner orchestration flow
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/shadow/reporter.py` -- ShadowReporter metrics pattern
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/reaction_labeler.py` -- Reaction label classification
  - `/Users/david/projects/orchestrator-policy-extraction/src/pipeline/episode_validator.py` -- Validation with business rules
  - `/Users/david/projects/orchestrator-policy-extraction/data/config.yaml` -- Configuration structure
  - `/Users/david/projects/orchestrator-policy-extraction/data/schemas/constraint.schema.json` -- Constraint schema
  - `/Users/david/projects/orchestrator-policy-extraction/data/schemas/orchestrator-episode.schema.json` -- Episode schema
  - `/Users/david/projects/orchestrator-policy-extraction/tests/conftest.py` -- Test helper patterns

- **CONTEXT.md and CLARIFICATIONS-ANSWERED.md** -- All 8 decisions locked via multi-provider synthesis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)

### Secondary (MEDIUM confidence)

- None needed -- this phase is internal application logic building on well-understood existing patterns.

### Tertiary (LOW confidence)

- None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries; pure extension of existing Python + DuckDB + Pydantic stack
- Architecture: HIGH -- all integration points verified by reading existing source code; patterns directly reusable
- Pitfalls: HIGH -- identified from concrete analysis of existing code contracts (label validators, schema validation, UPSERT patterns)
- Detection algorithm: MEDIUM -- the sliding window approach is straightforward but edge cases (multiple pending windows, exempt tool counting) need careful testing

**Research date:** 2026-02-19
**Valid until:** Indefinite (internal application logic; no external dependency versioning concerns)
