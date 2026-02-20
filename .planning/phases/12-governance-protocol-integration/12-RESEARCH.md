# Phase 12: Governance Protocol Integration - Research

**Researched:** 2026-02-20
**Domain:** Markdown parsing, dual-store ingestion, subprocess execution, DuckDB schema migration, Click CLI
**Confidence:** HIGH

## Summary

Phase 12 introduces a governance pipeline that bridges unstructured Markdown governance documents (pre-mortem files, DECISIONS.md) to the existing ConstraintStore (JSON) and WisdomStore (DuckDB). The implementation requires: (1) a header-hierarchy Markdown parser, (2) a dual-store ingestor orchestrating sequential writes, (3) a subprocess-based stability check runner, (4) DuckDB schema migration for new columns and a new table, and (5) a Click CLI subcommand group.

The codebase has strong, consistent patterns from Phases 9-11 that Phase 12 should follow exactly: config models defined inline in `src/pipeline/models/config.py` as Pydantic BaseModel subclasses, CLI groups defined as Click `@click.group()` functions registered in `__main__.py`, and DuckDB schema changes applied idempotently via `ALTER TABLE ... ADD COLUMN` with try/except in `storage/schema.py`. The ConstraintStore uses JSON Schema validation with `additionalProperties: false`, which means new fields like `source_excerpt` require a schema update. The WisdomEntity model has no metadata JSON column, so storing `related_constraint_ids` requires adding either a new column or model field.

For Markdown parsing, the project has no Markdown parsing library in requirements.txt. Given the locked decision to use header-hierarchy parsing with keyword matching (not full AST parsing), Python's stdlib `re` module with regex-based header extraction is the simplest approach and avoids adding a dependency. The 4 analysis documents have been thoroughly examined: they do NOT follow pre-mortem format, confirming the CLARIFICATIONS-ANSWERED.md decision to create a synthesized `data/objectivism_premortem.md` governance fixture.

**Primary recommendation:** Follow existing codebase patterns exactly -- Pydantic config in config.py, Click CLI in govern.py, DuckDB schema in schema.py, re-based Markdown parsing in a new `src/pipeline/governance/` package. No new dependencies needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Parser**: Header-hierarchy Markdown parser. H2/H3 headers with keywords "Failure Stories"/"Ways We Could Fail" -> dead_end extraction. Headers with "Assumptions"/"Key Assumptions" -> constraint extraction. Headers with "Decisions"/"Scope Decisions" -> scope_decision extraction. No YAML frontmatter required.

2. **Classification granularity**: Top-level list items within sections = one entity each. Linguistic regex as secondary check only.

3. **Bulk operation signal**: Ingest-triggered only (>=5 entities written in one govern ingest call). Configurable threshold `governance.bulk_ingest_threshold: 5`.

4. **Stability check**: Config-registered commands in data/config.yaml under `governance.stability_checks`. Execute via subprocess.run with 120s timeout. Results in new DuckDB table `stability_outcomes`. CLI exit codes: 0=pass, 1=error, 2=any-check-failed.

5. **Missing validation persistence**: Add `requires_stability_check BOOLEAN DEFAULT FALSE` and `stability_check_status VARCHAR` to `episodes` DuckDB table. `govern check-stability` is the active actor that marks episodes validated/missing (on-demand, no background timers).

6. **Idempotency**: SHA-256 content IDs + upsert semantics. WisdomIngestor.upsert() for wisdom. ConstraintStore.add() (already dedup-aware) for constraints.

7. **Dual-store write**: Sequential -- JSON ConstraintStore first (atomic rename), DuckDB WisdomStore second (DuckDB transaction). No DuckDB constraint mirror table.

8. **Constraint severity**: Default `requires_approval`. Apply forbidden heuristic: regex `\b(must not|never|forbidden|do not|shall not)\b` -> `forbidden`. Record `created_by: "govern_ingest"`.

9. **Wisdom-constraint linkage**: `related_constraint_ids: List[str]` in WisdomEntity metadata JSON field. Co-occurrence heuristic (same document = linked).

10. **Reference dataset fixture**: Create `data/objectivism_premortem.md` governance fixture by synthesizing content from the 4 analysis docs. Target: 11 failure stories + 15 assumptions. The analysis docs are in `docs/analysis/objectivism-knowledge-extraction/`.

