"""Structural integrity signal detectors (Phase 18, Plan 02).

Four second-pass detectors that operate READ-ONLY on existing DuckDB
tables (flame_events, axis_edges, project_wisdom) and produce lists
of StructuralEvent objects. They do NOT write to structural_events --
that is writer.py's responsibility.

Signal types:
- gravity_check: L5+ event grounded by L0-L2 event with same axis
- main_cable: L5+ event connected via axis_edges topology
- dependency_sequencing: new axis respects prerequisite ordering
- spiral_reinforcement: cross-reference to project_wisdom promotions

Exports:
    detect_gravity_checks
    detect_main_cables
    detect_dependency_sequencing
    detect_spiral_reinforcement
    detect_structural_signals
"""

from __future__ import annotations

from typing import Optional

import duckdb

from src.pipeline.ddf.structural.models import StructuralEvent
from src.pipeline.models.config import DDFConfig


def detect_gravity_checks(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    assessment_session_id: Optional[str] = None,
) -> list[StructuralEvent]:
    """Detect whether L5+ flame events have L0-L2 grounding within a window.

    For each L5+ flame_event in this session, checks for L0-L2 events
    with the same axis (via COALESCE(ccd_axis, axis_identified)) within
    plus/minus gravity_window prompts.

    Args:
        conn: DuckDB connection with flame_events table.
        session_id: Session to analyse.
        assessment_session_id: If None, filter to production events only.

    Returns:
        List of StructuralEvent objects (one per L5+ event).
    """
    config = DDFConfig().structural

    # Build assessment filter clause
    if assessment_session_id is None:
        assess_clause = "AND f.assessment_session_id IS NULL"
        assess_params: list = []
    else:
        assess_clause = "AND f.assessment_session_id = ?"
        assess_params = [assessment_session_id]

    # Find all L5+ events
    high_events = conn.execute(
        f"""
        SELECT f.flame_event_id, f.session_id, f.prompt_number,
               f.marker_level, f.subject,
               COALESCE(f.ccd_axis, f.axis_identified) AS axis,
               f.flood_confirmed
        FROM flame_events f
        WHERE f.session_id = ? AND f.marker_level >= 5
          {assess_clause}
        ORDER BY f.prompt_number
        """,
        [session_id] + assess_params,
    ).fetchall()

    if not high_events:
        return []

    events: list[StructuralEvent] = []

    for i, row in enumerate(high_events):
        fe_id, _, prompt_num, marker_level, subject, axis, flood_confirmed = row

        if prompt_num is None:
            prompt_num = 0

        contributing_ids = [fe_id]
        grounding_found = False

        if axis:
            # Check for L0-L2 events with same axis within window
            grounding_rows = conn.execute(
                f"""
                SELECT flame_event_id FROM flame_events
                WHERE session_id = ?
                  AND COALESCE(ccd_axis, axis_identified) = ?
                  AND marker_level BETWEEN 0 AND 2
                  AND ABS(prompt_number - ?) <= ?
                  {assess_clause}
                """,
                [session_id, axis, prompt_num, config.gravity_window] + assess_params,
            ).fetchall()

            if grounding_rows:
                grounding_found = True
                for (gid,) in grounding_rows:
                    contributing_ids.append(gid)

        signal_suffix = f"gravity_check_{i}" if i > 0 else "gravity_check"
        event_id = StructuralEvent.make_id(session_id, prompt_num, signal_suffix)

        events.append(
            StructuralEvent(
                event_id=event_id,
                session_id=session_id,
                assessment_session_id=assessment_session_id,
                prompt_number=prompt_num,
                subject=subject,
                signal_type="gravity_check",
                structural_role="grounding",
                evidence=f"L{marker_level} event at prompt {prompt_num}: {axis or 'no-axis'}",
                signal_passed=grounding_found,
                contributing_flame_event_ids=contributing_ids,
                op8_status="na",
            )
        )

    return events


