# Phase 22: Unified Discriminated Query Interface - Research

**Researched:** 2026-02-27
**Domain:** CLI query dispatcher, DuckDB BM25 fulltext search, DuckDB ATTACH cross-database queries, subprocess code search
**Confidence:** HIGH (all patterns verified against existing codebase and live DuckDB testing)

## Summary

Phase 22 adds a unified `query` CLI command that discriminates across three source types: documentation (via existing `query_docs()`), sessions/episodes (via BM25 fulltext search on `episode_search_text`), and code files (via subprocess `grep`/`rg`). A `--source` flag selects the source, and `--source all` aggregates results from all three. A `--project` flag enables cross-project queries via DuckDB ATTACH on registered project databases.

The codebase has all primitives needed. `query_docs()` in `src/pipeline/doc_query.py` already returns axis-matched documentation results. The `HybridRetriever` in `src/pipeline/rag/retriever.py` demonstrates the exact BM25 query pattern needed for episode search. The `MCBridgeReader` in `src/pipeline/bridge/mc_reader.py` demonstrates the ATTACH/DETACH lifecycle for cross-database queries. `data/projects.json` already exists with 4 projects registered. The primary new work is: (1) a `query_sessions()` function wrapping BM25 search with episode metadata enrichment, (2) a `query_code()` function wrapping subprocess `rg`/`grep`, (3) the CLI dispatcher with `--source` and `--project` flags, and (4) adding `db_path` to `projects.json` entries.

**Primary recommendation:** Build `query_sessions()` as a standalone function in `src/pipeline/session_query.py` following the same pattern as `query_docs()` (DuckDB read-only connect, BM25 search, metadata enrichment, fail-open). For cross-project doc queries, use DuckDB ATTACH with `READ_ONLY` since doc_index queries are plain SQL (no FTS). For cross-project session queries, use ATTACH without READ_ONLY to allow on-the-fly FTS index building when the remote database lacks a pre-built index. For code search, shell out to `rg` (ripgrep) with `grep` fallback.

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| DuckDB | 1.4.4 | BM25 fulltext search on `episode_search_text`, ATTACH for cross-project | Project's primary analytical DB |
| Click | (in requirements) | CLI command group with `--source` and `--project` options | All CLI commands use Click |
| subprocess (stdlib) | N/A | Shell out to `rg`/`grep` for code search | Standard for external tool invocation |
| json (stdlib) | N/A | Read `data/projects.json` for project registry | Standard JSON handling |

### Supporting (no new dependencies needed)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| shutil (stdlib) | `shutil.which('rg')` to detect ripgrep availability | Code search tool selection |
| pathlib (stdlib) | Path resolution for cross-project db_path | Project registry path handling |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| subprocess `rg`/`grep` | DuckDB `read_text()` | DuckDB `read_text` can read files but cannot do line-number grep; subprocess is simpler and gives line numbers natively |
| ILIKE on attached DBs | BM25 on attached DBs | BM25 requires `USE schema` or read-write ATTACH for FTS index building; ILIKE works on READ_ONLY but is less precise |
| Separate CLI command per source | Unified `query --source X` | Unified is more discoverable; user asks one question, gets discriminated results |

**Installation:**
```bash
# No new dependencies needed. All tools already available.
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/
  session_query.py        # NEW: query_sessions() - BM25 search over episode_search_text
  code_query.py           # NEW: query_code() - subprocess rg/grep search
  doc_query.py            # EXISTS: query_docs() - axis graph search over doc_index
  cli/
    __main__.py           # MODIFY: register query group
    query.py              # NEW: unified query CLI with --source and --project flags
data/
  projects.json           # MODIFY: add db_path field to project entries
```

