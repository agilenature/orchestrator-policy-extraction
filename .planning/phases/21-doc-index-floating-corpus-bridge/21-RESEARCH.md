# Phase 21: Doc Index Floating Corpus Bridge - Research

**Researched:** 2026-02-27
**Domain:** DuckDB schema extension, markdown corpus indexing, session-start briefing delivery
**Confidence:** HIGH (all patterns verified against existing codebase)

## Summary

Phase 21 adds three components: (1) a `doc_index` DuckDB table mapping 28 markdown files in `docs/` to CCD axis values, (2) a `doc_indexer.py` offline indexer with 3-tier axis extraction (frontmatter/regex/keyword), and (3) a session-start briefing extension delivering relevant docs alongside constraints via `/api/check`.

The codebase has well-established patterns for all three: schema DDL modules (`create_X_schema()` functions), CLI command groups (Click groups registered in `__main__.py`), and CheckResponse model extension (same as `epistemological_signals`). The primary implementation risk is the **query mechanism gap**: the CONTEXT.md assumes constraints carry `ccd_axis` values, but constraints.json has NO `ccd_axis` field. The GovernorDaemon currently reads only `constraints.json` (never `ope.db`). The query path must be redesigned: the daemon needs a DuckDB read connection to query `doc_index` for the `always-show` axis plus all non-unclassified entries, OR the axis filter must come from `memory_candidates` rather than constraints.

**Primary recommendation:** Follow existing codebase patterns exactly. Give GovernorDaemon a read-only DuckDB connection for doc_index queries. Deliver all non-unclassified docs ranked by confidence (max 3), plus `always-show` docs unconditionally. Do NOT attempt to filter by constraint axes since constraints lack that field.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **Axis extraction:** 3-tier hybrid cascade -- frontmatter (conf=1.0) -> regex in headers/comments (conf=0.7) -> keyword token matching (conf=0.4). Docs with no match get ccd_axis='unclassified'.

2. **Schema:** One row per (doc_path, ccd_axis). Columns: doc_path, ccd_axis, association_type CHECK IN ('frontmatter','regex','keyword','manual','unclassified'), extracted_confidence FLOAT, description_cache VARCHAR, section_anchor VARCHAR, content_hash VARCHAR, indexed_at TIMESTAMPTZ. PRIMARY KEY (doc_path, ccd_axis). File-level indexing only (not section-level).

3. **Write architecture:** Offline-first. doc_indexer.py checks for running bus via socket ping to /tmp/ope-governance-bus.sock; aborts if reachable. Runs full DELETE+INSERT refresh when bus stopped. Exposed as `python -m src.pipeline.cli docs reindex`.

4. **Query mechanism:** Extend /api/check response with `relevant_docs: list[dict]`. GovernorDaemon.get_briefing() queries doc_index for axes from active constraints. CheckResponse model extended (same pattern as epistemological_signals).

5. **Briefing format:** [OPE] prefix, max 3 docs, path + axis + description_cache (80 chars). Silent if 0 docs. Session_start.py reads relevant_docs from check response.

6. **General docs:** Reserved `always-show` ccd_axis for docs like GOVERNING-ORCHESTRATOR-METHODOLOGY.md. Delivered in every session regardless of constraint filter.

7. **Section-level indexing:** DEFERRED -- file-level only for Phase 21.

### Claude's Discretion
- Token overlap threshold for Tier 3 keyword matching (CONTEXT.md leaves open)
- Axis vocabulary source (memory_candidates vs. MEMORY.md vs. hardcoded list)
- How GovernorDaemon reads doc_index (new DuckDB connection vs. bus API)
- Description cache extraction strategy (first paragraph extraction)

### Deferred Ideas (OUT OF SCOPE)
- Section-level indexing (Phase 22 candidate)
- Incremental bus-owned refresh at startup
- Composite ranking (confidence + freshness + overlap weighting)
</user_constraints>

## Critical Finding: Constraint-to-Axis Query Gap

**Confidence: HIGH -- verified against data/constraints.json (275 constraints)**

