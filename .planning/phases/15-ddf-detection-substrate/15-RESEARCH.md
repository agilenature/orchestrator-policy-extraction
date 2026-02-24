# Phase 15: DDF Detection Substrate - Research

**Researched:** 2026-02-24
**Domain:** DDF marker detection, DuckDB schema extension, regex/keyword heuristic stubs, LLM-scored Tier 2 enrichment, memory_candidates deposit pipeline
**Confidence:** HIGH

## Summary

Phase 15 implements the DDF (Developmental Detection Framework) as a deposit substrate. The codebase is a mature Python pipeline (1349 tests, 14 prior phases) with well-established patterns: DuckDB for storage (v1.4.4), Pydantic v2 (2.11.7) for models, Click (8.3.1) for CLI, loguru for logging, and YAML config. The pipeline runner (`src/pipeline/runner.py`) already has 14 sequential steps; Phase 15 adds new steps and tables without restructuring the existing pipeline.

The CONTEXT.md decisions are highly specific: Tier 1 stubs (L0-2, O_AXS) use regex/keyword heuristics at high recall; Tier 2 OPE enrichment (L3-7) uses LLM scoring post-task. Write-on-detect deposits to `memory_candidates` are Tier 2 only (OPE pipeline writes atomically after confirming Level 6). The existing `memory_candidates` table schema (Phase 13.3) needs three new columns. Five new DuckDB tables are required: `flame_events`, `ai_flame_events`, `axis_hypotheses`, `constraint_metrics`, and one aggregate view for IntelligenceProfile.

