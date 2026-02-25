"""Structural integrity score computation (Phase 18, Plan 02).

Reads from the structural_events table (populated by writer.py after
detector pass) and computes the weighted StructuralIntegrityResult.

Formula (locked):
    score = 0.30*gravity_ratio + 0.40*main_cable_ratio
          + 0.20*dependency_ratio + 0.10*spiral_capped

Neutral fallback (0.5) applied when a signal type has zero events
(denominator=0) for gravity, main_cable, dependency ratios.
Spiral is different: 0 spirals = 0.0 (no bonus, no penalty).

Exports:
    compute_structural_integrity
"""

from __future__ import annotations

from typing import Optional

import duckdb

from src.pipeline.ddf.structural.models import StructuralIntegrityResult
from src.pipeline.models.config import DDFConfig


def compute_structural_integrity(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    subject: str,
    assessment_session_id: Optional[str] = None,
) -> StructuralIntegrityResult:
    """Compute structural integrity score from structural_events.

    Reads structural_events for the given session+subject, groups by
    signal_type and signal_passed, then applies the locked formula.

    Args:
        conn: DuckDB connection with structural_events table populated.
        session_id: Session to compute score for.
        subject: 'human' or 'ai'.
        assessment_session_id: If None, filter to production events only.

    Returns:
        StructuralIntegrityResult with computed ratios and score.
    """
    config = DDFConfig().structural

    # Build assessment filter
    if assessment_session_id is None:
        assess_clause = "AND assessment_session_id IS NULL"
        assess_params: list = []
    else:
        assess_clause = "AND assessment_session_id = ?"
        assess_params = [assessment_session_id]

    # Query structural_events grouped by signal_type and signal_passed
    rows = conn.execute(
        f"""
        SELECT signal_type, signal_passed, COUNT(*) AS cnt
        FROM structural_events
        WHERE session_id = ? AND subject = ?
          {assess_clause}
        GROUP BY signal_type, signal_passed
        """,
        [session_id, subject] + assess_params,
    ).fetchall()

    # Accumulate counts per signal type
    counts: dict[str, dict[str, int]] = {
        "gravity_check": {"passed": 0, "total": 0},
        "main_cable": {"passed": 0, "total": 0},
        "dependency_sequencing": {"passed": 0, "total": 0},
        "spiral_reinforcement": {"passed": 0, "total": 0},
    }

    total_event_count = 0

    for signal_type, signal_passed, cnt in rows:
        if signal_type in counts:
            counts[signal_type]["total"] += cnt
            if signal_passed:
                counts[signal_type]["passed"] += cnt
            total_event_count += cnt

    # Compute ratios with neutral fallback for empty denominators
    def _ratio(signal_type: str) -> float:
        total = counts[signal_type]["total"]
        if total == 0:
            return config.neutral_fallback
        return counts[signal_type]["passed"] / total

    gravity_ratio = _ratio("gravity_check")
    main_cable_ratio = _ratio("main_cable")
    dependency_ratio = _ratio("dependency_sequencing")

    # Spiral: count of passed events, capped at 3, divided by 3
    # 0 spirals = 0.0 (no bonus, not penalized)
    spiral_count = counts["spiral_reinforcement"]["passed"]
    spiral_capped = min(spiral_count, 3) / 3.0

    # Apply locked formula
    integrity_score = (
        config.gravity_weight * gravity_ratio
        + config.main_cable_weight * main_cable_ratio
        + config.dependency_weight * dependency_ratio
        + config.spiral_weight * spiral_capped
    )

    return StructuralIntegrityResult(
        session_id=session_id,
        subject=subject,
        integrity_score=round(integrity_score, 4),
        gravity_ratio=round(gravity_ratio, 4),
        main_cable_ratio=round(main_cable_ratio, 4),
        dependency_ratio=round(dependency_ratio, 4),
        spiral_capped=round(spiral_capped, 4),
        structural_event_count=total_event_count,
    )