The CONTEXT.md and CLARIFICATIONS-ANSWERED.md both assume that `GovernorDaemon.get_briefing()` will "extract unique ccd_axis values from active constraints" and use those to filter doc_index. This is impossible because:

1. **constraints.json has NO `ccd_axis` field.** Verified by inspecting all 275 constraints. The available keys are: `constraint_id`, `text`, `severity`, `scope`, `detection_hints`, `source_episode_id`, `created_at`, `examples`, `type`, `status_history`, `supersedes`, `epistemological_origin`, `epistemological_confidence`, `bypassed_constraint_id`, `source`, `status`.

2. **GovernorDaemon currently never reads ope.db.** The daemon docstring explicitly states: "DuckDB single-writer invariant: never reads ope.db directly." It reads only `data/constraints.json`.

3. **The axis vocabulary lives elsewhere.** CCD axes exist in:
   - `memory_candidates.ccd_axis` (DuckDB table)
   - `flame_events.axis_identified` (DuckDB table)
   - MEMORY.md (file, 15 axes listed)

**Resolution options (planner must choose one):**

| Option | How It Works | Pros | Cons |
|--------|-------------|------|------|
| A: Daemon reads doc_index directly | GovernorDaemon gets a DuckDB read connection; queries `SELECT ... FROM doc_index WHERE ccd_axis != 'unclassified' AND association_type != 'unclassified' ORDER BY extracted_confidence DESC LIMIT 5` plus `WHERE ccd_axis = 'always-show'` | Simplest; no constraint-axis dependency; reads are MVCC-safe | Breaks daemon's "never reads ope.db" convention |
| B: Filter by memory_candidates axes | Daemon reads ope.db to get validated axes from memory_candidates, then filters doc_index by those axes | More targeted filtering | Requires DB read; still no constraint-axis link |
| C: Deliver all non-unclassified docs | Since corpus is only 28 files, deliver top 3 by confidence from ALL non-unclassified entries | No filtering needed; always relevant | May not be most relevant to current session |

**Recommendation: Option A.** DuckDB MVCC means read-only connections are always safe. The "never reads ope.db" convention was about write conflicts, not reads. The daemon already accepts `db_path` in its constructor. Adding a read connection for doc_index queries is consistent with the architecture and avoids the false constraint-axis dependency.

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| DuckDB | (in requirements) | Storage for doc_index table | Project's primary analytical DB |
| Click | (in requirements) | CLI command group for `docs reindex` | All CLI commands use Click |
| Pydantic v2 | (in requirements) | CheckResponse model extension | All models use Pydantic |
| Starlette | (in requirements) | Bus server route handling | Bus server framework |
| hashlib (stdlib) | N/A | SHA-256 content hashing for change detection | Used throughout codebase |

### Supporting (new, minimal)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| PyYAML (or python-frontmatter) | Parse YAML frontmatter in docs | Tier 1 extraction only |

**Note on PyYAML:** Check if already in requirements. If not, a simple manual frontmatter parser (split on `---` markers, parse YAML block) avoids a new dependency. The frontmatter format is simple enough (just `axes: [list]`) that PyYAML alone suffices; `python-frontmatter` is overkill.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyYAML frontmatter | Manual string split on `---` | No new dependency but fragile |
| DuckDB read in daemon | Separate /api/docs endpoint | More code, same result |
| Token keyword matching | TF-IDF / embeddings | ML dependencies, unnecessary for 28 docs |

**Installation:**
```bash
# Check if PyYAML already installed:
pip show pyyaml
# If not:
pip install pyyaml
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/
  live/bus/
    doc_schema.py          # NEW: DOC_INDEX_DDL + create_doc_schema()
    schema.py              # MODIFY: wire create_doc_schema() into chain
    models.py              # MODIFY: add relevant_docs to CheckResponse
    server.py              # MODIFY: pass relevant_docs in /api/check response
  governor/
    daemon.py              # MODIFY: add doc_index query to get_briefing()
  hooks/
    session_start.py       # MODIFY: print relevant_docs block
  doc_indexer.py           # NEW: 3-tier axis extraction + bus-stop check
  cli/
    __main__.py            # MODIFY: register docs group
    docs.py                # NEW: docs CLI group with reindex subcommand
```

