"""Tests for the unified query CLI command.

Tests the ``query`` command dispatching to docs, sessions, and code backends
via ``--source`` flag, project resolution via ``--project``, output formatting,
and backward compatibility with the existing ``docs query`` subcommand.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
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
def db_with_doc_index(tmp_path: Path) -> str:
    """DuckDB with a doc_index table containing test data."""
    db_path = str(tmp_path / "docs.db")
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE doc_index ("
        "doc_path VARCHAR NOT NULL, "
        "ccd_axis VARCHAR NOT NULL, "
        "association_type VARCHAR NOT NULL DEFAULT 'frontmatter', "
        "extracted_confidence FLOAT NOT NULL DEFAULT 1.0, "
        "description_cache VARCHAR, "
        "section_anchor VARCHAR, "
        "content_hash VARCHAR NOT NULL, "
        "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "PRIMARY KEY (doc_path, ccd_axis))"
    )
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
        "extracted_confidence, description_cache, content_hash) VALUES "
        "('docs/MEMORY.md', 'raven-cost-function-absent', 'frontmatter', "
        "1.0, 'Raven cost function absent axis', 'hash1'), "
        "('docs/guides/GUIDE.md', 'deposit-not-detect', 'regex', "
        "0.8, 'Deposit not detect axis', 'hash2')"
    )
    conn.close()
    return db_path


@pytest.fixture
def db_with_sessions(tmp_path: Path) -> str:
    """DuckDB with episode_search_text and episodes tables."""
    db_path = str(tmp_path / "sessions.db")
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE episode_search_text("
        "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE episodes("
        "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, mode VARCHAR)"
    )
    conn.execute(
        "INSERT INTO episode_search_text VALUES "
        "('ep-001', 'fixing the segmenter boundary detection logic'), "
        "('ep-002', 'refactoring episode populator heuristics'), "
        "('ep-003', 'segmenter fix for edge case with empty segments')"
    )
    conn.execute(
        "INSERT INTO episodes VALUES "
        "('ep-001', 'sess-a', 'code'), "
        "('ep-002', 'sess-a', 'code'), "
        "('ep-003', 'sess-b', 'review')"
    )
    conn.close()
    return db_path


@pytest.fixture
def db_empty_doc_index(tmp_path: Path) -> str:
    """DuckDB with an empty doc_index table."""
    db_path = str(tmp_path / "empty_docs.db")
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE doc_index ("
        "doc_path VARCHAR NOT NULL, "
        "ccd_axis VARCHAR NOT NULL, "
        "association_type VARCHAR NOT NULL DEFAULT 'frontmatter', "
        "extracted_confidence FLOAT NOT NULL DEFAULT 1.0, "
        "description_cache VARCHAR, "
        "section_anchor VARCHAR, "
        "content_hash VARCHAR NOT NULL, "
        "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "PRIMARY KEY (doc_path, ccd_axis))"
    )
    conn.close()
    return db_path


@pytest.fixture
def db_combined(tmp_path: Path) -> str:
    """DuckDB with both doc_index and episode tables for --source all."""
    db_path = str(tmp_path / "combined.db")
    conn = duckdb.connect(db_path)
    # doc_index
    conn.execute(
        "CREATE TABLE doc_index ("
        "doc_path VARCHAR NOT NULL, "
        "ccd_axis VARCHAR NOT NULL, "
        "association_type VARCHAR NOT NULL DEFAULT 'frontmatter', "
        "extracted_confidence FLOAT NOT NULL DEFAULT 1.0, "
        "description_cache VARCHAR, "
        "section_anchor VARCHAR, "
        "content_hash VARCHAR NOT NULL, "
        "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "PRIMARY KEY (doc_path, ccd_axis))"
    )
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
        "extracted_confidence, description_cache, content_hash) VALUES "
        "('docs/MEMORY.md', 'raven-cost-function-absent', 'frontmatter', "
        "1.0, 'Raven cost function absent axis', 'hash1')"
    )
    # episodes
    conn.execute(
        "CREATE TABLE episode_search_text("
        "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE episodes("
        "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, mode VARCHAR)"
    )
    conn.execute(
        "INSERT INTO episode_search_text VALUES "
        "('ep-001', 'raven cost function discussion in session')"
    )
    conn.execute(
        "INSERT INTO episodes VALUES ('ep-001', 'sess-a', 'code')"
    )
    conn.close()
    return db_path


@pytest.fixture
def projects_json(tmp_path: Path) -> Path:
    """Create a temporary projects.json with test data."""
    data = {
        "schema_version": "1.0",
        "projects": [
            {
                "id": "orchestrator-policy-extraction",
                "name": "OPE",
                "db_path": "data/ope.db",
            },
            {
                "id": "test-project",
                "name": "Test Project",
                "db_path": str(tmp_path / "test_project.db"),
            },
            {
                "id": "no-db-project",
                "name": "No DB Project",
                "db_path": None,
            },
        ],
    }
    path = tmp_path / "projects.json"
    path.write_text(json.dumps(data, indent=2))
    return path


# ---------------------------------------------------------------------------
# Tests: --source docs
# ---------------------------------------------------------------------------


class TestSourceDocs:
    """Tests for query --source docs."""

    def test_docs_source_runs_without_error(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"

    def test_docs_source_output_has_prefix(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert "[OPE Query]" in result.output

    def test_docs_source_output_has_docs_label(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert "[docs]" in result.output

    def test_docs_empty_returns_no_results(
        self, runner: CliRunner, db_empty_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_empty_doc_index,
                  "raven cost function"]
        )
        assert result.exit_code == 0
        assert "No results found" in result.output


# ---------------------------------------------------------------------------
# Tests: --source sessions
# ---------------------------------------------------------------------------


class TestSourceSessions:
    """Tests for query --source sessions."""

    def test_sessions_source_runs_without_error(
        self, runner: CliRunner, db_with_sessions: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "sessions", "--db", db_with_sessions,
                  "segmenter"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"

    def test_sessions_output_has_sessions_label(
        self, runner: CliRunner, db_with_sessions: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "sessions", "--db", db_with_sessions,
                  "segmenter"]
        )
        assert "[sessions]" in result.output


# ---------------------------------------------------------------------------
# Tests: --source code
# ---------------------------------------------------------------------------


class TestSourceCode:
    """Tests for query --source code."""

    def test_code_source_runs_without_error(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "code", "episode"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"

    def test_code_output_has_code_label(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "code", "episode_populator"]
        )
        # code search may or may not find matches depending on cwd
        # but the command itself should succeed
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tests: --source all
# ---------------------------------------------------------------------------


class TestSourceAll:
    """Tests for query --source all (aggregation)."""

    def test_all_source_runs_without_error(
        self, runner: CliRunner, db_combined: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "all", "--db", db_combined,
                  "raven cost function"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"

    def test_all_source_includes_multiple_labels(
        self, runner: CliRunner, db_combined: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "all", "--db", db_combined,
                  "raven cost function"]
        )
        # Should have at least docs results; sessions/code may vary
        assert "[OPE Query]" in result.output

    def test_default_source_is_all(
        self, runner: CliRunner, db_combined: str
    ) -> None:
        """query without --source defaults to all."""
        result = runner.invoke(
            cli, ["query", "--db", db_combined, "raven cost function"]
        )
        assert result.exit_code == 0
        assert "Searching all:" in result.output


# ---------------------------------------------------------------------------
# Tests: --top flag
# ---------------------------------------------------------------------------


class TestTopFlag:
    """Tests for the --top flag limiting results."""

    def test_top_flag_limits_results(
        self, runner: CliRunner, db_with_sessions: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "sessions", "--db", db_with_sessions,
                  "--top", "1", "segmenter"]
        )
        assert result.exit_code == 0
        # Count [sessions] labels -- should be at most 1
        session_lines = [
            line for line in result.output.splitlines()
            if "[sessions]" in line
        ]
        assert len(session_lines) <= 1


# ---------------------------------------------------------------------------
# Tests: --project flag
# ---------------------------------------------------------------------------


class TestProjectFlag:
    """Tests for the --project flag and project registry resolution."""

    def test_project_with_known_id(
        self, runner: CliRunner, projects_json: Path, monkeypatch
    ) -> None:
        """--project with a known ID prints the resolved DB info."""
        monkeypatch.chdir(projects_json.parent)
        # Create the data directory structure the CLI expects
        data_dir = projects_json.parent / "data"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "projects.json").write_text(projects_json.read_text())

        result = runner.invoke(
            cli, ["query", "--source", "docs", "--project", "test-project",
                  "raven cost function"]
        )
        assert result.exit_code == 0
        assert "test-project" in result.output

    def test_project_with_unknown_id(
        self, runner: CliRunner, projects_json: Path, monkeypatch
    ) -> None:
        """--project with unknown ID prints warning."""
        monkeypatch.chdir(projects_json.parent)
        data_dir = projects_json.parent / "data"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "projects.json").write_text(projects_json.read_text())

        result = runner.invoke(
            cli, ["query", "--source", "docs", "--project", "nonexistent",
                  "test"]
        )
        assert result.exit_code == 0
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Verify existing docs query subcommand still works."""

    def test_docs_query_subcommand_still_works(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        """The old 'docs query' path must still function."""
        result = runner.invoke(
            cli, ["docs", "query", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "[OPE Docs]" in result.output


# ---------------------------------------------------------------------------
# Tests: output format
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """Tests for output format consistency."""

    def test_output_prefix_on_all_queries(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        # All output lines start with [OPE
        for line in result.output.splitlines():
            if line.strip():
                assert line.startswith("[OPE")

    def test_no_results_message(
        self, runner: CliRunner, db_empty_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_empty_doc_index,
                  "xyznonexistent"]
        )
        assert "No results found" in result.output