**Primary recommendation:** Follow the Wave structure from CONTEXT.md strictly. Wave 1 is schema + Tier 1 stubs + Tier 2 deposit path. Each subsequent wave extends detection fidelity. Do not hand-roll LLM orchestration -- use the existing ConstraintExtractor/EpisodePopulator patterns for Tier 2 scoring. All new DuckDB tables use the established `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` idempotent pattern from `schema.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Q1: Write-on-Detect Fidelity Boundary**
DECISION: Tier 2 Only (OPE pipeline writes to memory_candidates post-task)
- Tier 1 hooks write only to `flame_events` (staging)
- OPE pipeline processes flame_events, confirms Level 6, writes to memory_candidates atomically with confirmation
- No CHECK constraint relaxation needed
- Write authority stays in DuckDB single-writer bus process
- Add `flame_events.deposited_to_candidates BOOLEAN DEFAULT false` flag for retry tracking
- Add `memory_candidates.source_flame_event_id VARCHAR` FK for lineage

**Q2: DDF Marker Level Heuristics -- Tier 1 Stub Scope**
DECISION: Tier 1 = L0-2 + O_AXS; Tier 2 = L3-7
- Tier 1 stubs: L0 (trunk ID regex), L1 (causal marker regex), L2 (assertive causal regex), O_AXS (token count + noun phrase)
- Tier 2 OPE LLM scoring: L3-7 (requires cross-message context comparison)
- `flame_events.detection_source`: 'stub' (Tier 1) or 'opeml' (Tier 2)
- HIGH RECALL at Tier 1 -- false positives filtered by Tier 2

**Q3: O_AXS Signal Thresholds**
DECISION: Quantitative thresholds in config.yaml (Tier 1 computable)
- Granularity drop: current_token_count < 0.5 x avg(prior 4 prompts)
- Novel concept: capitalized noun phrase not in session known_concepts, appearing 2+ times in last 3 messages
- Human messages only (AI concept introduction uses ai_flame_events Level 2)
- known_concepts: per-session only (reset at session start)

**Q4: False Integration Proxy**
DECISION: LLM hypothesize-and-check in Tier 2 OPE
- One LLM call per episode in Tier 2 post-task pipeline
- Hypothesized axes stored in new `axis_hypotheses` table
- Confidence threshold: 0.6 to emit DDF-07 marker; below -> log as 'false_integration_inconclusive'
- Fired marker: `ai_flame_events` at `marker_type='false_integration'`

**Q5: Epistemological Origin Format**
DECISION: Hard enum + confidence float
- `epistemological_origin: reactive | principled | inductive`
- `epistemological_confidence FLOAT` column added to constraints
- Default fallback: 'principled'

**Q6: GeneralizationRadius**
DECISION: Count-based proxy for Phase 15
- `COUNT(DISTINCT scope_path_prefix) FROM session_constraint_eval WHERE constraint_id = X`
- Stagnation flag: radius = 1 AND firing_count >= 10
- New `constraint_metrics` DuckDB table (not bloating constraints.json)

**Q7: Causal Isolation Query Role**
DECISION: Passive recorder for Phase 15
- DDF-08 pipeline step reads FoilInstantiator results from premise_registry.foil_path_outcomes
- Successful isolation -> marker_level=3 in flame_events
- Failed foil -> marker_level=2, flood_confirmed=false
- Missing isolation -> marker_type='missing_isolation' (potential Post Hoc fallacy)

**Q8: memory_candidates Schema Extension**
DECISION: Add 3 columns + soft Python-level dedup
- source_flame_event_id VARCHAR NULL
- fidelity INTEGER NOT NULL DEFAULT 2
- detection_count INTEGER NOT NULL DEFAULT 1
- Soft dedup: check (ccd_axis, scope_rule) before INSERT; if exists, UPDATE detection_count

### Claude's Discretion

The CONTEXT.md does not explicitly list Claude's Discretion areas. The wave structure is fully specified. Implementation details within each wave (internal module organization, test structure, specific regex patterns for L0-2) are at Claude's discretion per the locked decisions.

### Deferred Ideas (OUT OF SCOPE)

- Bus transport implementation (locked in Phase 14-04; Phase 15 uses existing CLI pipeline, not the bus)
- Stream processor real-time path (Phase 16+)
- NATS/Redis transport evaluation (Phase 16+)
- SessionStart prompt delivery of DDF interventions (Phase 16)
- Cross-host governance (beyond scope)
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.4.4 | All DDF tables (flame_events, ai_flame_events, axis_hypotheses, constraint_metrics) | Already used for all pipeline storage; single-writer constraint preserved |
| pydantic | 2.11.7 | Pydantic v2 models for FlameEvent, AIFlameEvent, IntelligenceProfile | Project pattern: frozen BaseModel for all data models |
| click | 8.3.1 | CLI commands (intelligence profile, intelligence profile --ai) | Already used for all pipeline CLI |
| loguru | 0.7.3 | Logging for all new pipeline steps | Already used throughout pipeline |
| PyYAML | 6.0.3 | Config for DDF thresholds, O_AXS thresholds | Already used for all pipeline config |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| re (stdlib) | N/A | Tier 1 regex heuristics (L0 trunk ID, L1 causal markers, L2 assertive causal) | Wave 1 Tier 1 stubs |
| hashlib (stdlib) | N/A | Deterministic IDs for flame_events (SHA-256) | All ID generation |
| json (stdlib) | N/A | JSON column serialization for DuckDB | All DuckDB writes with JSON columns |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB JSON columns | STRUCT columns | JSON is more flexible for variable-shape marker evidence; DuckDB JSON functions (json_extract_string) work fine at project scale. STRUCT would be faster for typed queries but requires more migration effort. JSON is the established pattern (premise_registry, events). |
| Regex for L0-2 stubs | spaCy NER | Regex is <1ms, spaCy adds 50-100ms latency and a heavy dependency. The CONTEXT.md decision explicitly says HIGH RECALL Tier 1 with false positive filtering by Tier 2. Regex achieves this. |

**Installation:**
```bash
# No new dependencies required. All libraries already installed.
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/
    ddf/                         # NEW: DDF detection substrate
        __init__.py
        schema.py                # flame_events, ai_flame_events, axis_hypotheses, constraint_metrics DDL
        models.py                # FlameEvent, AIFlameEvent, IntelligenceProfile, AxisHypothesis Pydantic models
        tier1/                   # Tier 1 heuristic stubs
            __init__.py
            markers.py           # L0, L1, L2 regex detectors
            o_axs.py             # O_AXS detector (token count + noun phrase)
        tier2/                   # Tier 2 OPE LLM scoring
            __init__.py
            flame_extractor.py   # FlameEventExtractor (L3-7 LLM scorer)
            false_integration.py # DDF-07 False Integration proxy
            causal_isolation.py  # DDF-08 Causal Isolation Query recorder
            epistemological.py   # Epistemological origin classifier
        writer.py                # DuckDB writers for flame_events, ai_flame_events
        intelligence_profile.py  # IntelligenceProfile aggregation from flame_events
        generalization.py        # GeneralizationRadius computation
    cli/
        intelligence.py          # NEW: `intelligence profile` CLI command group
```

### Pattern 1: Idempotent Schema Extension (Established Codebase Pattern)

**What:** Add new tables using `CREATE TABLE IF NOT EXISTS` and new columns using `ALTER TABLE ... ADD COLUMN` wrapped in try/except.
**When to use:** Every new DuckDB table and column addition in Phase 15.
**Example:**
```python
# Source: src/pipeline/storage/schema.py (lines 251-266, Phase 9 pattern)
# This is the EXACT pattern used for escalation columns, governance columns,
# premise registry -- use it for all Phase 15 schema additions.

