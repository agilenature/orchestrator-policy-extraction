"""Tests for query-time axis retrieval (src.pipeline.doc_query).

Verifies the full query_docs pipeline:
  query string → axis match → axis_edges expansion → doc_index retrieval
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.doc_query import (
    _axis_non_stop_tokens,
    _expand_via_axis_edges,
    _load_doc_axes,
    _score_axis_match,
    _tokenize,
    query_docs,
)
from src.pipeline.live.bus.doc_schema import create_doc_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path):
    """Create an in-memory-style temp DuckDB with doc_index schema."""
    db_path = str(tmp_path / "test_query.db")
    conn = duckdb.connect(db_path)
    create_doc_schema(conn)
    return db_path, conn


def _insert_doc(
    conn,
    doc_path,
    ccd_axis,
    association_type="frontmatter",
    extracted_confidence=1.0,
    description_cache="",
    content_hash=None,
):
    if content_hash is None:
        content_hash = doc_path[:16].replace("/", "")
    conn.execute(
        "INSERT OR REPLACE INTO doc_index "
        "(doc_path, ccd_axis, association_type, extracted_confidence, "
        "description_cache, content_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [doc_path, ccd_axis, association_type, extracted_confidence, description_cache, content_hash],
    )


def _make_axis_edges_table(conn):
    """Create axis_edges table (mirrors Phase 16.1 DDL)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS axis_edges (
            edge_id             VARCHAR PRIMARY KEY,
            axis_a              VARCHAR NOT NULL,
            axis_b              VARCHAR NOT NULL,
            relationship_text   TEXT NOT NULL,
            activation_condition JSON NOT NULL,
            evidence            JSON NOT NULL,
            abstraction_level   INTEGER NOT NULL,
            status              VARCHAR NOT NULL DEFAULT 'candidate',
            trunk_quality       FLOAT NOT NULL DEFAULT 1.0,
            created_session_id  VARCHAR NOT NULL,
            created_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def _insert_edge(conn, axis_a, axis_b, status="active"):
    import hashlib
    edge_id = hashlib.sha256(f"{axis_a}{axis_b}".encode()).hexdigest()[:16]
    conn.execute(
        "INSERT OR REPLACE INTO axis_edges "
        "(edge_id, axis_a, axis_b, relationship_text, activation_condition, "
        "evidence, abstraction_level, status, trunk_quality, created_session_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            edge_id, axis_a, axis_b, "related", '{"condition": "always"}',
            '{"source": "test"}', 1, status, 1.0, "test-session",
        ],
    )


# ---------------------------------------------------------------------------
# Unit tests: _tokenize
# ---------------------------------------------------------------------------


def test_tokenize_basic():
    tokens = _tokenize("raven cost function absent")
    assert "raven" in tokens
    assert "cost" in tokens
    assert "function" in tokens
    assert "absent" in tokens


def test_tokenize_filters_stopwords():
    tokens = _tokenize("how does the raven work")
    assert "how" not in tokens
    assert "does" not in tokens
    assert "the" not in tokens
    assert "raven" in tokens


def test_tokenize_handles_hyphens():
    """Hyphens split into separate tokens (like axis names)."""
    tokens = _tokenize("raven-cost-function-absent")
    assert "raven" in tokens
    assert "cost" in tokens
    assert "function" in tokens
    assert "absent" in tokens


def test_tokenize_empty_string():
    assert _tokenize("") == set()


def test_tokenize_all_stopwords():
    assert _tokenize("how does the work") == set()


# ---------------------------------------------------------------------------
# Unit tests: _score_axis_match
# ---------------------------------------------------------------------------


def test_score_axis_match_full_match():
    tokens = _tokenize("raven cost function absent")
    # "raven-cost-function-absent" → 4 tokens: raven, cost, function, absent
    score = _score_axis_match(tokens, "raven-cost-function-absent")
    assert score >= 3  # at least 3 of 4 tokens match


def test_score_axis_match_partial():
    tokens = _tokenize("deposit something else")
    score = _score_axis_match(tokens, "deposit-not-detect")
    assert score == 1  # "deposit" matches; "detect" doesn't appear


def test_score_axis_match_no_match():
    tokens = _tokenize("something completely unrelated")
    score = _score_axis_match(tokens, "raven-cost-function-absent")
    assert score == 0


def test_score_axis_too_short():
    """Single-token axis (after stopwords) scores 0 — too ambiguous."""
    tokens = _tokenize("identity work")
    # "identity-firewall" → two tokens: identity, firewall
    # but "identity" alone can't trigger since min_axis_tokens=2
    score = _score_axis_match(tokens, "not-a")
    assert score == 0  # both tokens are stopwords → 0


