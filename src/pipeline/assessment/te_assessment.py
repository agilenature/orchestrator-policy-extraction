"""Assessment-specific TE computation (3-metric formula) (Phase 17, Plan 03).

Assessment TE uses a 3-metric formula without transport_speed:
    candidate_te = raven_depth * crow_efficiency * trunk_quality

This differs from production TE (4-metric) because assessment sessions
are too short for meaningful transport_speed measurement.

Exports:
    compute_assessment_te
    compute_candidate_ratio
    update_assessment_baselines
    write_assessment_te_row
"""

from __future__ import annotations

import hashlib
import logging
import statistics

import duckdb

logger = logging.getLogger(__name__)


def compute_assessment_te(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> dict | None:
    """Compute 3-metric assessment TE (no transport_speed).

    Assessment TE = raven_depth * crow_efficiency * trunk_quality

    - raven_depth: MAX(marker_level) / 7.0 for human flame_events
    - crow_efficiency: count(axis_identified IS NOT NULL) / count(*) for human events
    - trunk_quality: 0.5 (placeholder until confirmed by review)

    Args:
        conn: DuckDB connection with flame_events table.
        session_id: Assessment session ID.

    Returns:
        Dict with raven_depth, crow_efficiency, trunk_quality, candidate_te.
        None if no flame_events for session.
    """
    row = conn.execute(
        """
        SELECT
            MAX(marker_level) AS max_level,
            COUNT(*) AS total,
            SUM(CASE WHEN axis_identified IS NOT NULL THEN 1 ELSE 0 END) AS axis_count
        FROM flame_events
        WHERE session_id = ?
          AND subject = 'human'
        """,
        [session_id],
    ).fetchone()

    if row is None or row[1] == 0:
        return None

    max_level, total, axis_count = row

    raven_depth = (max_level or 0) / 7.0
    crow_efficiency = axis_count / total if total > 0 else 0.0
    trunk_quality = 0.5  # Placeholder until confirmed

    candidate_te = raven_depth * crow_efficiency * trunk_quality

    return {
        "raven_depth": round(raven_depth, 4),
        "crow_efficiency": round(crow_efficiency, 4),
        "trunk_quality": round(trunk_quality, 4),
        "candidate_te": round(candidate_te, 4),
    }


def compute_candidate_ratio(
    candidate_te: float, scenario_baseline_te: float
) -> float | None:
    """Compute candidate TE ratio against scenario baseline.

    Args:
        candidate_te: Candidate's assessment TE score.
        scenario_baseline_te: Baseline TE for the scenario.

    Returns:
        candidate_te / scenario_baseline_te, or None if baseline is 0 or None.
    """
    if not scenario_baseline_te or scenario_baseline_te == 0:
        return None
    return candidate_te / scenario_baseline_te


def update_assessment_baselines(
    conn: duckdb.DuckDBPyConnection, scenario_id: str
) -> None:
    """Update running mean/stddev for a scenario's assessment baselines.

    Queries all candidate_ratios for the scenario from assessment_te_sessions,
    computes mean and stddev in Python, then upserts to assessment_baselines.

    Args:
        conn: DuckDB connection with assessment_te_sessions and assessment_baselines.
        scenario_id: Scenario to update baselines for.
    """
    rows = conn.execute(
        "SELECT candidate_ratio FROM assessment_te_sessions "
        "WHERE scenario_id = ? AND candidate_ratio IS NOT NULL",
        [scenario_id],
    ).fetchall()

    ratios = [r[0] for r in rows]
    n = len(ratios)

    if n == 0:
        return

    mean_ratio = statistics.mean(ratios)
    stddev_ratio = statistics.stdev(ratios) if n >= 2 else 0.0

    # Upsert: DELETE + INSERT (DuckDB doesn't support INSERT OR REPLACE on all versions)
    conn.execute(
        "DELETE FROM assessment_baselines WHERE scenario_id = ?",
        [scenario_id],
    )
    conn.execute(
        "INSERT INTO assessment_baselines "
        "(scenario_id, n_assessments, mean_ratio, stddev_ratio, last_updated) "
        "VALUES (?, ?, ?, ?, NOW())",
        [scenario_id, n, mean_ratio, stddev_ratio],
    )

    logger.info(
        "Updated baselines for scenario %s: n=%d, mean=%.4f, stddev=%.4f",
        scenario_id,
        n,
        mean_ratio,
        stddev_ratio,
    )


def write_assessment_te_row(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    scenario_id: str,
    candidate_id: str,
    candidate_te: float | None,
    scenario_baseline_te: float | None,
    raven_depth: float | None,
    crow_efficiency: float | None,
    trunk_quality: float | None,
    fringe_drift_rate: float | None,
    scenario_ddf_level: int | None,
    session_artifact_path: str | None = None,
) -> str:
    """Write a row to assessment_te_sessions. Returns te_id.

    te_id is SHA-256[:16] of f"{session_id}:{candidate_id}".

    Args:
        conn: DuckDB connection with assessment_te_sessions table.
        session_id: Assessment session ID.
        scenario_id: Scenario ID.
        candidate_id: Candidate ID.
        candidate_te: Computed assessment TE score.
        scenario_baseline_te: Baseline TE for the scenario.
        raven_depth: Raven depth metric.
        crow_efficiency: Crow efficiency metric.
        trunk_quality: Trunk quality metric.
        fringe_drift_rate: Fringe drift rate.
        scenario_ddf_level: Target DDF level for the scenario.
        session_artifact_path: Path to archived session artifact.

    Returns:
        te_id (16-char hex string).
    """
    te_id = hashlib.sha256(
        f"{session_id}:{candidate_id}".encode()
    ).hexdigest()[:16]

    # Compute candidate_ratio
    candidate_ratio = compute_candidate_ratio(
        candidate_te, scenario_baseline_te
    ) if candidate_te is not None and scenario_baseline_te is not None else None

    # Upsert: DELETE + INSERT for idempotency
    conn.execute(
        "DELETE FROM assessment_te_sessions WHERE te_id = ?",
        [te_id],
    )
    conn.execute(
        "INSERT INTO assessment_te_sessions "
        "(te_id, session_id, scenario_id, candidate_id, candidate_te, "
        "scenario_baseline_te, candidate_ratio, raven_depth, crow_efficiency, "
        "trunk_quality, fringe_drift_rate, scenario_ddf_level, "
        "session_artifact_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            te_id,
            session_id,
            scenario_id,
            candidate_id,
            candidate_te,
            scenario_baseline_te,
            candidate_ratio,
            raven_depth,
            crow_efficiency,
            trunk_quality,
            fringe_drift_rate,
            scenario_ddf_level,
            session_artifact_path,
        ],
    )

    logger.info(
        "Wrote assessment TE row: te_id=%s, session=%s, candidate=%s, te=%.4f",
        te_id,
        session_id,
        candidate_id,
        candidate_te or 0.0,
    )

    return te_id
