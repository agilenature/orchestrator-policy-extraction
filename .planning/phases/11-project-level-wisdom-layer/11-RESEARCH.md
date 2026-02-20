# Phase 11: Project-Level Wisdom Layer - Research

**Researched:** 2026-02-20
**Domain:** DuckDB FTS/VSS hybrid retrieval, Pydantic v2 domain modeling, Click CLI subcommands, JSON seed ingestion
**Confidence:** HIGH

## Summary

Phase 11 adds a `project_wisdom` table to DuckDB storing four entity types (Breakthrough, DeadEnd, ScopeDecision, MethodDecision), with a WisdomRetriever running BM25+VSS searches independently from the existing HybridRetriever for episodes. Results are returned via a non-breaking `EnrichedRecommendation` wrapper around the existing frozen `Recommendation` model. Dead end detection uses dual BM25+vector top-10 agreement filtering. Wisdom entries are ingested from `data/seed_wisdom.json` via CLI, embedded with the existing `EpisodeEmbedder` (all-MiniLM-L6-v2, 384-dim), and indexed with FTS and HNSW.

All decisions in this phase are locked via CLARIFICATIONS-ANSWERED.md. The technical stack is entirely within the project's existing dependencies: DuckDB 1.4.4, Pydantic 2.11.7, sentence-transformers 5.2.2, Click. No new external dependencies are required. Every DuckDB capability needed (FLOAT[384], FTS multi-column indexing, HNSW index creation, INSERT OR REPLACE, array_cosine_similarity, JSON columns) has been verified against the running environment.

**Primary recommendation:** Follow the existing module patterns exactly (frozen Pydantic models, `INSERT OR REPLACE` idempotency, `create_schema()` table creation, Click groups with `@click.group` decorator, DuckDB `:memory:` for tests). The WisdomRetriever should mirror HybridRetriever's structure but operate on `project_wisdom` rather than `episode_search_text`/`episode_embeddings`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema: `project_wisdom` table**
```sql
CREATE TABLE project_wisdom (
    wisdom_id    VARCHAR PRIMARY KEY,     -- SHA-256(type + title + source_document)[:12]
    type         VARCHAR NOT NULL,         -- CHECK: breakthrough|dead_end|scope_decision|method_decision
    title        VARCHAR NOT NULL,
    description  TEXT NOT NULL,
    content_for_embedding TEXT NOT NULL,  -- synthesized text for FTS + VSS
    embedding    FLOAT[],                  -- same dimensions as episodes.embedding
    confidence_score FLOAT DEFAULT 0.9,
    episode_ids  JSON,                    -- optional
    source_document VARCHAR,
    created_at   TIMESTAMP DEFAULT now(),
    metadata     JSON                     -- type-specific attributes
)
```

**Retrieval: EnrichedRecommendation wrapper (non-breaking)**
```python
class WisdomRef(BaseModel, frozen=True):
    wisdom_id: str
    type: str
    title: str
    description: str
    confidence_score: float
    source_document: Optional[str] = None
    is_warning: bool = False

class EnrichedRecommendation(BaseModel, frozen=True):
    recommendation: Recommendation        # existing frozen model, unchanged
    wisdom_context: List[WisdomRef] = []  # top-3 relevant wisdom entries
    dead_end_warnings: List[WisdomRef] = []  # dead_end entities matching context
```

**Ingestion: data/seed_wisdom.json (NOT YAML) + wisdom ingest CLI**
- JSON format (consistent with data/constraints.json, no PyYAML dep)
- DuckDB is source of truth; seed_wisdom.json is ingestion input only
- `wisdom_id` = SHA-256(type + "|" + title + "|" + source_document)[:12] prefix
- INSERT OR REPLACE for idempotency

