# Claude Code Skills

Project-local skills for orchestrator-policy-extraction.

## Available Skills

### `/ingest` - Incremental Session Ingestion

Discovers and ingests new Claude Code sessions from `~/.claude/projects/` and generates embeddings for the RAG training system.

**Usage:**
```
/ingest                    # Full ingestion with embeddings
/ingest --dry-run          # Preview without executing
/ingest --no-embed         # Ingest without embeddings
/ingest --project=<name>   # Specific project only
```

**What it does:**
1. Scans `~/.claude/projects/` for new JSONL session files
2. Processes them through the extraction pipeline (tag → segment → populate → validate)
3. Generates embeddings for RAG retrieval (if --no-embed not specified)
4. Shows summary statistics

**Examples:**
```bash
# Weekly data update
/ingest

# Check what's available without ingesting
/ingest --dry-run

# Ingest just this project's sessions
/ingest --project=orchestrator-policy-extraction

# Ingest without embeddings (faster, can embed later)
/ingest --no-embed
```

**Behind the scenes:**
- Runs: `python scripts/ingest_incremental.py --embed -v`
- Automatically skips already-ingested sessions (idempotent)
- Updates RAG system with new training data
- Embeddings are incremental (only new episodes)

### `/add-project` - Register a New Project

Adds a project to `data/projects.json` so its Claude Code sessions can be discovered and ingested.

**Usage:**
```
/add-project <project-path>
/add-project <project-path> --git <git-repo-path>
/add-project <project-path> --name "Display Name"
```

**Arguments:**
- `<project-path>` — filesystem path to the project (required). Sessions location is derived automatically.
- `--git` — git repo path, if different from `project-path` (optional)
- `--name` — display name override (optional, derived from path if omitted)

**Examples:**
```bash
# Add a project
/add-project /Users/david/projects/my-project

# Add with explicit git repo
/add-project /Users/david/projects/my-project --git /Users/david/projects/my-project

# Then ingest its sessions
/ingest --project=my-project
```

**What it does:**
1. Derives project ID (last path component) and sessions location (`~/.claude/projects/<encoded-path>/`)
2. Checks whether sessions directory exists on disk
3. Appends entry to `data/projects.json` with correct `data_status` fields
4. Prints next-step commands to run ingestion

---

## How the Learning Loop Works

Every time you run `/ingest`, new data flows through:

```
New Sessions → Pipeline → Episodes → Embeddings → RAG System
```

The RAG system automatically uses ALL episodes in the database, so recommendations improve with each ingestion.

## Scheduling (Future)

For automatic daily ingestion, add to cron:
```bash
# Daily at 2 AM
0 2 * * * cd /path/to/orchestrator-policy-extraction && python scripts/ingest_incremental.py --embed
```

## See Also

- `scripts/INGESTION.md` - Detailed ingestion documentation
- `scripts/discover_new_sessions.py` - Discovery script (used by /ingest)
- `scripts/ingest_incremental.py` - Ingestion script (used by /ingest)