### Pattern 1: Schema DDL Module
**What:** Each subsystem defines its DDL as module-level string constants with a `create_X_schema()` function.
**When to use:** Always for new DuckDB tables.
**Example (verified from src/pipeline/live/bus/schema.py, src/pipeline/ddf/schema.py):**
```python
# src/pipeline/live/bus/doc_schema.py

from __future__ import annotations
import duckdb

DOC_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS doc_index (
    doc_path             VARCHAR NOT NULL,
    ccd_axis             VARCHAR NOT NULL,
    association_type     VARCHAR NOT NULL DEFAULT 'frontmatter'
        CHECK (association_type IN ('frontmatter', 'regex', 'keyword', 'manual', 'unclassified')),
    extracted_confidence FLOAT NOT NULL DEFAULT 1.0,
    description_cache    VARCHAR,
    section_anchor       VARCHAR,
    content_hash         VARCHAR NOT NULL,
    indexed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_path, ccd_axis)
)
"""

def create_doc_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create doc_index table idempotently. Safe to call on every startup."""
    conn.execute(DOC_INDEX_DDL)
```

### Pattern 2: Schema Chain Wiring
**What:** New schema functions are called from parent schema create functions.
**When to use:** Wiring doc_schema into the bus schema chain.
**Example (verified from src/pipeline/live/bus/schema.py lines 94-99):**
```python
# In create_bus_schema():
def create_bus_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(BUS_SESSIONS_DDL)
    conn.execute(GOVERNANCE_SIGNALS_DDL)
    _alter_bus_sessions(conn)
    conn.execute(PUSH_LINKS_DDL)
    # NEW: doc_index
    from .doc_schema import create_doc_schema
    create_doc_schema(conn)
```

### Pattern 3: CheckResponse Extension
**What:** Add new list field to CheckResponse model with empty default.
**When to use:** Adding relevant_docs to the check response.
**Example (verified from src/pipeline/live/bus/models.py lines 65-76):**
```python
class CheckResponse(BaseModel):
    constraints: list[dict[str, Any]] = []
    interventions: list[dict[str, Any]] = []
    epistemological_signals: list[dict[str, Any]] = []
    relevant_docs: list[dict[str, Any]] = []  # NEW: Phase 21
```

### Pattern 4: CLI Group Registration
**What:** Click groups defined in separate files, registered in __main__.py.
**When to use:** Adding `docs` CLI group.
**Example (verified from src/pipeline/cli/__main__.py and cli/bus.py):**
```python
# src/pipeline/cli/docs.py
import click

@click.group(name="docs")
def docs_group():
    """Documentation index management."""

@docs_group.command()
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option("--docs-dir", default="docs", help="Documentation directory")
def reindex(db: str, docs_dir: str):
    """Rebuild the doc_index table."""
    # ... implementation
```

```python
# In __main__.py:
from src.pipeline.cli.docs import docs_group
cli.add_command(docs_group, name="docs")
```

### Pattern 5: Bus Socket Check (Offline-First Write)
**What:** Check if bus daemon is running before writing to ope.db.
**When to use:** doc_indexer.py must verify bus is stopped.
**Example (verified from src/pipeline/live/hooks/session_start.py lines 48-61):**
```python
import socket

def _bus_is_running(socket_path: str = "/tmp/ope-governance-bus.sock") -> bool:
    """Check if the governance bus daemon is reachable."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(socket_path)
        sock.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
```