11. **CLI**: New `govern` subcommand group. Commands: `ingest <file> [--dry-run] [--source-id]`, `check-stability [--output json/text]`. Exit code convention: 0=clean, 1=error, 2=failure/violation.

12. **DECISIONS.md**: Produces only wisdom entities (scope_decision/method_decision), NOT constraints.

### Claude's Discretion

No explicitly marked discretion areas in CONTEXT.md. All decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- Directory ingestion (file-only for Phase 12)
- Session-level bulk detection (file-edit volume across tool events)
- Semantic similarity for wisdom-constraint linkage (co-occurrence heuristic only)
- DuckDB constraint mirror table
- Time-window grace period for missing validation (on-demand only)
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `re` | stdlib | Markdown header parsing and regex matching | No external dependency needed for header-hierarchy parsing; project already uses `re` in 9 modules |
| `duckdb` | >=1.0.0 (installed: 1.4.4) | WisdomStore, stability_outcomes table, episodes table | Already the project's primary analytical store |
| `pydantic` | >=2.0.0 (installed: 2.11.7) | GovernanceConfig, IngestResult, StabilityOutcome models | Project standard for all config and data models |
| `click` | >=8.0.0 (installed: 8.3.1) | govern CLI subcommand group | Project standard for all CLI commands |
| `pyyaml` | >=6.0.0 (installed: 6.0.3) | Config loading from data/config.yaml | Already used by load_config() |
| `loguru` | >=0.7 | Logging | Project standard logger |
| `hashlib` | stdlib | SHA-256 content IDs for constraints | Already used by ConstraintStore and WisdomEntity |
| `subprocess` | stdlib | Stability check command execution | Already used in git_history.py adapter |
| `jsonschema` | >=4.20.0 | Constraint validation | Already used by ConstraintStore |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uuid` | stdlib | run_id for stability_outcomes | Each stability check run gets a UUID |
| `json` | stdlib | ConstraintStore JSON operations | Already used throughout |
| `datetime` | stdlib | Timestamps for stability outcomes | Already used throughout |
| `pathlib` | stdlib | File path handling | Project standard |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `re` for Markdown | `mistune` 3.1.3 (installed) | Full AST parser; overkill for header-keyword matching. Adds complexity and dependency for no benefit given the locked header-hierarchy approach. |
| `re` for Markdown | `markdown-it-py` 4.0.0 (installed) | Same tradeoff as mistune. Would give proper AST but the parser only needs H2/H3 headers + list items. |
| Custom parser | YAML frontmatter | CONTEXT.md explicitly locked: "No YAML frontmatter required" |

**Installation:**
```bash
# No new dependencies needed. All libraries already in requirements.txt or stdlib.
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/governance/
    __init__.py          # Package init, exports main classes
    parser.py            # GovDocParser: Markdown -> structured sections/entities
    ingestor.py          # GovDocIngestor: orchestrates dual-store writes
    stability.py         # StabilityRunner: subprocess execution + outcome recording
    config.py            # GovernanceConfig (NOTE: should be in models/config.py per project pattern)
src/pipeline/cli/
    govern.py            # govern CLI group (ingest, check-stability)
data/
    objectivism_premortem.md  # Canonical governance fixture (11 stories + 15 assumptions)
```

**CRITICAL NOTE on config.py location:** Despite CLARIFICATIONS-ANSWERED.md listing `src/pipeline/governance/config.py` as a new module, the project pattern is to define ALL config models inline in `src/pipeline/models/config.py` alongside `EscalationConfig`, `DurabilityConfig`, etc. GovernanceConfig should follow this pattern -- defined in `models/config.py` and added as a field on `PipelineConfig`.

### Pattern 1: Config Model Definition (from existing code)
**What:** All phase-specific config models are Pydantic BaseModel subclasses defined inline in `src/pipeline/models/config.py`, added as fields on PipelineConfig with default_factory.
**When to use:** Always, for every new phase config.
**Example:**
```python
# Source: src/pipeline/models/config.py (lines 158-176, existing pattern)

class EscalationConfig(BaseModel):
    """Escalation detection settings (Phase 9)."""
    window_turns: int = 5
    exempt_tools: list[str] = Field(default_factory=lambda: [...])
    # ...

