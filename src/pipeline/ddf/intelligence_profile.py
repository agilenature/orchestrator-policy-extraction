"""IntelligenceProfile aggregation from flame_events (DDF-04).

Computes per-human and per-AI aggregate metrics from the flame_events
table. The IntelligenceProfile is the measurement surface that makes the
DDF observable -- it aggregates flame_events into meaningful metrics for
display in the CLI (Plan 06).

Phase 18 extension: integrity_score and structural_event_count from
structural_events, completing the three-dimensional profile:
Ignition (flame metrics) x Transport (TE) x Integrity (structural score).

Exports:
    compute_intelligence_profile
    compute_ai_profile
    compute_spiral_depth_for_human
    compute_structural_integrity_for_profile
    list_available_humans
"""

from __future__ import annotations

from typing import Optional

import duckdb

from src.pipeline.ddf.models import IntelligenceProfile


def compute_spiral_depth_for_human(
    conn: duckdb.DuckDBPyConnection, human_id: str
) -> int:
    """Compute spiral depth as longest ascending marker_level streak.

    Fetches all flame_events for the given human_id ordered by
    session_id and created_at, then iterates through each session
    tracking the longest ascending streak of marker_levels.

    Spiral depth = number of ascending transitions in the longest
    streak. E.g., L1->L2->L3->L4 = 3 transitions = depth 3.

    Args:
        conn: DuckDB connection with flame_events table.
        human_id: Human identifier to compute spiral depth for.

    Returns:
        Max ascending transition count across all sessions. 0 if no
        ascending transitions found or no data exists.
    """
    rows = conn.execute(
        """
        SELECT session_id, marker_level
        FROM flame_events
        WHERE subject = 'human'
          AND human_id = ?
          AND (assessment_session_id IS NULL)
        ORDER BY session_id, created_at
        """,
        [human_id],
    ).fetchall()

    if not rows:
        return 0

    max_depth = 0
    current_streak = 0
    prev_level: int | None = None
    prev_session: str | None = None

    for session_id, marker_level in rows:
        if session_id != prev_session:
            # New session: reset streak
            current_streak = 0
            prev_level = marker_level
            prev_session = session_id
            continue

        if marker_level > prev_level:
            current_streak += 1
            if current_streak > max_depth:
                max_depth = current_streak
        else:
            current_streak = 0

        prev_level = marker_level

    return max_depth


def _compute_ai_spiral_depth(conn: duckdb.DuckDBPyConnection) -> int:
    """Compute spiral depth for AI subject.

    Same algorithm as compute_spiral_depth_for_human but filters
    on subject='ai' instead of human_id.

    Args:
        conn: DuckDB connection with flame_events table.

    Returns:
        Max ascending transition count across all sessions for AI.
    """
    rows = conn.execute(
        """
        SELECT session_id, marker_level
        FROM flame_events
        WHERE subject = 'ai'
          AND (assessment_session_id IS NULL)
        ORDER BY session_id, created_at
        """
    ).fetchall()

    if not rows:
        return 0

    max_depth = 0
    current_streak = 0
    prev_level: int | None = None
    prev_session: str | None = None

    for session_id, marker_level in rows:
        if session_id != prev_session:
            current_streak = 0
            prev_level = marker_level
            prev_session = session_id
            continue

        if marker_level > prev_level:
            current_streak += 1
            if current_streak > max_depth:
                max_depth = current_streak
        else:
            current_streak = 0

        prev_level = marker_level

    return max_depth


def compute_structural_integrity_for_profile(
    conn: duckdb.DuckDBPyConnection,
    subject: str,
    human_id: Optional[str] = None,
) -> tuple[Optional[float], int]:
    """Compute aggregate structural integrity for a subject's profile.

    Queries structural_events for production sessions (assessment_session_id
    IS NULL) belonging to the given subject, then delegates to
    compute_structural_integrity per-session and averages.

    Falls back gracefully when the structural_events table does not exist
    (older DBs without Phase 18 schema).

    Args:
        conn: DuckDB connection with structural_events table (optional).
        subject: 'human' or 'ai'.
        human_id: Human identifier (used to find sessions). Ignored for AI.

    Returns:
        Tuple of (avg_integrity_score, total_structural_event_count).
        Returns (None, 0) when no structural data exists.
    """
    try:
        from src.pipeline.ddf.structural.computer import compute_structural_integrity

        # Find distinct sessions for this subject from structural_events
        if subject == "ai":
            session_rows = conn.execute(
                """
                SELECT DISTINCT session_id
                FROM structural_events
                WHERE subject = 'ai'
                  AND assessment_session_id IS NULL
                """,
            ).fetchall()
        else:
            # Join through flame_events to find sessions for this human_id
            session_rows = conn.execute(
                """
                SELECT DISTINCT se.session_id
                FROM structural_events se
                WHERE se.subject = 'human'
                  AND se.assessment_session_id IS NULL
                  AND se.session_id IN (
                      SELECT DISTINCT session_id
                      FROM flame_events
                      WHERE human_id = ?
                        AND subject = 'human'
                        AND assessment_session_id IS NULL
                  )
                """,
                [human_id],
            ).fetchall()

        if not session_rows:
            return None, 0

        total_score = 0.0
        total_events = 0
        session_count = 0

        for (sid,) in session_rows:
            result = compute_structural_integrity(conn, sid, subject)
            if result.structural_event_count > 0:
                total_score += result.integrity_score
                total_events += result.structural_event_count
                session_count += 1

        if session_count == 0:
            return None, 0

        avg_score = round(total_score / session_count, 4)
        return avg_score, total_events

    except Exception:
        # structural_events table may not exist in older DBs
        return None, 0