def create_ddf_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create DDF tables and extend existing tables. Idempotent."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flame_events (
            flame_event_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            human_id VARCHAR,
            prompt_number INTEGER,
            marker_level INTEGER NOT NULL,
            marker_type VARCHAR NOT NULL,
            evidence_excerpt TEXT,
            quality_score FLOAT,
            axis_identified VARCHAR,
            flood_confirmed BOOLEAN DEFAULT FALSE,
            subject VARCHAR NOT NULL DEFAULT 'human'
                CHECK (subject IN ('human', 'ai')),
            detection_source VARCHAR NOT NULL DEFAULT 'stub'
                CHECK (detection_source IN ('stub', 'opeml')),
            deposited_to_candidates BOOLEAN DEFAULT FALSE,
            source_episode_id VARCHAR,
            session_event_ref VARCHAR,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    # Indexes for common query patterns
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flame_session ON flame_events(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flame_level ON flame_events(marker_level)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flame_subject ON flame_events(subject)")

    # memory_candidates extension (3 new columns)
    for col_name, col_type in [
        ("source_flame_event_id", "VARCHAR"),
        ("fidelity", "INTEGER NOT NULL DEFAULT 2"),
        ("detection_count", "INTEGER NOT NULL DEFAULT 1"),
    ]:
        try:
            conn.execute(f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass  # Column already exists (idempotent)
```

### Pattern 2: Pipeline Step Integration (Established Codebase Pattern)

**What:** Add new steps to `PipelineRunner.run_session()` as numbered steps after the existing Step 14.5.
**When to use:** Tier 2 enrichment steps that run during the post-task OPE pipeline.
**Example:**
```python
# Source: src/pipeline/runner.py (Step 14.5 pattern, lines 635-688)
# New steps go after Step 14.5, before Step 15 (stats computation):

# Step 15: DDF Tier 1 flame event detection
# Step 16: DDF Tier 2 LLM enrichment (L3-7)
# Step 17: Deposit to memory_candidates (Level 6 confirmed)
# Step 18: GeneralizationRadius computation
# Step 19: Epistemological origin classification

# Each step follows the try/except pattern with stats tracking:
try:
    from src.pipeline.ddf.tier1.markers import detect_markers
    tier1_events = detect_markers(tagged_events, session_id, config)
    # Write to flame_events table
    ...
except ImportError:
    pass  # DDF module not yet available
except Exception as e:
    logger.warning("DDF Tier 1 detection failed: {}", e)
    warnings.append(f"DDF Tier 1 detection failed: {e}")
```

### Pattern 3: Config-Driven Thresholds (Established Codebase Pattern)

**What:** All DDF thresholds go in `data/config.yaml` under a new `ddf:` section, with corresponding Pydantic model in `models/config.py`.
**When to use:** O_AXS thresholds, LLM confidence thresholds, GeneralizationRadius stagnation thresholds.
**Example:**
```python
# New config section in data/config.yaml:
# ddf:
#   o_axs:
#     granularity_drop_ratio: 0.5
#     prior_prompts_window: 4
#     novel_concept_min_occurrences: 2
#     novel_concept_message_window: 3
#   tier2:
#     false_integration_confidence_threshold: 0.6
#     epistemological_default: "principled"
#   generalization:
#     stagnation_min_firing_count: 10

# Corresponding Pydantic model:
class OAxsConfig(BaseModel):
    granularity_drop_ratio: float = 0.5
    prior_prompts_window: int = 4
    novel_concept_min_occurrences: int = 2
    novel_concept_message_window: int = 3

class DDFConfig(BaseModel):
    o_axs: OAxsConfig = Field(default_factory=OAxsConfig)
    false_integration_confidence_threshold: float = 0.6
    epistemological_default: str = "principled"
    stagnation_min_firing_count: int = 10
```

### Pattern 4: Deterministic ID Generation (Established Codebase Pattern)

**What:** All IDs are SHA-256 of content-derived fields, truncated to 16 hex chars.
**When to use:** flame_event_id, ai_flame_event_id, axis_hypothesis_id.
**Example:**
```python
# Source: src/pipeline/premise/models.py (PremiseRecord.make_id, line 109)
# Also: src/pipeline/durability/amnesia.py (AmnesiaDetector)
# Also: src/pipeline/runner.py (escalation episode ID, line 493)
import hashlib

def make_flame_event_id(session_id: str, prompt_number: int, marker_type: str) -> str:
    """Deterministic ID: SHA-256(session_id + prompt_number + marker_type)[:16]."""
    return hashlib.sha256(
        f"{session_id}{prompt_number}{marker_type}".encode()
    ).hexdigest()[:16]
```

### Anti-Patterns to Avoid

- **Writing to ope.db from hooks:** The CONTEXT.md locks write authority to the DuckDB single-writer bus process. Tier 1 stubs write to `flame_events` ONLY via the OPE pipeline, not from hook scripts. The PAG hook pattern (JSONL staging) is explicitly NOT the Phase 15 pattern -- Tier 1 stubs run inside the post-task pipeline, not as hooks.
- **Relaxing memory_candidates CHECK constraints:** CONTEXT.md Q1 explicitly says "No CHECK constraint relaxation needed." The existing CCD format constraints (non-empty ccd_axis, scope_rule, flood_example) remain intact.
- **Bloating constraints.json with DDF metadata:** CONTEXT.md Q6 explicitly says GeneralizationRadius goes in a new `constraint_metrics` DuckDB table, not in constraints.json.
- **Implementing Tier 2 in Wave 1:** The wave structure is strict. Wave 1 = schema + Tier 1 stubs + Tier 2 deposit path. Do not add LLM calls in Wave 1.
- **Creating a new module at `src/hooks/`:** Hooks live at `src/pipeline/live/hooks/` per Phase 14.1 convention.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DuckDB schema idempotency | Custom migration framework | `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` in try/except | This is the established pattern from 14 prior phases; a migration framework adds complexity without value at this scale |
| Deterministic IDs | UUID generation | SHA-256(content fields)[:16] | Content-addressable IDs enable idempotent re-ingestion (established pattern) |
| JSON column handling | ORM or custom serializer | `json.dumps()` for INSERT, `json_extract_string()` for queries | DuckDB's native JSON type + functions work well; the project uses this everywhere |
| Config validation | Manual config parsing | Pydantic v2 BaseModel with field_validator | Established pattern in `models/config.py` with 200+ lines of validated config |
| CLI commands | argparse or custom | Click groups with `@click.command()` | 7 existing Click command groups; add `intelligence` as 8th |
| LLM calls for Tier 2 | Custom HTTP client | Whatever the existing ConstraintExtractor pattern uses (the project may have an LLM abstraction) | Consistency with existing LLM integration points |

**Key insight:** Phase 15 is large but architecturally conservative. Every pattern it needs already exists in the codebase (schema extension, pipeline step integration, config-driven thresholds, deterministic IDs, CLI commands). The complexity is in the number of new tables/detectors, not in novel architecture.

## Common Pitfalls

### Pitfall 1: Schema Drift Between DDF Tables and Existing Tables
**What goes wrong:** The `flame_events` table references `session_id` but sessions use different ID formats across JSONL sources. Or `source_episode_id` references an episode that hasn't been written yet (pipeline step ordering).
**Why it happens:** Phase 15 adds 5+ new tables that cross-reference existing tables (episodes, events, premise_registry, memory_candidates, session_constraint_eval).
**How to avoid:** Write schema DDL in a single `create_ddf_schema()` function called from `create_schema()` in `storage/schema.py`. Use `VARCHAR` for all FK-like columns (not FOREIGN KEY constraints) -- this matches the existing codebase pattern where referential integrity is enforced in Python, not in DuckDB.
**Warning signs:** `INSERT INTO flame_events` fails with type mismatch; queries joining flame_events to episodes return zero rows.

### Pitfall 2: Pipeline Step Ordering for Tier 2 Deposit
**What goes wrong:** The write-on-detect deposit to `memory_candidates` fires before episodes are fully populated, producing entries with empty `flood_example` or incorrect `scope_rule`.
**Why it happens:** CONTEXT.md Q1 says "OPE pipeline processes flame_events, confirms Level 6, writes to memory_candidates atomically with confirmation." This means the deposit step MUST run after episode population (Step 9), episode validation (Step 10), and Tier 2 LLM enrichment. If placed too early in the pipeline, episode context is unavailable.
**How to avoid:** Place the deposit step as Step 17 or later (after Tier 2 enrichment at Step 16). The deposit step reads confirmed Level 6 flame_events and constructs memory_candidates entries using the fully populated episode data.
**Warning signs:** memory_candidates entries have empty flood_example; detection_count never increments (dedup check failing).

### Pitfall 3: O_AXS Detector State Leaking Between Sessions
**What goes wrong:** `known_concepts` set accumulates across sessions, causing concepts from session A to suppress detection in session B.
**Why it happens:** CONTEXT.md Q3 says "known_concepts: per-session only (reset at session start)." If the O_AXS detector is instantiated once and reused across `run_batch()` calls, the set persists.
**How to avoid:** Instantiate the O_AXS detector fresh per session (matching the EpisodeSegmenter pattern at `runner.py` line 246: "Create a fresh segmenter for each session (clean state)"). Or explicitly call a `reset()` method at session start.
**Warning signs:** O_AXS detection rate drops in batch mode; second session in a batch produces fewer O_AXS events than when run standalone.

### Pitfall 4: Memory Candidates Dedup Race with Existing Entries
**What goes wrong:** The soft dedup check `(ccd_axis, scope_rule)` misses existing entries because the text comparison is case-sensitive or whitespace-sensitive, leading to near-duplicate entries.
**Why it happens:** CONTEXT.md Q8 says "Soft dedup: check (ccd_axis, scope_rule) before INSERT; if exists, UPDATE detection_count." But if the ccd_axis text differs by trailing whitespace or casing, the check misses.
**How to avoid:** Normalize ccd_axis and scope_rule before comparison (TRIM + LOWER). Use a deterministic dedup_key column: `SHA-256(LOWER(TRIM(ccd_axis)) + LOWER(TRIM(scope_rule)))[:16]`.
**Warning signs:** `SELECT ccd_axis, COUNT(*) FROM memory_candidates GROUP BY ccd_axis HAVING COUNT(*) > 1` returns results with near-identical text.

### Pitfall 5: DuckDB ALTER TABLE NOT NULL DEFAULT on Existing Table
**What goes wrong:** `ALTER TABLE memory_candidates ADD COLUMN fidelity INTEGER NOT NULL DEFAULT 2` fails because DuckDB 1.4.4 may not support `NOT NULL` on `ALTER TABLE ADD COLUMN` for existing rows.
**Why it happens:** DuckDB's `ALTER TABLE ADD COLUMN` behavior for `NOT NULL` columns depends on the version. In some versions, adding a `NOT NULL` column to a table with existing rows requires a DEFAULT that satisfies the constraint.
**How to avoid:** Test the exact ALTER TABLE statement against a table with existing rows in a test. If it fails, use `INTEGER DEFAULT 2` (without NOT NULL) and enforce NOT NULL in the Python writer code. This matches the codebase pattern where CHECK constraints are in CREATE TABLE but ALTER TABLE additions are nullable.
**Warning signs:** Schema creation fails on a database with existing memory_candidates rows; tests pass on empty databases but fail on populated ones.

### Pitfall 6: Existing Test Count Regression
**What goes wrong:** New DDF tests break existing tests because `create_schema()` now calls `create_ddf_schema()`, which requires the `memory_candidates` table, but some test fixtures don't call `create_review_schema()`.
**Why it happens:** The `create_schema()` function in `storage/schema.py` is called by many test fixtures. If `create_ddf_schema()` is added to it and references `memory_candidates` (from `review/schema.py`), tests that don't set up review schema will fail.
**How to avoid:** Either (a) call `create_ddf_schema()` separately from `create_schema()` (like `create_premise_schema()` which is already imported and called at line 403), or (b) make `create_ddf_schema()` internally call `create_review_schema()` first to ensure `memory_candidates` exists. Option (a) matches the established pattern better.
**Warning signs:** Existing test suite drops from 1349 passing to <1349 after adding DDF schema.

## Code Examples

### Example 1: FlameEvent Pydantic Model

```python
# Follow project pattern: frozen BaseModel (like PremiseRecord, EpisodeSegment)
from pydantic import BaseModel, ConfigDict

class FlameEvent(BaseModel, frozen=True):
    """A DDF marker detection record for flame_events table.

    Covers both human and AI markers. Subject field distinguishes.
    """
    model_config = ConfigDict(populate_by_name=True)

    flame_event_id: str
    session_id: str
    human_id: str | None = None
    prompt_number: int | None = None
    marker_level: int
    marker_type: str
    evidence_excerpt: str | None = None
    quality_score: float | None = None
    axis_identified: str | None = None
    flood_confirmed: bool = False
    subject: str = "human"  # 'human' | 'ai'
    detection_source: str = "stub"  # 'stub' | 'opeml'
    deposited_to_candidates: bool = False
    source_episode_id: str | None = None
    session_event_ref: str | None = None
    created_at: str | None = None
```

### Example 2: Tier 1 Marker Detection (L0 Trunk ID)

```python
import re

# L0: Trunk identification -- human explicitly names the core concept/axis.
# HIGH RECALL: broad regex catches many false positives; Tier 2 filters.
# Evidence: MEMORY.md "Level 0 Trunk Identification = human re-indexes AI's Basement"
L0_TRUNK_PATTERNS = [
    re.compile(r"\bthe (?:core|real|actual|fundamental|key|essential|root) (?:issue|problem|question|concept|axis|principle)\b", re.IGNORECASE),
    re.compile(r"\bthis is (?:really|fundamentally|essentially|actually) about\b", re.IGNORECASE),
    re.compile(r"\bthe trunk (?:is|here is)\b", re.IGNORECASE),
    re.compile(r"\bwhat (?:I|we) (?:actually|really) (?:need|want|mean)\b", re.IGNORECASE),
]

def detect_l0_trunk(text: str) -> tuple[bool, str | None]:
    """Detect Level 0 trunk identification in human text.

    Returns (detected, evidence_excerpt).
    """
    for pattern in L0_TRUNK_PATTERNS:
        match = pattern.search(text)
        if match:
            # Extract surrounding context (up to 200 chars)
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 150)
            return True, text[start:end]
    return False, None
```

### Example 3: O_AXS Detector with Session State

```python
import re
from collections import deque

class OAxsDetector:
    """Detects axis shift: instruction granularity drops + novel concept introduced.

    Per-session state. Must be reset between sessions.
    """

    def __init__(self, config):
        self._drop_ratio = config.ddf.o_axs.granularity_drop_ratio
        self._window = config.ddf.o_axs.prior_prompts_window
        self._min_occurrences = config.ddf.o_axs.novel_concept_min_occurrences
        self._msg_window = config.ddf.o_axs.novel_concept_message_window

        # Per-session state
        self._token_counts: deque[int] = deque(maxlen=self._window)
        self._known_concepts: set[str] = set()
        self._recent_messages: deque[str] = deque(maxlen=self._msg_window)

        # Capitalized noun phrase pattern (simplified)
        self._noun_phrase_re = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b')

    def reset(self) -> None:
        """Reset per-session state."""
        self._token_counts.clear()
        self._known_concepts.clear()
        self._recent_messages.clear()

    def detect(self, text: str, actor: str) -> tuple[bool, dict | None]:
        """Detect O_AXS in a human message.

        Returns (detected, evidence_dict).
        """
        if actor != "human_orchestrator":
            return False, None

        token_count = len(text.split())
        self._recent_messages.append(text)

        # Check granularity drop
        granularity_dropped = False
        if len(self._token_counts) >= self._window:
            avg_prior = sum(self._token_counts) / len(self._token_counts)
            if avg_prior > 0 and token_count < self._drop_ratio * avg_prior:
                granularity_dropped = True

        self._token_counts.append(token_count)

        # Check novel concept
        novel_concept = None
        phrases = self._noun_phrase_re.findall(text)
        for phrase in phrases:
            if phrase not in self._known_concepts:
                # Count occurrences in recent messages
                count = sum(
                    1 for msg in self._recent_messages
                    if phrase in msg
                )
                if count >= self._min_occurrences:
                    novel_concept = phrase
                    break

        # Update known concepts
        for phrase in phrases:
            self._known_concepts.add(phrase)

        if granularity_dropped and novel_concept:
            return True, {
                "token_count": token_count,
                "avg_prior": sum(self._token_counts) / max(1, len(self._token_counts)),
                "novel_concept": novel_concept,
            }

        return False, None
```

### Example 4: Writer Pattern for flame_events

```python
# Follow the write_amnesia_events pattern (INSERT OR REPLACE on PK)
def write_flame_events(
    conn: duckdb.DuckDBPyConnection,
    events: list,  # list of FlameEvent
) -> dict[str, int]:
    """Write flame events to DuckDB with INSERT OR REPLACE.

    Uses flame_event_id primary key for idempotent storage.
    """
    if not events:
        return {"written": 0}

    for event in events:
        conn.execute(
            """
            INSERT OR REPLACE INTO flame_events
            (flame_event_id, session_id, human_id, prompt_number,
             marker_level, marker_type, evidence_excerpt, quality_score,
             axis_identified, flood_confirmed, subject, detection_source,
             deposited_to_candidates, source_episode_id, session_event_ref,
             created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event.flame_event_id,
                event.session_id,
                event.human_id,
                event.prompt_number,
                event.marker_level,
                event.marker_type,
                event.evidence_excerpt,
                event.quality_score,
                event.axis_identified,
                event.flood_confirmed,
                event.subject,
                event.detection_source,
                event.deposited_to_candidates,
                event.source_episode_id,
                event.session_event_ref,
                event.created_at,
            ],
        )

    logger.info("Wrote {} flame events", len(events))
    return {"written": len(events)}
```

### Example 5: IntelligenceProfile Aggregation Query

```python
# DDF-04: Basic IntelligenceProfile per-human aggregate
INTELLIGENCE_PROFILE_SQL = """
SELECT
    human_id,
    COUNT(*) AS flame_frequency,
    AVG(marker_level) AS avg_marker_level,
    -- spiral_depth: max consecutive ascending marker levels per session
    MAX(marker_level) AS max_marker_level,
    -- flood_rate: proportion of marker_level >= 6 events
    SUM(CASE WHEN marker_level >= 6 THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) AS flood_rate,
    COUNT(DISTINCT session_id) AS session_count
FROM flame_events
WHERE subject = 'human'
  AND human_id = ?
GROUP BY human_id
"""
```

### Example 6: GeneralizationRadius Computation

```python
# DDF-05: Count-based proxy from CONTEXT.md Q6
GENERALIZATION_RADIUS_SQL = """
SELECT
    sce.constraint_id,
    COUNT(DISTINCT
        CASE
            WHEN LENGTH(COALESCE(
                json_extract_string(sce.evidence_json, '$.scope_path'), ''
            )) > 0
            THEN SPLIT_PART(
                json_extract_string(sce.evidence_json, '$.scope_path'),
                '/', 1
            )
            ELSE 'root'
        END
    ) AS radius,
    COUNT(*) AS firing_count
FROM session_constraint_eval sce
WHERE sce.eval_state = 'active'
GROUP BY sce.constraint_id
"""

# Stagnation detection (CONTEXT.md Q6):
# radius = 1 AND firing_count >= 10 => stagnation flagged
```

### Example 7: memory_candidates Deposit with Soft Dedup

```python
def deposit_to_memory_candidates(
    conn: duckdb.DuckDBPyConnection,
    ccd_axis: str,
    scope_rule: str,
    flood_example: str,
    source_flame_event_id: str,
    pipeline_component: str = "ddf_tier2",
    fidelity: int = 2,
) -> str | None:
    """Deposit a memory candidate with soft dedup.

    CONTEXT.md Q8: check (ccd_axis, scope_rule) before INSERT;
    if exists, UPDATE detection_count.

    Returns candidate_id if inserted, None if deduped (count incremented).
    """
    # Soft dedup check
    existing = conn.execute(
        "SELECT id, detection_count FROM memory_candidates "
        "WHERE LOWER(TRIM(ccd_axis)) = LOWER(TRIM(?)) "
        "AND LOWER(TRIM(scope_rule)) = LOWER(TRIM(?))",
        [ccd_axis, scope_rule],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE memory_candidates SET detection_count = detection_count + 1 "
            "WHERE id = ?",
            [existing[0]],
        )
        return None

    candidate_id = hashlib.sha256(
        (ccd_axis + scope_rule + source_flame_event_id).encode()
    ).hexdigest()

    conn.execute(
        """
        INSERT INTO memory_candidates
        (id, ccd_axis, scope_rule, flood_example,
         source_flame_event_id, pipeline_component,
         heuristic_description, status, fidelity, detection_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, 1)
        """,
        [
            candidate_id,
            ccd_axis,
            scope_rule,
            flood_example,
            source_flame_event_id,
            pipeline_component,
            f"DDF Tier {fidelity} deposit",
            fidelity,
        ],
    )
    return candidate_id
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-prompt heuristic scanning only | Two-tier fidelity (Tier 1 heuristic + Tier 2 OPE LLM) | Phase 14-04 spike results | Per-prompt scanning has ~10-20% precision; Tier 2 enrichment via OPE pipeline produces structured episodes with reaction labels |
| memory_candidates from review system only | memory_candidates from DDF detection + review system | Phase 15 | memory_candidates table gains `source_flame_event_id`, `fidelity`, `detection_count` columns; becomes the unified deposit target for both detection pathways |
| Constraints in JSON file only | Constraints + constraint_metrics in DuckDB | Phase 15 Q6 | GeneralizationRadius, stagnation detection live in DuckDB `constraint_metrics` table, not bloating constraints.json |
| No DDF tables | flame_events + ai_flame_events + axis_hypotheses + constraint_metrics | Phase 15 | Four new DuckDB tables form the detection substrate |

**Deprecated/outdated:**
- Phase 14 spike determined that a new "memory ingestion component" is NOT needed -- the existing `python -m src.pipeline.cli extract` command IS the post-task memory ingestion step (3.3s for 498 events)
- Per-prompt heuristic scanning alone is insufficient (10-20% precision) -- always pair with Tier 2 enrichment

## DuckDB-Specific Technical Notes

### DuckDB 1.4.4 Capabilities (Verified)

- **JSON type:** Supported. Use `JSON` column type (not `JSONB` -- DuckDB has no JSONB). Query with `json_extract_string(col, '$.key')`.
- **CHECK constraints:** Supported on CREATE TABLE. The existing `memory_candidates` table uses CHECK constraints (e.g., `CHECK (LENGTH(TRIM(ccd_axis)) > 0)`).
- **INSERT OR REPLACE:** Supported on tables with PRIMARY KEY. Used throughout the codebase for idempotent writes.
- **ALTER TABLE ADD COLUMN:** Supported. For NOT NULL columns with DEFAULT, test with existing rows. The codebase pattern wraps in try/except for idempotency.
- **MERGE statement:** Supported. Used in `write_episodes()` for upsert.
- **Window functions:** Supported. Used in `PARENT_EPISODE_BACKFILL_SQL` (LAG).
- **Staging table pattern:** Established pattern for batch upserts (see `_batch_upsert()` in `writer.py`).

### DuckDB Single-Writer Constraint

The project enforces single-writer access to DuckDB. The bus process owns all writes (Phase 14 decision). In Phase 15:
- All flame_events writes go through the OPE pipeline (runner.py), which holds the single DuckDB connection.
- No concurrent writes from hooks or other processes.
- The PAG hook opens read-only connections (`duckdb.connect(str(db_path), read_only=True)`).

## New DuckDB Tables Summary

| Table | Purpose | Primary Key | Key Columns |
|-------|---------|-------------|-------------|
| `flame_events` | DDF marker detections for human reasoning | `flame_event_id` | session_id, marker_level (0-7), marker_type, subject ('human'\|'ai'), detection_source ('stub'\|'opeml'), deposited_to_candidates |
| `ai_flame_events` | DDF markers for AI reasoning (same schema, separate table for clarity) | `ai_flame_event_id` | Same as flame_events with subject='ai' |
| `axis_hypotheses` | LLM-hypothesized axes from False Integration detection (DDF-07) | `hypothesis_id` | session_id, episode_id, hypothesized_axis, confidence, marker_type |
| `constraint_metrics` | GeneralizationRadius, firing counts, stagnation flags | `constraint_id` (natural key) | radius, firing_count, is_stagnant |

**Note on ai_flame_events vs flame_events:** CONTEXT.md DDF-02 and DDF-03 specify separate tables. However, the schemas are identical with only `subject` field differing. The planner should decide whether to implement as two tables (per spec) or one table with `subject` column (per DRY). The CONTEXT.md says "ai_flame_events DuckDB table records DDF markers detected in AI's own reasoning: same schema as flame_events with subject='ai'" -- this is compatible with either approach. A single `flame_events` table with `subject IN ('human', 'ai')` CHECK constraint is simpler and equally queryable via `WHERE subject = 'ai'`.

## Constraints.json Schema Extension

CONTEXT.md Q5 requires two new columns on constraint objects:
- `epistemological_origin: reactive | principled | inductive` (string enum)
- `epistemological_confidence: float`

These go in `data/schemas/constraint.schema.json` (adding two new properties) and in `data/constraints.json` (as nullable fields on existing constraints, with default `"principled"` and `1.0`). The ConstraintExtractor in `constraint_extractor.py` will need to set these fields on newly extracted constraints.

## Open Questions

1. **ai_flame_events: separate table or unified flame_events?**
   - What we know: CONTEXT.md DDF-03 says "same schema as flame_events with subject='ai'". The `subject` field already exists in the flame_events schema.
   - What's unclear: Whether to literally create a second table or use a single table with CHECK constraint.
   - Recommendation: Use a single `flame_events` table with `subject IN ('human', 'ai')` CHECK constraint. This is DRY, requires one writer function, and the planner can always create a view `CREATE VIEW ai_flame_events AS SELECT * FROM flame_events WHERE subject = 'ai'` for convenience. Flag this decision for the planner.

2. **LLM Integration for Tier 2**
   - What we know: The project uses LLM calls in the ConstraintExtractor. Tier 2 requires LLM scoring for L3-7 and False Integration.
   - What's unclear: Whether there's an existing LLM abstraction/client in the codebase, or if each component makes raw API calls.
   - Recommendation: The planner should investigate `src/pipeline/constraint_extractor.py` and any LLM client pattern. If none exists, create a minimal LLM client utility in `src/pipeline/ddf/tier2/llm.py` following the project's existing patterns.

3. **human_id Source**
   - What we know: flame_events requires `human_id` for per-human IntelligenceProfile. The existing events table has `actor` but not a persistent human_id.
   - What's unclear: Where does human_id come from? Is it extracted from session metadata?
   - Recommendation: For Phase 15, use a heuristic: extract human_id from the session JSONL metadata or default to "default_human" for single-user workflows. Add `human_id` as a nullable column; IntelligenceProfile queries filter `WHERE human_id IS NOT NULL`.

4. **Spiral Depth Computation**
   - What we know: DDF-04 lists `spiral_depth` as an IntelligenceProfile metric. The CONTEXT.md does not define its computation.
   - What's unclear: What exactly constitutes "spiral depth" -- is it the longest ascending sequence of marker_levels within a session?
   - Recommendation: Implement as `MAX(consecutive ascending marker_levels per session)`. This can be computed with a window function. Mark as LOW confidence and validate with the user.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/storage/schema.py` -- established schema extension patterns (14 phases of DDL)
- `src/pipeline/storage/writer.py` -- established writer patterns (INSERT OR REPLACE, staging table, MERGE)
- `src/pipeline/models/config.py` -- established config model patterns (PipelineConfig, sub-models)
- `src/pipeline/runner.py` -- established pipeline step integration (14.5 steps, try/except pattern)
- `src/pipeline/premise/` -- Phase 14.1 patterns for new DuckDB tables + models + registry
- `src/pipeline/review/schema.py` -- existing memory_candidates DDL (the table being extended)
- `.planning/phases/14-live-session-governance-research/14-04-SPIKE-RESULTS.md` -- validated architectural decisions
- `.planning/phases/15-ddf-detection-substrate/15-CONTEXT.md` -- locked decisions for Phase 15

### Secondary (MEDIUM confidence)
- DuckDB 1.4.4 documentation (ALTER TABLE, JSON type, CHECK constraints) -- verified via installed version
- Pydantic v2.11.7 documentation (BaseModel, frozen=True, ConfigDict) -- verified via installed version

### Tertiary (LOW confidence)
- spiral_depth computation -- no definition in CONTEXT.md; inferred from DDF-04 requirement name
- human_id extraction -- no established pattern in codebase; requires discovery

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used throughout the project
- Architecture: HIGH -- all patterns already established in prior phases; no novel architecture
- Schema design: HIGH -- tables defined in CONTEXT.md decisions; DDL patterns from 14 prior phases
- Tier 1 detection heuristics: MEDIUM -- regex patterns are custom; effectiveness depends on session data
- Tier 2 LLM integration: MEDIUM -- requires LLM client pattern investigation; not yet verified
- Pitfalls: HIGH -- derived from direct codebase analysis of 14 prior schema migrations and 1349 tests
- IntelligenceProfile metrics: LOW -- spiral_depth undefined; human_id source unclear

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (stable domain; no external API dependencies)