class DurabilityConfig(BaseModel):
    """Decision durability tracking settings (Phase 10)."""
    min_sessions_for_score: int = 3
    evidence_excerpt_max_chars: int = 500

# GovernanceConfig follows same pattern:
class StabilityCheckDef(BaseModel):
    """Single stability check command definition."""
    id: str
    command: list[str]
    timeout_seconds: int = 120
    description: str = ""

class GovernanceConfig(BaseModel):
    """Governance protocol settings (Phase 12)."""
    bulk_ingest_threshold: int = 5
    stability_checks: list[StabilityCheckDef] = Field(default_factory=list)

# In PipelineConfig:
class PipelineConfig(BaseModel):
    # ... existing fields ...
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
```

### Pattern 2: CLI Group Registration (from existing code)
**What:** Click groups defined with `@click.group("name")` decorator, commands added with `@group.command(name="...")`, registered in `__main__.py` via `cli.add_command()`.
**When to use:** Always, for every new CLI subcommand group.
**Example:**
```python
# Source: src/pipeline/cli/wisdom.py (lines 22-25, existing pattern)

@click.group("govern")
def govern_group():
    """Governance protocol management."""
    pass

@govern_group.command(name="ingest")
@click.argument("path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview without writing.")
@click.option("--source-id", default=None, help="Override source document ID.")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--constraints", default="data/constraints.json", help="Constraints file.")
@click.option("--config", default="data/config.yaml", help="Pipeline config path.")
def ingest(path, dry_run, source_id, db, constraints, config):
    """Ingest a governance document (pre-mortem or DECISIONS.md)."""
    ...

# __main__.py registration:
from src.pipeline.cli.govern import govern_group
cli.add_command(govern_group, name="govern")
```

### Pattern 3: DuckDB Schema Migration (from existing code)
**What:** New columns added via `ALTER TABLE ... ADD COLUMN` wrapped in try/except to be idempotent. New tables use `CREATE TABLE IF NOT EXISTS`.
**When to use:** Always, for schema changes in schema.py.
**Example:**
```python
# Source: src/pipeline/storage/schema.py (lines 250-265, existing pattern)

# Phase 9: Escalation-specific columns (nullable, backward-compatible)
escalation_columns = [
    ("escalate_block_event_ref", "VARCHAR"),
    ("escalate_bypass_event_ref", "VARCHAR"),
    # ...
]
for col_name, col_type in escalation_columns:
    try:
        conn.execute(f"ALTER TABLE episodes ADD COLUMN {col_name} {col_type}")
    except Exception:
        pass  # Column already exists (idempotent)

# Phase 12: Governance columns on episodes
governance_columns = [
    ("requires_stability_check", "BOOLEAN DEFAULT FALSE"),
    ("stability_check_status", "VARCHAR"),
]
for col_name, col_type in governance_columns:
    try:
        conn.execute(f"ALTER TABLE episodes ADD COLUMN {col_name} {col_type}")
    except Exception:
        pass
```

### Pattern 4: ConstraintStore Integration (from existing code)
**What:** ConstraintStore loads JSON, validates against schema, deduplicates by constraint_id. The `add()` method returns True if new, False if duplicate (enriches existing examples). Must call `save()` explicitly.
**When to use:** For writing governance-ingested constraints.
**Example:**
```python
# Source: src/pipeline/constraint_store.py (lines 58-95)

store = ConstraintStore(
    path=Path("data/constraints.json"),
    schema_path=Path("data/schemas/constraint.schema.json"),
)

constraint = {
    "constraint_id": hashlib.sha256((text + json.dumps(scope_paths)).encode()).hexdigest()[:16],
    "text": "Assumption text from pre-mortem",
    "severity": "requires_approval",  # or "forbidden" if prohibition heuristic matches
    "scope": {"paths": []},
    "detection_hints": [original_text_excerpt[:80]],
    "source_episode_id": "",  # No episode for governance-ingested
    "created_at": datetime.now(timezone.utc).isoformat(),
    "examples": [],
    "type": "behavioral_constraint",
    "status": "active",
    "source": "govern_ingest",
    "status_history": [{"status": "active", "changed_at": datetime.now(timezone.utc).isoformat()}],
    "bypassed_constraint_id": None,
    "supersedes": None,
}

