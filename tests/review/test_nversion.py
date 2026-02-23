"""Tests for N-version consistency check.

Tests NVersionConsistency which validates that accepted memory_candidates
entries have corresponding MEMORY.md counterparts.
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.review.nversion import NVersionConsistency
from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def conn():
    """In-memory DuckDB with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    yield c
    c.close()


@pytest.fixture
def memory_md_with_axes(tmp_path):
    """Create a MEMORY.md with known CCD axes."""
    md = tmp_path / "MEMORY.md"
    md.write_text(
        "# Memory\n\n"
        "## Entry One\n\n"
        "**CCD axis:** `deposit-not-detect`\n"
        "**Scope rule:** Everything deposits.\n\n"
        "## Entry Two\n\n"
        "**CCD axis:** `identity-firewall`\n"
        "**Scope rule:** Generator != validator.\n"
    )
    return str(md)


@pytest.fixture
def empty_memory_md(tmp_path):
    """Create an empty MEMORY.md."""
    md = tmp_path / "MEMORY.md"
    md.write_text("# Memory\n\nNo entries yet.\n")
    return str(md)


class TestNVersionConsistencyCheck:
    """Tests for NVersionConsistency.check()."""

    def test_passes_when_all_axes_present_in_memory_md(
        self, conn, memory_md_with_axes
    ):
        """Passes when all accepted axes appear in MEMORY.md."""
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status)
            VALUES ('mc-1', 'deposit-not-detect', 'scope', 'flood', 'validated')
            """
        )

        checker = NVersionConsistency(conn, memory_md_with_axes)
        result = checker.check()

        assert result.passed is True
        assert result.invariant_name == "nversion_consistency"
        assert len(result.violations) == 0

    def test_passes_on_empty_candidates(self, conn, memory_md_with_axes):
        """Passes vacuously when no accepted candidates exist."""
        checker = NVersionConsistency(conn, memory_md_with_axes)
        result = checker.check()

        assert result.passed is True

    def test_passes_when_pending_candidates_not_in_memory_md(
        self, conn, memory_md_with_axes
    ):
        """Pending candidates are not checked (only validated ones are)."""
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status)
            VALUES ('mc-1', 'nonexistent-axis', 'scope', 'flood', 'pending')
            """
        )

        checker = NVersionConsistency(conn, memory_md_with_axes)
        result = checker.check()

        assert result.passed is True

    def test_fails_when_accepted_axis_absent_from_memory_md(
        self, conn, memory_md_with_axes
    ):
        """Fails when an accepted entry's ccd_axis is absent from MEMORY.md."""
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status)
            VALUES ('mc-1', 'missing-axis-not-in-md', 'scope', 'flood', 'validated')
            """
        )

        checker = NVersionConsistency(conn, memory_md_with_axes)
        result = checker.check()

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0]["ccd_axis"] == "missing-axis-not-in-md"
        assert "MEMORY.md counterpart" in result.violations[0]["detail"]

    def test_handles_missing_memory_md(self, conn, tmp_path):
        """Returns violations when MEMORY.md does not exist."""
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status)
            VALUES ('mc-1', 'some-axis', 'scope', 'flood', 'validated')
            """
        )

        nonexistent = str(tmp_path / "nonexistent.md")
        checker = NVersionConsistency(conn, nonexistent)
        result = checker.check()

        assert result.passed is False
        assert len(result.violations) == 1


class TestParseMemoryMdAxes:
    """Tests for _parse_memory_md_axes()."""

    def test_extracts_axes_from_standard_format(
        self, conn, memory_md_with_axes
    ):
        """Correctly extracts axes from **CCD axis:** `name` format."""
        checker = NVersionConsistency(conn, memory_md_with_axes)
        axes = checker._parse_memory_md_axes()

        assert axes == {"deposit-not-detect", "identity-firewall"}

    def test_returns_empty_set_for_missing_file(self, conn, tmp_path):
        """Returns empty set when file does not exist."""
        checker = NVersionConsistency(
            conn, str(tmp_path / "nonexistent.md")
        )
        axes = checker._parse_memory_md_axes()

        assert axes == set()

    def test_returns_empty_set_for_no_axes(self, conn, empty_memory_md):
        """Returns empty set when file has no CCD axis entries."""
        checker = NVersionConsistency(conn, empty_memory_md)
        axes = checker._parse_memory_md_axes()

        assert axes == set()

    def test_handles_multiple_axes(self, conn, tmp_path):
        """Handles multiple axes in a single file."""
        md = tmp_path / "MEMORY.md"
        md.write_text(
            "**CCD axis:** `axis-one`\n"
            "**CCD axis:** `axis-two`\n"
            "**CCD axis:** `axis-three`\n"
        )

        checker = NVersionConsistency(conn, str(md))
        axes = checker._parse_memory_md_axes()

        assert axes == {"axis-one", "axis-two", "axis-three"}
