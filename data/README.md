# Data Directory Structure

This directory contains the multi-project dataset for Orchestrator Policy Extraction (OPE).

## Overview

```
data/
├── raw/                      # Original source data (sessions + git repos)
├── processed/                # Extracted artifacts per project
├── merged/                   # Cross-project unified datasets
└── validation/               # Manual validation sets
```

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
- Session logs from `~/.claude/projects/`
- Full or shallow git clones
- Project metadata (dates, authors, instrumentation settings)

**Storage Decision:** (To be determined in Phase 0.1)
- Copy sessions vs. reference in place
- Full clone vs. commit metadata extraction

### `processed/`
**Purpose:** Extracted and analyzed data per project

**Structure:**
```
processed/
├── PROJECT-ID/
│   ├── session-hashes.json           # File hashes from session tool calls
│   ├── commit-hashes.json            # File hashes from git commits
│   ├── session-commit-map.json       # Correlation results
│   ├── statistics.json               # Quality metrics
│   ├── episodes/                     # Turn-level datasets
│   │   ├── SESSION-ID.jsonl          # One file per session
│   │   └── ...
│   ├── episode-statistics.json       # Episode dataset metrics
│   └── parse-errors.log              # Errors encountered during processing
```

**Format Decision:** (To be determined in Phase 0.1)
- JSONL (human-readable, streamable)
- SQLite (queryable, compact)
- Parquet (columnar, analytics-optimized)

### `merged/`
**Purpose:** Cross-project unified datasets and indices

**Structure:**
```
merged/
├── all-correlations.json     # Combined session-commit maps
├── all-episodes.jsonl        # All episodes from all projects
├── by-phase/                 # Episodes grouped by phase type
│   ├── planning.jsonl
│   ├── implementation.jsonl
│   ├── testing.jsonl
│   └── ...
├── by-action-type/           # Episodes grouped by action taxonomy
│   ├── inspect-codebase.jsonl
│   ├── run-tests.jsonl
│   └── ...
└── statistics.json           # Aggregate statistics across projects
```

**Usage:**
- Training/testing RAG orchestrator
- Cross-project pattern analysis
- Dataset-wide metrics

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

**Recommended:**
- Raw data: Archive externally (GitHub releases, S3, etc.)
- Processed data: Git LFS or DVC for version tracking
- Merged indices: Commit to git (small enough)

**`.gitignore` Strategy:**
- Exclude `raw/` (too large, reproducible from source)
- Exclude `processed/*/episodes/` (large, reproducible)
- Include `processed/*/statistics.json` (small, useful)
- Include `merged/` (curated datasets)

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
