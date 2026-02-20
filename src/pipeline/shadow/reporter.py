"""Shadow mode reporter for computing and formatting metrics.

Queries shadow_mode_results table to compute aggregate agreement metrics,
per-session breakdowns, danger counts, PASS/FAIL threshold indicators,
and policy error rate metrics.

The policy_error_rate denominator is total_recommendations_attempted =
COUNT(*) FROM shadow_mode_results + COUNT(*) FROM policy_error_events
WHERE error_type='suppressed'. Suppressed recommendations never enter
shadow_mode_results (they are skipped before evaluation), so the
denominator must include them to avoid undercounting.

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

        # Escalation metrics (from episodes table, not shadow_mode_results)
        escalation_metrics = self._compute_escalation_metrics()

        # Amnesia and durability metrics (Phase 10)
        amnesia_metrics = self._compute_amnesia_metrics()

        # Policy error metrics (Phase 13)
        policy_errors = self._compute_policy_error_metrics()

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
            "escalation": escalation_metrics,
            "amnesia": amnesia_metrics,
            "policy_errors": policy_errors,
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

    def _compute_escalation_metrics(self) -> dict:
        """Compute escalation metrics from the episodes table.

        Returns:
            Dict with escalation_count_per_session, rejection_adherence_rate,
            and unapproved_escalation_rate.
        """
        try:
            row = self._conn.execute("""
                SELECT
                    COUNT(CASE WHEN mode = 'ESCALATE' THEN 1 END) as escalation_count,
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(*) as total_episodes,
                    COUNT(CASE WHEN mode = 'ESCALATE' AND escalate_approval_status = 'UNAPPROVED' THEN 1 END) as unapproved_count
                FROM episodes
            """).fetchone()
        except Exception:
            return {
                "escalation_count_per_session": None,
                "rejection_adherence_rate": None,
                "unapproved_escalation_rate": None,
            }

        esc_count = row[0] or 0
        total_sessions = row[1] or 0
        total_episodes = row[2] or 0
        unapproved_count = row[3] or 0

        # escalation_count_per_session: average escalations per session
        if total_sessions > 0:
            esc_per_session = esc_count / total_sessions
        else:
            esc_per_session = None

        # rejection_adherence_rate: 1 - (escalation_count / total_episodes)
        if total_episodes > 0:
            adherence_rate = 1.0 - (esc_count / total_episodes)
        else:
            adherence_rate = None

        # unapproved_escalation_rate: unapproved / total escalations
        if esc_count > 0:
            unapproved_rate = unapproved_count / esc_count
        else:
            unapproved_rate = 0.0

        return {
            "escalation_count_per_session": esc_per_session,
            "rejection_adherence_rate": adherence_rate,
            "unapproved_escalation_rate": unapproved_rate,
        }

    def _compute_amnesia_metrics(self) -> dict:
        """Compute amnesia and durability metrics from DuckDB tables.

        Returns:
            Dict with amnesia_rate (float|None) and
            avg_durability_score (float|None).
        """
        try:
            # Amnesia rate: sessions with at least one amnesia event / total audited sessions
            row = self._conn.execute("""
                SELECT
                    COUNT(DISTINCT e.session_id) as audited_sessions,
                    COUNT(DISTINCT a.session_id) as sessions_with_amnesia
                FROM (SELECT DISTINCT session_id FROM session_constraint_eval) e
                LEFT JOIN amnesia_events a ON e.session_id = a.session_id
            """).fetchone()
        except Exception:
            return {"amnesia_rate": None, "avg_durability_score": None}

        audited = row[0] or 0
        with_amnesia = row[1] or 0
        amnesia_rate = with_amnesia / audited if audited > 0 else None

        try:
            # Average durability score across all constraints with sufficient data (>= 3 sessions)
            dur_row = self._conn.execute("""
                SELECT AVG(durability_score)
                FROM (
                    SELECT
                        constraint_id,
                        CAST(SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) AS FLOAT)
                            / COUNT(*) as durability_score
                    FROM session_constraint_eval
                    WHERE eval_state IN ('HONORED', 'VIOLATED')
                    GROUP BY constraint_id
                    HAVING COUNT(*) >= 3
                )
            """).fetchone()
        except Exception:
            dur_row = (None,)

        avg_durability = dur_row[0] if dur_row else None

        return {
            "amnesia_rate": amnesia_rate,
            "avg_durability_score": avg_durability,
        }

    def _compute_policy_error_metrics(self) -> dict:
        """Compute policy error rate metrics from DuckDB tables.

        CRITICAL denominator formula:
        - evaluated_count = COUNT(*) FROM shadow_mode_results
        - suppressed = COUNT(*) FROM policy_error_events WHERE error_type='suppressed'
        - total_attempted = evaluated_count + suppressed
        - total_errors = COUNT(*) FROM policy_error_events
        - rate = total_errors / total_attempted

        The denominator MUST include suppressed recommendations because they
        never enter shadow_mode_results (suppressed before evaluation).

        Returns:
            Dict with total_errors, suppressed, surfaced_and_blocked,
            total_attempted, policy_error_rate, meets_threshold.
        """
        try:
            evaluated_count = self._conn.execute(
                "SELECT COUNT(*) FROM shadow_mode_results"
            ).fetchone()[0] or 0
        except Exception:
            return {
                "total_errors": None,
                "suppressed": None,
                "surfaced_and_blocked": None,
                "total_attempted": None,
                "policy_error_rate": None,
                "meets_threshold": None,
            }

        try:
            error_row = self._conn.execute("""
                SELECT
                    COUNT(*) as total_errors,
                    SUM(CASE WHEN error_type = 'suppressed' THEN 1 ELSE 0 END) as suppressed,
                    SUM(CASE WHEN error_type = 'surfaced_and_blocked' THEN 1 ELSE 0 END) as blocked
                FROM policy_error_events
            """).fetchone()
        except Exception:
            return {
                "total_errors": None,
                "suppressed": None,
                "surfaced_and_blocked": None,
                "total_attempted": None,
                "policy_error_rate": None,
                "meets_threshold": None,
            }

        total_errors = int(error_row[0] or 0)
        suppressed = int(error_row[1] or 0)
        surfaced_and_blocked = int(error_row[2] or 0)

        # Denominator includes suppressed (they are NOT in shadow_mode_results)
        total_attempted = evaluated_count + suppressed

        if total_attempted == 0:
            return {
                "total_errors": 0,
                "suppressed": 0,
                "surfaced_and_blocked": 0,
                "total_attempted": 0,
                "policy_error_rate": None,
                "meets_threshold": None,
            }

        rate = total_errors / total_attempted

        return {
            "total_errors": total_errors,
            "suppressed": suppressed,
            "surfaced_and_blocked": surfaced_and_blocked,
            "total_attempted": total_attempted,
            "policy_error_rate": rate,
            "meets_threshold": rate < 0.05,
        }

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

        # Escalation metrics section
        escalation = report.get("escalation", {})
        if escalation:
            lines.append("")
            lines.append("Escalation Metrics:")

            esc_per_session = escalation.get("escalation_count_per_session")
            if esc_per_session is not None:
                lines.append(f"  Escalation count per session: {esc_per_session:.2f}")
            else:
                lines.append("  Escalation count per session: N/A")

            adherence_rate = escalation.get("rejection_adherence_rate")
            if adherence_rate is not None:
                lines.append(f"  Rejection adherence rate: {adherence_rate:.1%}")
            else:
                lines.append("  Rejection adherence rate: N/A")

            unapproved_rate = escalation.get("unapproved_escalation_rate")
            if unapproved_rate is not None:
                gate_label = "PASS" if unapproved_rate == 0.0 else "FAIL"
                lines.append(
                    f"  Unapproved escalation rate: {unapproved_rate:.1%} "
                    f"(target: 0.0%)  {gate_label}"
                )
            else:
                lines.append("  Unapproved escalation rate: N/A")

        # Decision Durability Metrics section (Phase 10)
        amnesia = report.get("amnesia", {})
        if amnesia:
            lines.append("")
            lines.append("Decision Durability Metrics:")

            amnesia_rate = amnesia.get("amnesia_rate")
            if amnesia_rate is not None:
                amnesia_gate = "PASS" if amnesia_rate == 0.0 else "FAIL"
                lines.append(
                    f"  Amnesia rate: {amnesia_rate:.1%} "
                    f"(sessions with amnesia / audited sessions)  {amnesia_gate}"
                )
            else:
                lines.append("  Amnesia rate: N/A")

            avg_durability = amnesia.get("avg_durability_score")
            if avg_durability is not None:
                lines.append(
                    f"  Avg durability score: {avg_durability:.2f} "
                    f"(across constraints with >= 3 sessions)"
                )
            else:
                lines.append("  Avg durability score: N/A")

        # Policy Error Metrics section (Phase 13)
        policy_errors = report.get("policy_errors", {})
        if policy_errors:
            lines.append("")
            lines.append("Policy Error Metrics:")

            pe_rate = policy_errors.get("policy_error_rate")
            pe_total = policy_errors.get("total_errors", 0)
            pe_suppressed = policy_errors.get("suppressed", 0)
            pe_blocked = policy_errors.get("surfaced_and_blocked", 0)
            pe_attempted = policy_errors.get("total_attempted", 0)
            pe_meets = policy_errors.get("meets_threshold")

            if pe_rate is not None:
                pe_gate = "PASS" if pe_meets else "FAIL"
                lines.append(
                    f"  Policy error rate: {pe_rate:.1%} "
                    f"(target: <5%)  {pe_gate}"
                )
                lines.append(
                    f"  Total errors: {pe_total} "
                    f"(suppressed: {pe_suppressed}, blocked: {pe_blocked})"
                )
                lines.append(
                    f"  Total attempted: {pe_attempted} "
                    f"(evaluated + suppressed)"
                )
            else:
                lines.append("  Policy error rate: N/A")

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
