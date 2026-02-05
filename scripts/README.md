# Scripts Directory

CLI tools for dataset management and processing.

## Overview

This directory contains executable scripts for:
- Adding/validating projects
- Running processing pipeline
- Generating reports
- Maintenance tasks

## Scripts (to be created in future phases)

### Project Management

#### `add-project.py` (Phase 6)
**Purpose:** Interactive wizard for adding new projects

**Usage:**
```bash
python scripts/add-project.py \
  --name "My Project" \
  --repo "https://github.com/user/repo" \
  --sessions "/Users/user/.claude/projects/-path-to-project/" \
  --interactive
```

**Features:**
- Validates data availability
- Creates metadata.json
- Adds to projects.json registry
- Runs initial processing
- Generates quality report

---

#### `validate-project.py` (Phase 0.4)
**Purpose:** Validate project data before processing

**Usage:**
```bash
python scripts/validate-project.py --project modernizing-tool
```

**Checks:**
- ✅ Session directory exists and has JSONL files
- ✅ Git repository cloned
- ✅ metadata.json is valid
- ✅ Date ranges overlap (sessions + commits)
- ✅ Minimum data volume (5+ sessions, 10+ commits)
- ✅ Session IDs present in commits (if instrumented)

**Exit codes:**
- 0: Valid
- 1: Validation errors (see stderr)

---

#### `archive-project.py` (Phase 6)
**Purpose:** Archive completed project for long-term storage

**Usage:**
```bash
python scripts/archive-project.py --project modernizing-tool --copy-sessions
```

**Actions:**
- Copy sessions to `data/raw/PROJECT/sessions/` (if not already)
- Update metadata.json (status: archived)
- Generate final statistics
- Create tarball for export (optional)

---

### Data Processing

#### `process-project.py` (Phase 1)
**Purpose:** Run correlation pipeline on a project

**Usage:**
```bash
python scripts/process-project.py \
  --project modernizing-tool \
  --threshold 0.7 \
  --output-dir data/processed/modernizing-tool/
```

**Stages:**
1. Extract session hashes
2. Extract commit hashes
3. Run correlation algorithm
4. Generate session-commit-map.json
5. Update quality metrics

**Options:**
- `--threshold`: Correlation confidence threshold (default: 0.7)
- `--force`: Reprocess even if outputs exist
- `--verbose`: Debug logging

---

#### `extract-episodes.py` (Phase 2)
**Purpose:** Parse sessions and generate episodes

**Usage:**
```bash
python scripts/extract-episodes.py \
  --project modernizing-tool \
  --action-taxonomy data/action-taxonomy.json \
  --reaction-taxonomy data/reaction-taxonomy.json
```

**Stages:**
1. Parse session JSONL files
2. Build observation features
3. Map actions to taxonomy
4. Categorize reactions
5. Generate episode files

**Options:**
- `--sessions`: Specific session IDs to process (default: all)
- `--skip-reactions`: Don't categorize reactions (faster)
- `--output-format`: jsonl | json | parquet

---

#### `merge-datasets.py` (Phase 1-2)
**Purpose:** Regenerate cross-project merged indices

**Usage:**
```bash
python scripts/merge-datasets.py --all
```

**Outputs:**
- `data/merged/all-correlations.json`
- `data/merged/all-episodes.jsonl`
- `data/merged/statistics.json`

**Options:**
- `--projects`: Specific projects to merge (default: all)
- `--split-by-phase`: Create per-phase JSONL files
- `--split-by-action`: Create per-action-type JSONL files

---

### Analysis & Reporting

#### `generate-report.py` (Phase 1+)
**Purpose:** Generate quality report for project or dataset

**Usage:**
```bash
# Single project report
python scripts/generate-report.py --project modernizing-tool

# Full dataset report
python scripts/generate-report.py --all
```

**Outputs:**
- Correlation precision/recall
- Episode count and distribution
- Action/reaction taxonomy coverage
- Temporal distribution (sessions over time)
- File coverage (which files most modified)
- Markdown report + visualizations (plots)

---

#### `export-dataset.py` (Phase 2+)
**Purpose:** Export dataset for sharing or external use

**Usage:**
```bash
python scripts/export-dataset.py \
  --output dataset-v1.0.tar.gz \
  --include-raw-sessions \
  --anonymize
```

**Formats:**
- Tarball (tar.gz)
- Zip archive
- DVC repository
- Hugging Face Datasets format (future)

**Options:**
- `--include-raw-sessions`: Include original JSONL (large)
- `--anonymize`: Remove author names, redact sensitive paths
- `--split`: Train/val/test split

---

### Maintenance

#### `update-project.py` (Phase 6)
**Purpose:** Incrementally process new sessions/commits

**Usage:**
```bash
python scripts/update-project.py --project modernizing-tool
```

**Actions:**
1. Detect new session files (compare to processed list)
2. Detect new commits (git log since last update)
3. Process incrementally (don't reprocess old data)
4. Update merged indices

**Use case:** Weekly data refresh

---

#### `migrate-schema.py` (Future)
**Purpose:** Migrate dataset to new schema version

**Usage:**
```bash
python scripts/migrate-schema.py --from 1.0 --to 1.1
```

**Features:**
- Backward-compatible transformations
- Validation before/after migration
- Rollback on failure

---

## Development Guidelines

### Script Template

```python
#!/usr/bin/env python3
"""
Script name and purpose.

Usage:
    python scripts/script-name.py --arg value
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.module import function


def main():
    parser = argparse.ArgumentParser(description="Script description")
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")

    # Validate inputs
    if not validate_project_exists(args.project):
        logging.error(f"Project {args.project} not found")
        sys.exit(1)

    # Main logic
    try:
        result = function(args.project)
        logging.info("Success!")
        print(result)
    except Exception as e:
        logging.error(f"Failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Best Practices

- **Logging:** Use logging module, not print statements
- **Exit codes:** 0 = success, 1 = error, 2 = invalid usage
- **Validation:** Check inputs before processing
- **Progress:** Use tqdm for long-running operations
- **Idempotency:** Safe to run multiple times (check if outputs exist)
- **Atomicity:** Use temp files, move on success (avoid partial writes)

---

## Testing

**Unit tests:** `tests/scripts/` mirrors this directory

**Integration tests:**
```bash
# Test full pipeline on small project
pytest tests/integration/test_full_pipeline.py
```

**Manual testing checklist:**
- [ ] Validate on known-good project
- [ ] Test error handling (missing files, invalid data)
- [ ] Check output formats
- [ ] Verify idempotency (run twice, same result)

---

## Current Status

- ✅ Directory created
- ✅ README documented
- 🔲 Scripts implementation (Phase 0.4+)

---

## Dependencies

**Common to all scripts:**
```
argparse (stdlib)
logging (stdlib)
pathlib (stdlib)
jsonlines
tqdm
```

**Project-specific:**
- See `src/README.md` for module dependencies

---

## Next Steps

1. Phase 0.4: Implement `validate-project.py`
2. Phase 1: Implement `process-project.py`
3. Phase 2: Implement `extract-episodes.py`, `merge-datasets.py`
4. Phase 3: Implement `generate-report.py`
5. Phase 6: Implement `add-project.py`, `update-project.py`