def detect_main_cables(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    assessment_session_id: Optional[str] = None,
) -> list[StructuralEvent]:
    """Detect whether L5+ flame events are structurally connected (Main Cables).

    A Main Cable is a L5+ flame_event whose axis appears in axis_edges
    (has known topological connections). Without generalization_radius
    on flame_events, we check axis_edges presence only.

    Args:
        conn: DuckDB connection with flame_events and axis_edges tables.
        session_id: Session to analyse.
        assessment_session_id: If None, filter to production events only.

    Returns:
        List of StructuralEvent objects (one per L5+ event).
    """
    # Build assessment filter clause
    if assessment_session_id is None:
        assess_clause = "AND f.assessment_session_id IS NULL"
        assess_params: list = []
    else:
        assess_clause = "AND f.assessment_session_id = ?"
        assess_params = [assessment_session_id]

    # Find all L5+ events
    high_events = conn.execute(
        f"""
        SELECT f.flame_event_id, f.session_id, f.prompt_number,
               f.marker_level, f.subject,
               COALESCE(f.ccd_axis, f.axis_identified) AS axis,
               f.flood_confirmed
        FROM flame_events f
        WHERE f.session_id = ? AND f.marker_level >= 5
          {assess_clause}
        ORDER BY f.prompt_number
        """,
        [session_id] + assess_params,
    ).fetchall()

    if not high_events:
        return []

    # Check if axis_edges table exists
    try:
        conn.execute("SELECT 1 FROM axis_edges LIMIT 0")
        has_axis_edges = True
    except Exception:
        has_axis_edges = False

    events: list[StructuralEvent] = []

    for i, row in enumerate(high_events):
        fe_id, _, prompt_num, marker_level, subject, axis, flood_confirmed = row

        if prompt_num is None:
            prompt_num = 0

        in_axis_edges = False

        if axis and has_axis_edges:
            edge_count = conn.execute(
                "SELECT COUNT(*) FROM axis_edges WHERE axis_a = ? OR axis_b = ?",
                [axis, axis],
            ).fetchone()[0]
            in_axis_edges = edge_count > 0

        signal_passed = in_axis_edges

        signal_suffix = f"main_cable_{i}" if i > 0 else "main_cable"
        event_id = StructuralEvent.make_id(session_id, prompt_num, signal_suffix)

        events.append(
            StructuralEvent(
                event_id=event_id,
                session_id=session_id,
                assessment_session_id=assessment_session_id,
                prompt_number=prompt_num,
                subject=subject,
                signal_type="main_cable",
                structural_role="load_bearing",
                evidence=f"L{marker_level} axis={axis or 'no-axis'} edges={'yes' if in_axis_edges else 'no'}",
                signal_passed=signal_passed,
                contributing_flame_event_ids=[fe_id],
                op8_status="na",
            )
        )

    return events


