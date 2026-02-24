"""Assessment Report generator with terminal deposit (Phase 17, Plan 04).

Generates comprehensive Assessment Reports from completed assessment sessions
and deposits them as CCD-quality entries to memory_candidates with
source_type='simulation_review', fidelity=3, confidence=0.85.

The reporter is the terminal act of the assessment pipeline: every prior
plan (schema, scenario generation, session running, observation, TE computation,
rejection detection) is instrumental; this plan's deposit is terminal.

Includes auto-calibration proposal mechanism that deposits to memory_candidates
for human review (never auto-updates ddf_target_level).

Exports:
    AssessmentReporter
    generate_report
    deposit_report
"""

from __future__ import annotations

import hashlib
import logging
import math

import duckdb

from src.pipeline.assessment.models import AssessmentReport

logger = logging.getLogger(__name__)


class AssessmentReporter:
    """Generates Assessment Reports and deposits them as terminal memory candidates.

    The terminal deposit uses source_type='simulation_review', fidelity=3,
    confidence=0.85. This is the highest-fidelity deposit mechanism because
    it forces DDF Levels 5-7 reasoning during the assessment session.

    Args:
        conn: DuckDB connection with flame_events, assessment_te_sessions,
              assessment_baselines, and memory_candidates tables.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def generate_report(
        self,
        session_id: str,
        scenario_id: str,
        candidate_id: str,
    ) -> AssessmentReport:
        """Generate an Assessment Report from session data.

        Aggregates FlameEvent timeline, level distribution, TE metrics,
        axis quality scores, spiral evidence, AI contribution, and
        rejection analysis into a single AssessmentReport model.

        Args:
            session_id: Assessment session ID.
            scenario_id: Scenario ID.
            candidate_id: Candidate ID.

        Returns:
            Frozen AssessmentReport with all fields populated.
        """
        # 1. FlameEvent timeline
        all_events = self._conn.execute(
            """
            SELECT flame_event_id, prompt_number, marker_level, marker_type,
                   evidence_excerpt, quality_score, axis_identified,
                   flood_confirmed, subject
            FROM flame_events
            WHERE session_id = ?
            ORDER BY prompt_number, subject
            """,
            [session_id],
        ).fetchall()

        columns = [
            "flame_event_id", "prompt_number", "marker_level", "marker_type",
            "evidence_excerpt", "quality_score", "axis_identified",
            "flood_confirmed", "subject",
        ]
        events = [dict(zip(columns, row)) for row in all_events]

        human_events = [e for e in events if e["subject"] == "human"]

        # 2. Level distribution (human events only)
        level_distribution: dict[str, int] = {}
        for event in human_events:
            key = f"L{event['marker_level']}"
            level_distribution[key] = level_distribution.get(key, 0) + 1

        # 3. TE metrics from assessment_te_sessions
        te_row = self._conn.execute(
            """
            SELECT candidate_te, raven_depth, crow_efficiency, trunk_quality,
                   candidate_ratio, scenario_baseline_te, fringe_drift_rate
            FROM assessment_te_sessions
            WHERE session_id = ? AND candidate_id = ?
            """,
            [session_id, candidate_id],
        ).fetchone()

        candidate_te = te_row[0] if te_row else None
        raven_depth = te_row[1] if te_row else None
        crow_efficiency = te_row[2] if te_row else None
        trunk_quality = te_row[3] if te_row else None
        candidate_ratio = te_row[4] if te_row else None
        scenario_baseline_te = te_row[5] if te_row else None
        fringe_drift_rate = te_row[6] if te_row else None

        # 4. Percentile rank
        percentile_rank = self._compute_percentile(scenario_id, candidate_ratio)

        # 5. Axis quality scores
        axis_quality_scores: dict[str, float] = {}
        for event in human_events:
            axis = event["axis_identified"]
            if axis is not None:
                if axis not in axis_quality_scores:
                    axis_quality_scores[axis] = []
                axis_quality_scores[axis].append(event["quality_score"] or 0.0)
        # Compute averages
        axis_quality_scores = {
            axis: sum(scores) / len(scores)
            for axis, scores in axis_quality_scores.items()
            if scores
        }

        # 6. Flood rate
        flood_count = sum(1 for e in human_events if e["flood_confirmed"])
        flood_rate = (
            flood_count / len(human_events) if human_events else None
        )

        # 7. Spiral evidence
        spiral_evidence = self._detect_spirals(human_events)

        # 8. AI contribution
        ai_events = [e for e in events if e["subject"] == "ai"]
        ai_flame_event_count = len(ai_events)
        ai_avg_marker_level = (
            sum(e["marker_level"] for e in ai_events) / len(ai_events)
            if ai_events
            else None
        )

        # 9. Rejection analysis
        rejections_detected = 0
        rejections_level5 = 0
        stubbornness_indicators = 0
        if scenario_baseline_te is not None:
            from src.pipeline.assessment.rejection_detector import (
                RejectionDetector,
            )

            detector = RejectionDetector(self._conn)
            rejections = detector.detect_rejections(
                session_id, scenario_baseline_te
            )
            rejections_detected = len(rejections)
            rejections_level5 = sum(
                1
                for r in rejections
                if r["rejection_type"] in ("L5", "fringe_L5")
            )
            stubbornness_indicators = sum(
                1 for r in rejections if r["rejection_type"] == "stubbornness"
            )

        # 10. Build AssessmentReport
        report_id = AssessmentReport.make_id(session_id)
        return AssessmentReport(
            report_id=report_id,
            session_id=session_id,
            scenario_id=scenario_id,
            candidate_id=candidate_id,
            flame_event_count=len(human_events),
            level_distribution=level_distribution,
            candidate_te=candidate_te,
            raven_depth=raven_depth,
            crow_efficiency=crow_efficiency,
            trunk_quality=trunk_quality,
            candidate_ratio=candidate_ratio,
            percentile_rank=percentile_rank,
            axis_quality_scores=axis_quality_scores,
            flood_rate=flood_rate,
            spiral_evidence=spiral_evidence,
            fringe_drift_rate=fringe_drift_rate,
            ai_avg_marker_level=ai_avg_marker_level,
            ai_flame_event_count=ai_flame_event_count,
            rejections_detected=rejections_detected,
            rejections_level5=rejections_level5,
            stubbornness_indicators=stubbornness_indicators,
        )

    def _compute_percentile(
        self, scenario_id: str, candidate_ratio: float | None
    ) -> float | None:
        """Compute percentile rank from assessment baselines.

        Uses math.erf for normal CDF approximation (no scipy dependency).
        Returns None if fewer than 10 assessments exist for the scenario.

        Args:
            scenario_id: Scenario to look up baselines for.
            candidate_ratio: Candidate's TE ratio to compute percentile for.

        Returns:
            Percentile as float (0.0-1.0), or None if insufficient data.
        """
        if candidate_ratio is None:
            return None

        baseline = self._conn.execute(
            "SELECT n_assessments, mean_ratio, stddev_ratio "
            "FROM assessment_baselines WHERE scenario_id = ?",
            [scenario_id],
        ).fetchone()

        if baseline is None:
            return None

        n_assessments, mean_ratio, stddev_ratio = baseline

        if n_assessments is None or n_assessments < 10:
            return None

        if stddev_ratio is None or stddev_ratio == 0:
            return None

        z = (candidate_ratio - mean_ratio) / stddev_ratio
        percentile = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        return round(percentile, 4)

    def _detect_spirals(self, human_events: list[dict]) -> list[str]:
        """Detect ascending runs of length >= 3 in marker_level sequence.

        Args:
            human_events: Human flame events (will be sorted by prompt_number).

        Returns:
            List of spiral descriptions like "L1->L5 (4 steps)".
        """
        sorted_events = sorted(
            human_events, key=lambda x: x["prompt_number"] or 0
        )
        levels = [e["marker_level"] for e in sorted_events]

        if not levels:
            return []

        spiral_evidence: list[str] = []
        current_run = [levels[0]]

        for lvl in levels[1:]:
            if lvl > current_run[-1]:
                current_run.append(lvl)
            else:
                if len(current_run) >= 3:
                    spiral_evidence.append(
                        f"L{current_run[0]}->L{current_run[-1]} "
                        f"({len(current_run)} steps)"
                    )
                current_run = [lvl]

        if len(current_run) >= 3:
            spiral_evidence.append(
                f"L{current_run[0]}->L{current_run[-1]} "
                f"({len(current_run)} steps)"
            )

        return spiral_evidence

    def format_report_markdown(self, report: AssessmentReport) -> str:
        """Format an AssessmentReport as markdown.

        Args:
            report: The AssessmentReport to format.

        Returns:
            Markdown string with all report sections.
        """
        lines: list[str] = []
        lines.append(f"# Assessment Report: {report.candidate_id}")
        lines.append("")
        lines.append(f"**Session:** {report.session_id}")
        lines.append(f"**Scenario:** {report.scenario_id}")
        lines.append(f"**Date:** {report.created_at.isoformat()}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(
            f"| Candidate TE | {report.candidate_te} |"
        )
        lines.append(
            f"| Scenario Baseline TE | "
            f"{self._get_scenario_baseline(report)} |"
        )
        lines.append(
            f"| Candidate Ratio | {report.candidate_ratio} |"
        )
        percentile_str = (
            f"{report.percentile_rank * 100:.1f}%"
            if report.percentile_rank is not None
            else "Baseline pending (N<10)"
        )
        lines.append(f"| Percentile Rank | {percentile_str} |")
        lines.append("")

        # TE Breakdown
        lines.append("## TransportEfficiency Breakdown (3-metric)")
        lines.append("")
        lines.append("| Sub-metric | Score |")
        lines.append("|-----------|-------|")
        lines.append(f"| Raven Depth | {report.raven_depth} |")
        lines.append(f"| Crow Efficiency | {report.crow_efficiency} |")
        trunk_str = (
            f"{report.trunk_quality} (pending)"
            if report.trunk_quality is not None
            else "None (pending)"
        )
        lines.append(f"| Trunk Quality | {trunk_str} |")
        lines.append("")
        lines.append(
            "*Note: transport_speed excluded from assessment TE per design.*"
        )
        lines.append("")

        # FlameEvent Timeline
        lines.append("## FlameEvent Timeline")
        lines.append("")
        lines.append("| # | Level | Type | Subject | Evidence |")
        lines.append("|---|-------|------|---------|----------|")
        # Re-query for timeline (report doesn't store raw events)
        try:
            timeline_rows = self._conn.execute(
                """
                SELECT prompt_number, marker_level, marker_type, subject,
                       evidence_excerpt
                FROM flame_events
                WHERE session_id = ?
                ORDER BY prompt_number, subject
                """,
                [report.session_id],
            ).fetchall()
            for row in timeline_rows:
                pn, lvl, mtype, subj, evidence = row
                ev_short = (
                    (evidence[:60] + "...")
                    if evidence and len(evidence) > 60
                    else (evidence or "")
                )
                lines.append(
                    f"| {pn} | L{lvl} | {mtype} | {subj} | {ev_short} |"
                )
        except Exception:
            lines.append("| - | - | - | - | No data |")
        lines.append("")

        # DDF Level Distribution
        lines.append("## DDF Level Distribution")
        lines.append("")
        lines.append("| Level | Count |")
        lines.append("|-------|-------|")
        for level_key in sorted(report.level_distribution.keys()):
            lines.append(
                f"| {level_key} | {report.level_distribution[level_key]} |"
            )
        lines.append("")

        # Axis Quality Scores
        lines.append("## Axis Quality Scores")
        lines.append("")
        if report.axis_quality_scores:
            lines.append("| Axis | Avg Quality |")
            lines.append("|------|------------|")
            for axis, score in sorted(report.axis_quality_scores.items()):
                lines.append(f"| {axis} | {score:.3f} |")
        else:
            lines.append("No axes identified")
        lines.append("")

        # Spiral Evidence
        lines.append("## Spiral Evidence")
        lines.append("")
        if report.spiral_evidence:
            for spiral in report.spiral_evidence:
                lines.append(f"- {spiral}")
        else:
            lines.append("No spirals detected")
        lines.append("")

        # AI Contribution
        lines.append("## AI Contribution Profile")
        lines.append("")
        lines.append(f"- AI FlameEvents: {report.ai_flame_event_count}")
        lines.append(
            f"- AI Avg Marker Level: {report.ai_avg_marker_level}"
        )
        lines.append("")

        # Rejection Analysis
        lines.append("## Rejection Analysis")
        lines.append("")
        lines.append(
            f"- Rejections detected: {report.rejections_detected}"
        )
        lines.append(
            f"- Level 5 confirmed (outcome-gated): "
            f"{report.rejections_level5}"
        )
        lines.append(
            f"- Stubbornness indicators: "
            f"{report.stubbornness_indicators}"
        )
        lines.append("")

        # Fringe Drift
        lines.append("## Fringe Drift")
        lines.append("")
        lines.append(f"- Fringe Drift Rate: {report.fringe_drift_rate}")
        lines.append("")

        # Population Comparison
        lines.append("## Population Comparison")
        lines.append("")
        if report.percentile_rank is not None:
            pct = report.percentile_rank * 100
            lines.append(
                f"Candidate ranks at the {pct:.1f}th percentile "
                f"among {report.scenario_id} assessments."
            )
        else:
            lines.append("Insufficient baseline data (N<10)")
        lines.append("")

        return "\n".join(lines)

    def _get_scenario_baseline(self, report: AssessmentReport) -> str:
        """Look up scenario_baseline_te from assessment_te_sessions.

        Args:
            report: The report to look up baseline for.

        Returns:
            String representation of the baseline TE.
        """
        try:
            row = self._conn.execute(
                "SELECT scenario_baseline_te FROM assessment_te_sessions "
                "WHERE session_id = ? LIMIT 1",
                [report.session_id],
            ).fetchone()
            if row and row[0] is not None:
                return str(row[0])
        except Exception:
            pass
        return "N/A"

    def deposit_report(self, report: AssessmentReport) -> str | None:
        """Terminal deposit: write report as a CCD-quality memory candidate.

        Direct INSERT into memory_candidates (does NOT use
        deposit_to_memory_candidates function -- that function doesn't
        support source_type, fidelity, confidence).

        Uses DELETE + INSERT for idempotent upsert, matching the
        project-wide DuckDB pattern.

        Args:
            report: The AssessmentReport to deposit.

        Returns:
            The memory_candidates id (16-char hex), or None on error.
        """
        candidate_id_hash = hashlib.sha256(
            f"assessment:{report.session_id}".encode()
        ).hexdigest()[:16]

        # Build CCD-format fields (must be non-empty due to CHECK constraints)
        ccd_axis = (
            f"assessment-{report.scenario_id[:8]}-{report.candidate_id[:8]}"
        )
        scope_rule = (
            f"Assessment session measuring candidate {report.candidate_id} "
            f"on scenario {report.scenario_id}. "
            f"Candidate TE ratio: {report.candidate_ratio}. "
            f"L5 rejections: {report.rejections_level5}."
        )
        flood_example = (
            f"Session {report.session_id}: "
            f"{report.flame_event_count} flame events, "
            f"level distribution {report.level_distribution}, "
            f"candidate TE {report.candidate_te}."
        )

        try:
            # Idempotent upsert: DELETE + INSERT
            self._conn.execute(
                "DELETE FROM memory_candidates WHERE id = ?",
                [candidate_id_hash],
            )
            self._conn.execute(
                """
                INSERT INTO memory_candidates (
                    id, source_instance_id, ccd_axis, scope_rule,
                    flood_example, pipeline_component, status,
                    source_flame_event_id, fidelity, detection_count,
                    confidence, subject, session_id, source_type
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, 1, ?, ?, ?, ?
                )
                """,
                [
                    candidate_id_hash,
                    report.session_id,
                    ccd_axis,
                    scope_rule,
                    flood_example,
                    "assessment_reporter",
                    report.fidelity,      # 3
                    report.confidence,    # 0.85
                    "assessment",         # subject
                    report.session_id,
                    report.source_type,   # 'simulation_review'
                ],
            )
            logger.info(
                "Terminal deposit: memory_candidates id=%s "
                "(source_type=%s, fidelity=%d, confidence=%.2f)",
                candidate_id_hash,
                report.source_type,
                report.fidelity,
                report.confidence,
            )
            return candidate_id_hash
        except Exception:
            logger.exception(
                "Failed to deposit report for session %s",
                report.session_id,
            )
            return None

    def check_auto_calibration(self, scenario_id: str) -> str | None:
        """Check if scenario needs auto-calibration and deposit proposal.

        Deposits a calibration proposal to memory_candidates for human review.
        Does NOT auto-update project_wisdom.ddf_target_level.

        Logic:
        - If n_assessments < 10: return None (insufficient data)
        - If last 3 candidate_ratios all > 1.3: too easy
        - If last 3 candidate_ratios all < 0.5: too hard
        - Otherwise: return None

        Args:
            scenario_id: Scenario to check calibration for.

        Returns:
            memory_candidates id if proposal deposited, None otherwise.
        """
        baseline = self._conn.execute(
            "SELECT n_assessments, mean_ratio, stddev_ratio "
            "FROM assessment_baselines WHERE scenario_id = ?",
            [scenario_id],
        ).fetchone()

        if baseline is None:
            return None

        n_assessments = baseline[0]
        if n_assessments is None or n_assessments < 10:
            return None

        # Get last 3 candidate_ratios
        rows = self._conn.execute(
            "SELECT candidate_ratio FROM assessment_te_sessions "
            "WHERE scenario_id = ? AND candidate_ratio IS NOT NULL "
            "ORDER BY assessment_date DESC LIMIT 3",
            [scenario_id],
        ).fetchall()

        if len(rows) < 3:
            return None

        ratios = [r[0] for r in rows]

        too_easy = all(r > 1.3 for r in ratios)
        too_hard = all(r < 0.5 for r in ratios)

        if not too_easy and not too_hard:
            return None

        direction = "too_easy" if too_easy else "too_hard"
        proposal_hash = hashlib.sha256(
            f"calibration:{scenario_id}:{direction}".encode()
        ).hexdigest()[:16]

        ccd_axis = f"calibration-proposal-{scenario_id[:8]}"
        scope_rule = (
            f"Auto-calibration proposal for scenario {scenario_id}: "
            f"{direction}. Last 3 ratios: {ratios}. "
            f"Scenario may need DDF level adjustment."
        )
        flood_example = (
            f"Scenario {scenario_id}: n_assessments={n_assessments}, "
            f"last 3 ratios={ratios}, direction={direction}."
        )

        try:
            self._conn.execute(
                "DELETE FROM memory_candidates WHERE id = ?",
                [proposal_hash],
            )
            self._conn.execute(
                """
                INSERT INTO memory_candidates (
                    id, source_instance_id, ccd_axis, scope_rule,
                    flood_example, pipeline_component, status,
                    source_flame_event_id, fidelity, detection_count,
                    confidence, subject, session_id, source_type
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, 1, ?, ?, NULL, ?
                )
                """,
                [
                    proposal_hash,
                    scenario_id,
                    ccd_axis,
                    scope_rule,
                    flood_example,
                    "assessment_reporter",
                    3,                    # fidelity
                    0.85,                 # confidence
                    "calibration",        # subject
                    "simulation_review",  # source_type
                ],
            )
            logger.info(
                "Auto-calibration proposal deposited: %s (%s) for scenario %s",
                proposal_hash,
                direction,
                scenario_id,
            )
            return proposal_hash
        except Exception:
            logger.exception(
                "Failed to deposit calibration proposal for scenario %s",
                scenario_id,
            )
            return None


def generate_report(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    scenario_id: str,
    candidate_id: str,
) -> AssessmentReport:
    """Convenience: generate an AssessmentReport.

    Args:
        conn: DuckDB connection.
        session_id: Assessment session ID.
        scenario_id: Scenario ID.
        candidate_id: Candidate ID.

    Returns:
        AssessmentReport with all fields populated.
    """
    return AssessmentReporter(conn).generate_report(
        session_id, scenario_id, candidate_id
    )


def deposit_report(
    conn: duckdb.DuckDBPyConnection, report: AssessmentReport
) -> str | None:
    """Convenience: deposit an AssessmentReport to memory_candidates.

    Args:
        conn: DuckDB connection.
        report: The AssessmentReport to deposit.

    Returns:
        The memory_candidates id, or None on error.
    """
    return AssessmentReporter(conn).deposit_report(report)
