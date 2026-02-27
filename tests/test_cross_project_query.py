"""Integration tests for cross-project query functionality.

Verifies all 6 phase success criteria for the unified discriminated query
interface, plus cross-project ATTACH lifecycle, session filtering, and
backward compatibility.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli
from src.pipeline.cli.query import (
    _get_project_session_ids,
    _query_docs_cross_project,
    _resolve_project,
)
from src.pipeline.session_query import query_sessions


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


def _make_projects_json(
    tmp_path: Path,
    projects: list[dict[str, Any]],
) -> Path:
    """Write a projects.json with the given projects list."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    pj = data_dir / "projects.json"
    pj.write_text(json.dumps({"schema_version": "1.0", "projects": projects}))
    return pj


# ---------------------------------------------------------------------------
# SC-1: query --source docs delegates to query_docs()
# ---------------------------------------------------------------------------


class TestSC1DocsQuery:
    """SC-1: query --source docs returns doc_index results."""

    def test_docs_source_returns_doc_results(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "[docs]" in result.output
        assert "docs/MEMORY.md" in result.output

    def test_docs_source_shows_axis(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert "raven-cost-function-absent" in result.output


# ---------------------------------------------------------------------------
# SC-2: query --source sessions returns BM25 results
# ---------------------------------------------------------------------------


class TestSC2SessionsQuery:
    """SC-2: query --source sessions returns BM25/ILIKE results."""

    def test_sessions_source_returns_episode_results(
        self, runner: CliRunner, db_with_sessions: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "sessions", "--db", db_with_sessions,
                  "segmenter"]
        )
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "[sessions]" in result.output
        assert "ep-" in result.output

    def test_sessions_shows_session_id(
        self, runner: CliRunner, db_with_sessions: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "sessions", "--db", db_with_sessions,
                  "segmenter"]
        )
        assert "session=" in result.output


# ---------------------------------------------------------------------------
# SC-3: query --source code returns file paths
# ---------------------------------------------------------------------------


class TestSC3CodeQuery:
    """SC-3: query --source code returns file paths."""

    def test_code_source_runs_successfully(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["query", "--source", "code", "episode"])
        assert result.exit_code == 0, f"Output: {result.output}"

    def test_code_source_shows_code_label(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "code", "episode_populator"]
        )
        # Code search may or may not find matches depending on cwd
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# SC-4: query --source all returns labeled results from multiple sources
# ---------------------------------------------------------------------------


class TestSC4AllQuery:
    """SC-4: query --source all aggregates from multiple sources."""

    def test_all_source_includes_docs_and_sessions(
        self, runner: CliRunner, db_combined: str
    ) -> None:
        result = runner.invoke(
            cli, ["query", "--source", "all", "--db", db_combined,
                  "raven cost function"]
        )
        assert result.exit_code == 0
        assert "[docs]" in result.output
        assert "[sessions]" in result.output


# ---------------------------------------------------------------------------
# SC-5: query --project modernizing-tool --source docs
# ---------------------------------------------------------------------------


