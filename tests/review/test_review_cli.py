"""Integration tests for the review CLI command.

Tests the full flow: pool build -> sample -> present -> collect -> write,
using temporary DuckDB files and mocked constraints. Also tests edge
cases like empty pools and repeated review on single-instance pools.
"""

from __future__ import annotations

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.review.cli_test_helpers import seed_minimal_pool
from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def runner():
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def no_constraints(tmp_path):
    """Return path to a non-existent constraints file."""
    return str(tmp_path / "nonexistent_constraints.json")


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DuckDB with review schema only (empty pool)."""
    path = str(tmp_path / "test.db")
    conn = duckdb.connect(path)
    create_review_schema(conn)
    conn.close()
    return path


@pytest.fixture
def db_with_pool(tmp_path):
    """Create a temp DuckDB with review schema and one reviewable instance."""
    path = str(tmp_path / "pool.db")
    conn = duckdb.connect(path)
    create_review_schema(conn)
    seed_minimal_pool(conn)
    conn.close()
    return path


class TestReviewNextEmpty:
    """Tests for review next with empty pool."""

    def test_empty_pool_prints_all_reviewed(self, runner, db_path, no_constraints):
        """review next with empty pool prints 'All identification instances'."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["next", "--db", db_path, "--constraints", no_constraints],
        )

        assert result.exit_code == 0
        assert "All identification instances have been reviewed" in result.output


class TestReviewNextWithPool:
    """Tests for review next with a populated pool."""

    def test_presents_all_five_fields(self, runner, db_with_pool, no_constraints):
        """review next with one unreviewed instance presents all five fields."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["next", "--db", db_with_pool, "--constraints", no_constraints],
            input="accept\n\n",
        )

        assert result.exit_code == 0
        assert "IDENTIFICATION POINT:" in result.output
        assert "RAW DATA:" in result.output
        assert "DECISION MADE:" in result.output
        assert "DOWNSTREAM IMPACT:" in result.output
        assert "PROVENANCE:" in result.output

    def test_end_to_end_accept(self, runner, db_with_pool, no_constraints):
        """End-to-end: pool -> sample -> present -> accept -> row in DB."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["next", "--db", db_with_pool, "--constraints", no_constraints],
            input="accept\n\n",
        )

        assert result.exit_code == 0
        assert "Accepted -- review written" in result.output

        # Verify row was written
        conn = duckdb.connect(db_with_pool)
        count = conn.execute(
            "SELECT COUNT(*) FROM identification_reviews"
        ).fetchone()[0]
        assert count == 1

        row = conn.execute(
            "SELECT verdict FROM identification_reviews"
        ).fetchone()
        assert row[0] == "accept"
        conn.close()

    def test_end_to_end_reject_with_opinion(self, runner, db_with_pool, no_constraints):
        """End-to-end: reject with opinion writes row and shows routing hint."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["next", "--db", db_with_pool, "--constraints", no_constraints],
            input="reject\nWrong label\n",
        )

        assert result.exit_code == 0
        assert "Rejected -- review written" in result.output
        assert "Spec-correction candidate" in result.output

        conn = duckdb.connect(db_with_pool)
        row = conn.execute(
            "SELECT verdict, opinion FROM identification_reviews"
        ).fetchone()
        assert row[0] == "reject"
        assert row[1] == "Wrong label"
        conn.close()

    def test_reject_without_opinion_shows_tip(self, runner, db_with_pool, no_constraints):
        """Reject without opinion shows tip about spec-correction targets."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["next", "--db", db_with_pool, "--constraints", no_constraints],
            input="reject\n\n",
        )

        assert result.exit_code == 0
        assert "Tip:" in result.output

    def test_exhausted_pool_returns_all_reviewed(self, runner, db_with_pool, no_constraints):
        """After reviewing all instances, next run returns 'all reviewed'.

        The seeded pool produces 4 instances (L1-1, L1-2, L2-1, L2-2)
        from one events row. Review all of them, then verify the next
        invocation reports all reviewed.
        """
        from src.pipeline.cli.review import review_group

        cli_args = ["next", "--db", db_with_pool, "--constraints", no_constraints]

        # Review all instances in the pool
        for _ in range(4):
            result = runner.invoke(
                review_group,
                cli_args,
                input="accept\n\n",
            )
            assert result.exit_code == 0
            assert "Accepted" in result.output

        # Next invocation -- pool exhausted
        final = runner.invoke(review_group, cli_args)
        assert final.exit_code == 0
        assert "All identification instances have been reviewed" in final.output