### Pattern 6: GovernorDaemon DB Read for doc_index
**What:** Daemon gains a read-only DuckDB connection to query doc_index.
**When to use:** Extending get_briefing() to return relevant docs.
**Key insight:** DuckDB supports concurrent readers via MVCC. The "single-writer" constraint means only ONE process writes; reads are always safe. The daemon already receives `db_path` in its constructor but currently ignores it for reads. Adding a read connection is architecturally sound.
```python
# In daemon.py get_briefing():
def _query_relevant_docs(self) -> list[dict[str, str]]:
    """Query doc_index for relevant documents."""
    try:
        conn = duckdb.connect(self._db_path, read_only=True)
        # Check if doc_index table exists (graceful pre-Phase-21 fallback)
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'doc_index'"
        ).fetchall()
        if not tables:
            conn.close()
            return []
        rows = conn.execute(
            "SELECT DISTINCT doc_path, ccd_axis, description_cache "
            "FROM doc_index "
            "WHERE association_type != 'unclassified' "
            "ORDER BY CASE WHEN ccd_axis = 'always-show' THEN 0 ELSE 1 END, "
            "extracted_confidence DESC "
            "LIMIT 5"
        ).fetchall()
        conn.close()
        return [
            {"doc_path": r[0], "ccd_axis": r[1], "description_cache": r[2] or ""}
            for r in rows
        ]
    except Exception:
        return []  # fail-open
```

### Anti-Patterns to Avoid
- **Writing to ope.db while bus is running:** DuckDB single-writer constraint. The doc_indexer MUST check bus status first.
- **Caching DuckDB connections in daemon:** The daemon is stateless between requests. Open and close read connections per call (fast for DuckDB read-only mode).
- **Printing full doc content to stdout:** Context window flooding. Only print paths + 80-char description.
- **Hardcoding axis vocabulary:** Load from memory_candidates or MEMORY.md, not a static list. New axes should be discoverable automatically.
- **Treating 'unclassified' as a real axis:** It is an absence marker. Never deliver unclassified docs in briefings.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | Custom regex parser for YAML | PyYAML with `---` delimiter split | Edge cases in YAML (lists, quotes, multiline) |
| Content hashing | Custom hash function | `hashlib.sha256(content.encode()).hexdigest()[:16]` | Consistent with existing pattern in models.py |
| Socket connectivity check | HTTP request to bus | Raw `socket.AF_UNIX` connect attempt | Lighter weight, no HTTP overhead needed |
| CLI group structure | Standalone script | Click group registered in __main__.py | Consistent with all other CLI commands |
| Schema idempotency | Check-then-create | `CREATE TABLE IF NOT EXISTS` | DuckDB native idempotent DDL |

**Key insight:** Every pattern needed for Phase 21 already exists in the codebase. The doc_indexer is the only genuinely new logic (3-tier extraction). Everything else is applying established patterns.

## Common Pitfalls

### Pitfall 1: Constraint-Axis Join Failure
**What goes wrong:** Code attempts to extract `ccd_axis` from constraints and gets `KeyError` or empty set.
**Why it happens:** constraints.json has no `ccd_axis` field. The CONTEXT.md assumed it did.
**How to avoid:** Do NOT filter doc_index by constraint axes. Instead, query doc_index directly for all non-unclassified entries + always-show entries, ranked by confidence.
**Warning signs:** `check.get("relevant_docs", [])` always returns empty list in integration tests.

### Pitfall 2: DuckDB Write Conflict
**What goes wrong:** doc_indexer.py opens ope.db for writing while bus daemon is running, causing a lock error.
**Why it happens:** DuckDB allows only one writer process at a time.
**How to avoid:** Socket ping check BEFORE opening DB connection. Print clear error message with stop command.
**Warning signs:** `duckdb.IOException: Could not set lock on file` in stderr.

### Pitfall 3: doc_index Table Missing at Query Time
**What goes wrong:** Bus starts before `docs reindex` has ever run. GovernorDaemon queries doc_index but table does not exist (schema not yet created).
**Why it happens:** `create_bus_schema()` will create the table DDL, but it will be empty until `docs reindex` is run.
**How to avoid:** The `create_doc_schema()` call in `create_bus_schema()` creates the table at bus startup. The daemon query should handle empty results gracefully. Additionally, check for table existence with `information_schema.tables` before querying.
**Warning signs:** `Catalog Error: Table with name doc_index does not exist` in bus logs.

