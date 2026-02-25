"""Op-8 correction depositor for floating cables (Phase 18, Plan 02).

Reads structural_events for AI Main Cable failures (signal_passed=False)
and deposits one correction per floating axis per session to
memory_candidates with source_type='op8_correction'.

Uses SHA-256 dedup ID to prevent duplicate deposits on re-run.

Exports:
    deposit_op8_corrections
"""

from __future__ import annotations

import hashlib
from typing import Optional

import duckdb


def deposit_op8_corrections(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    assessment_session_id: Optional[str] = None,
) -> int:
    """Deposit Op-8 corrections for AI floating cables.

    Reads structural_events for AI main_cable failures (signal_passed=False),
    then inserts one memory_candidates entry per unique floating axis.

    Dedup: id = sha256("op8:{session_id}:{axis}")[:16] ensures idempotent
    re-runs produce the same candidate IDs.

    Args:
        conn: DuckDB connection with structural_events and memory_candidates.
        session_id: Session to deposit corrections for.
        assessment_session_id: If None, filter to production events only.

    Returns:
        Count of corrections deposited.
    """
    # Build assessment filter
    if assessment_session_id is None:
        assess_clause = "AND se.assessment_session_id IS NULL"
        assess_params: list = []
    else:
        assess_clause = "AND se.assessment_session_id = ?"
        assess_params = [assessment_session_id]

    # Find AI Main Cable failures with axis from contributing flame_events
    rows = conn.execute(
        f"""
        SELECT se.event_id, se.evidence, se.contributing_flame_event_ids
        FROM structural_events se
        WHERE se.session_id = ?
          AND se.signal_type = 'main_cable'
          AND se.signal_passed = false
          AND se.subject = 'ai'
          {assess_clause}
        """,
        [session_id] + assess_params,
    ).fetchall()

    if not rows:
        return 0

    deposited = 0
    seen_axes: set[str] = set()

    for se_event_id, evidence, contributing_ids in rows:
        # Extract axis from contributing flame_event
        axis = None
        if contributing_ids and len(contributing_ids) > 0:
            fe_id = contributing_ids[0]
            axis_row = conn.execute(
                """
                SELECT COALESCE(ccd_axis, axis_identified) AS axis
                FROM flame_events
                WHERE flame_event_id = ?
                """,
                [fe_id],
            ).fetchone()
            if axis_row:
                axis = axis_row[0]

        if not axis or axis in seen_axes:
            continue
        seen_axes.add(axis)

        # SHA-256 dedup ID
        candidate_id = hashlib.sha256(
            f"op8:{session_id}:{axis}".encode()
        ).hexdigest()[:16]

        # Deposit to memory_candidates
        conn.execute(
            """
            INSERT OR REPLACE INTO memory_candidates
            (id, ccd_axis, scope_rule, flood_example, status, source_type,
             fidelity, confidence, session_id, source_flame_event_id, created_at)
            VALUES (?, ?, ?, ?, 'pending', 'op8_correction', 2, 0.60, ?, ?, NOW())
            """,
            [
                candidate_id,
                axis,
                "This axis appeared in AI reasoning without concrete grounding -- apply gravity check before asserting.",
                f"AI floating cable detected at session {session_id}",
                session_id,
                se_event_id,
            ],
        )
        deposited += 1

    return deposited