def compute_intelligence_profile(
    conn: duckdb.DuckDBPyConnection, human_id: str
) -> IntelligenceProfile | None:
    """Compute IntelligenceProfile for a human subject.

    Aggregates flame_events WHERE subject='human' AND human_id=?
    into frequency, level averages, flood rate, and session count.
    Spiral depth is computed via Python-side iteration.

    Args:
        conn: DuckDB connection with flame_events table.
        human_id: Human identifier to compute profile for.

    Returns:
        IntelligenceProfile with subject='human', or None if no
        flame_events exist for this human_id.
    """
    row = conn.execute(
        """
        SELECT
            human_id,
            COUNT(*) AS flame_frequency,
            AVG(marker_level) AS avg_marker_level,
            MAX(marker_level) AS max_marker_level,
            CAST(
                SUM(CASE WHEN marker_level >= 6 THEN 1 ELSE 0 END) AS FLOAT
            ) / NULLIF(COUNT(*), 0) AS flood_rate,
            COUNT(DISTINCT session_id) AS session_count
        FROM flame_events
        WHERE subject = 'human'
          AND human_id = ?
          AND (assessment_session_id IS NULL)
        GROUP BY human_id
        """,
        [human_id],
    ).fetchone()

    if row is None:
        return None

    spiral_depth = compute_spiral_depth_for_human(conn, human_id)

    # Phase 18: structural integrity (three-dimensional profile)
    integrity_score, structural_count = compute_structural_integrity_for_profile(
        conn, subject="human", human_id=human_id,
    )

    return IntelligenceProfile(
        human_id=row[0],
        subject="human",
        flame_frequency=row[1],
        avg_marker_level=round(float(row[2]), 4),
        max_marker_level=row[3],
        spiral_depth=spiral_depth,
        flood_rate=round(float(row[4]), 4),
        session_count=row[5],
        integrity_score=integrity_score,
        structural_event_count=structural_count,
    )


def compute_ai_profile(
    conn: duckdb.DuckDBPyConnection,
) -> IntelligenceProfile | None:
    """Compute IntelligenceProfile for the AI subject.

    Same aggregation as compute_intelligence_profile but filters on
    subject='ai'. The returned profile has human_id='ai'.

    Args:
        conn: DuckDB connection with flame_events table.

    Returns:
        IntelligenceProfile with subject='ai' and human_id='ai',
        or None if no AI flame_events exist.
    """
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS flame_frequency,
            AVG(marker_level) AS avg_marker_level,
            MAX(marker_level) AS max_marker_level,
            CAST(
                SUM(CASE WHEN marker_level >= 6 THEN 1 ELSE 0 END) AS FLOAT
            ) / NULLIF(COUNT(*), 0) AS flood_rate,
            COUNT(DISTINCT session_id) AS session_count
        FROM flame_events
        WHERE subject = 'ai'
          AND (assessment_session_id IS NULL)
        """
    ).fetchone()

    if row is None or row[0] == 0:
        return None

    spiral_depth = _compute_ai_spiral_depth(conn)

    # Phase 18: structural integrity (three-dimensional profile)
    integrity_score, structural_count = compute_structural_integrity_for_profile(
        conn, subject="ai",
    )

    return IntelligenceProfile(
        human_id="ai",
        subject="ai",
        flame_frequency=row[0],
        avg_marker_level=round(float(row[1]), 4),
        max_marker_level=row[2],
        spiral_depth=spiral_depth,
        flood_rate=round(float(row[3]), 4),
        session_count=row[4],
        integrity_score=integrity_score,
        structural_event_count=structural_count,
    )


def list_available_humans(
    conn: duckdb.DuckDBPyConnection,
) -> list[str]:
    """List distinct human_ids from flame_events.

    Args:
        conn: DuckDB connection with flame_events table.

    Returns:
        Sorted list of distinct human_id values where subject='human'
        and human_id is not NULL.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT human_id
        FROM flame_events
        WHERE subject = 'human'
          AND human_id IS NOT NULL
          AND (assessment_session_id IS NULL)
        ORDER BY human_id
        """
    ).fetchall()

    return [row[0] for row in rows]
