"""DuckDB writer for flame_events table.

Writes FlameEvent Pydantic models to the DuckDB flame_events table
using INSERT OR REPLACE for idempotent writes.

Exports:
    write_flame_events
"""

from __future__ import annotations

import duckdb

from src.pipeline.ddf.models import FlameEvent


def write_flame_events(
    conn: duckdb.DuckDBPyConnection,
    events: list[FlameEvent],
) -> dict[str, int]:
    """Write FlameEvent records to DuckDB flame_events table.

    Uses INSERT OR REPLACE for idempotent writes -- re-inserting an
    event with the same flame_event_id overwrites the existing row.

    Args:
        conn: DuckDB connection with flame_events table created.
        events: List of FlameEvent Pydantic models to write.

    Returns:
        Dict with 'written' key indicating number of events processed.
    """
    if not events:
        return {"written": 0}

    rows = []
    for e in events:
        rows.append((
            e.flame_event_id,
            e.session_id,
            e.human_id,
            e.prompt_number,
            e.marker_level,
            e.marker_type,
            e.evidence_excerpt,
            e.quality_score,
            e.axis_identified,
            e.flood_confirmed,
            e.subject,
            e.detection_source,
            e.deposited_to_candidates,
            e.source_episode_id,
            e.session_event_ref,
            e.created_at.isoformat() if e.created_at else None,
        ))

    conn.executemany(
        """
        INSERT OR REPLACE INTO flame_events (
            flame_event_id, session_id, human_id, prompt_number,
            marker_level, marker_type, evidence_excerpt, quality_score,
            axis_identified, flood_confirmed, subject, detection_source,
            deposited_to_candidates, source_episode_id, session_event_ref,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    return {"written": len(events)}