### Pitfall 4: Frontmatter Parsing Failure on Docs Without Frontmatter
**What goes wrong:** Parser crashes or returns garbage when markdown file has no YAML frontmatter.
**Why it happens:** Current docs/ files have NO YAML frontmatter. The `---` delimiter is used as a horizontal rule in many docs (e.g., `BOUNDED-SUPERVISORY-ARCHITECTURE.md` has 109 `---` occurrences).
**How to avoid:** Frontmatter detection must require `---` as the VERY FIRST LINE of the file, followed by valid YAML, followed by closing `---`. Files starting with `#` or blank lines have no frontmatter. Test with all 28 existing files.
**Warning signs:** Every doc incorrectly classified as having frontmatter; regex/keyword tiers never fire.

### Pitfall 5: Token Overlap False Positives
**What goes wrong:** Tier 3 keyword matching produces spurious axis matches because axis tokens are common English words.
**Why it happens:** Axes like `terminal-vs-instrumental` split into tokens ['terminal', 'vs', 'instrumental']. The word "terminal" appears in many unrelated contexts.
**How to avoid:** Require minimum 2 DISTINCT non-stopword tokens matched, with at least 3 total occurrences. Filter out stopwords: 'not', 'vs', 'as', 'to', 'the', etc. Consider requiring that matched tokens appear within the same paragraph or section.
**Warning signs:** Every doc matches every axis at Tier 3.

### Pitfall 6: Description Cache Extraction Gets Frontmatter YAML
**What goes wrong:** The `description_cache` field contains raw YAML frontmatter instead of human-readable description text.
**Why it happens:** First-paragraph extraction starts from line 1 and captures the `---` block.
**How to avoid:** Skip frontmatter block (everything between first `---` and second `---`), then take first non-empty paragraph.
**Warning signs:** description_cache values start with `axes:` or `---`.

### Pitfall 7: Stale Content Hash After Doc Edits
**What goes wrong:** Doc content changes but doc_index still has old axis mappings and description.
**Why it happens:** doc_indexer.py is offline-first; it only runs when manually invoked.
**How to avoid:** Document this as a known limitation. The full DELETE+INSERT refresh pattern means any run of `docs reindex` produces fresh results. Content hash is for future incremental refresh (deferred).
**Warning signs:** N/A (expected behavior for Phase 21).

## Code Examples

