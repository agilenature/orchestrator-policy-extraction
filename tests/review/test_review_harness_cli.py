"""Integration tests for the review harness and review stats CLI commands.

Tests the full flow:
- review harness: all invariants passing exits 0
- review harness: specification_closure violation exits 2
- review stats: shows verdict distribution and layer coverage
"""

from __future__ import annotations

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def runner():
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DuckDB with review schema only."""
    path = str(tmp_path / "test.db")
    conn = duckdb.connect(path)
    create_review_schema(conn)
    conn.close()
    return path


@pytest.fixture
def memory_md(tmp_path):
    """Create a minimal MEMORY.md."""
    md = tmp_path / "MEMORY.md"
    md.write_text("# Memory\n\nNo entries.\n")
    return str(md)


def _seed_review(
    db_path: str,
    review_id: str,
    instance_id: str,
    verdict: str = "accept",
    opinion: str | None = None,
    layer: str = "L1",
    point_id: str = "L1-1",
    component: str = "TestComponent",
) -> None:
    """Insert a review row directly for testing."""
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        INSERT INTO identification_reviews (
            review_id, identification_instance_id, layer, point_id,
            pipeline_component, trigger_text, observation_state,
            action_taken, downstream_impact, provenance_pointer,
            verdict, opinion
        ) VALUES (?, ?, ?, ?, ?, 'trigger', 'obs', 'action', 'impact', 'prov', ?, ?)
        """,
        [review_id, instance_id, layer, point_id, component, verdict, opinion],
    )
    conn.close()


class TestReviewHarnessAllPassing:
    """review harness with all invariants passing."""

    def test_exits_zero_on_empty_db(self, runner, db_path, memory_md):
        """review harness exits 0 when database is empty."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["harness", "--db", db_path, "--memory-md", memory_md],
        )

        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_prints_pass_for_each_invariant(self, runner, db_path, memory_md):
        """review harness prints PASS for each invariant."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["harness", "--db", db_path, "--memory-md", memory_md],
        )

        assert result.exit_code == 0
        assert "at_most_once_verdict" in result.output
        assert "layer_coverage_monotonic" in result.output
        assert "specification_closure" in result.output
        assert "delta_retrieval" in result.output
        assert "nversion_consistency" in result.output

    def test_harness_with_clean_reviews(self, runner, db_path, memory_md):
        """review harness passes with properly routed reviews."""
        _seed_review(db_path, "rev-1", "inst-1", verdict="accept")

        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["harness", "--db", db_path, "--memory-md", memory_md],
        )

        assert result.exit_code == 0


class TestReviewHarnessWithViolation:
    """review harness with invariant violations."""

    def test_exits_two_on_specification_closure_violation(
        self, runner, db_path, memory_md
    ):
        """review harness exits 2 when specification_closure fails."""
        # Seed a rejected review with opinion but no memory_candidates row
        _seed_review(
            db_path,
            "rev-1",
            "inst-1",
            verdict="reject",
            opinion="Wrong label -- should be curiosity",
            component="ReactionLabeler",
        )

        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["harness", "--db", db_path, "--memory-md", memory_md],
        )

        assert result.exit_code == 2
        assert "specification_closure" in result.output
        assert "FAIL" in result.output

    def test_prints_violation_detail(self, runner, db_path, memory_md):
        """review harness prints violation details on failure."""
        _seed_review(
            db_path,
            "rev-1",
            "inst-1",
            verdict="reject",
            opinion="Wrong label",
            component="ReactionLabeler",
        )

        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["harness", "--db", db_path, "--memory-md", memory_md],
        )

        assert result.exit_code == 2
        assert "violations" in result.output


class TestReviewStats:
    """review stats command."""

    def test_no_reviews_shows_message(self, runner, db_path):
        """review stats with no reviews prints informational message."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["stats", "--db", db_path])

        assert result.exit_code == 0
        assert "No reviews found" in result.output

    def test_shows_verdict_distribution(self, runner, db_path):
        """review stats shows verdict distribution after reviews exist."""
        _seed_review(db_path, "rev-1", "inst-1", verdict="accept")
        _seed_review(
            db_path, "rev-2", "inst-2", verdict="reject", opinion="bad"
        )

        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["stats", "--db", db_path])

        assert result.exit_code == 0
        assert "Verdict Distribution" in result.output
        assert "accept" in result.output
        assert "reject" in result.output

    def test_shows_layer_coverage(self, runner, db_path):
        """review stats shows layer coverage."""
        _seed_review(db_path, "rev-1", "inst-1", layer="L1")
        _seed_review(db_path, "rev-2", "inst-2", layer="L2", point_id="L2-1")

        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["stats", "--db", db_path])

        assert result.exit_code == 0
        assert "Layer Coverage" in result.output
        assert "L1" in result.output
        assert "L2" in result.output