### Pattern 1: BM25 Standalone Query (query_sessions)
**What:** Direct BM25 search on `episode_search_text` without requiring embeddings (unlike `HybridRetriever` which requires both BM25 + embeddings).
**When to use:** Session/episode search via CLI. The user provides text, we return episode matches.
**Example (verified from `src/pipeline/rag/retriever.py` lines 82-98):**
```python
# Source: Verified from HybridRetriever._bm25_search() and live DuckDB testing
import duckdb

def query_sessions(
    query: str,
    db_path: str = "data/ope.db",
    top_n: int = 5,
) -> list[dict]:
    """BM25 fulltext search over episode_search_text.

    Returns list of {source, episode_id, session_id, content_preview, match_reason}
    """
    try:
        conn = duckdb.connect(db_path, read_only=True)
        conn.execute("LOAD fts;")

        rows = conn.execute("""
            SELECT sq.episode_id, sq.score
            FROM (
                SELECT *, fts_main_episode_search_text.match_bm25(
                    episode_id, ?
                ) AS score
                FROM episode_search_text
            ) sq
            WHERE sq.score IS NOT NULL
            ORDER BY sq.score DESC
            LIMIT ?
        """, [query, top_n]).fetchall()

        if not rows:
            conn.close()
            return []

        # Enrich with episode metadata
        eids = [r[0] for r in rows]
        scores = {r[0]: r[1] for r in rows}
        placeholders = ",".join(["?"] * len(eids))

        details = conn.execute(f"""
            SELECT e.episode_id, e.session_id, e.mode,
                   LEFT(est.search_text, 200) as preview
            FROM episodes e
            JOIN episode_search_text est ON e.episode_id = est.episode_id
            WHERE e.episode_id IN ({placeholders})
        """, eids).fetchall()

        conn.close()

        results = []
        for d in details:
            results.append({
                "source": "sessions",
                "episode_id": d[0],
                "session_id": d[1],
                "content_preview": d[3] or "",
                "match_reason": f"bm25 (score={scores.get(d[0], 0):.2f})",
            })
        # Sort by BM25 score
        results.sort(key=lambda r: scores.get(r["episode_id"], 0), reverse=True)
        return results
    except Exception:
        return []
```

### Pattern 2: Subprocess Code Search (query_code)
**What:** Shell out to `rg` (ripgrep, preferred) or `grep` for code search with file paths and line numbers.
**When to use:** `--source code` flag.
**Example (verified: `rg` available at `/opt/homebrew/bin/rg`, `grep` at `/usr/bin/grep`):**
```python
# Source: Verified tool availability on system
import subprocess
import shutil

def query_code(
    query: str,
    search_dir: str = "src/",
    top_n: int = 10,
) -> list[dict]:
    """Search code files for query text using rg or grep.

    Returns list of {source, file_path, line_number, content_preview, match_reason}
    """
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "-n", "-i", "--max-count", "3",
               "--type", "py", "--type", "md",
               query, search_dir]
    else:
        cmd = ["grep", "-rn", "-i", "--include=*.py", "--include=*.md",
               query, search_dir]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode not in (0, 1):  # 1 = no matches
            return []

        results = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: file:line:content
            parts = line.split(":", 2)
            if len(parts) >= 3:
                results.append({
                    "source": "code",
                    "file_path": parts[0],
                    "line_number": int(parts[1]),
                    "content_preview": parts[2].strip()[:120],
                    "match_reason": "text match",
                })
            if len(results) >= top_n:
                break
        return results
    except Exception:
        return []
```

### Pattern 3: Cross-Project DuckDB ATTACH
**What:** ATTACH a remote project's DuckDB file to query its doc_index or episodes.
**When to use:** `--project` flag specifies a different project.
**Critical findings from live testing (DuckDB 1.4.4):**

1. **ATTACH READ_ONLY works for plain SQL:** `SELECT ... FROM remote.doc_index` works perfectly on read-only attached databases.
2. **BM25/FTS fails on attached databases** unless you `USE schema` first. The FTS function `fts_main_episode_search_text.match_bm25()` resolves only within the current `USE`d schema.
3. **Cannot build FTS index on READ_ONLY attached databases.** `PRAGMA create_fts_index(...)` requires write access; READ_ONLY ATTACH blocks it.
4. **ATTACH nonexistent files fails** with `IOException` -- must check file existence first.
5. **Multiple ATTACHes work** simultaneously from a single connection.
6. **Must `USE memory` before detaching** the currently USEd schema; otherwise DuckDB raises `BinderException`.