added = store.add(constraint)
store.save()  # Persist to disk
```

### Pattern 5: WisdomIngestor Usage (from existing code)
**What:** WisdomIngestor validates entries, generates deterministic IDs, and upserts into WisdomStore. Uses `_make_wisdom_id(entity_type, title)` for ID generation.
**When to use:** For writing governance-extracted wisdom entities.
**Example:**
```python
# Source: src/pipeline/wisdom/ingestor.py + models.py

from src.pipeline.wisdom.models import WisdomEntity, _make_wisdom_id
from src.pipeline.wisdom.store import WisdomStore

store = WisdomStore(db_path)

# GovDocIngestor builds WisdomEntity directly and calls store.upsert()
entity = WisdomEntity.create(
    entity_type="dead_end",
    title="pybreaker for circuit breaker",
    description="pybreaker tracks consecutive failures, not percentage-based rate",
    context_tags=["governance", "pre-mortem"],
    scope_paths=[],
    confidence=1.0,
    source_document="objectivism_premortem.md",
    source_phase=12,
)
store.upsert(entity)
```

### Anti-Patterns to Avoid
- **Defining GovernanceConfig in a separate governance/config.py:** Project pattern is ALL config in `src/pipeline/models/config.py`. Violating this splits config across files.
- **Using WisdomIngestor.ingest_list() for governance:** The existing ingestor expects JSON dicts. The governance ingestor should build WisdomEntity objects directly via `WisdomEntity.create()` and call `store.upsert()`, which gives more control over field mapping.
- **Using WisdomIngestor.ingest_file() for .md files:** It only handles JSON. The governance ingestor is a separate module that parses Markdown.
- **Adding new columns to episodes table outside schema.py:** ALL schema changes must go through `create_schema()` in `storage/schema.py` for idempotency.
- **Forgetting ConstraintStore.save():** The `add()` method only modifies in-memory state. You MUST call `save()` to persist to disk.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Constraint deduplication | Custom dedup logic | `ConstraintStore.add()` | Already SHA-256 dedup-aware; returns False for duplicates and enriches examples |
| Wisdom ID generation | Custom ID scheme | `_make_wisdom_id(entity_type, title)` | Deterministic `w-` + 16 hex chars from SHA-256, already standard |
| Wisdom upsert | Custom insert-or-update | `WisdomStore.upsert()` | Already implements INSERT OR REPLACE |
| Config loading | Custom YAML parser | `load_config()` from `models/config.py` | Already validates against Pydantic models |
| JSON Schema validation | Custom validation | `ConstraintStore._validator` (jsonschema) | Already set up with format checker |
| DuckDB connection | Direct duckdb.connect | `get_connection()` from `storage/schema.py` | Handles directory creation, consistent path handling |
| CLI logging setup | Custom logger config | `_setup_logging()` pattern from wisdom.py | Suppresses INFO, routes WARNING+ to stderr |

**Key insight:** Phase 12 is primarily an integration phase -- it connects existing stores (ConstraintStore, WisdomStore) to a new input source (Markdown documents). The core storage and validation infrastructure already exists. The new code is the parser, the orchestrating ingestor, and the stability runner.

## Common Pitfalls

### Pitfall 1: Constraint Schema Validation Failure
**What goes wrong:** New governance-ingested constraints fail JSON Schema validation because the schema has `additionalProperties: false` and a new field (like `source_excerpt`) was added without updating the schema.
**Why it happens:** The constraint schema at `data/schemas/constraint.schema.json` is strict. Any field not explicitly listed will cause `ConstraintStore.add()` to log a warning and return False.
**How to avoid:** Either (a) add `source_excerpt` to the JSON Schema before using it, or (b) put the source excerpt into the existing `detection_hints` array, which is already in the schema.
**Warning signs:** `store.add()` returns False for all governance constraints; loguru warnings about validation failures.

### Pitfall 2: ConstraintStore.save() Not Called
**What goes wrong:** Constraints are added in memory but never persisted to data/constraints.json.
**Why it happens:** `ConstraintStore.add()` modifies the in-memory list but does NOT auto-save. Explicit `store.save()` is required.
**How to avoid:** Always call `store.save()` after all `add()` calls in the governance ingestor.
**Warning signs:** Ingest reports "15 inserted" but `data/constraints.json` file doesn't change.

### Pitfall 3: WisdomEntity Has No Metadata JSON Column
**What goes wrong:** Attempting to store `related_constraint_ids` in a "metadata" field that doesn't exist.
**Why it happens:** CONTEXT.md decision 9 says "related_constraint_ids: List[str] in WisdomEntity metadata JSON field" but the WisdomEntity model and project_wisdom DuckDB table have NO metadata column. The model has: wisdom_id, entity_type, title, description, context_tags, scope_paths, confidence, source_document, source_phase, embedding.
**How to avoid:** One of these approaches:
  1. **Recommended:** Add a `metadata JSON` column to the `project_wisdom` table in schema.py and a `metadata: dict` field to WisdomEntity. This is the most flexible approach and aligns with the decision.
  2. **Alternative:** Store constraint IDs in `context_tags` with a prefix like `constraint:abc123`. Hacky but avoids schema change.
  3. **Alternative:** Add a `related_constraint_ids VARCHAR[]` column directly. More specific but less flexible.
**Warning signs:** AttributeError when trying to set `.metadata` on a WisdomEntity.

### Pitfall 4: Subprocess Timeout Not Handled
**What goes wrong:** `subprocess.run()` with `timeout=120` raises `subprocess.TimeoutExpired` which is not `Exception` subclass behavior you might expect.
**Why it happens:** TimeoutExpired IS a subclass of SubprocessError which IS a subclass of Exception, but the timeout behavior needs explicit handling for clean reporting.
**How to avoid:** Catch `subprocess.TimeoutExpired` explicitly, record it as `status='error'` in stability_outcomes with descriptive error message.
**Warning signs:** Unhandled exceptions when a stability check takes longer than 120 seconds.

### Pitfall 5: Markdown List Item Parsing Edge Cases
**What goes wrong:** Parser extracts wrong number of entities from the governance fixture because of nested lists, continuation lines, or sub-items.
**Why it happens:** Markdown list items can span multiple lines (indented continuation), have nested sub-lists, or use different markers (-, *, 1.).
**How to avoid:** Define "top-level list item" precisely: lines starting with `- `, `* `, or `N. ` at the section's base indentation level. Continuation lines (indented) are part of the same item. Nested sub-items (deeper indentation) are NOT separate entities.
**Warning signs:** Entity count doesn't match expected 11+15 from the fixture.

### Pitfall 6: Dual-Store Partial Write
**What goes wrong:** Constraints are written to JSON but wisdom write to DuckDB fails, leaving stores inconsistent.
**Why it happens:** Sequential write order: JSON first, DuckDB second. DuckDB connection issues, disk full, etc.
**How to avoid:** The CONTEXT.md decision accepts this: "If step 3 fails, constraints remain committed (acceptable -- they're independently valid)." Log the partial failure clearly. Return an IngestResult that accurately reports what was written.
**Warning signs:** Constraint count increases but wisdom count doesn't, or vice versa.

### Pitfall 7: Exit Code Confusion Between Error and Failure
**What goes wrong:** CLI returns exit code 1 (runtime error) when it should return 2 (validation failure/check failed), or vice versa.
**Why it happens:** The project uses a 3-code convention: 0=clean, 1=error, 2=failure. Mixing up "the command itself crashed" (1) vs "the command ran successfully and reported a failure condition" (2).
**How to avoid:** `sys.exit(1)` only in generic exception handlers. `sys.exit(2)` only when the command completed normally but found a problem (e.g., stability check failed, ingest found zero entities).
**Warning signs:** CI scripts that check exit codes get unexpected behavior.

## Code Examples

### Markdown Header-Hierarchy Parser
```python
# Recommended implementation approach for parser.py
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ParsedSection:
    """A section extracted from a governance Markdown document."""
    header_level: int        # 2 for H2, 3 for H3
    header_text: str         # Raw header text
    section_type: str        # "failure_story", "assumption", "scope_decision", "method_decision"
    items: list[str]         # Extracted list items or sub-heading blocks