### 3-Tier Axis Extraction (Core Algorithm)
```python
# Source: Verified against CONTEXT.md locked decisions + codebase patterns

import hashlib
import re
from pathlib import Path
from typing import Any

# Axis vocabulary loaded from MEMORY.md or memory_candidates
KNOWN_AXES: list[str] = []  # Populated at index time

# Stopwords to exclude from Tier 3 token matching
TIER3_STOPWORDS = {'not', 'vs', 'as', 'to', 'the', 'a', 'an', 'in', 'of', 'for', 'is'}


def extract_axes(doc_path: Path, content: str, known_axes: list[str]) -> list[dict[str, Any]]:
    """Extract CCD axis associations from a document using 3-tier cascade.

    Returns list of dicts with keys: ccd_axis, association_type, extracted_confidence.
    """
    results: list[dict[str, Any]] = []

    # Tier 1: YAML frontmatter (conf=1.0)
    frontmatter_axes = _parse_frontmatter_axes(content)
    for axis in frontmatter_axes:
        results.append({
            "ccd_axis": axis,
            "association_type": "frontmatter",
            "extracted_confidence": 1.0,
        })

    # Only proceed to lower tiers for axes not already found
    found_axes = {r["ccd_axis"] for r in results}

    # Tier 2: Regex in headers/comments (conf=0.7)
    for axis in known_axes:
        if axis in found_axes:
            continue
        if _axis_in_headers_or_comments(content, axis):
            results.append({
                "ccd_axis": axis,
                "association_type": "regex",
                "extracted_confidence": 0.7,
            })
            found_axes.add(axis)

    # Tier 3: Keyword token matching (conf=0.4)
    for axis in known_axes:
        if axis in found_axes:
            continue
        if _axis_token_match(content, axis):
            results.append({
                "ccd_axis": axis,
                "association_type": "keyword",
                "extracted_confidence": 0.4,
            })
            found_axes.add(axis)

    # Unclassified fallback
    if not results:
        results.append({
            "ccd_axis": "unclassified",
            "association_type": "unclassified",
            "extracted_confidence": 0.0,
        })

    return results


def _parse_frontmatter_axes(content: str) -> list[str]:
    """Extract axes from YAML frontmatter if present.

    Frontmatter must start on line 1 with --- and close with ---.
    Looks for axes: [list] field.
    """
    lines = content.split('\n')
    if not lines or lines[0].strip() != '---':
        return []
    # Find closing ---
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            yaml_block = '\n'.join(lines[1:i])
            # Simple parse: look for axes: [...] or axes:\n  - item
            match = re.search(r'axes:\s*\[([^\]]+)\]', yaml_block)
            if match:
                return [a.strip().strip('"').strip("'") for a in match.group(1).split(',')]
            # YAML list format
            axes = re.findall(r'axes:\s*\n((?:\s+-\s+.+\n?)+)', yaml_block)
            if axes:
                return [a.strip().lstrip('- ') for a in axes[0].strip().split('\n')]
            return []
    return []


def _axis_in_headers_or_comments(content: str, axis: str) -> bool:
    """Check if axis name appears in H1/H2 headers or HTML comments."""
    # Header match: # or ## containing axis name
    header_pattern = rf'^#{1,2}\s+.*{re.escape(axis)}.*$'
    if re.search(header_pattern, content, re.MULTILINE | re.IGNORECASE):
        return True
    # HTML comment: <!-- ccd: axis-name -->
    comment_pattern = rf'<!--\s*ccd:\s*{re.escape(axis)}\s*-->'
    if re.search(comment_pattern, content, re.IGNORECASE):
        return True
    return False


def _axis_token_match(content: str, axis: str, min_tokens: int = 2, min_total: int = 3) -> bool:
    """Check if axis tokens appear frequently enough in content.

    Split axis on '-', exclude stopwords, require min_tokens distinct
    tokens found with min_total total occurrences.
    """
    tokens = [t for t in axis.split('-') if t.lower() not in TIER3_STOPWORDS]
    if len(tokens) < 2:
        return False  # Axis too short for reliable token matching

    content_lower = content.lower()
    matched_tokens = set()
    total_count = 0

    for token in tokens:
        count = content_lower.count(token.lower())
        if count > 0:
            matched_tokens.add(token)
            total_count += count

    return len(matched_tokens) >= min_tokens and total_count >= min_total
```

### Description Cache Extraction
```python
def _extract_description(content: str, max_length: int = 200) -> str:
    """Extract first meaningful paragraph after frontmatter for description_cache.

    Skips YAML frontmatter, blank lines, and heading-only lines.
    Returns first paragraph of actual prose content, truncated.
    """
    lines = content.split('\n')
    start = 0

    # Skip frontmatter
    if lines and lines[0].strip() == '---':
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == '---':
                start = i + 1
                break

    # Find first non-empty, non-heading paragraph
    paragraph_lines: list[str] = []
    in_paragraph = False

    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            if in_paragraph:
                break  # End of paragraph
            continue
        if stripped.startswith('#'):
            if in_paragraph:
                break
            continue  # Skip headings
        if stripped.startswith('---'):
            if in_paragraph:
                break
            continue  # Skip horizontal rules
        in_paragraph = True
        paragraph_lines.append(stripped)

    text = ' '.join(paragraph_lines)
    if len(text) > max_length:
        text = text[:max_length - 3] + '...'
    return text
```

### Content Hash Generation
```python
# Source: Consistent with hashlib pattern in src/pipeline/live/bus/models.py

def _content_hash(content: str) -> str:
    """Generate SHA-256[:16] hash of file content for change detection."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
```

