"""Tests for quality metrics calculator.

Covers:
1. compute_metrics with all labels matching (100% accuracy)
2. compute_metrics with mixed matches (partial accuracy)
3. compute_metrics with zero denominator for each metric type
4. Constraint extraction rate with matching episode_ids in examples
5. Constraint extraction rate with multiple examples per constraint
6. Threshold checking (above, below, None)
7. Per-mode and per-reaction accuracy breakdowns
8. format_report produces readable output with PASS/FAIL
9. Empty gold labels produce zero sample_size
10. Missing pipeline episodes handled gracefully
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.storage.schema import create_schema
from src.pipeline.validation.metrics import (
    MetricsReport,
    compute_metrics,
    format_report,
)


@pytest.fixture
def conn_with_episodes():
    """Create DuckDB with sample episodes for metrics testing."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)

    episodes = [
        ("ep-001", "Implement", "approve", 0.9),
        ("ep-002", "Implement", "correct", 0.8),
        ("ep-003", "Explore", "approve", 0.95),
        ("ep-004", "Plan", "redirect", 0.7),
        ("ep-005", "Verify", "approve", 0.85),
        ("ep-006", "Implement", "block", 0.6),
        ("ep-007", "Triage", "question", 0.5),
        ("ep-008", "Refactor", "approve", 0.9),
    ]

    for eid, mode, rl, rc in episodes:
        action_json = json.dumps({"mode": mode, "risk": "low"})
        outcome_json = json.dumps({"reaction": {"label": rl, "confidence": rc}})
        provenance_json = json.dumps({"sources": []})
        conn.execute(
            """
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp,
                mode, risk, reaction_label, reaction_confidence, outcome_type,
                observation, orchestrator_action, outcome, provenance
            ) VALUES (
                ?, 'sess-1', 'seg-1', '2026-01-01T00:00:00Z',
                ?, 'low', ?, ?, 'success',
                {
                    repo_state: {changed_files: [], diff_stat: {files: 0, insertions: 0, deletions: 0}},
                    quality_state: {tests_status: 'pass', lint_status: 'pass', build_status: 'pass'},
                    context: {recent_summary: '', open_questions: [], constraints_in_force: []}
                },
                CAST(? AS JSON), CAST(? AS JSON), CAST(? AS JSON)
            )
            """,
            [eid, mode, rl, rc, action_json, outcome_json, provenance_json],
        )

    return conn


class TestComputeMetricsAllMatch:
    """Tests for 100% accuracy scenario."""

    def test_perfect_mode_accuracy(self, conn_with_episodes):
        """All gold labels match pipeline modes -> 100% mode accuracy."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-003", "verified_mode": "Explore", "verified_reaction_label": "approve"},
            {"episode_id": "ep-004", "verified_mode": "Plan", "verified_reaction_label": "redirect"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        assert report.mode_accuracy == 1.0
        assert report.reaction_accuracy == 1.0
        assert report.sample_size == 3

    def test_perfect_reaction_confidence(self, conn_with_episodes):
        """Correctly labeled episodes have their confidence averaged."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-003", "verified_mode": "Explore", "verified_reaction_label": "approve"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        # ep-001 conf=0.9, ep-003 conf=0.95 -> avg = 0.925
        assert report.reaction_avg_confidence == pytest.approx(0.925)


