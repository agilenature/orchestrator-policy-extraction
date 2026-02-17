# Ingestion Scripts

Incremental ingestion system for Claude Code sessions → Training pipeline.

## Quick Start

```bash
# 1. Discover what's available
python scripts/discover_new_sessions.py

# 2. Ingest new sessions + generate embeddings
python scripts/ingest_incremental.py --embed -v

# 3. Done! RAG automatically uses new data
```

## How It Works

### Learning Loop
```
New JSONL Sessions
    ↓ (ingest_incremental.py)
DuckDB episodes table
    ↓ (train embed - incremental)
episode_embeddings + episode_search_text
    ↓ (automatic)
RAG Retriever queries ALL episodes
    ↓
Smarter recommendations
```

**Key insight:** No "retraining" needed! RAG queries DuckDB directly.

## Scripts

### discover_new_sessions.py
Scans for new JSONL files not in DuckDB yet.

```bash
python scripts/discover_new_sessions.py          # Human summary
python scripts/discover_new_sessions.py --json   # JSON output
```

### ingest_incremental.py
Processes only new sessions.

```bash
python scripts/ingest_incremental.py --dry-run   # Show plan
python scripts/ingest_incremental.py --embed     # Ingest + embed
python scripts/ingest_incremental.py --project orchestrator-policy-extraction  # Specific project
```

## Examples

### Initial Ingestion (First Time)
```bash
python scripts/discover_new_sessions.py
python scripts/ingest_incremental.py --embed -v
```

### Weekly Update
```bash
python scripts/ingest_incremental.py --embed
python -m src.pipeline.cli.train shadow-run
```

## How Tracking Works

- **State**: DuckDB `events` table (`SELECT DISTINCT session_id`)
- **Discovery**: Scan `~/.claude/projects/*.jsonl` for UUID
- **Delta**: `found - ingested = new_sessions`

## How Incremental Embedding Works

```python
# src/pipeline/rag/embedder.py only embeds NEW episodes:
SELECT e.episode_id, e.observation FROM episodes e
LEFT JOIN episode_embeddings ee ON e.episode_id = ee.episode_id
WHERE ee.episode_id IS NULL  # The magic!
```

## Verification

```bash
python -c "
import duckdb
conn = duckdb.connect('data/ope.db')
print(f\"Sessions: {conn.execute('SELECT COUNT(DISTINCT session_id) FROM events').fetchone()[0]}\")
print(f\"Episodes: {conn.execute('SELECT COUNT(*) FROM episodes').fetchone()[0]}\")
print(f\"Embeddings: {conn.execute('SELECT COUNT(*) FROM episode_embeddings').fetchone()[0]}\")
conn.close()
"
```

## See Also
- Main README: `scripts/README.md`
- Pipeline docs: `src/pipeline/README.md`
