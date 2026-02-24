"""Outcome-gated L5-7 rejection detection (Phase 17, Plan 03).

Detects genuine Level 5+ rejections in assessment sessions by applying
an outcome gate: the candidate must have achieved TE above threshold
(0.9 * scenario_baseline_te) for a rejection to be classified as L5
rather than stubbornness.

Fringe-signal rejections bypass the outcome gate entirely -- a candidate
who rejects on a fringe signal (novel axis, not in existing taxonomy)
is classified as fringe_L5 regardless of TE.

Exports:
    RejectionDetector
    detect_rejections
"""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


class RejectionDetector:
    """Outcome-gated rejection detector for assessment sessions.

    Distinguishes genuine L5+ rejections from stubbornness by checking
    whether the candidate's TE exceeds the scenario baseline threshold.
    Fringe-signal rejections bypass the outcome gate.

    Args:
        conn: DuckDB connection with flame_events table.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def detect_rejections(
        self,
        session_id: str,
        scenario_baseline_te: float,
    ) -> list[dict]:
        """Detect rejection events in an assessment session.

        Queries flame_events for human events that indicate rejection
        (marker_level >= 5 with rejection indicators), then classifies
        each via the outcome gate.

        Args:
            session_id: Assessment session ID.
            scenario_baseline_te: Baseline TE for the scenario.

        Returns:
            List of rejection dicts with prompt_number, rejection_type,
            candidate_te, threshold, evidence.
        """
        # Query human flame_events at L5+ for this session
        rows = self._conn.execute(
            """
            SELECT
                prompt_number,
                marker_level,
                axis_identified,
                ccd_axis,
                differential
            FROM flame_events
            WHERE session_id = ?
              AND subject = 'human'
              AND marker_level >= 5
            ORDER BY prompt_number
            """,
            [session_id],
        ).fetchall()

        if not rows:
            return []

        # Compute candidate TE for outcome gate
        from src.pipeline.assessment.te_assessment import compute_assessment_te

        te_result = compute_assessment_te(self._conn, session_id)
        candidate_te = te_result["candidate_te"] if te_result else None

        threshold = scenario_baseline_te * 0.9

        rejections = []
        for prompt_number, marker_level, axis_identified, ccd_axis, differential in rows:
            # Check for fringe signal: axis identified but not in standard taxonomy
            is_fringe = self._is_fringe_signal(axis_identified, ccd_axis)

            rejection_type = self.classify_rejection(
                candidate_te, scenario_baseline_te, is_fringe
            )

            rejections.append({
                "prompt_number": prompt_number,
                "marker_level": marker_level,
                "rejection_type": rejection_type,
                "candidate_te": candidate_te,
                "threshold": threshold,
                "is_fringe": is_fringe,
                "axis_identified": axis_identified,
                "evidence": {
                    "ccd_axis": ccd_axis,
                    "differential": differential,
                },
            })

        logger.info(
            "Detected %d rejection events for session %s: %s",
            len(rejections),
            session_id,
            [r["rejection_type"] for r in rejections],
        )

        return rejections

    def classify_rejection(
        self,
        candidate_te: float | None,
        scenario_baseline_te: float,
        is_fringe: bool,
    ) -> str:
        """Classify a rejection as L5, fringe_L5, or stubbornness.

        Decision logic:
        1. Fringe signal -> fringe_L5 (bypass outcome gate)
        2. No TE data -> stubbornness (conservative)
        3. candidate_te > threshold -> L5 (outcome-gated)
        4. Otherwise -> stubbornness

        Note: Uses strict > (not >=) for L5 classification. A candidate
        at exactly the threshold is classified as stubbornness.

        Args:
            candidate_te: Candidate's assessment TE score (None if no data).
            scenario_baseline_te: Baseline TE for the scenario.
            is_fringe: Whether the rejection is on a fringe signal.

        Returns:
            "L5", "fringe_L5", or "stubbornness".
        """
        if is_fringe:
            return "fringe_L5"

        if candidate_te is None:
            return "stubbornness"

        threshold = scenario_baseline_te * 0.9
        if candidate_te > threshold:
            return "L5"

        return "stubbornness"

    def _is_fringe_signal(
        self,
        axis_identified: str | None,
        ccd_axis: str | None,
    ) -> bool:
        """Check if a flame event represents a fringe signal.

        A fringe signal is one where an axis is identified but doesn't
        match any existing CCD axis in the taxonomy. This indicates the
        candidate may have identified a genuinely novel conceptual axis.

        Args:
            axis_identified: The axis identified by the candidate.
            ccd_axis: The matched CCD axis (None if no match).

        Returns:
            True if axis is identified but no CCD match found.
        """
        if axis_identified is None:
            return False
        # Fringe = axis identified but no match to known CCD axis
        return ccd_axis is None


def detect_rejections(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    scenario_baseline_te: float,
) -> list[dict]:
    """Convenience: detect rejections in an assessment session.

    Args:
        conn: DuckDB connection with flame_events table.
        session_id: Assessment session ID.
        scenario_baseline_te: Baseline TE for the scenario.

    Returns:
        List of rejection dicts.
    """
    detector = RejectionDetector(conn)
    return detector.detect_rejections(session_id, scenario_baseline_te)
