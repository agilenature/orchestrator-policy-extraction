"""Append-only JSONL staging writer for premise records.

Solves the DuckDB two-writer conflict: the PAG hook writes to a JSONL file;
the batch pipeline ingests into ope.db. This avoids DuckDB lock contention
between the real-time hook and the batch pipeline.

The staging file is an append-only JSONL file with file locking (fcntl.flock)
for concurrent hook invocations.

Exports:
    STAGING_PATH: Default staging file path
    append_to_staging: Write records to staging JSONL
    read_staging: Read all records from staging JSONL
    clear_staging: Truncate the staging file
"""

from __future__ import annotations

import fcntl
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default staging path (overridable per function call)
STAGING_PATH = "data/premise_staging.jsonl"


def append_to_staging(
    records: list[dict], staging_path: str = STAGING_PATH
) -> int:
    """Append premise records to the staging JSONL file.

    Creates the parent directory if needed. Uses file locking (fcntl.flock)
    to handle concurrent hook invocations safely.

    Each record dict should contain all PremiseRecord fields.

    Args:
        records: List of premise record dicts to append.
        staging_path: Path to the staging JSONL file.

    Returns:
        Number of records written.
    """
    if not records:
        return 0

    path = Path(staging_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for record in records:
        try:
            lines.append(json.dumps(record, default=str) + "\n")
        except (TypeError, ValueError) as e:
            logger.warning("Failed to serialize premise record: %s", e)
            continue

    if not lines:
        return 0

    with open(path, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.writelines(lines)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return len(lines)


def read_staging(staging_path: str = STAGING_PATH) -> list[dict]:
    """Read all records from the staging JSONL file.

    Handles: file not found (return []), corrupt lines (skip with warning).

    Args:
        staging_path: Path to the staging JSONL file.

    Returns:
        List of premise record dicts.
    """
    path = Path(staging_path)
    if not path.exists():
        return []

    records: list[dict] = []
    try:
        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "Skipping corrupt line %d in %s", line_num, staging_path
                    )
                    continue
    except OSError as e:
        logger.warning("Failed to read staging file %s: %s", staging_path, e)
        return []

    return records


def clear_staging(staging_path: str = STAGING_PATH) -> int:
    """Read count, then truncate the staging file.

    Called by the batch pipeline AFTER successful ingestion.

    Args:
        staging_path: Path to the staging JSONL file.

    Returns:
        Number of records that were in the file before clearing.
    """
    path = Path(staging_path)
    if not path.exists():
        return 0

    # Count records first
    count = len(read_staging(staging_path))

    # Truncate the file
    try:
        with open(path, "w") as f:
            pass  # Truncate to empty
    except OSError as e:
        logger.warning("Failed to clear staging file %s: %s", staging_path, e)

    return count