# Header keyword mapping (from locked decision 1)
SECTION_KEYWORDS = {
    "failure_story": ["failure stories", "ways we could fail", "dead ends"],
    "assumption": ["assumptions", "key assumptions", "core assumptions"],
    "scope_decision": ["scope decisions", "decisions"],
    "method_decision": ["method decisions"],
}

_HEADER_RE = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
_LIST_ITEM_RE = re.compile(r'^[-*]\s+(.+)$|^(\d+)\.\s+(.+)$', re.MULTILINE)

def parse_sections(content: str) -> list[ParsedSection]:
    """Extract typed sections from Markdown content."""
    headers = list(_HEADER_RE.finditer(content))
    sections = []

    for i, match in enumerate(headers):
        level = len(match.group(1))  # 2 or 3
        text = match.group(2).strip()

        # Determine section type by keyword matching
        section_type = _classify_header(text)
        if section_type is None:
            continue

        # Extract content between this header and the next
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        body = content[start:end]

        # Extract top-level list items from body
        items = _extract_list_items(body)

        sections.append(ParsedSection(
            header_level=level,
            header_text=text,
            section_type=section_type,
            items=items,
        ))

    return sections

def _classify_header(text: str) -> str | None:
    """Match header text to a section type via keyword lookup."""
    lower = text.lower()
    for section_type, keywords in SECTION_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return section_type
    return None