def test_axis_non_stop_tokens():
    tokens = _axis_non_stop_tokens("deposit-not-detect")
    assert "deposit" in tokens
    assert "detect" in tokens
    assert "not" not in tokens  # stopword


# ---------------------------------------------------------------------------
# Unit tests: _load_doc_axes
# ---------------------------------------------------------------------------


def test_load_doc_axes_excludes_unclassified(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_doc(conn, "docs/a.md", "deposit-not-detect")
    _insert_doc(conn, "docs/b.md", "unclassified", "unclassified", 0.0)
    _insert_doc(conn, "docs/c.md", "always-show", "manual")

    axes = _load_doc_axes(conn)
    assert "deposit-not-detect" in axes
    assert "unclassified" not in axes
    assert "always-show" not in axes
    conn.close()


def test_load_doc_axes_empty_table(tmp_path):
    db_path, conn = _make_db(tmp_path)
    assert _load_doc_axes(conn) == []
    conn.close()


# ---------------------------------------------------------------------------
# Unit tests: _expand_via_axis_edges
# ---------------------------------------------------------------------------


def test_expand_via_axis_edges_returns_neighbors(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _make_axis_edges_table(conn)
    _insert_edge(conn, "deposit-not-detect", "terminal-vs-instrumental", "active")

    neighbors = _expand_via_axis_edges(["deposit-not-detect"], conn)
    assert "terminal-vs-instrumental" in neighbors
    assert "deposit-not-detect" in neighbors
    conn.close()


def test_expand_via_axis_edges_includes_candidate_status(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _make_axis_edges_table(conn)
    _insert_edge(conn, "raven-cost-function-absent", "snippet-not-chunk", "candidate")

    neighbors = _expand_via_axis_edges(["raven-cost-function-absent"], conn)
    assert "snippet-not-chunk" in neighbors
    conn.close()


def test_expand_via_axis_edges_excludes_superseded(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _make_axis_edges_table(conn)
    _insert_edge(conn, "deposit-not-detect", "old-axis", "superseded")

    neighbors = _expand_via_axis_edges(["deposit-not-detect"], conn)
    assert "old-axis" not in neighbors
    conn.close()


def test_expand_via_axis_edges_no_table(tmp_path):
    db_path, conn = _make_db(tmp_path)
    # No axis_edges table — should return empty set
    result = _expand_via_axis_edges(["some-axis"], conn)
    assert result == set()
    conn.close()


def test_expand_via_axis_edges_empty_input(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _make_axis_edges_table(conn)
    assert _expand_via_axis_edges([], conn) == set()
    conn.close()


# ---------------------------------------------------------------------------
# Integration tests: query_docs
# ---------------------------------------------------------------------------


def test_query_docs_direct_axis_match(tmp_path):
    """Query with axis name tokens returns docs indexed under that axis."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(
        conn,
        "docs/guides/MEMORY.md",
        "raven-cost-function-absent",
        description_cache="The AI has no retrieval cost.",
    )
    conn.close()

    results = query_docs("raven cost function absent", db_path=db_path)
    assert len(results) == 1
    assert results[0]["doc_path"] == "docs/guides/MEMORY.md"
    assert results[0]["ccd_axis"] == "raven-cost-function-absent"
    assert results[0]["match_reason"] == "direct"


def test_query_docs_neighbor_axis_included(tmp_path):
    """Docs indexed under neighbor axes are included with reason='neighbor'."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(conn, "docs/a.md", "deposit-not-detect")
    _insert_doc(conn, "docs/b.md", "terminal-vs-instrumental")  # neighbor
    _make_axis_edges_table(conn)
    _insert_edge(conn, "deposit-not-detect", "terminal-vs-instrumental", "active")
    conn.close()

    results = query_docs("deposit detect", db_path=db_path, top_n=5)
    paths = {r["doc_path"] for r in results}
    assert "docs/a.md" in paths  # direct
    assert "docs/b.md" in paths  # neighbor

    reasons = {r["doc_path"]: r["match_reason"] for r in results}
    assert reasons["docs/a.md"] == "direct"
    assert reasons["docs/b.md"] == "neighbor"


def test_query_docs_direct_before_neighbor(tmp_path):
    """Direct axis matches appear before neighbor matches."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(conn, "docs/direct.md", "deposit-not-detect", extracted_confidence=0.4)
    _insert_doc(conn, "docs/neighbor.md", "terminal-vs-instrumental", extracted_confidence=1.0)
    _make_axis_edges_table(conn)
    _insert_edge(conn, "deposit-not-detect", "terminal-vs-instrumental", "active")
    conn.close()

    results = query_docs("deposit detect", db_path=db_path, top_n=5)
    assert results[0]["doc_path"] == "docs/direct.md"
    assert results[1]["doc_path"] == "docs/neighbor.md"


def test_query_docs_max_top_n(tmp_path):
    """Never returns more than top_n results."""
    db_path, conn = _make_db(tmp_path)
    for i in range(6):
        _insert_doc(
            conn,
            f"docs/doc{i}.md",
            "raven-cost-function-absent",
            content_hash=f"hash{i:04d}",
        )
    conn.close()

    results = query_docs("raven cost function absent", db_path=db_path, top_n=3)
    assert len(results) <= 3


def test_query_docs_dedup_by_doc_path(tmp_path):
    """A doc indexed under multiple axes appears only once."""
    db_path, conn = _make_db(tmp_path)
    # Same doc_path indexed under two axes
    _insert_doc(conn, "docs/a.md", "raven-cost-function-absent", content_hash="hash0001")
    _insert_doc(conn, "docs/a.md", "deposit-not-detect", content_hash="hash0002")
    conn.close()

    results = query_docs("raven cost function absent deposit detect", db_path=db_path, top_n=5)
    paths = [r["doc_path"] for r in results]
    assert paths.count("docs/a.md") == 1


def test_query_docs_excludes_unclassified(tmp_path):
    """Unclassified docs are never returned."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(conn, "docs/classified.md", "raven-cost-function-absent")
    _insert_doc(conn, "docs/unclass.md", "unclassified", "unclassified", 0.0)
    conn.close()

    results = query_docs("raven cost function absent", db_path=db_path)
    paths = {r["doc_path"] for r in results}
    assert "docs/unclass.md" not in paths


def test_query_docs_empty_query_returns_empty(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_doc(conn, "docs/a.md", "raven-cost-function-absent")
    conn.close()

    assert query_docs("", db_path=db_path) == []
    assert query_docs("   ", db_path=db_path) == []


def test_query_docs_no_axis_match_returns_empty(tmp_path):
    """Query with no tokens matching any axis → empty list."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(conn, "docs/a.md", "raven-cost-function-absent")
    conn.close()

    results = query_docs("completely unrelated xyz123", db_path=db_path)
    assert results == []


def test_query_docs_missing_doc_index_returns_empty(tmp_path):
    """DB with no doc_index table → empty list (graceful fallback)."""
    db_path = str(tmp_path / "empty.db")
    conn = duckdb.connect(db_path)
    conn.close()

    assert query_docs("raven cost function absent", db_path=db_path) == []


def test_query_docs_invalid_db_path_returns_empty():
    """Non-existent DB path → empty list (fail-open)."""
    results = query_docs("raven cost function absent", db_path="/nonexistent/path.db")
    assert results == []


def test_query_docs_confidence_ordering_within_direct(tmp_path):
    """Within direct matches, higher confidence appears first."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(
        conn, "docs/low.md", "raven-cost-function-absent",
        extracted_confidence=0.4, content_hash="low0000",
    )
    _insert_doc(
        conn, "docs/high.md", "raven-cost-function-absent",
        extracted_confidence=1.0, content_hash="high000",
    )
    conn.close()

    results = query_docs("raven cost function absent", db_path=db_path, top_n=5)
    paths = [r["doc_path"] for r in results]
    assert paths.index("docs/high.md") < paths.index("docs/low.md")


def test_query_docs_description_cache_in_result(tmp_path):
    """description_cache is included in result dict."""
    db_path, conn = _make_db(tmp_path)
    _insert_doc(
        conn, "docs/a.md", "raven-cost-function-absent",
        description_cache="AI has no retrieval cost.",
    )
    conn.close()

    results = query_docs("raven cost function absent", db_path=db_path)
    assert results[0]["description_cache"] == "AI has no retrieval cost."


def test_query_docs_none_description_cache(tmp_path):
    """NULL description_cache is returned as empty string."""
    db_path, conn = _make_db(tmp_path)
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
        "extracted_confidence, description_cache, content_hash) "
        "VALUES (?, ?, ?, ?, NULL, ?)",
        ["docs/a.md", "raven-cost-function-absent", "frontmatter", 1.0, "hash0001"],
    )
    conn.close()

    results = query_docs("raven cost function absent", db_path=db_path)
    assert results[0]["description_cache"] == ""