### Axis Vocabulary Loading
```python
# Source: Verified from src/pipeline/review/nversion.py _parse_memory_md_axes()
# and memory_candidates schema in src/pipeline/review/schema.py

import re
import duckdb

def load_axis_vocabulary(
    db_path: str = "data/ope.db",
    memory_md_path: str | None = None,
) -> list[str]:
    """Load known CCD axis vocabulary from memory_candidates + optionally MEMORY.md.

    Priority: memory_candidates (DuckDB) > MEMORY.md (file).
    Deduplicates and returns sorted list.
    """
    axes: set[str] = set()

    # From DuckDB memory_candidates
    try:
        conn = duckdb.connect(db_path, read_only=True)
        rows = conn.execute(
            "SELECT DISTINCT ccd_axis FROM memory_candidates WHERE LENGTH(TRIM(ccd_axis)) > 0"
        ).fetchall()
        axes.update(r[0].strip() for r in rows if r[0])
        conn.close()
    except Exception:
        pass  # DB may not exist yet

    # From MEMORY.md (fallback/supplement)
    if memory_md_path:
        try:
            with open(memory_md_path) as f:
                content = f.read()
            # Same regex as nversion.py
            axes.update(re.findall(r'\*\*CCD axis:\*\*\s+`?([^`\n]+)`?', content))
        except FileNotFoundError:
            pass

    return sorted(axes)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No docs indexing | Docs as floating corpus (unindexed) | Pre-Phase 21 | Sessions need human hint to find docs |
| GovernorDaemon reads constraints.json only | Phase 21 adds DuckDB read for doc_index | Phase 21 | Daemon gains read-only DB access |
| CheckResponse: constraints + interventions + epistemological_signals | Phase 21 adds relevant_docs field | Phase 21 | Wire format extends without breaking existing clients |

**Current CCD axis vocabulary (15 axes from MEMORY.md):**
1. `deposit-not-detect`
2. `raven-cost-function-absent`
3. `terminal-vs-instrumental`
4. `ground-truth-pointer`
5. `epistemological-layer-hierarchy`
6. `snippet-not-chunk`
7. `identity-firewall`
8. `closed-loop-to-specification`
9. `reconstruction-not-accumulation`
10. `decision-boundary-externalization`
11. `causal-chain-completeness`
12. `temporal-closure-dependency`
13. `run-id-dissolves-repo-boundary`
14. `bootstrap-circularity`
15. `fallacy-as-process-failure`

**Docs corpus (28 files, 16472 total lines):**
```
docs/
  analysis/
    knowledge-architecture-conciliation/
      PHASE_8_SYNTHESIS.md
    objectivism-knowledge-extraction/
      CONCEPTUAL_TYPE_THEORY_RESEARCH_SPEC.md
      DECISION_AMNESIA_REPORT.md
      DISCOVERY_DETECTION_FRAMEWORK.md
      FUTURE_WORK_AND_POTENTIALITIES.md
      PROBLEM_FORMULATION_RETROSPECTIVE.md
      REUSABLE_KNOWLEDGE_GUIDE.md
      VALIDATION_GATE_AUDIT.md
  architecture/
    BOUNDED-SUPERVISORY-ARCHITECTURE.md
    BUILDER-OPERATOR-BOUNDARY.md
  design/
    AUTHORITATIVE_DESIGN.md
    Mission Control - supervisory control layer.md
    The Genus Method - Justification.md
    The Genus Method.md
    WHY_TURN_LEVEL - Improved.md
    WHY_TURN_LEVEL - Revision.md
    WHY_TURN_LEVEL.md
  guides/
    GLOBAL_GIT_HOOKS.md
    GOVERNING-ORCHESTRATOR-METHODOLOGY.md
    INSTRUMENTATION.md
  research/
    delegation-to-openclaw.md
    epistemological-integrity-framework.md
    formal-problem-statement.md
    fundamental-issue.md
  PROJECT.md
  README.md
  ROADMAP.md
  VISION.md
```

**Current frontmatter status:** NONE of the 28 docs have YAML frontmatter. Most begin with `#` headings. Several use `---` as horizontal rules (not frontmatter delimiters). Human pre-work to add frontmatter to key docs is needed before/during Phase 21 execution.

## Open Questions

1. **How does the daemon access doc_index without violating its current convention?**
   - What we know: DuckDB MVCC makes reads always safe; daemon already has `db_path` parameter.
   - What's unclear: Whether the team considers adding a read connection an acceptable architecture change.
   - Recommendation: Add `duckdb.connect(self._db_path, read_only=True)` in a new private method. Open/close per call (stateless). Document as "Phase 21: daemon gains read-only DB access for doc_index queries."

2. **What is the axis filter for doc delivery since constraints lack ccd_axis?**
   - What we know: Constraints have no axis field. The axis vocabulary lives in memory_candidates and MEMORY.md.
   - What's unclear: Whether to deliver docs based on ALL known axes or filter by some session-relevant subset.
   - Recommendation: For Phase 21, deliver top 3 non-unclassified docs by confidence + all always-show docs. No axis filtering. This is correct for a 28-file corpus. Session-specific filtering (based on what the session is working on) can be added later when constraints gain axis tags.

3. **Should the MEMORY.md path for axis vocabulary loading be configurable?**
   - What we know: MEMORY.md lives at a project-specific Claude path, not in the repo root.
   - What's unclear: The correct path to MEMORY.md from the indexer's perspective.
   - Recommendation: Load axis vocabulary primarily from `memory_candidates` in DuckDB (the authoritative machine-readable source). Use MEMORY.md as a fallback only if the DB is empty or unavailable.

4. **Should human frontmatter pre-work be a separate plan or part of the indexer plan?**
   - What we know: Zero docs currently have frontmatter. Tier 1 extraction is useless without it.
   - What's unclear: Whether frontmatter addition is a Phase 21 deliverable or pre-Phase-21 prep.
   - Recommendation: Include a task in Plan 02 (indexer) that adds frontmatter to the ~10 most important docs. The indexer handles the rest via Tier 2/3. This is manual work (human reviews each doc and adds `axes: [...]`) but is fast for 10 files.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/live/bus/schema.py` -- verified schema chain pattern, DDL constants, `create_bus_schema()` function
- `src/pipeline/live/bus/models.py` -- verified CheckResponse model with `epistemological_signals` extension pattern
- `src/pipeline/live/bus/server.py` -- verified /api/check handler, daemon integration, fail-open pattern
- `src/pipeline/live/governor/daemon.py` -- verified constraints.json-only reading, no DuckDB access
- `src/pipeline/live/governor/briefing.py` -- verified ConstraintBriefing model, generate_briefing()
- `src/pipeline/live/hooks/session_start.py` -- verified [OPE] prefix, fail-open, socket connection pattern
- `src/pipeline/cli/__main__.py` -- verified Click group registration pattern
- `src/pipeline/cli/bus.py` -- verified CLI group structure with --db and --socket options
- `src/pipeline/cli/wisdom.py` -- verified reindex subcommand pattern
- `src/pipeline/review/schema.py` -- verified memory_candidates schema with ccd_axis field
- `src/pipeline/review/nversion.py` -- verified MEMORY.md axis parsing regex
- `src/pipeline/ddf/schema.py` -- verified schema chain wiring pattern
- `src/pipeline/ddf/deposit.py` -- verified hashlib SHA-256[:16] ID generation pattern
- `data/constraints.json` -- verified NO ccd_axis field exists (275 constraints inspected)
- MEMORY.md -- verified 15 CCD axis values currently defined

### Secondary (MEDIUM confidence)
- CONTEXT.md and CLARIFICATIONS-ANSWERED.md -- design decisions, but contain the constraint-axis assumption error
- docs/ folder inspection (28 files) -- verified no YAML frontmatter exists in any doc

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, patterns verified
- Architecture: HIGH -- every pattern has an exact precedent in the codebase
- Schema: HIGH -- DDL follows exact established pattern
- Axis extraction: MEDIUM -- 3-tier cascade is novel code, needs testing against all 28 docs
- Query mechanism: HIGH -- gap identified and resolution clear (daemon read-only DB access)
- Pitfalls: HIGH -- all identified from codebase inspection, not speculation

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable codebase, no fast-moving external dependencies)
