"""Tests for session query BM25/ILIKE search backend.

Tests both the BM25 path (with FTS index) and the ILIKE fallback path,
plus enrichment, fail-open behavior, and edge cases.
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.session_query import query_sessions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_fts(tmp_path):
    """DuckDB file with episode_search_text, episodes, and FTS index built."""
    db_path = str(tmp_path / "test.db")
    conn = duckdb.connect(db_path)
    _create_tables(conn)
    _insert_test_data(conn)
    conn.execute("INSTALL fts; LOAD fts;")
    conn.execute(
        "PRAGMA create_fts_index("
        "'episode_search_text', 'episode_id', 'search_text', "
        "stemmer='porter', stopwords='english', lower=1, overwrite=1"
        ")"
    )
    conn.close()
    return db_path


@pytest.fixture
def db_without_fts(tmp_path):
    """DuckDB file with episode_search_text and episodes but NO FTS index."""
    db_path = str(tmp_path / "test_no_fts.db")
    conn = duckdb.connect(db_path)
    _create_tables(conn)
    _insert_test_data(conn)
    conn.close()
    return db_path


@pytest.fixture
def db_empty(tmp_path):
    """DuckDB file with tables but no data."""
    db_path = str(tmp_path / "test_empty.db")
    conn = duckdb.connect(db_path)
    _create_tables(conn)
    conn.close()
    return db_path


def _create_tables(conn):
    """Create minimal episode_search_text and episodes tables."""
    conn.execute(
        "CREATE TABLE episode_search_text("
        "episode_id VARCHAR PRIMARY KEY, search_text VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE episodes("
        "episode_id VARCHAR PRIMARY KEY, session_id VARCHAR, mode VARCHAR)"
    )


def _insert_test_data(conn):
    """Insert test episodes for search testing."""
    episodes = [
        ("ep-001", "sess-a", "code", "fixing the segmenter boundary detection logic"),
        ("ep-002", "sess-a", "code", "refactoring episode populator heuristics"),
        ("ep-003", "sess-b", "review", "segmenter fix for edge case with empty segments"),
        ("ep-004", "sess-b", "code", "constraint extraction from validation failures"),
        ("ep-005", "sess-c", "explore", "DDF intelligence profile analysis pipeline"),
        ("ep-006", "sess-c", "code", "episode boundary detection in stream processor"),
        ("ep-007", "sess-d", "code", "memory candidate deposit from flame events"),
    ]
    for eid, sid, mode, text in episodes:
        conn.execute(
            "INSERT INTO episode_search_text VALUES (?, ?)", [eid, text]
        )
        conn.execute(
            "INSERT INTO episodes VALUES (?, ?, ?)", [eid, sid, mode]
        )


# ---------------------------------------------------------------------------
# BM25 path tests
# ---------------------------------------------------------------------------


class TestBM25Search:
    """Tests for the BM25 search path (FTS index present)."""

    def test_bm25_returns_matches(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        assert all(r["source"] == "sessions" for r in results)

    def test_bm25_match_reason_contains_bm25(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        for r in results:
            assert "bm25" in r["match_reason"]

    def test_bm25_match_reason_contains_score(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        # match_reason format: "bm25 (score=-1.23)"
        assert "score=" in results[0]["match_reason"]

    def test_bm25_result_has_required_keys(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        required_keys = {"source", "episode_id", "session_id", "content_preview", "match_reason"}
        for r in results:
            assert set(r.keys()) == required_keys

    def test_bm25_enrichment_has_session_id(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        # ep-001 and ep-003 match "segmenter"; both have session_ids
        session_ids = {r["session_id"] for r in results}
        assert any(sid for sid in session_ids)

    def test_bm25_content_preview_populated(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        for r in results:
            assert len(r["content_preview"]) > 0

    def test_bm25_top_n_limits_results(self, db_with_fts):
        results = query_sessions("episode", db_path=db_with_fts, top_n=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# ILIKE fallback tests
# ---------------------------------------------------------------------------


class TestILIKEFallback:
    """Tests for the ILIKE fallback path (no FTS index)."""

    def test_ilike_returns_matches(self, db_without_fts):
        results = query_sessions("segmenter", db_path=db_without_fts)
        assert len(results) > 0

    def test_ilike_match_reason(self, db_without_fts):
        results = query_sessions("segmenter", db_path=db_without_fts)
        assert len(results) > 0
        for r in results:
            assert r["match_reason"] == "ilike"

    def test_ilike_case_insensitive(self, db_without_fts):
        results = query_sessions("SEGMENTER", db_path=db_without_fts)
        assert len(results) > 0

    def test_ilike_result_has_required_keys(self, db_without_fts):
        results = query_sessions("segmenter", db_path=db_without_fts)
        assert len(results) > 0
        required_keys = {"source", "episode_id", "session_id", "content_preview", "match_reason"}
        for r in results:
            assert set(r.keys()) == required_keys

    def test_ilike_top_n_limits_results(self, db_without_fts):
        results = query_sessions("episode", db_path=db_without_fts, top_n=1)
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# Edge case / fail-open tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and fail-open behavior."""

    def test_empty_query_returns_empty(self, db_with_fts):
        assert query_sessions("", db_path=db_with_fts) == []

    def test_whitespace_query_returns_empty(self, db_with_fts):
        assert query_sessions("   ", db_path=db_with_fts) == []

    def test_no_matches_returns_empty(self, db_with_fts):
        results = query_sessions("xyznonexistent123", db_path=db_with_fts)
        assert results == []

    def test_no_matches_ilike_returns_empty(self, db_without_fts):
        results = query_sessions("xyznonexistent123", db_path=db_without_fts)
        assert results == []

    def test_invalid_db_path_returns_empty(self):
        results = query_sessions("segmenter", db_path="/nonexistent/path/db.db")
        assert results == []

    def test_empty_table_returns_empty(self, db_empty):
        results = query_sessions("segmenter", db_path=db_empty)
        assert results == []

    def test_source_field_is_sessions(self, db_with_fts):
        results = query_sessions("segmenter", db_path=db_with_fts)
        assert len(results) > 0
        for r in results:
            assert r["source"] == "sessions"