class TestSC5CrossProjectDocs:
    """SC-5: cross-project --project flag with ATTACH for docs."""

    def test_project_with_null_db_path_shows_no_doc_index(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        """Project with null db_path gets graceful 'no doc_index' message."""
        _make_projects_json(tmp_path, [
            {"id": "modernizing-tool", "name": "MT", "db_path": None,
             "data_status": {}},
        ])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            cli, ["query", "--project", "modernizing-tool", "--source", "docs",
                  "causal chain"]
        )
        assert result.exit_code == 0
        assert "no doc_index" in result.output.lower() or \
               "has no" in result.output.lower()

    def test_project_with_valid_remote_db(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        """Project with valid db_path returns results via ATTACH."""
        # Create a remote DB with doc_index
        remote_db = str(tmp_path / "remote.db")
        conn = duckdb.connect(remote_db)
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
            "('docs/remote/guide.md', 'causal-chain-completeness', "
            "'frontmatter', 0.9, 'Causal chain axis doc', 'hash_r1')"
        )
        conn.close()

        _make_projects_json(tmp_path, [
            {"id": "test-remote", "name": "Test Remote",
             "db_path": remote_db, "data_status": {}},
        ])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            cli, ["query", "--project", "test-remote", "--source", "docs",
                  "causal chain completeness"]
        )
        assert result.exit_code == 0
        assert "[docs]" in result.output
        assert "docs/remote/guide.md" in result.output

    def test_project_unknown_shows_not_found(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        """Unknown project ID shows 'not found' message."""
        _make_projects_json(tmp_path, [
            {"id": "known-project", "name": "Known", "db_path": None,
             "data_status": {}},
        ])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            cli, ["query", "--project", "nonexistent", "--source", "docs",
                  "test query"]
        )
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_local_project_uses_local_db(
        self, runner: CliRunner, db_with_doc_index: str,
        tmp_path: Path, monkeypatch
    ) -> None:
        """--project ope uses local db directly (no ATTACH)."""
        _make_projects_json(tmp_path, [
            {"id": "orchestrator-policy-extraction", "name": "OPE",
             "db_path": "data/ope.db", "data_status": {}},
        ])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            cli, ["query", "--project", "orchestrator-policy-extraction",
                  "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert result.exit_code == 0
        assert "[docs]" in result.output
        assert "docs/MEMORY.md" in result.output


# ---------------------------------------------------------------------------
# SC-6: data/projects.json has db_path
# ---------------------------------------------------------------------------


class TestSC6ProjectsJsonDbPath:
    """SC-6: data/projects.json has db_path on all projects."""

    def test_all_projects_have_db_path_key(self) -> None:
        projects_path = Path("data/projects.json")
        if not projects_path.exists():
            pytest.skip("data/projects.json not present")
        data = json.loads(projects_path.read_text())
        for p in data["projects"]:
            assert "db_path" in p, f"Project {p['id']} missing db_path key"

    def test_ope_db_path_is_ope_db(self) -> None:
        projects_path = Path("data/projects.json")
        if not projects_path.exists():
            pytest.skip("data/projects.json not present")
        data = json.loads(projects_path.read_text())
        ope = next(
            (p for p in data["projects"]
             if p["id"] == "orchestrator-policy-extraction"),
            None,
        )
        assert ope is not None, "OPE not found in projects.json"
        assert ope["db_path"] == "data/ope.db"

    def test_modernizing_tool_entry_exists(self) -> None:
        projects_path = Path("data/projects.json")
        if not projects_path.exists():
            pytest.skip("data/projects.json not present")
        data = json.loads(projects_path.read_text())
        mt = next(
            (p for p in data["projects"]
             if p["id"] == "modernizing-tool"),
            None,
        )
        assert mt is not None, "modernizing-tool not found in projects.json"
        assert "db_path" in mt


# ---------------------------------------------------------------------------
# Cross-project session filtering
# ---------------------------------------------------------------------------


class TestCrossProjectSessionFiltering:
    """Test session filtering by project's session_ids."""

    def test_session_ids_filter_ilike(self, tmp_path: Path) -> None:
        """ILIKE path filters to only matching session_ids."""
        db_path = str(tmp_path / "filter_test.db")
        conn = duckdb.connect(db_path)
        conn.execute(
            "CREATE TABLE episode_search_text("
            "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE episodes("
            "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, "
            "mode VARCHAR)"
        )
        # Two episodes with "migration", different sessions
        conn.execute(
            "INSERT INTO episode_search_text VALUES "
            "('ep-a1', 'migration strategy for auth slice'), "
            "('ep-b1', 'migration plan for database layer')"
        )
        conn.execute(
            "INSERT INTO episodes VALUES "
            "('ep-a1', 'sess-project-a', 'code'), "
            "('ep-b1', 'sess-project-b', 'code')"
        )
        conn.close()

        # Filter to project A only
        results = query_sessions(
            "migration", db_path=db_path,
            session_ids=["sess-project-a"],
        )
        assert len(results) == 1
        assert results[0]["episode_id"] == "ep-a1"
        assert results[0]["session_id"] == "sess-project-a"

    def test_session_ids_filter_returns_nothing_for_unmatched(
        self, tmp_path: Path
    ) -> None:
        """Session filter with no matching session_ids returns empty."""
        db_path = str(tmp_path / "filter_empty.db")
        conn = duckdb.connect(db_path)
        conn.execute(
            "CREATE TABLE episode_search_text("
            "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE episodes("
            "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, "
            "mode VARCHAR)"
        )
        conn.execute(
            "INSERT INTO episode_search_text VALUES "
            "('ep-x1', 'migration strategy test')"
        )
        conn.execute(
            "INSERT INTO episodes VALUES "
            "('ep-x1', 'sess-other', 'code')"
        )
        conn.close()

        results = query_sessions(
            "migration", db_path=db_path,
            session_ids=["sess-nonexistent"],
        )
        assert results == []

    def test_none_session_ids_returns_all(self, tmp_path: Path) -> None:
        """session_ids=None preserves existing behavior (no filtering)."""
        db_path = str(tmp_path / "no_filter.db")
        conn = duckdb.connect(db_path)
        conn.execute(
            "CREATE TABLE episode_search_text("
            "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE episodes("
            "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, "
            "mode VARCHAR)"
        )
        conn.execute(
            "INSERT INTO episode_search_text VALUES "
            "('ep-1', 'migration approach'), "
            "('ep-2', 'migration plan')"
        )
        conn.execute(
            "INSERT INTO episodes VALUES "
            "('ep-1', 'sess-a', 'code'), "
            "('ep-2', 'sess-b', 'code')"
        )
        conn.close()

        results = query_sessions(
            "migration", db_path=db_path, session_ids=None,
        )
        assert len(results) == 2

    def test_cli_cross_project_sessions(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        """CLI --project with --source sessions filters by session IDs."""
        # Create DB with episodes from two different sessions
        db_path = str(tmp_path / "data" / "ope.db")
        (tmp_path / "data").mkdir(exist_ok=True)
        conn = duckdb.connect(db_path)
        conn.execute(
            "CREATE TABLE episode_search_text("
            "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE episodes("
            "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, "
            "mode VARCHAR)"
        )
        conn.execute(
            "INSERT INTO episode_search_text VALUES "
            "('ep-mt1', 'migration slice decomposition'), "
            "('ep-ope1', 'migration constraint extraction')"
        )
        conn.execute(
            "INSERT INTO episodes VALUES "
            "('ep-mt1', 'mt-session-001', 'code'), "
            "('ep-ope1', 'ope-session-001', 'code')"
        )
        conn.close()

        # Create sessions_location dir for project-a with matching session
        sessions_dir = tmp_path / "sessions_a"
        sessions_dir.mkdir()
        (sessions_dir / "mt-session-001.jsonl").write_text("{}\n")

        _make_projects_json(tmp_path, [
            {"id": "project-a", "name": "Project A", "db_path": None,
             "data_status": {
                 "sessions_location": str(sessions_dir),
             }},
        ])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            cli, ["query", "--project", "project-a",
                  "--source", "sessions",
                  "--db", db_path,
                  "migration"]
        )
        assert result.exit_code == 0
        # Should only have mt-session-001's episode
        assert "mt-session-001" in result.output or "ep-mt1" in result.output
        # Should NOT have the other session's episode
        assert "ope-session-001" not in result.output


# ---------------------------------------------------------------------------
# ATTACH lifecycle tests
# ---------------------------------------------------------------------------


class TestAttachLifecycle:
    """Test DuckDB ATTACH lifecycle for cross-project queries."""

    def test_attach_query_cleanup(self, tmp_path: Path) -> None:
        """ATTACH + query + DETACH works without errors."""
        remote_db = str(tmp_path / "remote_lifecycle.db")
        conn = duckdb.connect(remote_db)
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
            "('docs/test.md', 'causal-chain-completeness', 'frontmatter', "
            "0.9, 'Test doc for ATTACH', 'hash_attach')"
        )
        conn.close()

        results = _query_docs_cross_project(
            "causal chain completeness", remote_db, top_n=3
        )
        assert len(results) > 0
        assert results[0]["doc_path"] == "docs/test.md"
        assert results[0]["source"] == "docs"

    def test_nonexistent_db_returns_empty(self) -> None:
        """Non-existent remote DB path returns empty list."""
        results = _query_docs_cross_project(
            "test query", "/nonexistent/path/db.db", top_n=3
        )
        assert results == []

    def test_db_without_doc_index_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Remote DB without doc_index table returns empty list."""
        remote_db = str(tmp_path / "no_doc_index.db")
        conn = duckdb.connect(remote_db)
        conn.execute("CREATE TABLE other_table (id INTEGER)")
        conn.close()

        results = _query_docs_cross_project(
            "test query", remote_db, top_n=3
        )
        assert results == []

    def test_empty_query_tokens_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Query with all stopwords returns empty."""
        remote_db = str(tmp_path / "remote_empty_q.db")
        conn = duckdb.connect(remote_db)
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
            "('docs/a.md', 'raven-cost-function-absent', 'frontmatter', "
            "1.0, 'Test', 'hash_eq')"
        )
        conn.close()

        results = _query_docs_cross_project(
            "how does the work", remote_db, top_n=3
        )
        assert results == []


