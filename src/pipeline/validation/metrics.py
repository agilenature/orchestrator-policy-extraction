"""Quality metrics calculator for gold-standard validation.

Computes mode accuracy, reaction accuracy, reaction confidence, and
constraint extraction rate by comparing pipeline output against
human-verified gold-standard labels.

Exports:
    compute_metrics: Calculate quality metrics from gold labels
    MetricsReport: Dataclass for metrics results
    format_report: Human-readable text report
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import duckdb
from loguru import logger


# Threshold values for quality gates
THRESHOLD_MODE_ACCURACY = 0.85
THRESHOLD_REACTION_CONFIDENCE = 0.80
THRESHOLD_CONSTRAINT_EXTRACTION_RATE = 0.90


@dataclass
class MetricsReport:
    """Quality metrics report from gold-standard comparison.

    Attributes:
        mode_accuracy: Fraction of episodes where pipeline mode matches gold label.
            None if no episodes to compare.
        reaction_accuracy: Fraction of episodes where pipeline reaction_label matches gold label.
            None if no episodes to compare.
        reaction_avg_confidence: Average reaction_confidence for correctly labeled episodes.
            None if no correctly labeled episodes.
        constraint_extraction_rate: Fraction of constraint_should_extract=True episodes
            where a constraint was actually extracted. None if no such episodes.
        per_mode_accuracy: Per-mode breakdown of accuracy.
        per_reaction_accuracy: Per-reaction-label breakdown of accuracy.
        sample_size: Total number of gold labels compared.
        thresholds_met: Dict of threshold name -> whether threshold is met.
    """

    mode_accuracy: float | None = None
    reaction_accuracy: float | None = None
    reaction_avg_confidence: float | None = None
    constraint_extraction_rate: float | None = None
    per_mode_accuracy: dict[str, float | None] = field(default_factory=dict)
    per_reaction_accuracy: dict[str, float | None] = field(default_factory=dict)
    sample_size: int = 0
    thresholds_met: dict[str, bool] = field(default_factory=dict)


def compute_metrics(
    gold_labels: list[dict],
    conn: duckdb.DuckDBPyConnection,
    constraints: list[dict] | None = None,
) -> MetricsReport:
    """Compute quality metrics by comparing pipeline output to gold labels.

    Args:
        gold_labels: List of validated gold-standard label dicts. Each must
            have episode_id, verified_mode, verified_reaction_label.
        conn: DuckDB connection with episodes table.
        constraints: Optional list of constraint dicts (from ConstraintStore.constraints).
            Each has an 'examples' array of {episode_id, violation_description} dicts.

    Returns:
        MetricsReport with computed metrics and threshold checks.
    """
    report = MetricsReport(sample_size=len(gold_labels))

    if not gold_labels:
        report.thresholds_met = _compute_thresholds(report)
        return report

    # Fetch pipeline episodes by ID
    episode_ids = [g["episode_id"] for g in gold_labels]
    pipeline_episodes = _fetch_episodes_by_ids(conn, episode_ids)

    # Build lookup: episode_id -> pipeline episode
    pipeline_lookup: dict[str, dict] = {
        ep["episode_id"]: ep for ep in pipeline_episodes
    }

    # --- Mode accuracy ---
    mode_correct = 0
    mode_total = 0
    per_mode_correct: dict[str, int] = defaultdict(int)
    per_mode_total: dict[str, int] = defaultdict(int)

    for gold in gold_labels:
        eid = gold["episode_id"]
        pipeline_ep = pipeline_lookup.get(eid)
        if pipeline_ep is None:
            continue

        verified_mode = gold["verified_mode"]
        pipeline_mode = pipeline_ep.get("mode")

        per_mode_total[verified_mode] += 1
        mode_total += 1

        if pipeline_mode == verified_mode:
            mode_correct += 1
            per_mode_correct[verified_mode] += 1

    report.mode_accuracy = _safe_divide(mode_correct, mode_total)

    # Per-mode breakdown
    for mode in per_mode_total:
        report.per_mode_accuracy[mode] = _safe_divide(
            per_mode_correct.get(mode, 0), per_mode_total[mode]
        )

    # --- Reaction accuracy ---
    reaction_correct = 0
    reaction_total = 0
    per_reaction_correct: dict[str, int] = defaultdict(int)
    per_reaction_total: dict[str, int] = defaultdict(int)
    confidence_sum = 0.0
    confidence_count = 0

    for gold in gold_labels:
        eid = gold["episode_id"]
        pipeline_ep = pipeline_lookup.get(eid)
        if pipeline_ep is None:
            continue

        verified_reaction = gold["verified_reaction_label"]
        pipeline_reaction = pipeline_ep.get("reaction_label")

        per_reaction_total[verified_reaction] += 1
        reaction_total += 1

        if pipeline_reaction == verified_reaction:
            reaction_correct += 1
            per_reaction_correct[verified_reaction] += 1

            # Accumulate confidence for correctly labeled episodes
            conf = pipeline_ep.get("reaction_confidence")
            if conf is not None:
                confidence_sum += conf
                confidence_count += 1

    report.reaction_accuracy = _safe_divide(reaction_correct, reaction_total)
    report.reaction_avg_confidence = _safe_divide(confidence_sum, confidence_count)

    # Per-reaction breakdown
    for rl in per_reaction_total:
        report.per_reaction_accuracy[rl] = _safe_divide(
            per_reaction_correct.get(rl, 0), per_reaction_total[rl]
        )

    # --- Constraint extraction rate ---
    constraint_should_extract = [
        g for g in gold_labels if g.get("constraint_should_extract") is True
    ]

    if constraint_should_extract:
        # Build set of episode_ids that have constraints extracted
        extracted_episode_ids: set[str] = set()
        if constraints:
            for constraint in constraints:
                examples = constraint.get("examples", [])
                for ex in examples:
                    ex_eid = ex.get("episode_id")
                    if ex_eid:
                        extracted_episode_ids.add(ex_eid)

        constraint_found = sum(
            1
            for g in constraint_should_extract
            if g["episode_id"] in extracted_episode_ids
        )
        report.constraint_extraction_rate = _safe_divide(
            constraint_found, len(constraint_should_extract)
        )

    # --- Threshold checking ---
    report.thresholds_met = _compute_thresholds(report)

    logger.info(
        "Metrics: mode_acc={}, reaction_acc={}, confidence={}, constraint_rate={}",
        _fmt(report.mode_accuracy),
        _fmt(report.reaction_accuracy),
        _fmt(report.reaction_avg_confidence),
        _fmt(report.constraint_extraction_rate),
    )

    return report


def format_report(report: MetricsReport) -> str:
    """Format a MetricsReport as human-readable text.

    Args:
        report: Computed MetricsReport.

    Returns:
        Multi-line string with metrics and PASS/FAIL indicators.
    """
    lines: list[str] = []
    lines.append("=" * 50)
    lines.append("Quality Metrics Report")
    lines.append("=" * 50)
    lines.append(f"Sample size: {report.sample_size}")
    lines.append("")

    # Overall metrics
    lines.append("--- Overall Metrics ---")
    lines.append(
        f"  Mode accuracy:               {_fmt(report.mode_accuracy):>8s}  "
        f"{_threshold_indicator('mode_accuracy', report.thresholds_met)}"
    )
    lines.append(
        f"  Reaction accuracy:           {_fmt(report.reaction_accuracy):>8s}"
    )
    lines.append(
        f"  Reaction avg confidence:     {_fmt(report.reaction_avg_confidence):>8s}  "
        f"{_threshold_indicator('reaction_avg_confidence', report.thresholds_met)}"
    )
    lines.append(
        f"  Constraint extraction rate:  {_fmt(report.constraint_extraction_rate):>8s}  "
        f"{_threshold_indicator('constraint_extraction_rate', report.thresholds_met)}"
    )

    # Per-mode breakdown
    if report.per_mode_accuracy:
        lines.append("")
        lines.append("--- Per-Mode Accuracy ---")
        for mode, acc in sorted(report.per_mode_accuracy.items()):
            lines.append(f"  {mode:20s} {_fmt(acc):>8s}")

    # Per-reaction breakdown
    if report.per_reaction_accuracy:
        lines.append("")
        lines.append("--- Per-Reaction Accuracy ---")
        for rl, acc in sorted(report.per_reaction_accuracy.items()):
            lines.append(f"  {rl:20s} {_fmt(acc):>8s}")

    # Thresholds summary
    lines.append("")
    lines.append("--- Thresholds ---")
    for name, met in sorted(report.thresholds_met.items()):
        indicator = "PASS" if met else "FAIL"
        lines.append(f"  {name:35s} [{indicator}]")

    lines.append("=" * 50)
    return "\n".join(lines)


# --- Private helpers ---


def _fetch_episodes_by_ids(
    conn: duckdb.DuckDBPyConnection,
    episode_ids: list[str],
) -> list[dict]:
    """Fetch episodes by a list of IDs from DuckDB."""
    if not episode_ids:
        return []

    # Use a parameterized IN clause via a temporary table for safety
    conn.execute("DROP TABLE IF EXISTS _tmp_gold_ids")
    conn.execute("CREATE TEMPORARY TABLE _tmp_gold_ids (episode_id VARCHAR)")
    conn.executemany(
        "INSERT INTO _tmp_gold_ids VALUES (?)",
        [(eid,) for eid in episode_ids],
    )

    rows = conn.execute("""
        SELECT
            e.episode_id, e.mode, e.reaction_label, e.reaction_confidence
        FROM episodes e
        INNER JOIN _tmp_gold_ids g ON e.episode_id = g.episode_id
    """).fetchall()

    conn.execute("DROP TABLE IF EXISTS _tmp_gold_ids")

    columns = ["episode_id", "mode", "reaction_label", "reaction_confidence"]
    return [dict(zip(columns, row)) for row in rows]


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    """Safe division returning None when denominator is 0."""
    if denominator == 0:
        return None
    return numerator / denominator


def _compute_thresholds(report: MetricsReport) -> dict[str, bool]:
    """Compute threshold checks. None metrics result in False."""
    return {
        "mode_accuracy": (
            report.mode_accuracy is not None
            and report.mode_accuracy >= THRESHOLD_MODE_ACCURACY
        ),
        "reaction_avg_confidence": (
            report.reaction_avg_confidence is not None
            and report.reaction_avg_confidence >= THRESHOLD_REACTION_CONFIDENCE
        ),
        "constraint_extraction_rate": (
            report.constraint_extraction_rate is not None
            and report.constraint_extraction_rate >= THRESHOLD_CONSTRAINT_EXTRACTION_RATE
        ),
    }


def _fmt(value: float | None) -> str:
    """Format a metric value for display."""
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def _threshold_indicator(name: str, thresholds: dict[str, bool]) -> str:
    """Return PASS/FAIL indicator for a threshold."""
    met = thresholds.get(name)
    if met is None:
        return ""
    return "[PASS]" if met else "[FAIL]"