**Recommended cross-project query flow:**
```python
# For doc_index queries (plain SQL, no FTS needed):
conn = duckdb.connect(":memory:")
conn.execute(f"ATTACH '{remote_db_path}' AS remote (READ_ONLY)")
rows = conn.execute("SELECT doc_path, ccd_axis, description_cache FROM remote.doc_index WHERE ...")

# For BM25 episode queries on remote DB:
conn = duckdb.connect(":memory:")
conn.execute(f"ATTACH '{remote_db_path}' AS remote (READ_ONLY)")
conn.execute("USE remote")
conn.execute("LOAD fts;")
# Now BM25 works if FTS index was pre-built in the remote DB
rows = conn.execute("""
    SELECT sq.episode_id, sq.score FROM (
        SELECT *, fts_main_episode_search_text.match_bm25(episode_id, ?) AS score
        FROM episode_search_text
    ) sq WHERE sq.score IS NOT NULL ...
""", [query])
# Clean up
conn.execute("USE memory")
conn.execute("DETACH remote")
```

**Example (verified from `src/pipeline/bridge/mc_reader.py` lines 74-96):**
```python
# Source: MCBridgeReader ATTACH pattern (uses context manager for lifecycle)
class CrossProjectQueryer:
    def __init__(self, remote_db_path: str):
        self._remote_path = remote_db_path
        self._conn = None

    def __enter__(self):
        self._conn = duckdb.connect(":memory:")
        self._conn.execute(f"ATTACH '{self._remote_path}' AS remote (READ_ONLY)")
        return self

    def __exit__(self, *args):
        try:
            self._conn.execute("USE memory")
            self._conn.execute("DETACH remote")
        except Exception:
            pass
        self._conn.close()
```

### Pattern 4: CLI Group with Choice Options
**What:** Click group with `--source` choice and `--project` option.
**When to use:** The unified query command.
**Example (verified from `src/pipeline/cli/govern.py` line 123 for click.Choice pattern):**
```python
import click

@click.group(name="query")
def query_group():
    """Search across sessions, docs, and code."""

@query_group.command(name="search")
@click.argument("query_text")
@click.option(
    "--source",
    type=click.Choice(["docs", "sessions", "code", "all"]),
    default="all",
    help="Source to search"
)
@click.option("--project", default=None, help="Project ID from projects.json")
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option("--top", "top_n", default=5, help="Max results per source")
def search(query_text, source, project, db, top_n):
    """Search for QUERY_TEXT across project sources."""
    ...
```

### Pattern 5: Unified Output Format
**What:** All three source types return results in a common format for `--source all` aggregation.
**When to use:** Aggregating and displaying results from multiple sources.
```python
# Common result shape (all sources return this):
{
    "source": "docs" | "sessions" | "code",
    # Source-specific fields:
    "doc_path": ...,        # docs only
    "ccd_axis": ...,        # docs only
    "episode_id": ...,      # sessions only
    "session_id": ...,      # sessions only
    "file_path": ...,       # code only
    "line_number": ...,     # code only
    # Common fields:
    "content_preview": ..., # all sources (truncated text)
    "match_reason": ...,    # all sources (how it matched)
}
```

### Anti-Patterns to Avoid
- **Requiring embeddings for session search:** The HybridRetriever needs `query_embedding` (384-dim vector). Phase 22's `query_sessions()` should use BM25 only -- no embedding dependency. This makes it callable without model inference.
- **Using FTS on READ_ONLY attached databases without pre-built index:** The FTS index must already exist in the attached DB file. If it does not, fall back to ILIKE search.
- **Hardcoding project db_paths:** Always read from `data/projects.json`. Never hardcode `data/ope.db` as the only option.
- **Forgetting to DETACH:** The `MCBridgeReader` pattern (context manager with attach/detach) must be followed to avoid resource leaks.
- **Building a custom search engine for code:** `rg` is available on the system and purpose-built for this. Do not reinvent it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Code search | Custom file walker + regex matching | `subprocess.run(['rg', ...])` | `rg` handles binary detection, gitignore, encoding, parallelism |
| BM25 text search | TF-IDF implementation | DuckDB FTS extension `match_bm25()` | Already used in 2 other modules, battle-tested |
| Project registry | Custom config format | Existing `data/projects.json` with `db_path` field added | Registry already has 4 projects, `add_project.py` manages it |
| Cross-DB queries | Export/import between databases | DuckDB ATTACH | Native DuckDB feature, used in `MCBridgeReader` |
| CLI choice validation | Manual string checking | `click.Choice(["docs", "sessions", "code", "all"])` | Click handles validation and help text |