class TestComputeMetricsPartialMatch:
    """Tests for partial accuracy scenario."""

    def test_mixed_mode_accuracy(self, conn_with_episodes):
        """Some modes match, some don't -> partial accuracy."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-002", "verified_mode": "Explore", "verified_reaction_label": "correct"},  # Pipeline: Implement
            {"episode_id": "ep-003", "verified_mode": "Explore", "verified_reaction_label": "approve"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        # 2 of 3 modes match
        assert report.mode_accuracy == pytest.approx(2 / 3)

    def test_mixed_reaction_accuracy(self, conn_with_episodes):
        """Some reactions match, some don't -> partial accuracy."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-002", "verified_mode": "Implement", "verified_reaction_label": "approve"},  # Pipeline: correct
            {"episode_id": "ep-003", "verified_mode": "Explore", "verified_reaction_label": "approve"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        # 2 of 3 reactions match (ep-001 approve, ep-003 approve)
        assert report.reaction_accuracy == pytest.approx(2 / 3)


class TestZeroDenominator:
    """Tests for zero-denominator safety."""

    def test_empty_gold_labels(self, conn_with_episodes):
        """No gold labels -> all metrics None, no crash."""
        report = compute_metrics([], conn_with_episodes)

        assert report.mode_accuracy is None
        assert report.reaction_accuracy is None
        assert report.reaction_avg_confidence is None
        assert report.constraint_extraction_rate is None
        assert report.sample_size == 0

    def test_no_matching_pipeline_episodes(self, conn_with_episodes):
        """Gold labels reference non-existent episodes -> metrics None."""
        gold = [
            {"episode_id": "ep-999", "verified_mode": "Implement", "verified_reaction_label": "approve"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        # No pipeline episodes found to compare
        assert report.mode_accuracy is None
        assert report.reaction_accuracy is None
        assert report.sample_size == 1

    def test_no_constraint_should_extract_labels(self, conn_with_episodes):
        """No labels with constraint_should_extract=True -> rate is None."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        assert report.constraint_extraction_rate is None

    def test_no_correct_reactions_for_confidence(self, conn_with_episodes):
        """All reactions wrong -> avg confidence is None."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "block"},
            {"episode_id": "ep-002", "verified_mode": "Implement", "verified_reaction_label": "approve"},
        ]
        report = compute_metrics(gold, conn_with_episodes)

        # Neither reaction matches -> no correctly labeled episodes
        assert report.reaction_avg_confidence is None


class TestConstraintExtractionRate:
    """Tests for constraint extraction rate calculation."""

    def test_constraint_rate_with_matching_examples(self, conn_with_episodes):
        """Constraint rate correctly links episodes via examples array."""
        gold = [
            {
                "episode_id": "ep-002",
                "verified_mode": "Implement",
                "verified_reaction_label": "correct",
                "constraint_should_extract": True,
            },
            {
                "episode_id": "ep-006",
                "verified_mode": "Implement",
                "verified_reaction_label": "block",
                "constraint_should_extract": True,
            },
        ]

        constraints = [
            {
                "constraint_id": "c-1",
                "text": "Do not use global state",
                "examples": [
                    {"episode_id": "ep-002", "violation_description": "Used global var"},
                ],
            },
        ]

        report = compute_metrics(gold, conn_with_episodes, constraints=constraints)

        # 1 of 2 constraint_should_extract episodes has a constraint
        assert report.constraint_extraction_rate == pytest.approx(0.5)

    def test_constraint_rate_with_multiple_examples(self, conn_with_episodes):
        """Constraints enriched with multiple examples are detected correctly."""
        gold = [
            {
                "episode_id": "ep-002",
                "verified_mode": "Implement",
                "verified_reaction_label": "correct",
                "constraint_should_extract": True,
            },
            {
                "episode_id": "ep-006",
                "verified_mode": "Implement",
                "verified_reaction_label": "block",
                "constraint_should_extract": True,
            },
        ]

        # Single constraint with both episodes in its examples array
        # (as would happen after ConstraintStore dedup enrichment)
        constraints = [
            {
                "constraint_id": "c-1",
                "text": "Do not use global state",
                "examples": [
                    {"episode_id": "ep-002", "violation_description": "Used global var"},
                    {"episode_id": "ep-006", "violation_description": "Used shared state"},
                ],
            },
        ]

        report = compute_metrics(gold, conn_with_episodes, constraints=constraints)

        # Both found -> 100%
        assert report.constraint_extraction_rate == pytest.approx(1.0)

    def test_constraint_rate_no_constraints_provided(self, conn_with_episodes):
        """No constraints list -> extraction rate computed as 0."""
        gold = [
            {
                "episode_id": "ep-002",
                "verified_mode": "Implement",
                "verified_reaction_label": "correct",
                "constraint_should_extract": True,
            },
        ]

        report = compute_metrics(gold, conn_with_episodes, constraints=None)

        # 0 of 1 found
        assert report.constraint_extraction_rate == pytest.approx(0.0)


class TestThresholds:
    """Tests for threshold checking."""

    def test_thresholds_all_pass(self, conn_with_episodes):
        """Metrics above thresholds -> all thresholds pass."""
        gold = [
            {
                "episode_id": "ep-001",
                "verified_mode": "Implement",
                "verified_reaction_label": "approve",
                "constraint_should_extract": True,
            },
        ]
        constraints = [
            {
                "constraint_id": "c-1",
                "text": "test",
                "examples": [{"episode_id": "ep-001", "violation_description": ""}],
            },
        ]

        report = compute_metrics(gold, conn_with_episodes, constraints=constraints)

        # 100% mode, 100% reaction, 0.9 confidence, 100% constraint rate
        assert report.thresholds_met["mode_accuracy"] is True
        assert report.thresholds_met["reaction_avg_confidence"] is True
        assert report.thresholds_met["constraint_extraction_rate"] is True

    def test_thresholds_fail_on_none(self, conn_with_episodes):
        """None metrics result in threshold = False."""
        report = compute_metrics([], conn_with_episodes)

        assert report.thresholds_met["mode_accuracy"] is False
        assert report.thresholds_met["reaction_avg_confidence"] is False
        assert report.thresholds_met["constraint_extraction_rate"] is False

    def test_thresholds_below(self, conn_with_episodes):
        """Metrics below thresholds -> fail."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Explore", "verified_reaction_label": "block"},
            {"episode_id": "ep-002", "verified_mode": "Plan", "verified_reaction_label": "approve"},
        ]

        report = compute_metrics(gold, conn_with_episodes)

        # 0/2 mode matches -> 0%, below 85% threshold
        assert report.thresholds_met["mode_accuracy"] is False


class TestPerBreakdowns:
    """Tests for per-mode and per-reaction accuracy breakdowns."""

    def test_per_mode_accuracy(self, conn_with_episodes):
        """Per-mode breakdown shows accuracy per mode."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-002", "verified_mode": "Implement", "verified_reaction_label": "correct"},
            {"episode_id": "ep-003", "verified_mode": "Plan", "verified_reaction_label": "approve"},  # Pipeline: Explore
        ]

        report = compute_metrics(gold, conn_with_episodes)

        # Implement: 2/2 = 1.0, Plan: 0/1 = 0.0
        assert report.per_mode_accuracy["Implement"] == pytest.approx(1.0)
        assert report.per_mode_accuracy["Plan"] == pytest.approx(0.0)

    def test_per_reaction_accuracy(self, conn_with_episodes):
        """Per-reaction breakdown shows accuracy per reaction label."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-002", "verified_mode": "Implement", "verified_reaction_label": "correct"},
            {"episode_id": "ep-003", "verified_mode": "Explore", "verified_reaction_label": "block"},  # Pipeline: approve
        ]

        report = compute_metrics(gold, conn_with_episodes)

        # approve: 1/1 = 1.0, correct: 1/1 = 1.0, block: 0/1 = 0.0
        assert report.per_reaction_accuracy["approve"] == pytest.approx(1.0)
        assert report.per_reaction_accuracy["correct"] == pytest.approx(1.0)
        assert report.per_reaction_accuracy["block"] == pytest.approx(0.0)


class TestFormatReport:
    """Tests for format_report output."""

    def test_format_report_readable(self, conn_with_episodes):
        """format_report produces human-readable text with PASS/FAIL."""
        gold = [
            {
                "episode_id": "ep-001",
                "verified_mode": "Implement",
                "verified_reaction_label": "approve",
                "constraint_should_extract": True,
            },
        ]
        constraints = [
            {
                "constraint_id": "c-1",
                "text": "test",
                "examples": [{"episode_id": "ep-001", "violation_description": ""}],
            },
        ]

        report = compute_metrics(gold, conn_with_episodes, constraints=constraints)
        text = format_report(report)

        assert "Quality Metrics Report" in text
        assert "Mode accuracy" in text
        assert "PASS" in text
        assert "Sample size: 1" in text

    def test_format_report_with_none_metrics(self, conn_with_episodes):
        """format_report handles None metrics gracefully."""
        report = compute_metrics([], conn_with_episodes)
        text = format_report(report)

        assert "N/A" in text
        assert "FAIL" in text
        assert "Sample size: 0" in text

    def test_format_report_with_per_breakdowns(self, conn_with_episodes):
        """format_report includes per-mode and per-reaction breakdowns."""
        gold = [
            {"episode_id": "ep-001", "verified_mode": "Implement", "verified_reaction_label": "approve"},
            {"episode_id": "ep-003", "verified_mode": "Explore", "verified_reaction_label": "approve"},
        ]

        report = compute_metrics(gold, conn_with_episodes)
        text = format_report(report)

        assert "Per-Mode Accuracy" in text
        assert "Per-Reaction Accuracy" in text
        assert "Implement" in text
        assert "Explore" in text
