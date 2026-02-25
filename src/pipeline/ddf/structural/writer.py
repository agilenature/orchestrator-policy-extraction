"""DuckDB writer for structural_events table.

Writes StructuralEvent Pydantic models to the DuckDB structural_events
table using INSERT OR REPLACE for idempotent writes.

Exports:
    write_structural_events
"""

from __future__ import annotations

import duckdb

from src.pipeline.ddf.structural.models import StructuralEvent


def write_structural_events(
    conn: duckdb.DuckDBPyConnection,
    events: list[StructuralEvent],
) -> int:
    """Write StructuralEvent records to DuckDB structural_events table.

    Uses INSERT OR REPLACE for idempotent writes -- re-inserting an
    event with the same event_id overwrites the existing row.

    Args:
        conn: DuckDB connection with structural_events table created.
        events: List of StructuralEvent Pydantic models to write.

    Returns:
        Number of events written.
    """
    if not events:
        return 0

    for e in events:
        conn.execute(
            """
            INSERT OR REPLACE INTO structural_events (
                event_id, session_id, assessment_session_id, prompt_number,
                subject, signal_type, structural_role, evidence,
                signal_passed, score_contribution,
                contributing_flame_event_ids,
                op8_status, op8_correction_candidate_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                e.event_id,
                e.session_id,
                e.assessment_session_id,
                e.prompt_number,
                e.subject,
                e.signal_type,
                e.structural_role,
                e.evidence,
                e.signal_passed,
                e.score_contribution,
                e.contributing_flame_event_ids,
                e.op8_status,
                e.op8_correction_candidate_id,
                e.created_at.isoformat() if e.created_at else None,
            ],
        )

    return len(events)
