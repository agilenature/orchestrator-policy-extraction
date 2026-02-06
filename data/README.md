# Data Directory Structure

This directory contains the multi-project dataset for Orchestrator Policy Extraction (OPE).

## Overview

```
data/
├── ope.db                    # DuckDB database (primary storage - sessions, commits, episodes)
├── raw/                      # Original source data (sessions + git repos, archival backup)
├── processed/                # Exported datasets (Parquet, JSONL for specific use cases)
├── merged/                   # Cross-project unified datasets (deprecated - now in ope.db)
└── validation/               # Manual validation sets
```

**Primary Storage:** All structured data (sessions, commits, correlations, episodes) is stored in `ope.db` (DuckDB database). This enables:
- Fast incremental daily updates (process only new sessions/commits)
- Efficient analytical queries (aggregations, filtering, joins)
- Flexible exports to JSONL/Parquet when needed

## Subdirectories

### `raw/`
**Purpose:** Store or reference original data sources

**Structure:**
```
raw/
├── PROJECT-ID/
│   ├── sessions/             # Claude Code session JSONL files (copied or symlinked)
│   ├── git/                  # Cloned git repository
│   ├── metadata.json         # Project metadata and configuration
│   └── NOTES.md              # Project-specific notes and issues
```

**Contents:**
- **Session logs:** Copied from `~/.claude/projects/` to `sessions/` subdirectory
- **Git repositories:** Shallow clones (temporary, excluded from git)
- **Project metadata:** `metadata.json` with dates, authors, instrumentation settings

**Storage & Backup Strategy:** ✅ **Decision made**
- **Sessions:** ALWAYS COPY to `data/raw/PROJECT/sessions/` and COMMIT TO GIT
  - Rationale: Data loss prevention, reproducibility, portability
  - Size: ~50-200 MB per project (manageable for git)
  - Backup layers: Original + local copy + GitHub remote
- **Git repos:** Shallow clone → extract metadata → delete clone
  - Metadata saved to `data/processed/PROJECT/git-metadata.json`
  - Repo excluded from git (can re-clone if needed)

### `processed/`
**Purpose:** Exported datasets for specific use cases (all primary data lives in `ope.db`)

**Structure:**
```
processed/
├── training_episodes.parquet         # ML training data export
├── test_episodes.parquet             # ML test data export
├── statistics.json                   # Dataset-wide quality metrics
├── PROJECT-ID/                       # Per-project exports (if needed)
│   ├── statistics.json               # Project-specific metrics
│   └── parse-errors.log              # Errors encountered during processing
```

**Note:** Session hashes, commit metadata, correlations, and episodes are stored in `data/ope.db` tables, not as separate JSON/JSONL files. This directory is primarily for exports to other formats.

**Storage Format:** ✅ **Decision made:** DuckDB database (`data/ope.db`)
- Primary storage for all structured data (sessions, commits, correlations, episodes)
- Exports to JSONL (human inspection), Parquet (ML pipelines) as needed
- Enables incremental daily updates and fast analytical queries

### `merged/`
**Purpose:** Cross-project exports (deprecated - replaced by DuckDB queries)

**Note:** With DuckDB as primary storage, cross-project queries are done via SQL:
```sql
-- All episodes across projects
SELECT * FROM episodes;

-- Episodes by phase
SELECT * FROM episodes WHERE json_extract(observation, '$.phase_label') LIKE '03%';

-- Episodes by action type
SELECT * FROM episodes WHERE json_extract(claude_action, '$.tool') = 'Bash';

-- Export merged dataset if needed
COPY (SELECT * FROM episodes) TO 'merged/all-episodes.parquet' (FORMAT PARQUET);
```

**This directory may contain:**
- Exported snapshots for specific analyses
- Archived dataset versions for reproducibility
- Generated reports and visualizations

### `validation/`
**Purpose:** Manual validation sets for quality assurance

**Structure:**
```
validation/
├── reaction-labels.json      # Gold standard reaction categorizations
├── correlation-labels.json   # Manual session-commit links
├── action-taxonomy-review.json
└── inter-rater-agreement/    # Multi-annotator studies
```

**Created in:** Phase 3 (Reaction Taxonomy Development)

## Data Volume Expectations

### Per Project (Typical)
- **Sessions:** 20-50 JSONL files (~50-200 MB)
- **Git repo:** 10-500 MB (depends on full vs. shallow clone)
- **Processed artifacts:** ~10-50 MB
- **Episodes:** 100-500 per project

### Merged Dataset (5 Projects)
- **Total episodes:** 500-2500
- **Storage:** ~500 MB - 2 GB

## Access Patterns

### Read-Heavy Operations
- Episode retrieval for RAG orchestrator (frequent)
- Cross-project analysis (occasional)
- Validation set loading (during development)

### Write Operations
- Project onboarding (infrequent)
- Incremental processing (weekly updates)
- Merged index regeneration (after new project)

## Backup & Versioning

**Backup Strategy (3 Layers):**
1. **Primary:** `~/.claude/projects/` (original session files)
2. **Local backup:** `data/raw/PROJECT/sessions/` (copied)
3. **Remote backup:** GitHub (via git push)
4. **Extracted data:** `data/ope.db` (DuckDB - can reconstruct if needed)

**`.gitignore` Strategy:**
- ✅ **Include** `data/raw/*/sessions/` (session JSONL files - COMMITTED for backup)
- ✅ **Include** `data/ope.db` (DuckDB database - primary extracted data)
- ✅ **Include** `data/processed/statistics.json` (small, useful metrics)
- ❌ **Exclude** `data/raw/*/git/` (can re-clone repositories)
- ❌ **Exclude** `data/processed/*.parquet` (exported datasets, reproducible)

**Dataset Versioning:**
- Tag releases when significant milestones reached: `v1.0`, `v1.1`, etc.
- GitHub releases can include additional archives if needed
- Commit messages track when sessions/data added

## Data Quality Metrics

Each project's `statistics.json` includes:
- **Correlation precision/recall**
- **Episode count and completeness**
- **Action taxonomy coverage**
- **Reaction categorization accuracy**

See `data/merged/statistics.json` for aggregate metrics.

## Adding New Projects

See `INSTRUMENTATION.md` for step-by-step guide.

**Quick checklist:**
1. Add to `data/projects.json` registry
2. Create `data/raw/PROJECT-ID/metadata.json`
3. Run `scripts/validate-project.py`
4. Run `scripts/process-project.py`
5. Run `scripts/merge-datasets.py`

## Schema Versions

**Current schema version:** 1.0

**Compatibility:**
- Processing scripts validate schema version
- Breaking changes require migration scripts
- Version tracked in `projects.json`
