"""Tests for the wisdom CLI subcommands.

Tests wisdom ingest, check-scope, reindex, and list subcommands using
Click's CliRunner for isolated invocation with tmp_path DuckDB databases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_json(tmp_path: Path) -> Path:
    """Create a temporary JSON file with valid wisdom entries."""
    entries = [
        {
            "entity_type": "breakthrough",
            "title": "Staging table upsert pattern",
            "description": "Use temp staging table for DuckDB MERGE operations",
            "context_tags": ["duckdb", "upsert"],
            "scope_paths": ["src/pipeline/storage/"],
            "confidence": 0.9,
            "source_document": "REUSABLE_KNOWLEDGE_GUIDE.md",
            "source_phase": 7,
        },
        {
            "entity_type": "scope_decision",
            "title": "CLI uses click groups",
            "description": "All CLI subcommands organized as click groups",
            "scope_paths": ["src/pipeline/cli/"],
        },
        {
            "entity_type": "dead_end",
            "title": "pybreaker for circuit breaker",
            "description": "pybreaker tracks consecutive failures, not percentage-based rate",
            "context_tags": ["circuit-breaker"],
        },
    ]
    path = tmp_path / "test_wisdom.json"
    path.write_text(json.dumps(entries))
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_wisdom_list_empty_db(runner: CliRunner, tmp_path: Path) -> None:
    """List on an empty database should exit 0 and report no entities."""
    db = str(tmp_path / "empty.db")
    result = runner.invoke(cli, ["wisdom", "list", "--db", db])
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
    assert "No wisdom entities found" in result.output


def test_wisdom_ingest_valid_file(
    runner: CliRunner, tmp_path: Path, sample_json: Path
) -> None:
    """Ingest a valid JSON file and verify output contains Added count."""
    db = str(tmp_path / "ingest.db")
    result = runner.invoke(cli, ["wisdom", "ingest", str(sample_json), "--db", db])
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
    assert "Added: 3" in result.output
    assert "Updated: 0" in result.output
    assert "Skipped: 0" in result.output


def test_wisdom_ingest_missing_file(runner: CliRunner, tmp_path: Path) -> None:
    """Ingest with a non-existent file path should produce a non-zero exit."""
    db = str(tmp_path / "missing.db")
    missing = str(tmp_path / "does_not_exist.json")
    result = runner.invoke(cli, ["wisdom", "ingest", missing, "--db", db])
    assert result.exit_code != 0


def test_wisdom_check_scope_no_match(runner: CliRunner, tmp_path: Path) -> None:
    """Check-scope with no matching scope decisions should exit 0 with message."""
    db = str(tmp_path / "scope.db")
    result = runner.invoke(
        cli, ["wisdom", "check-scope", "nonexistent/path/", "--db", db]
    )
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
    assert "No scope decisions found" in result.output


def test_wisdom_reindex_empty(runner: CliRunner, tmp_path: Path) -> None:
    """Reindex on an empty wisdom table should exit 0 with confirmation."""
    db = str(tmp_path / "reindex.db")
    # Create the wisdom table first by instantiating a store
    from src.pipeline.wisdom.store import WisdomStore

    WisdomStore(Path(db))

    result = runner.invoke(cli, ["wisdom", "reindex", "--db", db])
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
    assert "rebuilt" in result.output.lower()


def test_wisdom_list_after_ingest(
    runner: CliRunner, tmp_path: Path, sample_json: Path
) -> None:
    """List after ingesting entries shows entity titles and types."""
    db = str(tmp_path / "list_after.db")
    # Ingest first
    runner.invoke(cli, ["wisdom", "ingest", str(sample_json), "--db", db])

    # List all
    result = runner.invoke(cli, ["wisdom", "list", "--db", db])
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
    assert "[breakthrough]" in result.output
    assert "[scope_decision]" in result.output
    assert "[dead_end]" in result.output
    assert "Staging table upsert pattern" in result.output


def test_wisdom_list_filter_by_type(
    runner: CliRunner, tmp_path: Path, sample_json: Path
) -> None:
    """List --type filters to a specific entity type."""
    db = str(tmp_path / "filter.db")
    runner.invoke(cli, ["wisdom", "ingest", str(sample_json), "--db", db])

    result = runner.invoke(cli, ["wisdom", "list", "--type", "breakthrough", "--db", db])
    assert result.exit_code == 0
    assert "[breakthrough]" in result.output
    assert "[dead_end]" not in result.output
    assert "[scope_decision]" not in result.output


def test_wisdom_check_scope_with_match(
    runner: CliRunner, tmp_path: Path, sample_json: Path
) -> None:
    """Check-scope with a matching path and no constraint violations exits 0."""
    db = str(tmp_path / "scope_match.db")
    runner.invoke(cli, ["wisdom", "ingest", str(sample_json), "--db", db])

    # Create empty constraints to ensure no violations
    empty_constraints = tmp_path / "empty_constraints.json"
    empty_constraints.write_text("[]")

    result = runner.invoke(
        cli,
        [
            "wisdom", "check-scope", "src/pipeline/cli/",
            "--db", db,
            "--constraints", str(empty_constraints),
        ],
    )
    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
    assert "No violations found" in result.output
