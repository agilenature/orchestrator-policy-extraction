"""Durability index calculator via SQL aggregation.

Computes per-constraint durability scores from the session_constraint_eval
table. A durability score = sessions_honored / sessions_active, with null
returned when fewer than min_sessions evaluations exist.

Exports:
    DurabilityIndex
"""

from __future__ import annotations

import duckdb
from loguru import logger


class DurabilityIndex:
    """Computes durability scores from session constraint evaluations.

    Runs SQL aggregation queries against the session_constraint_eval
    and amnesia_events tables.

    Args:
        conn: DuckDB connection with evaluation tables created.
        min_sessions: Minimum sessions required for a meaningful score.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        min_sessions: int = 3,
    ) -> None:
        self._conn = conn
        self._min_sessions = min_sessions

    def compute_score(self, constraint_id: str) -> dict:
        """Compute durability score for a single constraint.

        Args:
            constraint_id: The constraint to compute score for.

        Returns:
            Dict with constraint_id, sessions_active, sessions_honored,
            sessions_violated, durability_score (float|None),
            insufficient_data (bool).
        """
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) as sessions_active,
                SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) as sessions_honored,
                SUM(CASE WHEN eval_state = 'VIOLATED' THEN 1 ELSE 0 END) as sessions_violated
            FROM session_constraint_eval
            WHERE constraint_id = ? AND eval_state IN ('HONORED', 'VIOLATED')
            """,
            [constraint_id],
        ).fetchone()

        sessions_active = row[0]
        sessions_honored = row[1]
        sessions_violated = row[2]

        if sessions_active < self._min_sessions:
            durability_score = None
            insufficient_data = True
        else:
            durability_score = sessions_honored / sessions_active
            insufficient_data = False

        return {
            "constraint_id": constraint_id,
            "sessions_active": sessions_active,
            "sessions_honored": sessions_honored,
            "sessions_violated": sessions_violated,
            "durability_score": durability_score,
            "insufficient_data": insufficient_data,
        }

    def compute_all_scores(self) -> list[dict]:
        """Compute durability scores for all constraints with evaluations.

        Returns:
            List of score dicts, one per constraint_id.
        """
        rows = self._conn.execute(
            """
            SELECT
                constraint_id,
                COUNT(*) as sessions_active,
                SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) as sessions_honored,
                SUM(CASE WHEN eval_state = 'VIOLATED' THEN 1 ELSE 0 END) as sessions_violated
            FROM session_constraint_eval
            WHERE eval_state IN ('HONORED', 'VIOLATED')
            GROUP BY constraint_id
            ORDER BY constraint_id
            """,
        ).fetchall()

        results = []
        for row in rows:
            constraint_id = row[0]
            sessions_active = row[1]
            sessions_honored = row[2]
            sessions_violated = row[3]

            if sessions_active < self._min_sessions:
                durability_score = None
                insufficient_data = True
            else:
                durability_score = sessions_honored / sessions_active
                insufficient_data = False

            results.append(
                {
                    "constraint_id": constraint_id,
                    "sessions_active": sessions_active,
                    "sessions_honored": sessions_honored,
                    "sessions_violated": sessions_violated,
                    "durability_score": durability_score,
                    "insufficient_data": insufficient_data,
                }
            )

        return results

    def get_amnesia_events(
        self, session_id: str | None = None
    ) -> list[dict]:
        """Query amnesia events, optionally filtered by session_id.

        Args:
            session_id: Optional session ID filter.

        Returns:
            List of amnesia event dicts.
        """
        if session_id:
            rows = self._conn.execute(
                """
                SELECT
                    amnesia_id, session_id, constraint_id,
                    constraint_type, severity, evidence_json, detected_at
                FROM amnesia_events
                WHERE session_id = ?
                ORDER BY detected_at
                """,
                [session_id],
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT
                    amnesia_id, session_id, constraint_id,
                    constraint_type, severity, evidence_json, detected_at
                FROM amnesia_events
                ORDER BY detected_at
                """,
            ).fetchall()

        columns = [
            "amnesia_id",
            "session_id",
            "constraint_id",
            "constraint_type",
            "severity",
            "evidence_json",
            "detected_at",
        ]

        return [dict(zip(columns, row)) for row in rows]