```

### Forbidden Severity Heuristic
```python
# From locked decision 8
import re

_FORBIDDEN_RE = re.compile(
    r'\b(must not|never|forbidden|do not|shall not)\b',
    re.IGNORECASE,
)

def determine_severity(text: str) -> str:
    """Determine constraint severity from text content.

    Default: 'requires_approval'. Upgraded to 'forbidden' if
    prohibition language is detected.
    """
    if _FORBIDDEN_RE.search(text):
        return "forbidden"
    return "requires_approval"
```

### Constraint ID Generation for Governance-Ingested Constraints
```python
# Must match existing ConstraintStore dedup pattern
import hashlib
import json

def make_constraint_id(text: str, scope_paths: list[str]) -> str:
    """Generate deterministic constraint ID matching ConstraintStore pattern.

    Uses SHA-256 of (text + JSON-serialized scope_paths), truncated to 16 hex chars.
    """
    raw = (text + json.dumps(scope_paths, sort_keys=True)).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
```

### Stability Check Execution
```python
# From locked decision 4
import subprocess
import uuid
from datetime import datetime, timezone

def run_stability_check(
    check_id: str,
    command: list[str],
    timeout_seconds: int,
    cwd: str,
) -> dict:
    """Execute a stability check command and return outcome record."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd,
        )
        ended_at = datetime.now(timezone.utc)

        status = "pass" if result.returncode == 0 else "fail"

        return {
            "run_id": run_id,
            "check_id": check_id,
            "status": status,
            "exit_code": result.returncode,
            "stdout": result.stdout[:10000],  # Truncate for DuckDB storage
            "stderr": result.stderr[:10000],
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        }
    except subprocess.TimeoutExpired:
        ended_at = datetime.now(timezone.utc)
        return {
            "run_id": run_id,
            "check_id": check_id,
            "status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Timeout after {timeout_seconds}s",
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        }
```

### DuckDB stability_outcomes Table
```python
# New table in storage/schema.py
conn.execute("""
    CREATE TABLE IF NOT EXISTS stability_outcomes (
        run_id VARCHAR PRIMARY KEY,
        check_id VARCHAR NOT NULL,
        session_id VARCHAR,
        status VARCHAR NOT NULL CHECK (status IN ('pass', 'fail', 'error')),
        exit_code INTEGER,
        stdout TEXT,
        stderr TEXT,
        started_at TIMESTAMPTZ NOT NULL,
        ended_at TIMESTAMPTZ,
        actor_name VARCHAR,
        actor_email VARCHAR
    )