**Key insight:** Every component exists as a tested pattern in the codebase. The Phase 22 work is composition (wiring existing patterns into a unified interface), not invention.

## Common Pitfalls

### Pitfall 1: FTS Index Missing in episode_search_text
**What goes wrong:** BM25 query returns 0 results even though `episode_search_text` has rows.
**Why it happens:** The FTS index is built by `EpisodeEmbedder.rebuild_fts_index()` which must be called after batch insertion. Only 53 of 961 episodes currently have search text populated. If the index was never built, `match_bm25()` returns NULL for all rows.
**How to avoid:** Check if `fts_main_episode_search_text` tables exist before attempting BM25. Fall back to ILIKE if FTS is absent. Log a warning suggesting `python -m src.pipeline.cli train embed`.
**Warning signs:** `query_sessions()` always returns `[]` despite episodes existing.

### Pitfall 2: Cross-Project FTS on READ_ONLY ATTACH Fails
**What goes wrong:** `PRAGMA create_fts_index()` on a READ_ONLY attached database raises `InvalidInputException: Cannot execute statement of type "DROP" on database "..." which is attached in read-only mode!`
**Why it happens:** FTS index creation involves DROP + CREATE internally. READ_ONLY blocks all write operations.
**How to avoid:** For cross-project session queries, either: (a) require the remote DB to have a pre-built FTS index, or (b) ATTACH without READ_ONLY and build FTS on-the-fly, or (c) fall back to ILIKE search on READ_ONLY attached DBs. Option (c) is safest -- it always works, even if less precise.
**Warning signs:** `InvalidInputException` in cross-project session queries.

### Pitfall 3: DuckDB schema Qualification for ATTACH Queries
**What goes wrong:** Queries like `SELECT * FROM remote.information_schema.tables` fail with `Table with name tables does not exist!`
**Why it happens:** DuckDB 1.4.4 does not support 3-part names for `information_schema`. You must `USE remote` first, then query `information_schema.tables` unqualified, or use `duckdb_tables()` system function with `database_name` filter.
**How to avoid:** Use `SELECT table_name FROM duckdb_tables() WHERE database_name = 'remote'` for table introspection on attached databases.
**Warning signs:** `CatalogException` when querying information_schema on attached DB.

### Pitfall 4: Detaching the Currently-USEd Schema
**What goes wrong:** `DETACH remote` raises `BinderException: Cannot detach database "remote" because it is the default database`.
**Why it happens:** After `USE remote`, the remote schema becomes the default. DuckDB won't detach the default.
**How to avoid:** Always `USE memory` (or the original schema) before `DETACH remote`.
**Warning signs:** `BinderException` during cleanup.

### Pitfall 5: projects.json Missing db_path
**What goes wrong:** Cross-project `--project modernizing-tool` fails because there's no way to find the remote DB.
**Why it happens:** Current `projects.json` has no `db_path` field. The phase description says `--project` should work, but the registry doesn't know where each project's DuckDB lives.
**How to avoid:** Add `db_path` field to `projects.json` entries. For `orchestrator-policy-extraction` this is `data/ope.db`. For other projects, it would be their respective DB paths. Since `ope.db` contains ALL projects' sessions, cross-project session queries can just query `ope.db` with a session_id filter. Cross-project doc queries need the remote project's doc_index, which only exists if that project has run `docs reindex`.
**Warning signs:** `KeyError: 'db_path'` or empty results for cross-project queries.