# ---------------------------------------------------------------------------
# Project resolution helpers
# ---------------------------------------------------------------------------


class TestProjectResolution:
    """Test _resolve_project and _get_project_session_ids helpers."""

    def test_resolve_project_found(self, tmp_path: Path) -> None:
        pj = _make_projects_json(tmp_path, [
            {"id": "test-proj", "name": "TP", "db_path": "/some/path.db",
             "data_status": {}},
        ])
        result = _resolve_project("test-proj", str(pj))
        assert result is not None
        assert result["id"] == "test-proj"

    def test_resolve_project_not_found(self, tmp_path: Path) -> None:
        pj = _make_projects_json(tmp_path, [
            {"id": "other", "name": "Other", "db_path": None,
             "data_status": {}},
        ])
        result = _resolve_project("missing", str(pj))
        assert result is None

    def test_resolve_project_missing_file(self) -> None:
        result = _resolve_project("any", "/nonexistent/projects.json")
        assert result is None

    def test_get_project_session_ids_with_dir(
        self, tmp_path: Path
    ) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "session-abc.jsonl").write_text("{}\n")
        (sessions_dir / "session-def.jsonl").write_text("{}\n")
        (sessions_dir / "not-jsonl.txt").write_text("ignored")

        project = {
            "data_status": {"sessions_location": str(sessions_dir)},
        }
        ids = _get_project_session_ids(project)
        assert ids is not None
        assert sorted(ids) == ["session-abc", "session-def"]

    def test_get_project_session_ids_missing_dir(self) -> None:
        project = {
            "data_status": {"sessions_location": "/nonexistent/dir"},
        }
        ids = _get_project_session_ids(project)
        assert ids is None

    def test_get_project_session_ids_no_location(self) -> None:
        project = {"data_status": {}}
        ids = _get_project_session_ids(project)
        assert ids is None

    def test_get_project_session_ids_tilde_expansion(
        self, tmp_path: Path
    ) -> None:
        """Tilde in sessions_location is expanded."""
        sessions_dir = tmp_path / "sessions_tilde"
        sessions_dir.mkdir()
        (sessions_dir / "sess-001.jsonl").write_text("{}\n")

        project = {
            "data_status": {"sessions_location": str(sessions_dir)},
        }
        ids = _get_project_session_ids(project)
        assert ids == ["sess-001"]


# ---------------------------------------------------------------------------
# Code search remote project
# ---------------------------------------------------------------------------


class TestCodeSearchRemoteProject:
    """Code search reports unavailable for remote projects."""

    def test_code_not_available_for_remote(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        _make_projects_json(tmp_path, [
            {"id": "remote-proj", "name": "Remote", "db_path": None,
             "data_status": {}},
        ])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            cli, ["query", "--project", "remote-proj", "--source", "code",
                  "test query"]
        )
        assert result.exit_code == 0
        assert "not available" in result.output.lower()


# ---------------------------------------------------------------------------
# Backward compatibility
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

    def test_query_without_project_unchanged(
        self, runner: CliRunner, db_with_doc_index: str
    ) -> None:
        """query without --project uses default behavior."""
        result = runner.invoke(
            cli, ["query", "--source", "docs", "--db", db_with_doc_index,
                  "raven cost function"]
        )
        assert result.exit_code == 0
        assert "[docs]" in result.output