def detect_dependency_sequencing(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    assessment_session_id: Optional[str] = None,
) -> list[StructuralEvent]:
    """Check whether new axis introductions respect prerequisite ordering.

    For each L5+ event introducing a new CCD axis (first appearance at
    L5+ in this session), checks axis_edges for prerequisite axes. If a
    prerequisite has NOT appeared at L3+ yet, signal_passed=False.

    Args:
        conn: DuckDB connection with flame_events and axis_edges tables.
        session_id: Session to analyse.
        assessment_session_id: If None, filter to production events only.

    Returns:
        List of StructuralEvent objects (one per new axis introduction).
    """
    # Build assessment filter clause
    if assessment_session_id is None:
        assess_clause = "AND f.assessment_session_id IS NULL"
        assess_params: list = []
    else:
        assess_clause = "AND f.assessment_session_id = ?"
        assess_params = [assessment_session_id]

    # Find all L5+ events ordered by prompt_number
    high_events = conn.execute(
        f"""
        SELECT f.flame_event_id, f.prompt_number, f.marker_level,
               f.subject,
               COALESCE(f.ccd_axis, f.axis_identified) AS axis
        FROM flame_events f
        WHERE f.session_id = ? AND f.marker_level >= 5
          {assess_clause}
        ORDER BY f.prompt_number
        """,
        [session_id] + assess_params,
    ).fetchall()

    if not high_events:
        return []

    # Check if axis_edges table exists
    try:
        conn.execute("SELECT 1 FROM axis_edges LIMIT 0")
        has_axis_edges = True
    except Exception:
        has_axis_edges = False

    # Track which axes have been introduced at L5+ and which at L3+
    seen_axes_l5: set[str] = set()
    events: list[StructuralEvent] = []
    counter = 0

    for row in high_events:
        fe_id, prompt_num, marker_level, subject, axis = row

        if not axis:
            continue
        if prompt_num is None:
            prompt_num = 0

        # Skip if already seen this axis at L5+
        if axis in seen_axes_l5:
            continue
        seen_axes_l5.add(axis)

        # Check prerequisites from axis_edges
        signal_passed = True
        prerequisite_info = ""

        if has_axis_edges:
            edges = conn.execute(
                """
                SELECT axis_a, axis_b FROM axis_edges
                WHERE axis_a = ? OR axis_b = ?
                """,
                [axis, axis],
            ).fetchall()

            for edge_a, edge_b in edges:
                # The partner axis is the prerequisite
                partner = edge_b if edge_a == axis else edge_a

                # Check if partner has appeared at L3+ before this prompt
                prior_appearance = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM flame_events
                    WHERE session_id = ?
                      AND COALESCE(ccd_axis, axis_identified) = ?
                      AND marker_level >= 3
                      AND prompt_number < ?
                      {assess_clause}
                    """,
                    [session_id, partner, prompt_num] + assess_params,
                ).fetchone()[0]

                if prior_appearance == 0:
                    signal_passed = False
                    prerequisite_info = f" missing prerequisite: {partner}"
                    break

        signal_suffix = f"dependency_sequencing_{counter}" if counter > 0 else "dependency_sequencing"
        event_id = StructuralEvent.make_id(session_id, prompt_num, signal_suffix)
        counter += 1

        events.append(
            StructuralEvent(
                event_id=event_id,
                session_id=session_id,
                assessment_session_id=assessment_session_id,
                prompt_number=prompt_num,
                subject=subject,
                signal_type="dependency_sequencing",
                structural_role="hierarchical",
                evidence=f"New axis {axis} at L{marker_level} prompt {prompt_num}{prerequisite_info}",
                signal_passed=signal_passed,
                contributing_flame_event_ids=[fe_id],
                op8_status="na",
            )
        )

    return events


def detect_spiral_reinforcement(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    assessment_session_id: Optional[str] = None,
) -> list[StructuralEvent]:
    """Cross-reference project_wisdom spiral promotions for this session.

    Finds wisdom entries whose metadata references this session_id,
    producing one signal_passed=True event per matching wisdom entry.
    Returns empty list if no matches (no spiral events to record).

    Args:
        conn: DuckDB connection with project_wisdom table.
        session_id: Session to check for spiral promotions.
        assessment_session_id: Unused (spiral detection is session-level).

    Returns:
        List of StructuralEvent objects (one per wisdom promotion).
    """
    # Check if project_wisdom table exists
    try:
        conn.execute("SELECT 1 FROM project_wisdom LIMIT 0")
    except Exception:
        return []

    # project_wisdom stores session references in metadata JSON
    # Search for session_id in metadata
    rows = conn.execute(
        """
        SELECT wisdom_id, title, entity_type
        FROM project_wisdom
        WHERE metadata::VARCHAR LIKE '%' || ? || '%'
        """,
        [session_id],
    ).fetchall()

    if not rows:
        return []

    events: list[StructuralEvent] = []

    for i, (wisdom_id, title, entity_type) in enumerate(rows):
        signal_suffix = f"spiral_reinforcement_{i}" if i > 0 else "spiral_reinforcement"
        event_id = StructuralEvent.make_id(session_id, 0, signal_suffix)

        events.append(
            StructuralEvent(
                event_id=event_id,
                session_id=session_id,
                assessment_session_id=assessment_session_id,
                prompt_number=0,
                subject="human",  # Spiral promotions originate from human activity
                signal_type="spiral_reinforcement",
                structural_role="reinforcing",
                evidence=f"Wisdom promotion: {title} ({entity_type})",
                signal_passed=True,
                contributing_flame_event_ids=[wisdom_id],
                op8_status="na",
            )
        )

    return events


def detect_structural_signals(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    assessment_session_id: Optional[str] = None,
) -> list[StructuralEvent]:
    """Orchestrator: run all four structural detectors and return combined results.

    Args:
        conn: DuckDB connection with flame_events, axis_edges, project_wisdom.
        session_id: Session to analyse.
        assessment_session_id: If None, filter to production events only.

    Returns:
        Combined list of StructuralEvent objects from all four detectors.
    """
    events: list[StructuralEvent] = []
    events.extend(detect_gravity_checks(conn, session_id, assessment_session_id))
    events.extend(detect_main_cables(conn, session_id, assessment_session_id))
    events.extend(detect_dependency_sequencing(conn, session_id, assessment_session_id))
    events.extend(detect_spiral_reinforcement(conn, session_id, assessment_session_id))
    return events