**Dead End Detection: Dual BM25 + vector top-10 agreement**
- A dead end surfaces as warning ONLY if it appears in top-10 of BOTH BM25 and vector searches
- Filtered by confidence_score >= 0.7
- Annotate only (don't suppress recommendation)
- Real-time in EnrichedRecommendation.dead_end_warnings

**Scope Decision Enforcement: ConstraintStore linkage**
- ScopeDecision metadata has optional `constraint_ids: List[str]`
- `wisdom check-scope [--session <id>]` exits 0/1/2
- Links to existing SessionConstraintEvaluator (Phase 10)

**Embedding: Same model as episodes (EpisodeEmbedder reuse)**
- Same dimensions as episodes.embedding (384-dim, all-MiniLM-L6-v2)
- `wisdom reindex` rebuilds FTS + HNSW after bulk ingest

**New CLI subcommands (under `python -m src.pipeline.cli wisdom`):**
- `wisdom ingest <json_file>` -- load -> DuckDB -> embed -> reindex
- `wisdom check-scope [--session <id>]` -- exit 0/1/2
- `wisdom reindex` -- rebuild FTS + HNSW
- `wisdom list [--type <type>]` -- list entries

**New modules:**
- `src/pipeline/wisdom/models.py`
- `src/pipeline/wisdom/store.py`
- `src/pipeline/wisdom/retriever.py`
- `src/pipeline/wisdom/ingestor.py`

**content_for_embedding templates:**
- Breakthrough: `"Breakthrough: {title}. {description}."`
- DeadEnd: `"Dead end: {title}. {description}."`
- ScopeDecision: `"Scope decision: {title}. {description}."`
- MethodDecision: `"Method decision: {title}. {description}."`

**Target:** ~40 new tests, 15+ wisdom entries from 4 objectivism analysis docs

### Claude's Discretion

None specified -- all key decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- LLM-assisted parsing of analysis documents (manual JSON extraction instead)
- Dead end severity field beyond warning/non-warning
- Embedding prefix prompts (experiment after initial implementation)
- RRF fusion between wisdom and episodes (optional future, not Phase 11)
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| DuckDB | 1.4.4 | Storage, FTS (BM25), VSS (HNSW + cosine) | Already used for all pipeline data |
| Pydantic | 2.11.7 | Domain models (frozen BaseModel) | Already used for all pipeline models |
| sentence-transformers | 5.2.2 | Embedding via all-MiniLM-L6-v2 (384-dim) | Already used by EpisodeEmbedder |
| Click | (installed) | CLI subcommand groups | Already used for all CLI commands |
| hashlib | stdlib | SHA-256 for deterministic wisdom_id generation | Already used by constraint_store |
| json | stdlib | Seed file parsing, JSON column serialization | Already used throughout pipeline |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| loguru | (installed) | Structured logging | All wisdom module logging |
| pytest | (installed) | Testing | All ~40 new tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSON seed file | YAML seed file | JSON is project standard; no PyYAML dependency needed |
| Separate wisdom table | Extending episodes table | Wisdom is semantically different; separate table is cleaner |
| Metadata JSON column | Separate attributes table | JSON column matches project pattern; < 1000 rows makes joins unnecessary |

**Installation:**
```bash
# No new dependencies required -- everything is already installed
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/wisdom/
    __init__.py          # exports: WisdomEntity, WisdomRef, EnrichedRecommendation, WisdomStore, WisdomRetriever, WisdomIngestor
    models.py            # Pydantic models: WisdomEntity, WisdomRef, EnrichedRecommendation
    store.py             # WisdomStore: DuckDB CRUD, FTS/VSS search, schema creation
    retriever.py         # WisdomRetriever: BM25+VSS hybrid search, dead end detection
    ingestor.py          # WisdomIngestor: JSON loading, validation, embedding, DB write
```

### Pattern 1: Frozen Pydantic Models with JSON Metadata
**What:** All domain models use `BaseModel, frozen=True`. Type-specific attributes stored in a JSON `metadata` column.
**When to use:** Every model in this phase.
**Example:**
```python
# Source: Verified against Pydantic 2.11.7 discriminated unions
from pydantic import BaseModel
from typing import Optional, Literal

class WisdomEntity(BaseModel, frozen=True):
    wisdom_id: str
    type: Literal["breakthrough", "dead_end", "scope_decision", "method_decision"]
    title: str
    description: str
    content_for_embedding: str
    confidence_score: float = 0.9
    episode_ids: list[str] | None = None
    source_document: str | None = None
    metadata: dict | None = None

class WisdomRef(BaseModel, frozen=True):
    wisdom_id: str
    type: str
    title: str
    description: str
    confidence_score: float
    source_document: Optional[str] = None
    is_warning: bool = False

class EnrichedRecommendation(BaseModel, frozen=True):
    recommendation: "Recommendation"   # imported from recommender
    wisdom_context: list[WisdomRef] = []
    dead_end_warnings: list[WisdomRef] = []
```

### Pattern 2: DuckDB Store with INSERT OR REPLACE
**What:** WisdomStore manages all DuckDB interactions using `INSERT OR REPLACE` for idempotent writes.
**When to use:** All write operations to `project_wisdom`.
**Example:**
```python
# Source: Verified against DuckDB 1.4.4
def write_wisdom(self, entity: WisdomEntity, embedding: list[float]) -> None:
    self._conn.execute(
        """INSERT OR REPLACE INTO project_wisdom
        (wisdom_id, type, title, description, content_for_embedding,
         embedding, confidence_score, episode_ids, source_document,
         created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?::FLOAT[384], ?, ?, ?, now(), ?)""",
        [
            entity.wisdom_id,
            entity.type,
            entity.title,
            entity.description,
            entity.content_for_embedding,
            embedding,
            entity.confidence_score,
            json.dumps(entity.episode_ids) if entity.episode_ids else None,
            entity.source_document,
            json.dumps(entity.metadata) if entity.metadata else None,
        ],
    )
```

### Pattern 3: Click CLI Group Registration
**What:** New `wisdom` subcommand group registered in `__main__.py` following the exact pattern of `train`, `validate`, `audit`.
**When to use:** CLI integration.
**Example:**
```python
# In src/pipeline/cli/wisdom.py
import click

@click.group("wisdom")
def wisdom_group():
    """Wisdom layer commands."""
    pass

@wisdom_group.command(name="ingest")
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def ingest_cmd(json_file: str, db: str) -> None:
    """Load wisdom entries from JSON into DuckDB."""
    ...

# In src/pipeline/cli/__main__.py
from src.pipeline.cli.wisdom import wisdom_group
cli.add_command(wisdom_group, name="wisdom")
```

### Pattern 4: Dual BM25+VSS Search (WisdomRetriever)
**What:** WisdomRetriever runs two independent searches (BM25 on description+content_for_embedding, VSS on embedding) against `project_wisdom`, then applies type-specific filtering.
**When to use:** Every wisdom retrieval call.
**Example:**
```python
# Source: Modeled after HybridRetriever in src/pipeline/rag/retriever.py
class WisdomRetriever:
    def __init__(self, conn, top_k: int = 3):
        self._conn = conn
        self._top_k = top_k

    def retrieve(self, query_text: str, query_embedding: list[float]) -> list[dict]:
        bm25 = self._bm25_search(query_text)
        vss = self._vss_search(query_embedding)
        return self._rrf_fuse(bm25, vss, k=self._top_k)

    def detect_dead_ends(self, query_text: str, query_embedding: list[float]) -> list[dict]:
        """Return dead_end entries in top-10 of BOTH BM25 and VSS."""
        bm25_ids = {r[0] for r in self._bm25_search(query_text, type_filter="dead_end", limit=10)}
        vss_ids = {r[0] for r in self._vss_search(query_embedding, type_filter="dead_end", limit=10)}
        agreed = bm25_ids & vss_ids  # dual agreement
        # Filter by confidence_score >= 0.7
        ...
```

### Pattern 5: SHA-256 Deterministic ID Generation
**What:** `wisdom_id = SHA-256(type + "|" + title + "|" + source_document)[:12]`
**When to use:** During ingest, to ensure idempotency.
**Example:**
```python
# Source: Verified with hashlib
import hashlib

def generate_wisdom_id(type: str, title: str, source_document: str) -> str:
    raw = f"{type}|{title}|{source_document}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]

# Example output: "2d4a79c7e5cd"
```

### Pattern 6: FTS + HNSW Index Rebuild
**What:** Rebuild FTS and HNSW indexes after bulk ingest, following the Phase 5 pattern.
**When to use:** After `wisdom ingest` and `wisdom reindex`.
**Example:**
```python
# Source: Modeled after EpisodeEmbedder.rebuild_fts_index()
def rebuild_wisdom_indexes(conn):
    # FTS on description + content_for_embedding
    conn.execute("INSTALL fts; LOAD fts;")
    conn.execute("""
        PRAGMA create_fts_index(
            'project_wisdom', 'wisdom_id',
            'description', 'content_for_embedding',
            stemmer='porter', stopwords='english', lower=1, overwrite=1
        )
    """)
    # HNSW on embedding
    conn.execute("INSTALL vss; LOAD vss;")
    # Drop existing HNSW index if present, then recreate
    try:
        conn.execute("DROP INDEX IF EXISTS wisdom_hnsw")
    except Exception:
        pass
    conn.execute("CREATE INDEX wisdom_hnsw ON project_wisdom USING HNSW (embedding)")
```

### Anti-Patterns to Avoid
- **Modifying the Recommendation model:** The `Recommendation` and `SourceEpisodeRef` are frozen and used by shadow runner, evaluator, reporter, and 643 tests. Use `EnrichedRecommendation` wrapper instead.
- **Building a separate attribute table:** The project consistently uses JSON columns for type-specific data. Do not create a `wisdom_attributes` table.
- **Querying wisdom and episodes from a single SQL query:** Keep WisdomRetriever independent from HybridRetriever. They operate on different tables with different semantics.
- **Using YAML for seed data:** The project uses JSON for all data files (`constraints.json`). Do not introduce PyYAML dependency.
- **HNSW index with metric parameter:** DuckDB 1.4.4 does not support `WITH (metric = "cosine")` in HNSW index creation. Use `CREATE INDEX ... USING HNSW (embedding)` without metric specification. Cosine similarity is applied at query time via `array_cosine_similarity()`.
- **Embedding in create_schema():** HNSW index requires data to exist. Build it in `rebuild_wisdom_indexes()` after data load, not in schema creation. The FTS index also requires data. Both are deferred to after ingest.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Embedding generation | Custom embedding code | `EpisodeEmbedder.embed_text()` | Already handles model loading, 384-dim output, numpy conversion |
| BM25 text search | Custom text search | DuckDB FTS extension (`match_bm25()`) | Production-quality BM25 with stemming, stopwords |
| Vector similarity search | Custom ANN search | DuckDB VSS extension (`array_cosine_similarity()`) | HNSW index for fast approximate search |
| Idempotent upsert | Custom dedup logic | `INSERT OR REPLACE INTO` | DuckDB native, same pattern as `write_constraint_evals()` |
| Deterministic IDs | UUID generation | `hashlib.sha256(canonical_string)[:12]` | Ensures same input always produces same ID |
| CLI framework | argparse | Click groups with `@click.group()` | Already used for all 4 existing CLI groups |
| Constraint compliance check | Custom scope enforcement | `SessionConstraintEvaluator.evaluate()` | Phase 10 infrastructure handles HONORED/VIOLATED evaluation |
| FTS index management | Custom inverted index | `PRAGMA create_fts_index()` with `overwrite=1` | Idempotent rebuild, Porter stemming, English stopwords |

**Key insight:** Every infrastructure component needed by Phase 11 already exists in the codebase. The wisdom layer is a new domain model and retrieval path, not new infrastructure.

## Common Pitfalls

### Pitfall 1: HNSW Index Creation Before Data Load
**What goes wrong:** `CREATE INDEX ... USING HNSW (embedding)` on an empty table succeeds but produces a useless index. Inserting data after index creation does NOT automatically update the HNSW index in DuckDB 1.4.4.
**Why it happens:** Developers put index creation in `create_schema()` alongside table creation.
**How to avoid:** Always create HNSW index AFTER bulk data load. Call `rebuild_wisdom_indexes()` at the end of `wisdom ingest`, not in `create_schema()`.
**Warning signs:** Vector search returns no results or incorrect rankings despite data being present.

### Pitfall 2: FTS Index Not Rebuilt After INSERT OR REPLACE
**What goes wrong:** BM25 search returns stale results or misses newly ingested entries.
**Why it happens:** DuckDB FTS index is not automatically updated on row changes. The `overwrite=1` flag in `PRAGMA create_fts_index` rebuilds from scratch, but must be called explicitly.
**How to avoid:** Always call `rebuild_wisdom_indexes()` after any batch of writes to `project_wisdom`. The `wisdom ingest` command should call it automatically after all entries are written.
**Warning signs:** BM25 search returns 0 results for text that is definitely in the table.

### Pitfall 3: Embedding Dimension Mismatch
**What goes wrong:** `INSERT` fails or cosine similarity returns meaningless values.
**Why it happens:** The column is `FLOAT[]` (unspecified dimension) but the cast should use `?::FLOAT[384]` to match the model's output dimension.
**How to avoid:** Always cast embeddings explicitly: `?::FLOAT[384]`. The `EpisodeEmbedder` uses `all-MiniLM-L6-v2` which outputs exactly 384 dimensions.
**Warning signs:** DuckDB type error on INSERT, or `array_cosine_similarity` returning NULL.

### Pitfall 4: Breaking the Recommender Return Type
**What goes wrong:** Existing tests and shadow pipeline break because `Recommender.recommend()` return type changed.
**Why it happens:** Adding wisdom context directly to `Recommendation` instead of using wrapper.
**How to avoid:** Keep `Recommender.recommend()` returning `Recommendation` unchanged. Create a new method (e.g., `recommend_enriched()`) or a separate enrichment step that wraps the result in `EnrichedRecommendation`. Alternatively, modify `recommend()` to return `EnrichedRecommendation` but ensure the shadow pipeline uses `result.recommendation` to get the plain `Recommendation`.
**Warning signs:** Test failures in shadow_runner, shadow_evaluator, shadow_reporter, recommender tests.

### Pitfall 5: JSON Column Read/Write Inconsistency
**What goes wrong:** Reading `episode_ids` or `metadata` from DuckDB returns a string instead of parsed dict/list.
**Why it happens:** DuckDB JSON columns may return strings on read. The existing codebase handles this with explicit `json.loads()` on read.
**How to avoid:** Always `json.dumps()` on write and `json.loads()` on read for JSON columns. Check `isinstance(val, str)` before parsing, same pattern as `read_events()` in `storage/writer.py`.
**Warning signs:** Type errors when iterating over `episode_ids` or accessing `metadata` keys.

### Pitfall 6: Dead End Detection Over-Triggering
**What goes wrong:** Every recommendation gets dead-end warnings, causing alert fatigue.
**Why it happens:** Low confidence threshold or insufficient dual-signal filtering.
**How to avoid:** Require dual BM25+VSS top-10 agreement AND `confidence_score >= 0.7`. The dual agreement requirement is the primary false-positive filter. Start conservative; loosen later with empirical data.
**Warning signs:** More than ~20% of recommendations include dead-end warnings.

### Pitfall 7: wisdom_id Collision or Non-Determinism
**What goes wrong:** Re-ingesting the same seed file creates duplicate entries or fails to update existing ones.
**Why it happens:** The SHA-256 input string varies (e.g., trailing whitespace, different casing).
**How to avoid:** Strip and normalize all three input fields (type, title, source_document) before hashing. Use the exact format `f"{type}|{title}|{source_document}"`. The `INSERT OR REPLACE` handles the idempotency once IDs match.
**Warning signs:** Duplicate wisdom entries after re-ingest, or entry counts growing on each run.

## Code Examples

### Example 1: Schema Creation for project_wisdom Table
```python
# Source: Verified against DuckDB 1.4.4
# Add to create_schema() in src/pipeline/storage/schema.py
conn.execute("""
    CREATE TABLE IF NOT EXISTS project_wisdom (
        wisdom_id    VARCHAR PRIMARY KEY,
        type         VARCHAR NOT NULL,
        title        VARCHAR NOT NULL,
        description  TEXT NOT NULL,
        content_for_embedding TEXT NOT NULL,
        embedding    FLOAT[],
        confidence_score FLOAT DEFAULT 0.9,
        episode_ids  JSON,
        source_document VARCHAR,
        created_at   TIMESTAMP DEFAULT now(),
        metadata     JSON
    )
""")
```

### Example 2: Wisdom Ingest Flow
```python
# Source: Modeled after write_constraint_evals() and EpisodeEmbedder patterns
import hashlib, json

def ingest_wisdom_file(conn, embedder, json_path: str) -> dict:
    with open(json_path) as f:
        entries = json.load(f)

    written = 0
    for entry in entries:
        # Generate deterministic ID
        wisdom_id = hashlib.sha256(
            f"{entry['type']}|{entry['title']}|{entry.get('source_document', '')}".encode()
        ).hexdigest()[:12]

        # Synthesize embedding text
        type_label = entry["type"].replace("_", " ").title()
        content = f"{type_label}: {entry['title']}. {entry['description']}."

        # Generate embedding
        embedding = embedder.embed_text(content)

        # Write to DuckDB
        conn.execute(
            """INSERT OR REPLACE INTO project_wisdom
            (wisdom_id, type, title, description, content_for_embedding,
             embedding, confidence_score, episode_ids, source_document,
             created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?::FLOAT[384], ?, ?, ?, now(), ?)""",
            [wisdom_id, entry["type"], entry["title"], entry["description"],
             content, embedding, entry.get("confidence_score", 0.9),
             json.dumps(entry.get("episode_ids")),
             entry.get("source_document"),
             json.dumps(entry.get("metadata"))]
        )
        written += 1

    # Rebuild indexes after bulk load
    rebuild_wisdom_indexes(conn)
    return {"written": written}
```

### Example 3: Dual Dead End Detection
```python
# Source: Modeled after HybridRetriever._bm25_search() and _embedding_search()
def detect_dead_ends(self, query_text: str, query_embedding: list[float]) -> list[WisdomRef]:
    # BM25 top-10 dead ends
    bm25_rows = self._conn.execute("""
        SELECT wisdom_id, fts_main_project_wisdom.match_bm25(wisdom_id, ?) AS score
        FROM project_wisdom
        WHERE score IS NOT NULL AND type = 'dead_end' AND confidence_score >= 0.7
        ORDER BY score DESC
        LIMIT 10
    """, [query_text]).fetchall()
    bm25_ids = {row[0] for row in bm25_rows}

    # VSS top-10 dead ends
    vss_rows = self._conn.execute("""
        SELECT wisdom_id, array_cosine_similarity(embedding, ?::FLOAT[384]) AS sim
        FROM project_wisdom
        WHERE embedding IS NOT NULL AND type = 'dead_end' AND confidence_score >= 0.7
        ORDER BY sim DESC
        LIMIT 10
    """, [query_embedding]).fetchall()
    vss_ids = {row[0] for row in vss_rows}

    # Dual agreement filter
    agreed_ids = bm25_ids & vss_ids
    if not agreed_ids:
        return []

    # Fetch full records for agreed IDs
    ...
```

### Example 4: Scope Decision Check with ConstraintStore Linkage
```python
# Source: Modeled after audit_session() in src/pipeline/cli/audit.py
def check_scope(conn, session_id=None) -> int:
    """Check scope decision compliance. Returns exit code 0/1/2."""
    # Load scope_decision entries from project_wisdom
    scope_decisions = conn.execute(
        "SELECT wisdom_id, title, description, metadata FROM project_wisdom WHERE type = 'scope_decision'"
    ).fetchall()

    violations = []
    text_only = []
    for wd_id, title, desc, meta_json in scope_decisions:
        meta = json.loads(meta_json) if meta_json else {}
        constraint_ids = meta.get("constraint_ids", [])
        if constraint_ids:
            # Delegate to SessionConstraintEvaluator for linked constraints
            ...  # check each constraint_id against session
        else:
            text_only.append((wd_id, title, desc))

    if violations:
        return 1  # violation found
    return 0  # all pass (text-only reported for human review)
```

### Example 5: seed_wisdom.json Entry Format
```json
[
    {
        "type": "breakthrough",
        "title": "Two-Step Gemini Upload Pattern",
        "description": "The Gemini File Search API requires a two-step upload pattern for metadata attachment: first upload the raw file to the Files API, then import into File Search store with custom_metadata.",
        "confidence_score": 0.95,
        "source_document": "docs/analysis/objectivism-knowledge-extraction/REUSABLE_KNOWLEDGE_GUIDE.md",
        "episode_ids": null,
        "metadata": {
            "discovery_path": "Phase 2 research, commit 58322531",
            "impact": "Enables crash recovery via separate upload/import failure handling"
        }
    },
    {
        "type": "dead_end",
        "title": "Single-Step Upload With Metadata",
        "description": "Attempting to attach custom_metadata directly via upload_to_file_search_store() fails silently. The single-step upload method does not support custom_metadata in its documented config.",
        "confidence_score": 0.9,
        "source_document": "docs/analysis/objectivism-knowledge-extraction/REUSABLE_KNOWLEDGE_GUIDE.md",
        "episode_ids": null,
        "metadata": {
            "attempted_strategy": "upload_to_file_search_store() with custom_metadata parameter",
            "failure_reason": "Method does not support custom_metadata; requires two-step pattern instead"
        }
    },
    {
        "type": "scope_decision",
        "title": "Metadata-First Execution Strategy",
        "description": "Phase 6 AI metadata extraction must run before full library upload because Gemini custom_metadata cannot be updated without re-uploading. This inverts the standard execution order.",
        "confidence_score": 0.95,
        "source_document": "docs/analysis/objectivism-knowledge-extraction/PROBLEM_FORMULATION_RETROSPECTIVE.md",
        "episode_ids": null,
        "metadata": {
            "constraint_ids": [],
            "rationale": "Re-uploading 1,721 files to update metadata is prohibitively expensive"
        }
    }
]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| DuckDB HNSW with metric param | `CREATE INDEX ... USING HNSW (col)` no metric | DuckDB 1.x | Must NOT use `WITH (metric = "cosine")` -- causes NotImplementedError |
| Pydantic v1 discriminated unions | Pydantic v2 `Literal` + `Field(discriminator=...)` | Pydantic 2.0 | Use v2 syntax for type discriminators |
| FTS single column | FTS multi-column in single PRAGMA | DuckDB 0.9+ | Can index `description` AND `content_for_embedding` in one index |

**Deprecated/outdated:**
- DuckDB HNSW `WITH (metric = "cosine")` syntax: not supported in 1.4.4. Cosine similarity computed via `array_cosine_similarity()` at query time regardless.
- `CREATE VIRTUAL TABLE ... USING fts5(...)`: This is SQLite FTS, not DuckDB. Use `PRAGMA create_fts_index(...)`.

## Technical Verification Results

All capabilities were verified against the actual running environment (DuckDB 1.4.4, Pydantic 2.11.7, sentence-transformers 5.2.2):

| Capability | Status | Notes |
|-----------|--------|-------|
| `CREATE TABLE project_wisdom` with FLOAT[] embedding | VERIFIED | Works with `FLOAT[]` (no fixed dimension in schema) |
| `INSERT OR REPLACE INTO project_wisdom` | VERIFIED | Correctly upserts on PK collision |
| `?::FLOAT[384]` cast on insert | VERIFIED | Required for embedding parameter binding |
| `array_cosine_similarity(embedding, ?::FLOAT[384])` | VERIFIED | Returns correct similarity scores |
| `CREATE INDEX ... USING HNSW (embedding)` | VERIFIED | Without metric parameter; works after data load |
| FTS multi-column: `description`, `content_for_embedding` | VERIFIED | Both columns indexed, BM25 search works correctly |
| `match_bm25(wisdom_id, ?)` with type filter | VERIFIED | WHERE type = 'dead_end' AND score IS NOT NULL works |
| Pydantic v2 discriminated unions with Literal | VERIFIED | BreakthroughMeta/DeadEndMeta union works |
| SHA-256 [:12] wisdom_id generation | VERIFIED | Deterministic, e.g. "2d4a79c7e5cd" |
| `json.dumps()`/`json.loads()` for JSON columns | VERIFIED | Standard pattern used throughout codebase |

## Analysis Documents Content Survey

The four analysis documents in `docs/analysis/objectivism-knowledge-extraction/` contain rich extractable content:

### REUSABLE_KNOWLEDGE_GUIDE.md
- **Breakthroughs:** Two-Step Gemini Upload Pattern, string_list_value metadata format, Magistral response content array format, batch API for cost-effective processing, validation gates between phases
- **Dead Ends:** Single-step upload with metadata, bare list metadata format (400 errors), treating Magistral response.content as string
- **Estimated entries:** 6-8 wisdom entries

### PROBLEM_FORMULATION_RETROSPECTIVE.md
- **Breakthroughs:** Gemini File Search collapses 7-stage RAG to 3 stages, Metadata-First execution strategy, batch API discovery
- **Scope Decisions:** Metadata-First ordering (Phase 6 before Phase 4/5)
- **Method Decisions:** Always map managed service boundaries before building, place enrichment before immutable store interaction
- **Estimated entries:** 4-6 wisdom entries

### DECISION_AMNESIA_REPORT.md
- **Dead Ends:** Declaring phase complete based on infrastructure without running production extraction, scope contraction cascade
- **Scope Decisions:** Process all applicable files before declaring completion, not just infrastructure
- **Method Decisions:** Batch over sequential for large-scale API work
- **Estimated entries:** 4-5 wisdom entries

### VALIDATION_GATE_AUDIT.md
- **Breakthroughs:** Machine-checkable count gates between phases, explicit expected vs actual assertions
- **Dead Ends:** Verifying on synthetic test data only (not production counts), conflating infrastructure completion with work completion
- **Method Decisions:** Always enforce count gates at phase transitions
- **Estimated entries:** 3-4 wisdom entries

**Total estimated:** 17-23 extractable wisdom entries (well above the 15+ target)

## Open Questions

1. **How should Recommender.recommend() integrate with WisdomRetriever?**
   - What we know: The locked decision specifies `EnrichedRecommendation` wrapping `Recommendation`. The shadow pipeline receives plain `Recommendation`.
   - What's unclear: Should `Recommender` itself be modified to optionally produce `EnrichedRecommendation`, or should a separate orchestrator layer call both and combine?
   - Recommendation: Add an optional `wisdom_retriever` parameter to `Recommender.__init__()`. When present, `recommend()` internally calls it and returns `EnrichedRecommendation`. When absent, behavior is unchanged (backward compatible). This keeps the integration point minimal.

2. **Should `create_schema()` be updated to include `project_wisdom` table creation?**
   - What we know: All existing tables are created in `create_schema()`. The HNSW and FTS indexes require data.
   - What's unclear: Whether the table DDL should go in `create_schema()` (table only, no indexes) or in `WisdomStore.create_schema()`.
   - Recommendation: Add the `CREATE TABLE IF NOT EXISTS project_wisdom` DDL to the central `create_schema()` function for consistency. Index creation goes in `rebuild_wisdom_indexes()` called by `wisdom ingest`/`wisdom reindex`.

3. **Where exactly should `EnrichedRecommendation` live -- in wisdom/models.py or rag/recommender.py?**
   - What we know: It wraps `Recommendation` (from rag/recommender.py) with `WisdomRef` (from wisdom/models.py).
   - What's unclear: Import direction. If in recommender.py, it imports from wisdom/models.py. If in wisdom/models.py, it imports from recommender.py.
   - Recommendation: Put it in `wisdom/models.py` alongside `WisdomRef`. This keeps the wisdom layer as the dependent, not the dependency. `rag/recommender.py` remains unchanged.

## Sources

### Primary (HIGH confidence)
- DuckDB 1.4.4 environment verification -- schema, FTS, VSS, HNSW, INSERT OR REPLACE all tested
- Pydantic 2.11.7 environment verification -- frozen models, discriminated unions tested
- sentence-transformers 5.2.2 environment verification -- EpisodeEmbedder already functional
- Codebase analysis: `src/pipeline/rag/embedder.py`, `retriever.py`, `recommender.py` -- existing patterns documented
- Codebase analysis: `src/pipeline/storage/schema.py`, `writer.py` -- schema and write patterns documented
- Codebase analysis: `src/pipeline/cli/__main__.py`, `audit.py`, `train.py` -- CLI group patterns documented
- Codebase analysis: `src/pipeline/durability/evaluator.py` -- SessionConstraintEvaluator patterns documented
- Codebase analysis: `src/pipeline/constraint_store.py` -- ConstraintStore interface documented
- Analysis documents: all 4 files in `docs/analysis/objectivism-knowledge-extraction/` surveyed for extractable content

### Secondary (MEDIUM confidence)
- None needed -- all critical capabilities verified locally

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and verified in running environment
- Architecture: HIGH -- all patterns verified against existing codebase; no new patterns introduced
- Pitfalls: HIGH -- HNSW index timing, FTS rebuild, embedding dimension all verified empirically
- Integration points: HIGH -- existing `Recommender`, `SessionConstraintEvaluator`, `ConstraintStore`, `EpisodeEmbedder` all examined in detail

**Research date:** 2026-02-20
**Valid until:** 2026-03-20 (stable -- no external API dependencies, all local DuckDB/Python)
