"""GenusEdgeWriter for Genus-Check Gate (Phase 24).

Writes accepted genus declarations as:
- EdgeRecord to axis_edges table (relationship_text='genus_of', abstraction_level=3)
- FlameEvent to flame_events table (marker_type='genus_shift', subject='ai')

Both writes use the staging pattern (data/genus_staging.jsonl) to avoid
DuckDB single-writer conflicts with the batch pipeline. The PAG hook appends
to genus_staging.jsonl; runner.py's Step 11.6 calls ingest_genus_staging().

Exports:
    GenusEdgeWriter
    append_genus_staging
    ingest_genus_staging
"""

from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.topology.models import ActivationCondition, EdgeRecord
from src.pipeline.ddf.topology.writer import EdgeWriter
from src.pipeline.ddf.writer import write_flame_events

logger = logging.getLogger(__name__)

# Separate staging file from premise_staging.jsonl
GENUS_STAGING_PATH = "data/genus_staging.jsonl"


class GenusEdgeWriter:
    """Builds EdgeRecord and FlameEvent for accepted genus declarations.

    Does NOT write to DuckDB directly. Instead, the build_* methods
    produce Pydantic models that are serialized to genus_staging.jsonl
    by append_genus_staging(). The batch pipeline calls ingest_genus_staging()
    to write to ope.db.
    """

    def build_genus_edge(
        self,
        genus_name: str,
        premise_claim: str,
        session_id: str,
        instances: list[str] | None = None,
    ) -> EdgeRecord:
        """Build an EdgeRecord for a genus declaration.

        Args:
            genus_name: The genus name (becomes axis_a).
            premise_claim: The premise claim text (truncated to 100 chars for axis_b).
            session_id: Current session ID.
            instances: List of genus instance names (stored in evidence).

        Returns:
            EdgeRecord with relationship_text='genus_of', abstraction_level=3.
        """
        axis_b = premise_claim[:100] if premise_claim else ""
        edge_id = EdgeRecord.make_id(genus_name, axis_b, "genus_of")

        return EdgeRecord(
            edge_id=edge_id,
            axis_a=genus_name,
            axis_b=axis_b,
            relationship_text="genus_of",
            activation_condition=ActivationCondition(
                goal_type=["write_class"],
                scope_prefix="",
                min_axes_simultaneously_active=1,
            ),
            evidence={
                "instances": instances or [],
                "source": "genus_check_gate",
                "session_id": session_id,
            },
            abstraction_level=3,
            status="candidate",
            trunk_quality=1.0,
            created_session_id=session_id,
        )

    def build_genus_shift_event(
        self,
        genus_name: str,
        session_id: str,
        evidence_excerpt: str | None = None,
    ) -> FlameEvent:
        """Build a FlameEvent for a genus shift detection.

        Args:
            genus_name: The genus name (becomes axis_identified).
            session_id: Current session ID.
            evidence_excerpt: Optional evidence text (premise claim or genus name).

        Returns:
            FlameEvent with marker_type='genus_shift', subject='ai', marker_level=2.
        """
        flame_event_id = FlameEvent.make_id(
            session_id, None, f"genus_shift:{genus_name[:40]}"
        )

        return FlameEvent(
            flame_event_id=flame_event_id,
            session_id=session_id,
            marker_level=2,
            marker_type="genus_shift",
            subject="ai",
            detection_source="stub",
            axis_identified=genus_name,
            deposited_to_candidates=False,
            evidence_excerpt=evidence_excerpt or genus_name,
        )


def append_genus_staging(
    records: list[dict],
    staging_path: str = GENUS_STAGING_PATH,
) -> int:
    """Append genus staging records to the JSONL file.

    Creates the parent directory if needed. Uses file locking (fcntl.flock)
    for concurrent safety (same pattern as premise staging.py).

    Each record dict should contain: edge, flame_event, session_id, created_at.

    Args:
        records: List of genus staging record dicts.
        staging_path: Path to the genus staging JSONL file.

    Returns:
        Number of records written.
    """
    if not records:
        return 0

    path = Path(staging_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for record in records:
        try:
            lines.append(json.dumps(record, default=str) + "\n")
        except (TypeError, ValueError) as e:
            logger.warning("Failed to serialize genus staging record: %s", e)
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


def ingest_genus_staging(
    conn: duckdb.DuckDBPyConnection,
    staging_path: str = GENUS_STAGING_PATH,
) -> dict[str, int]:
    """Ingest staged genus records from JSONL into DuckDB.

    Steps:
      1. Read all staged records from genus_staging.jsonl.
      2. For each record, reconstruct EdgeRecord and FlameEvent from stored dicts.
      3. Write EdgeRecord via EdgeWriter.write_edge().
      4. Write FlameEvent via write_flame_events().
      5. Clear the staging file ONLY after successful writes.
      6. Return stats dict.

    Args:
        conn: DuckDB connection with axis_edges and flame_events tables.
        staging_path: Path to the genus staging JSONL file.

    Returns:
        Stats dict: {"edges_written": N, "events_written": M, "errors": E}
    """
    stats: dict[str, int] = {
        "edges_written": 0,
        "events_written": 0,
        "errors": 0,
    }

    path = Path(staging_path)
    if not path.exists():
        return stats

    # Read staging records
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
                    stats["errors"] += 1
    except OSError as e:
        logger.warning("Failed to read genus staging file %s: %s", staging_path, e)
        return stats

    if not records:
        return stats

    edge_writer = EdgeWriter(conn)

    for record in records:
        try:
            # Reconstruct EdgeRecord from stored dict
            edge_data = record["edge"]
            ac_data = edge_data.pop("activation_condition", {})
            edge_data.pop("created_at", None)  # Let Pydantic default handle it
            ac = ActivationCondition(**ac_data)
            edge = EdgeRecord(activation_condition=ac, **edge_data)
            edge_writer.write_edge(edge)
            stats["edges_written"] += 1

            # Reconstruct FlameEvent from stored dict
            fe_data = record["flame_event"]
            fe_data.pop("created_at", None)  # Let Pydantic default handle it
            flame_event = FlameEvent(**fe_data)
            write_flame_events(conn, [flame_event])
            stats["events_written"] += 1

        except Exception as e:
            logger.warning("Failed to ingest genus staging record: %s", e)
            stats["errors"] += 1

    # Clear staging file only after successful writes
    if stats["edges_written"] > 0 or stats["events_written"] > 0:
        try:
            with open(path, "w") as f:
                pass  # Truncate to empty
        except OSError as e:
            logger.warning(
                "Failed to clear genus staging file %s: %s", staging_path, e
            )

    return stats
