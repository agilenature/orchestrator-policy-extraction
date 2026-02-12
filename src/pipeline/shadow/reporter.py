"""Shadow mode reporter for computing and formatting metrics.

Queries shadow_mode_results table to compute aggregate agreement metrics,
per-session breakdowns, danger counts, and PASS/FAIL threshold indicators.

Exports:
    ShadowReporter: Compute and format shadow mode metrics from stored results
"""

from __future__ import annotations

import json

import duckdb


class ShadowReporter:
    """Compute and format shadow mode metrics from stored results.

    Queries the shadow_mode_results table for aggregate and per-session
    agreement rates, danger counts, and threshold checks.

    Args:
        conn: DuckDB connection with shadow_mode_results table populated.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def compute_report(self, batch_id: str | None = None) -> dict:
        """Compute aggregate metrics from shadow_mode_results table.

        Args:
            batch_id: Optional batch ID to filter results. If None, uses
                      all results.

        Returns:
            Report dict with total_episodes, total_sessions,
            mode_agreement_rate, risk_agreement_rate, avg_scope_overlap,
            gate_agreement_rate, dangerous_count, danger_categories,
            meets_threshold, meets_session_minimum, per_session.
        """
        # Aggregate metrics
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT session_id) as sessions,
                AVG(CASE WHEN mode_agrees THEN 1.0 ELSE 0.0 END) as mode_rate,
                AVG(CASE WHEN risk_agrees THEN 1.0 ELSE 0.0 END) as risk_rate,
                AVG(scope_overlap) as avg_scope,
                AVG(CASE WHEN gate_agrees THEN 1.0 ELSE 0.0 END) as gate_rate,
                SUM(CASE WHEN is_dangerous THEN 1 ELSE 0 END) as dangerous
            FROM shadow_mode_results
            WHERE (? IS NULL OR run_batch_id = ?)
            """,
            [batch_id, batch_id],
        ).fetchone()

        total = row[0] or 0
        sessions = row[1] or 0
        mode_rate = row[2] or 0.0
        risk_rate = row[3] or 0.0
        avg_scope = row[4] or 0.0
        gate_rate = row[5]  # Can be None if no gate data
        dangerous = int(row[6] or 0)

        # Per-session breakdown
        session_rows = self._conn.execute(
            """
            SELECT
                session_id,
                COUNT(*) as episode_count,
                AVG(CASE WHEN mode_agrees THEN 1.0 ELSE 0.0 END) as mode_rate
            FROM shadow_mode_results
            WHERE (? IS NULL OR run_batch_id = ?)
            GROUP BY session_id
            ORDER BY session_id
            """,
            [batch_id, batch_id],
        ).fetchall()

        per_session = [
            {
                "session_id": sr[0],
                "episode_count": sr[1],
                "mode_agreement_rate": sr[2] or 0.0,
            }
            for sr in session_rows
        ]

        # Danger categories breakdown
        danger_categories = self._compute_danger_categories(batch_id)

        return {
            "total_episodes": total,
            "total_sessions": sessions,
            "mode_agreement_rate": mode_rate,
            "risk_agreement_rate": risk_rate,
            "avg_scope_overlap": avg_scope,
            "gate_agreement_rate": gate_rate,
            "dangerous_count": dangerous,
            "danger_categories": danger_categories,
            "meets_threshold": mode_rate >= 0.70,
            "meets_session_minimum": sessions >= 50,
            "per_session": per_session,
        }

    def _compute_danger_categories(self, batch_id: str | None) -> dict:
        """Count danger reasons across all results.

        Parses the danger_reasons JSON column and counts each category.

        Args:
            batch_id: Optional batch ID filter.

        Returns:
            Dict mapping danger category name to count.
        """
        rows = self._conn.execute(
            """
            SELECT danger_reasons
            FROM shadow_mode_results
            WHERE is_dangerous = TRUE
              AND (? IS NULL OR run_batch_id = ?)
            """,
            [batch_id, batch_id],
        ).fetchall()

        categories: dict[str, int] = {}
        for (reasons_json,) in rows:
            if reasons_json:
                if isinstance(reasons_json, str):
                    try:
                        reasons = json.loads(reasons_json)
                    except (json.JSONDecodeError, TypeError):
                        reasons = []
                elif isinstance(reasons_json, list):
                    reasons = reasons_json
                else:
                    reasons = []

                for reason in reasons:
                    if isinstance(reason, str):
                        categories[reason] = categories.get(reason, 0) + 1

        return categories

    def format_report(self, report: dict) -> str:
        """Format report dict as human-readable text for CLI output.

        Args:
            report: Report dict from compute_report().

        Returns:
            Formatted multi-line string with metrics and PASS/FAIL indicators.
        """
        total = report["total_episodes"]
        sessions = report["total_sessions"]
        mode_rate = report["mode_agreement_rate"]
        risk_rate = report["risk_agreement_rate"]
        avg_scope = report["avg_scope_overlap"]
        gate_rate = report.get("gate_agreement_rate")
        dangerous = report["dangerous_count"]
        meets_threshold = report["meets_threshold"]
        meets_session = report["meets_session_minimum"]
        danger_cats = report.get("danger_categories", {})
        per_session = report.get("per_session", [])

        threshold_label = "PASS" if meets_threshold else "FAIL"
        session_label = "PASS" if meets_session else "FAIL"

        lines = [
            "Shadow Mode Report",
            "==================",
            f"Episodes:  {total} across {sessions} sessions",
            f"Threshold: {mode_rate:.1%} mode agreement (target: >=70%)  {threshold_label}",
            f"Sessions:  {sessions} (target: >=50)  {session_label}",
            "",
            "Agreement Metrics:",
            f"  Mode:  {mode_rate:.1%}",
            f"  Risk:  {risk_rate:.1%}",
            f"  Scope: {avg_scope:.1%} (avg Jaccard)",
        ]

        if gate_rate is not None:
            lines.append(f"  Gates: {gate_rate:.1%}")
        else:
            lines.append("  Gates: N/A")

        lines.append("")
        lines.append("Safety:")
        lines.append(f"  Dangerous recommendations: {dangerous}")

        if danger_cats:
            for cat, count in sorted(danger_cats.items()):
                lines.append(f"    {cat}: {count}")

        if per_session:
            lines.append("")
            lines.append("Per-Session Breakdown:")
            for sess in per_session:
                sid = sess["session_id"]
                ep_count = sess["episode_count"]
                sess_rate = sess["mode_agreement_rate"]
                lines.append(
                    f"  {sid}: {ep_count} episodes, {sess_rate:.1%} mode agreement"
                )

        return "\n".join(lines)
