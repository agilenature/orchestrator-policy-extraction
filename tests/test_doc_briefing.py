"""Tests for the doc briefing delivery pipeline (Phase 21-03).

Covers:
- GovernorDaemon._query_relevant_docs() -- DuckDB doc_index queries
- ConstraintBriefing.relevant_docs field
- GovernorDaemon.get_briefing() integration with doc_index
- /api/check endpoint returning relevant_docs
- session_start.py printing relevant docs with [OPE] prefix

Uses temporary DuckDB files for daemon/server tests (daemon opens its own
connection, so in-memory databases cannot be shared).  Session start tests
use monkeypatching to control _post_json responses.
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from typing import Any

import duckdb
import pytest

from src.pipeline.live.bus.doc_schema import create_doc_schema
from src.pipeline.live.bus.schema import create_bus_schema
from src.pipeline.live.governor.briefing import ConstraintBriefing
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doc_db(tmp_path: Path) -> str:
    """Create a temporary DuckDB file with doc_index table.

    Returns the path to the database file.  The write connection is closed
    before returning so the daemon can open its own connection.
    """
    db_path = str(tmp_path / "test.db")
    conn = duckdb.connect(db_path)
    create_doc_schema(conn)
    conn.close()
    return db_path


@pytest.fixture
def doc_db_populated(tmp_path: Path) -> str:
    """Create a temp DuckDB with doc_index populated with test rows.

    Contains:
      - docs/always.md (always-show, manual, 1.0)
      - docs/high.md (deposit-not-detect, regex, 0.9)
      - docs/medium.md (ground-truth-pointer, keyword, 0.6)
    """
    db_path = str(tmp_path / "test_pop.db")
    conn = duckdb.connect(db_path)
    create_doc_schema(conn)
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
        "extracted_confidence, description_cache, content_hash) VALUES "
        "('docs/always.md', 'always-show', 'manual', 1.0, 'Always relevant doc', 'h1'), "
        "('docs/high.md', 'deposit-not-detect', 'regex', 0.9, 'High confidence', 'h2'), "
        "('docs/medium.md', 'ground-truth-pointer', 'keyword', 0.6, 'Medium confidence', 'h3')"
    )
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Daemon tests: _query_relevant_docs
# ---------------------------------------------------------------------------


class TestQueryRelevantDocs:
    """Tests for GovernorDaemon._query_relevant_docs()."""

    def test_empty_table(self, doc_db: str) -> None:
        """Daemon with empty doc_index returns []."""
        daemon = GovernorDaemon(db_path=doc_db)
        assert daemon._query_relevant_docs() == []

    def test_no_table(self, tmp_path: Path) -> None:
        """Daemon with DB that has no doc_index table returns [] (pre-Phase-21 fallback)."""
        db_path = str(tmp_path / "no_doc_index.db")
        conn = duckdb.connect(db_path)
        # Create some other table, but NOT doc_index
        conn.execute("CREATE TABLE other (id INTEGER)")
        conn.close()
        daemon = GovernorDaemon(db_path=db_path)
        assert daemon._query_relevant_docs() == []

    def test_always_show_first(self, doc_db_populated: str) -> None:
        """Always-show docs appear before regular docs regardless of confidence."""
        daemon = GovernorDaemon(db_path=doc_db_populated)
        docs = daemon._query_relevant_docs()
        assert len(docs) == 3
        assert docs[0]["ccd_axis"] == "always-show"
        assert docs[0]["doc_path"] == "docs/always.md"

    def test_confidence_ordering(self, tmp_path: Path) -> None:
        """Docs are ordered by extracted_confidence DESC (after always-show)."""
        db_path = str(tmp_path / "confidence.db")
        conn = duckdb.connect(db_path)
        create_doc_schema(conn)
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
            "extracted_confidence, content_hash) VALUES "
            "('docs/low.md', 'axis-a', 'regex', 0.3, 'ha'), "
            "('docs/high.md', 'axis-b', 'regex', 0.9, 'hb'), "
            "('docs/mid.md', 'axis-c', 'regex', 0.6, 'hc')"
        )
        conn.close()
        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()
        assert len(docs) == 3
        assert docs[0]["doc_path"] == "docs/high.md"
        assert docs[1]["doc_path"] == "docs/mid.md"
        assert docs[2]["doc_path"] == "docs/low.md"

    def test_dedup_by_path(self, tmp_path: Path) -> None:
        """Same doc_path with 2 axes returns only 1 result (highest priority wins)."""
        db_path = str(tmp_path / "dedup.db")
        conn = duckdb.connect(db_path)
        create_doc_schema(conn)
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
            "extracted_confidence, content_hash) VALUES "
            "('docs/multi.md', 'always-show', 'manual', 1.0, 'ha'), "
            "('docs/multi.md', 'deposit-not-detect', 'regex', 0.7, 'hb')"
        )
        conn.close()
        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()
        assert len(docs) == 1
        assert docs[0]["doc_path"] == "docs/multi.md"
        # Should get the always-show entry (higher priority)
        assert docs[0]["ccd_axis"] == "always-show"

    def test_max_3(self, tmp_path: Path) -> None:
        """Insert 5 non-unclassified docs, verify max 3 returned."""
        db_path = str(tmp_path / "max3.db")
        conn = duckdb.connect(db_path)
        create_doc_schema(conn)
        for i in range(5):
            conn.execute(
                "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
                "extracted_confidence, content_hash) VALUES (?, ?, 'regex', ?, ?)",
                [f"docs/doc{i}.md", f"axis-{i}", 0.5 + i * 0.1, f"hash{i}"],
            )
        conn.close()
        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()
        assert len(docs) == 3

    def test_excludes_unclassified(self, tmp_path: Path) -> None:
        """Unclassified docs are excluded from results."""
        db_path = str(tmp_path / "unclass.db")
        conn = duckdb.connect(db_path)
        create_doc_schema(conn)
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
            "extracted_confidence, content_hash) VALUES "
            "('docs/good.md', 'deposit-not-detect', 'regex', 0.8, 'h1'), "
            "('docs/bad.md', 'unknown', 'unclassified', 0.1, 'h2')"
        )
        conn.close()
        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()
        assert len(docs) == 1
        assert docs[0]["doc_path"] == "docs/good.md"

    def test_fail_open_invalid_path(self) -> None:
        """Daemon with invalid db_path returns [] (fail-open)."""
        daemon = GovernorDaemon(db_path="/nonexistent/path/to.db")
        assert daemon._query_relevant_docs() == []


# ---------------------------------------------------------------------------
# Briefing model tests
# ---------------------------------------------------------------------------


class TestBriefingModel:
    """Tests for ConstraintBriefing relevant_docs field."""

    def test_constraint_briefing_has_relevant_docs(self) -> None:
        """ConstraintBriefing() defaults to relevant_docs=[]."""
        briefing = ConstraintBriefing()
        assert briefing.relevant_docs == []

    def test_get_briefing_includes_docs(self, doc_db_populated: str) -> None:
        """GovernorDaemon.get_briefing() with populated doc_index includes relevant_docs."""
        daemon = GovernorDaemon(db_path=doc_db_populated)
        briefing = daemon.get_briefing(
            session_id="test-sid", run_id="test-rid"
        )
        assert isinstance(briefing, ConstraintBriefing)
        assert len(briefing.relevant_docs) == 3
        assert briefing.relevant_docs[0]["ccd_axis"] == "always-show"


# ---------------------------------------------------------------------------
# Server /api/check tests
# ---------------------------------------------------------------------------


class TestCheckEndpoint:
    """Tests for /api/check returning relevant_docs."""

    def test_check_response_includes_relevant_docs(self, tmp_path: Path) -> None:
        """POST /api/check with populated doc_index returns relevant_docs."""
        from starlette.testclient import TestClient
        from src.pipeline.live.bus.server import create_app

        db_path = str(tmp_path / "server_check.db")
        conn = duckdb.connect(db_path)
        create_bus_schema(conn)
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
            "extracted_confidence, content_hash) VALUES "
            "('docs/guide.md', 'always-show', 'manual', 1.0, 'h1')"
        )
        conn.close()

        app = create_app(db_path=db_path)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post(
            "/api/check",
            json={"session_id": "s1", "run_id": "r1"},
        )
        body = response.json()
        assert "relevant_docs" in body
        assert len(body["relevant_docs"]) == 1
        assert body["relevant_docs"][0]["doc_path"] == "docs/guide.md"

    def test_check_response_empty_docs_fallback(self, tmp_path: Path) -> None:
        """POST /api/check with no doc_index data returns relevant_docs: []."""
        from starlette.testclient import TestClient
        from src.pipeline.live.bus.server import create_app

        db_path = str(tmp_path / "server_empty.db")
        conn = duckdb.connect(db_path)
        create_bus_schema(conn)
        conn.close()

        app = create_app(db_path=db_path)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post(
            "/api/check",
            json={"session_id": "s1", "run_id": "r1"},
        )
        body = response.json()
        assert "relevant_docs" in body
        assert body["relevant_docs"] == []


# ---------------------------------------------------------------------------
# Session start printing tests
# ---------------------------------------------------------------------------


class TestSessionStartPrinting:
    """Tests for session_start.py relevant docs output."""

    def _make_mock_post_json(
        self,
        relevant_docs: list[dict[str, Any]],
        constraints: list[dict[str, Any]] | None = None,
    ):
        """Create a mock _post_json that returns controlled responses."""
        def mock_post_json(path: str, payload: dict) -> dict:
            if path == "/api/register":
                return {
                    "status": "registered",
                    "session_id": payload.get("session_id", ""),
                    "run_id": payload.get("run_id", ""),
                }
            if path == "/api/check":
                return {
                    "constraints": constraints or [],
                    "interventions": [],
                    "epistemological_signals": [],
                    "relevant_docs": relevant_docs,
                }
            return {}
        return mock_post_json

    def test_prints_docs(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """session_start prints relevant docs with [OPE] prefix."""
        docs = [
            {"doc_path": "docs/guide.md", "ccd_axis": "always-show", "description_cache": "A guide"},
            {"doc_path": "docs/ref.md", "ccd_axis": "deposit-not-detect", "description_cache": "A reference"},
        ]
        mock = self._make_mock_post_json(relevant_docs=docs)
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._post_json", mock
        )
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._OPE_SESSION_ID", "test-sid"
        )
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._OPE_RUN_ID", "test-rid"
        )

        from src.pipeline.live.hooks.session_start import main
        main()

        captured = capsys.readouterr()
        assert "[OPE] 2 relevant doc(s) for this session:" in captured.out
        assert "[OPE]   - docs/guide.md (axis: always-show)" in captured.out
        assert "[OPE]     A guide" in captured.out
        assert "[OPE]   - docs/ref.md (axis: deposit-not-detect)" in captured.out
        assert "[OPE]     A reference" in captured.out

    def test_silent_no_docs(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """No docs output when relevant_docs is empty."""
        mock = self._make_mock_post_json(relevant_docs=[])
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._post_json", mock
        )
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._OPE_SESSION_ID", "test-sid"
        )
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._OPE_RUN_ID", "test-rid"
        )

        from src.pipeline.live.hooks.session_start import main
        main()

        captured = capsys.readouterr()
        assert "relevant doc" not in captured.out

    def test_truncates_description(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """Description longer than 80 chars is truncated in output."""
        long_desc = "A" * 100  # 100 chars
        docs = [
            {"doc_path": "docs/long.md", "ccd_axis": "axis-1", "description_cache": long_desc},
        ]
        mock = self._make_mock_post_json(relevant_docs=docs)
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._post_json", mock
        )
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._OPE_SESSION_ID", "test-sid"
        )
        monkeypatch.setattr(
            "src.pipeline.live.hooks.session_start._OPE_RUN_ID", "test-rid"
        )

        from src.pipeline.live.hooks.session_start import main
        main()

        captured = capsys.readouterr()
        # The description line should contain at most 80 A's
        desc_lines = [
            line for line in captured.out.split("\n")
            if "AAAA" in line
        ]
        assert len(desc_lines) == 1
        # Extract the description text after "[OPE]     "
        desc_text = desc_lines[0].strip().replace("[OPE]     ", "")
        assert len(desc_text) == 80
        assert desc_text == "A" * 80
