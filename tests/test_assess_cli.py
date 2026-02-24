"""Tests for assessment CLI commands (Phase 17, Plan 02).

Covers:
- list-scenarios with no entries
- list-scenarios with entries
- list-scenarios with level filter
- annotate-scenarios updates wisdom
- annotate-scenarios skip
- annotate-scenarios quit
- assess group registered under intelligence
"""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.assess import assess_group
from src.pipeline.cli.intelligence import intelligence_group


def _create_test_db(db_path: str, entries: list[tuple] | None = None) -> None:
    """Create a test DuckDB with project_wisdom table and optional entries.

    Args:
        db_path: Path to the DuckDB file.
        entries: List of (wisdom_id, entity_type, title, description,
                 scenario_seed, ddf_target_level) tuples.
    """
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_wisdom (
            wisdom_id VARCHAR PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            description TEXT NOT NULL,
            scenario_seed TEXT,
            ddf_target_level INTEGER
        )
    """)
    # Create assessment tables (needed for annotate-scenarios schema check)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assessment_te_sessions (
            te_id VARCHAR PRIMARY KEY
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assessment_baselines (
            scenario_id VARCHAR PRIMARY KEY
        )
    """)
    if entries:
        for entry in entries:
            conn.execute(
                "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
                list(entry),
            )
    conn.close()


@pytest.fixture
def tmp_db(tmp_path):
    """Return path to a temporary DuckDB file."""
    return str(tmp_path / "test.db")


@pytest.fixture
def runner():
    """Click test runner."""
    return CliRunner()


# ── Test 1: list-scenarios with no entries ──


def test_list_scenarios_empty(runner, tmp_db):
    """Empty project_wisdom shows 0 in summary."""
    _create_test_db(tmp_db)

    result = runner.invoke(assess_group, ["list-scenarios", "--db", tmp_db])
    assert result.exit_code == 0
    assert "0 annotated" in result.output
    assert "0 unannotated" in result.output


# ── Test 2: list-scenarios with entries ──


def test_list_scenarios_with_entries(runner, tmp_db):
    """Shows annotated entries correctly."""
    _create_test_db(
        tmp_db,
        entries=[
            ("w-001", "dead_end", "Deadlock bug", "Desc one", None, 3),
            ("w-002", "breakthrough", "Stream insight", "Desc two", "seed", 1),
            ("w-003", "scope_decision", "DB choice", "Desc three", None, None),
        ],
    )

    result = runner.invoke(assess_group, ["list-scenarios", "--db", tmp_db])
    assert result.exit_code == 0
    assert "2 annotated" in result.output
    assert "1 unannotated" in result.output
    assert "dead_end" in result.output
    assert "breakthrough" in result.output
    assert "Deadlock bug" in result.output


# ── Test 3: list-scenarios with level filter ──


def test_list_scenarios_level_filter(runner, tmp_db):
    """--level 3 only shows L3 entries."""
    _create_test_db(
        tmp_db,
        entries=[
            ("w-001", "dead_end", "L3 entry", "Desc", None, 3),
            ("w-002", "breakthrough", "L1 entry", "Desc", None, 1),
            ("w-003", "dead_end", "Another L3", "Desc", None, 3),
        ],
    )

    result = runner.invoke(assess_group, ["list-scenarios", "--db", tmp_db, "--level", "3"])
    assert result.exit_code == 0
    assert "2 annotated" in result.output
    assert "L3 entry" in result.output
    assert "Another L3" in result.output
    assert "L1 entry" not in result.output


# ── Test 4: annotate-scenarios updates wisdom ──


def test_annotate_scenarios_updates_wisdom(runner, tmp_db):
    """CliRunner input assigns level and seed to project_wisdom."""
    _create_test_db(
        tmp_db,
        entries=[
            ("w-unann", "dead_end", "Unannotated", "Description text", None, None),
        ],
    )

    # Input: level 3, then seed "some seed text"
    result = runner.invoke(
        assess_group,
        ["annotate-scenarios", "--db", tmp_db],
        input="3\nsome seed text\n",
    )
    assert result.exit_code == 0
    assert "1 entries annotated" in result.output

    # Verify the update in the database
    conn = duckdb.connect(tmp_db, read_only=True)
    row = conn.execute(
        "SELECT ddf_target_level, scenario_seed FROM project_wisdom WHERE wisdom_id = 'w-unann'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 3
    assert row[1] == "some seed text"


# ── Test 5: annotate-scenarios skip ──


def test_annotate_scenarios_skip(runner, tmp_db):
    """Input 's' skips the entry without annotation."""
    _create_test_db(
        tmp_db,
        entries=[
            ("w-skip", "dead_end", "Skippable", "Description", None, None),
        ],
    )

    result = runner.invoke(
        assess_group,
        ["annotate-scenarios", "--db", tmp_db],
        input="s\n",
    )
    assert result.exit_code == 0
    assert "0 entries annotated" in result.output

    # Entry should remain unannotated
    conn = duckdb.connect(tmp_db, read_only=True)
    row = conn.execute(
        "SELECT ddf_target_level FROM project_wisdom WHERE wisdom_id = 'w-skip'"
    ).fetchone()
    conn.close()
    assert row[0] is None


# ── Test 6: annotate-scenarios quit ──


def test_annotate_scenarios_quit(runner, tmp_db):
    """Input 'q' stops processing."""
    _create_test_db(
        tmp_db,
        entries=[
            ("w-quit1", "dead_end", "First", "Desc", None, None),
            ("w-quit2", "dead_end", "Second", "Desc", None, None),
        ],
    )

    result = runner.invoke(
        assess_group,
        ["annotate-scenarios", "--db", tmp_db],
        input="q\n",
    )
    assert result.exit_code == 0
    assert "Quit" in result.output

    # Neither should be annotated
    conn = duckdb.connect(tmp_db, read_only=True)
    rows = conn.execute(
        "SELECT ddf_target_level FROM project_wisdom WHERE ddf_target_level IS NOT NULL"
    ).fetchall()
    conn.close()
    assert len(rows) == 0


# ── Test 7: assess group registered under intelligence ──


def test_assess_group_registered_under_intelligence(runner):
    """intelligence assess --help works."""
    result = runner.invoke(intelligence_group, ["assess", "--help"])
    assert result.exit_code == 0
    assert "Assessment scenario management" in result.output
    assert "annotate-scenarios" in result.output
    assert "list-scenarios" in result.output