### Pitfall 6: ope.db is Multi-Project -- Sessions Don't Need ATTACH
**What goes wrong:** Implementing cross-project session queries via ATTACH when the data is already in `ope.db`.
**Why it happens:** Assumption that each project has its own separate DuckDB. In reality, `ope.db` contains sessions from ALL 4 registered projects (modernizing-tool: 114 sessions, OPE: 59, personal-website: 7, objectivism-library: 72).
**How to avoid:** For session queries, `ope.db` already has all projects. The `--project` filter for sessions should filter by session_id (match against project's `sessions_location`), NOT by ATTACHing a different DB. ATTACH is only needed for cross-project doc_index queries (if the remote project has its own doc_index in a separate DB).
**Warning signs:** Unnecessary ATTACH calls for session queries; same results regardless of `--project` flag.

### Pitfall 7: Low episode_search_text Coverage
**What goes wrong:** BM25 search finds results for only 53 of 961 episodes (5.5% coverage).
**Why it happens:** `episode_search_text` is populated by the embedding pipeline (`train embed`), which has only been run on a subset of episodes. Most episodes have no search text.
**How to avoid:** Document this limitation. Consider adding a direct-from-episodes fallback that searches the JSON `observation`, `orchestrator_action`, and `outcome` fields via ILIKE when `episode_search_text` coverage is low. This is slower but comprehensive.
**Warning signs:** Very few BM25 results; user asks about topics they know exist but gets no hits.

### Pitfall 8: Code Search Across Projects Requires Knowing the Code Directory
**What goes wrong:** `--project modernizing-tool --source code` has no way to search the modernizing-tool's source code.
**Why it happens:** Code search uses subprocess `rg` which needs a filesystem path. The registry has `git_location` but this may be a remote URL (e.g., `https://github.com/...`), not a local path.
**How to avoid:** For Phase 22, code search operates only on the local project (`src/`, `docs/`). Cross-project code search is deferred until projects have local clones registered. The `git_location` field can be used for local paths when it's a filesystem path (not a URL).
**Warning signs:** `rg` failing with non-existent directory errors for remote projects.

## Code Examples

### BM25 Query with FTS Check and ILIKE Fallback
```python
# Source: Verified from live DuckDB 1.4.4 testing
import duckdb

def _bm25_search(conn, query: str, top_n: int) -> list[tuple]:
    """BM25 search with FTS availability check."""
    # Check if FTS index exists
    fts_tables = conn.execute(
        "SELECT table_name FROM duckdb_tables() "
        "WHERE table_name LIKE 'fts_main_episode_search_text%'"
    ).fetchall()

    if fts_tables:
        # FTS index exists -- use BM25
        conn.execute("LOAD fts;")
        return conn.execute("""
            SELECT sq.episode_id, sq.score
            FROM (
                SELECT *, fts_main_episode_search_text.match_bm25(
                    episode_id, ?
                ) AS score
                FROM episode_search_text
            ) sq
            WHERE sq.score IS NOT NULL
            ORDER BY sq.score DESC
            LIMIT ?
        """, [query, top_n]).fetchall()
    else:
        # No FTS index -- fallback to ILIKE
        return conn.execute("""
            SELECT episode_id, 1.0 AS score
            FROM episode_search_text
            WHERE search_text ILIKE ?
            LIMIT ?
        """, [f"%{query}%", top_n]).fetchall()
```

### Cross-Project doc_index Query via ATTACH
```python
# Source: Verified from MCBridgeReader pattern + live ATTACH testing
import duckdb
from pathlib import Path

def query_docs_cross_project(
    query: str,
    remote_db_path: str,
    top_n: int = 3,
) -> list[dict]:
    """Query doc_index on a remote project's DuckDB via ATTACH."""
    if not Path(remote_db_path).exists():
        return []

    try:
        conn = duckdb.connect(":memory:")
        conn.execute(f"ATTACH '{remote_db_path}' AS remote (READ_ONLY)")

        # Check if remote has doc_index
        has_table = conn.execute(
            "SELECT name FROM duckdb_tables() "
            "WHERE database_name = 'remote' AND name = 'doc_index'"
        ).fetchall()
        if not has_table:
            conn.execute("DETACH remote")
            conn.close()
            return []

        # query_docs() logic works on attached tables (plain SQL, no FTS)
        # Import and delegate to query_docs with modified db_path handling
        # OR inline the axis-match logic here

        conn.execute("DETACH remote")
        conn.close()
        return results
    except Exception:
        return []
```

### Project Registry db_path Resolution
```python
# Source: Verified from data/projects.json structure
import json
from pathlib import Path

def resolve_project_db(project_id: str, registry_path: str = "data/projects.json") -> str | None:
    """Resolve a project ID to its DuckDB path from the registry.

    Falls back to 'data/ope.db' for the local project.
    """
    with open(registry_path) as f:
        registry = json.load(f)

    for project in registry["projects"]:
        if project["id"] == project_id:
            return project.get("db_path", "data/ope.db")

    return None
```

### CLI Dispatcher Output Format
```python
# Source: Verified from src/pipeline/cli/docs.py output format
import click

def _print_results(results: list[dict], source_filter: str):
    """Print query results with source labels."""
    if not results:
        click.echo(f"[OPE Query] No results found.")
        return

    click.echo(f"[OPE Query] {len(results)} result(s):")
    for r in results:
        source = r["source"]
        if source == "docs":
            click.echo(f"[OPE]   [{source}] {r['doc_path']} (axis: {r.get('ccd_axis', 'N/A')}, {r['match_reason']})")
            if r.get("content_preview"):
                click.echo(f"[OPE]     {r['content_preview'][:80]}")
        elif source == "sessions":
            click.echo(f"[OPE]   [{source}] episode={r['episode_id']} session={r['session_id']} ({r['match_reason']})")
            if r.get("content_preview"):
                click.echo(f"[OPE]     {r['content_preview'][:80]}")
        elif source == "code":
            click.echo(f"[OPE]   [{source}] {r['file_path']}:{r['line_number']} ({r['match_reason']})")
            click.echo(f"[OPE]     {r['content_preview']}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate `docs query` CLI | Phase 22: unified `query --source` CLI | Phase 22 | Single entry point for all search |
| No session text search via CLI | Phase 22: BM25 session search | Phase 22 | Episodes searchable by text content |
| Manual grep for code search | Phase 22: `query --source code` | Phase 22 | Integrated code search with same output format |
| Single-project queries only | Phase 22: `--project` flag with ATTACH | Phase 22 | Cross-project knowledge retrieval |

**Current data state (verified 2026-02-27):**
- `ope.db`: 961 episodes, 53 with search text, 100 doc_index rows, FTS index pre-built
- `self.db`: 85 episodes, 0 with search text, no doc_index, no FTS index
- `projects.json`: 4 projects registered, no `db_path` field
- `episode_search_text` coverage: 5.5% (53/961) -- BM25 will miss most episodes
- ripgrep (`rg`) available at `/opt/homebrew/bin/rg`

**Key architectural insight:** `ope.db` is the multi-project database. It already contains sessions from ALL 4 registered projects. For session queries, `--project` filtering should filter by session_id against the project's sessions_location, NOT by ATTACHing a separate database. ATTACH is only needed for cross-project doc_index queries when a remote project has its own doc_index in a separate DuckDB file.

## Critical Design Decisions

### 1. db_path in projects.json
The `projects.json` registry needs a `db_path` field per project. Two options:

| Option | Description | Implication |
|--------|-------------|-------------|
| **A: All projects share ope.db** | `db_path` = `"data/ope.db"` for all projects | Session search works immediately; doc_index queries only work for OPE (the only project with doc_index) |
| **B: Per-project db_path** | `db_path` = `"data/ope.db"` for OPE, other projects get their own db files when they build doc_index | Future-proof but most projects don't have doc_index yet |

**Recommendation: Option A for sessions, Option B for docs.** Since ope.db has all sessions, session queries always use ope.db. For doc_index, only OPE has indexed docs. Add a `docs_db_path` field (optional) alongside the main `db_path`. When absent, doc queries are unavailable for that project.

### 2. Session Filtering by Project
Since ope.db has sessions from all projects, filtering by project requires mapping project_id to session_ids. The `data_status.sessions_location` field in `projects.json` tells us where each project's JSONL files live. The session_id = the JSONL filename (stem). The filter flow:
1. Read `projects.json[project_id].data_status.sessions_location`
2. List `*.jsonl` files in that directory
3. Extract session_ids from filenames
4. Filter BM25 results by those session_ids

Or simpler: join episodes with events table, and events has session_id which was ingested per-project.

### 3. CLI Shape: Subcommand vs. Direct Command
The phase spec uses: `python -m src.pipeline.cli query --source docs "raven cost function"`

This means `query` is a CLI group/command, not a subgroup. The simplest implementation:
```python
@click.command(name="query")
@click.argument("query_text")
@click.option("--source", type=click.Choice(["docs", "sessions", "code", "all"]), default="all")
@click.option("--project", default=None)
def query_cmd(query_text, source, project):
    ...
```
Registered in `__main__.py` as: `cli.add_command(query_cmd, name="query")`

## Open Questions

1. **Should the existing `docs query` command be preserved or replaced?**
   - What we know: `src/pipeline/cli/docs.py` already has a `query` subcommand (`docs query "text"`). Phase 22 adds `query --source docs "text"`.
   - What's unclear: Whether to deprecate `docs query` or keep both.
   - Recommendation: Keep `docs query` as-is (backward compatibility). The new `query --source docs` delegates to the same `query_docs()` function. No code duplication, just a new entry point.

2. **How should cross-project doc queries work when the remote project has no doc_index?**
   - What we know: Only OPE currently has a `doc_index` table. The modernizing-tool has no DuckDB database at all. The objectivism-library has `library.db` with a completely different schema (no doc_index).
   - What's unclear: Whether cross-project doc queries should fail silently or suggest running `docs reindex`.
   - Recommendation: Fail-open with a message: `[OPE Query] Project 'modernizing-tool' has no doc_index. Run 'docs reindex' for that project.` For Phase 22, cross-project doc queries are best-effort.

3. **Should ILIKE fallback be automatic when FTS index is missing?**
   - What we know: 53/961 episodes have search text. If FTS index is absent, BM25 returns nothing.
   - What's unclear: Whether ILIKE on the full `episode_search_text` table (or even `episodes` JSON fields) is acceptable performance.
   - Recommendation: Yes, automatic fallback. For 53 rows, ILIKE is instant. For larger tables, add a warning about building FTS index. The fallback prevents silent failure.

4. **What should `--project all` do for session queries?**
   - What we know: All sessions are already in `ope.db` regardless of project. `--project all` for sessions is equivalent to no project filter.
   - What's unclear: Whether `--project all` should be the default or whether unfiltered is the default.
   - Recommendation: Default is no filter (all projects). `--project X` filters to that project only. `--project all` is explicitly all (same as no filter). This matches the spec.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/doc_query.py` -- verified `query_docs()` API, return format, axis matching logic
- `src/pipeline/rag/retriever.py` -- verified `HybridRetriever._bm25_search()` BM25 query pattern
- `src/pipeline/bridge/mc_reader.py` -- verified ATTACH/DETACH lifecycle pattern with context manager
- `src/pipeline/rag/embedder.py` -- verified FTS index creation: `PRAGMA create_fts_index('episode_search_text', 'episode_id', 'search_text', stemmer='porter', stopwords='english', lower=1, overwrite=1)`
- `src/pipeline/storage/schema.py` -- verified `episode_search_text` DDL: `(episode_id VARCHAR PK, search_text VARCHAR)`
- `src/pipeline/cli/__main__.py` -- verified Click group registration pattern
- `src/pipeline/cli/docs.py` -- verified existing `docs query` command structure
- `data/projects.json` -- verified 4 projects, no `db_path` field, has `data_status.sessions_location`
- `scripts/add_project.py` -- verified project registry management script
- Live DuckDB 1.4.4 testing -- verified ATTACH, FTS on attached DBs, READ_ONLY limitations, `USE schema` requirement

### Secondary (MEDIUM confidence)
- `src/pipeline/wisdom/retriever.py` -- BM25 pattern for `project_wisdom` table (same pattern as episode search)
- `src/pipeline/live/governor/daemon.py` -- verified `_query_relevant_docs()` reads doc_index from ope.db
- Phase 21 RESEARCH.md -- verified doc_index schema, axis extraction patterns

### Tertiary (LOW confidence)
- Cross-project doc_index availability -- only OPE has doc_index currently; assumption that other projects will build theirs needs validation per project

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies
- Architecture (session query): HIGH -- exact BM25 pattern verified from `HybridRetriever`, live-tested
- Architecture (code query): HIGH -- `rg` verified available, subprocess pattern standard
- Architecture (cross-project): HIGH for mechanism (ATTACH verified), MEDIUM for data availability (most projects lack doc_index and FTS)
- Pitfalls: HIGH -- all discovered through live testing, not speculation
- CLI integration: HIGH -- Click patterns verified from 10+ existing command groups

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable codebase, DuckDB 1.4.4 API stable)