""")
conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_stability_session "
    "ON stability_outcomes(session_id)"
)
conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_stability_check_id "
    "ON stability_outcomes(check_id)"
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase config in separate files | All config in `models/config.py` | Phase 9 (EscalationConfig) | Single source of truth for all config; GovernanceConfig must follow |
| Manual constraint creation | ConstraintStore with JSON Schema validation | Phase 3 | Governance ingestor must create dicts matching the schema exactly |
| Wisdom from JSON files only | WisdomIngestor.ingest_list() + WisdomEntity.create() | Phase 11 | Governance can build WisdomEntity directly, no JSON intermediate |
| No subprocess usage in tests | subprocess in git_history adapter only | Phase 1 | Stability runner is only the second subprocess user; test with mock |

**Deprecated/outdated:**
- None relevant to Phase 12. All patterns from Phases 9-11 are current.

## Analysis Document Content Inventory

### REUSABLE_KNOWLEDGE_GUIDE.md
**Dead Ends section (Section B):** 6 entries with H3 sub-headings
1. Dead End 1: `pybreaker` for Circuit Breaker
2. Dead End 2: Single-Step Upload Assumption
3. Dead End 3: Mistral SDK Import Path
4. Dead End 4: Using `request_options` in Gemini Search
5. Dead End 5: Sync `sqlite3` in Async Upload Pipeline
6. Dead End 6: JSON Mode + Magistral Thinking Blocks Conflict

**No Assumptions section.** Has Breakthrough Moments (Section A) and Reusable Patterns (Section C).

### DECISION_AMNESIA_REPORT.md
**Section 1: Amnesia Inventory** -- 6 entries with H3 sub-headings:
1. 1.1 Layer 1 -- Scope Amnesia: Phase 6 Processing Only "Unknown" Files
2. 1.2 Layer 2 -- Method Amnesia: Reversion from Batch to Sequential Processing
3. 1.3 Constraint Amnesia: The "Unknown Files Only" Constraint vs the Full Pipeline
4. 1.4 Decision Amnesia: The Metadata-First Strategy Rationale
5. 1.5 Constraint Amnesia: The 48-Hour Gemini TTL
6. 1.6 Status Amnesia: Database State vs. Gemini State

**Section 3: Prevention Strategies** -- Contains DECISIONS.md template with Scope Decisions, Method Decisions, Constraint Decisions, Architecture Decisions. Contains verification gate templates.

### VALIDATION_GATE_AUDIT.md
**Section 1: Missing Gate Inventory** -- 9 entries with H3 sub-headings:
1. Gate 1: No Count Gate on Actual Scan Results
2. Gate 2: File Count After Full Upload Not Enforced
3. Gate 3: No Gate Requiring Full Upload Completion
4. Gate 4: Phase 6 Extraction Scope Not Machine-Verified
5. Gate 5: Agent Self-Imposed Count Gate, Accepted Partial
6. Gate 6: "Uploaded" Status Not Verified Against Gemini Store
7. Gate 7: 38 "Failed" Files Accepted Without Retry Gate
8. Gate 8: 148 Failures Accepted as "Edge Cases"
9. Gate 9: Polling Timeout Files Uncertain State Not Gated

**Section 2: The 100% Principle** -- Contains enforcement templates
**Section 3: Progressive Gate Strategy** -- Contains gate level definitions

### PROBLEM_FORMULATION_RETROSPECTIVE.md
**7 breakthroughs** -- each as H2 sections (not H3):
1-7: Problem formulation retrospectives about questions that could have accelerated discovery

**No failure stories, assumptions, or decisions sections.**

### Synthesis Plan for `data/objectivism_premortem.md`
Per CLARIFICATIONS-ANSWERED.md Q1/Q2:
- **11 failure stories:** 6 from REUSABLE_KNOWLEDGE_GUIDE.md Dead Ends + 5 selected from DECISION_AMNESIA_REPORT.md amnesia instances
- **15 assumptions:** 8-9 from VALIDATION_GATE_AUDIT.md missing gates (synthesized as assumption statements) + 6-7 from DECISION_AMNESIA_REPORT.md prevention strategies (synthesized as assumption statements)

The fixture must use the format:
```markdown
# Objectivism Library Project Pre-Mortem

## Failure Stories

### Story 1: pybreaker for Circuit Breaker
[description synthesized from Dead End 1]

### Story 2: ...
[11 total stories]

## Key Assumptions

- [Assumption 1 text synthesized from Gate 1]
- [Assumption 2 text]
[15 total assumptions as bullet list items]
```

## Open Questions

1. **WisdomEntity metadata field for related_constraint_ids**
   - What we know: CONTEXT.md decision 9 specifies `related_constraint_ids: List[str]` in "WisdomEntity metadata JSON field." The WisdomEntity model has no metadata field. The project_wisdom DuckDB table has no metadata column.
   - What's unclear: Whether to add a generic `metadata JSON` column (most flexible, matches decision language) or a specific `related_constraint_ids VARCHAR[]` column (simpler, more explicit).
   - Recommendation: Add a `metadata JSON` column to project_wisdom and a `metadata: dict | None = None` field to WisdomEntity. This matches the decision language and is extensible. Update `_row_to_entity()` and `upsert()` in WisdomStore to handle the new column.

2. **Constraint source_excerpt field**
   - What we know: CONTEXT.md decision 8 says "Record `created_by: 'govern_ingest'` and `source_excerpt: <original text>`." The `created_by` maps to the existing `source` field (use value "govern_ingest"). But `source_excerpt` is not in the constraint schema, and `additionalProperties: false` blocks unknown fields.
   - What's unclear: Whether to update the schema to add `source_excerpt`, or use `detection_hints` to carry the original text.
   - Recommendation: Add `source_excerpt` as a new optional property in `data/schemas/constraint.schema.json`. This is the cleanest approach and preserves the intended semantics. Alternatively, store the excerpt as the first item in `detection_hints`.

3. **Actor name/email for stability outcomes**
   - What we know: CLARIFICATIONS-ANSWERED.md specifies `actor_name` and `actor_email` columns on stability_outcomes, obtained from git config.
   - What's unclear: Whether `git config user.name` and `git config user.email` should be called during stability check execution or cached.
   - Recommendation: Call `subprocess.run(["git", "config", "user.name"])` once per `govern check-stability` invocation and reuse for all checks in that run. Cache as local variables, not persistent config.

4. **Exact content of the 15 assumptions in the fixture**
   - What we know: The target is 15 assumptions. Sources: VALIDATION_GATE_AUDIT.md (9 missing gates) and DECISION_AMNESIA_REPORT.md (6 prevention strategies). But these need to be reformulated as assumption statements.
   - What's unclear: The exact phrasing and selection. Some gates may be too specific to reformulate as general assumptions.
   - Recommendation: The fixture creation task should synthesize and phrase assumptions as declarative statements (e.g., "Pipeline phase completion must be verified by machine-checkable count queries, not narrative declarations"), then count to confirm exactly 15.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/models/config.py` -- Config model patterns (EscalationConfig, DurabilityConfig, PipelineConfig)
- `src/pipeline/wisdom/ingestor.py` -- WisdomIngestor pattern (IngestResult, ingest_list, ingest_file)
- `src/pipeline/wisdom/models.py` -- WisdomEntity model, _make_wisdom_id()
- `src/pipeline/wisdom/store.py` -- WisdomStore CRUD, upsert(), _ensure_schema()
- `src/pipeline/constraint_store.py` -- ConstraintStore with JSON Schema validation, dedup, save()
- `src/pipeline/storage/schema.py` -- DuckDB schema creation pattern, ALTER TABLE idempotent migration
- `src/pipeline/cli/wisdom.py` -- CLI group pattern, exit code convention, _setup_logging()
- `src/pipeline/cli/audit.py` -- CLI with --json output, db/constraints/config options
- `src/pipeline/cli/__main__.py` -- CLI group registration pattern
- `data/config.yaml` -- Configuration structure, escalation/durability sections
- `data/schemas/constraint.schema.json` -- Constraint JSON Schema (additionalProperties: false)
- `requirements.txt` -- No markdown parsing library present
- `docs/analysis/objectivism-knowledge-extraction/` -- All 4 analysis documents examined

### Secondary (MEDIUM confidence)
- Python `re` module documentation -- regex-based Markdown parsing approach
- Python `subprocess` module -- subprocess.run() with timeout, capture_output
- Existing codebase subprocess usage in `src/pipeline/adapters/git_history.py`

### Tertiary (LOW confidence)
- None. All findings are from direct codebase examination.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies needed
- Architecture: HIGH -- patterns directly observed in 6+ existing modules
- Pitfalls: HIGH -- identified from actual schema constraints and API behavior in codebase
- Analysis doc inventory: HIGH -- all 4 documents read in full, entity counts verified

**Research date:** 2026-02-20
**Valid until:** 2026-03-20 (stable -- internal codebase patterns, no external API changes)
