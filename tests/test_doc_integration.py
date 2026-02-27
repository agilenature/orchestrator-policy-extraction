"""Integration tests for the full doc index pipeline (Phase 21-04).

End-to-end tests verifying the complete pipeline:
  reindex_docs() -> doc_index populated -> GovernorDaemon queries ->
  /api/check returns docs -> session_start.py prints

Tests use temporary DuckDB files and temporary markdown docs to exercise
the pipeline without touching production data.  Each test is independent
(no shared state across tests).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from src.pipeline.doc_indexer import reindex_docs
from src.pipeline.live.bus.doc_schema import create_doc_schema
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Test doc fixture
# ---------------------------------------------------------------------------


def _create_test_docs(docs_dir: Path) -> Path:
    """Create a controlled set of test markdown files.

    Returns the docs_dir path for convenience.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Doc with frontmatter axes (Tier 1) - conf=1.0
    (docs_dir / "with_frontmatter.md").write_text(
        "---\naxes: [deposit-not-detect]\n---\n# Title\n\nThis doc covers deposit methodology."
    )

    # Doc with axis in H2 header (Tier 2) - conf=0.7
    (docs_dir / "with_header.md").write_text(
        "# Guide\n\n## identity-firewall section\n\nContent about identity separation."
    )

    # Doc with HTML comment (Tier 2) - conf=0.7
    (docs_dir / "with_comment.md").write_text(
        "# Architecture\n\n<!-- ccd: bootstrap-circularity -->\n\nCircularity discussion."
    )

    # Doc with no match (unclassified)
    (docs_dir / "no_match.md").write_text(
        "# Random Notes\n\nNothing related to any known axis here at all."
    )

    # Doc for always-show
    (docs_dir / "always_show.md").write_text(
        "---\naxes: [always-show]\n---\n# Essential Guide\n\nAlways delivered to sessions."
    )

    return docs_dir


def _create_memory_md(tmp_path: Path) -> Path:
    """Create a temp MEMORY.md with known CCD axis entries."""
    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text(
        "**CCD axis:** `deposit-not-detect`\n"
        "**CCD axis:** `identity-firewall`\n"
        "**CCD axis:** `bootstrap-circularity`\n"
        "**CCD axis:** `always-show`\n"
    )
    return memory_md


def _setup_pipeline(tmp_path: Path) -> tuple[str, Path, Path]:
    """Common setup: create temp db, docs, and memory file.

    Returns (db_path, docs_dir, memory_md_path).
    """
    db_path = str(tmp_path / "test.db")
    docs_dir = _create_test_docs(tmp_path / "docs")
    memory_md = _create_memory_md(tmp_path)

    # Pre-create the doc_index schema so reindex_docs finds it
    conn = duckdb.connect(db_path)
    create_doc_schema(conn)
    conn.close()

    return db_path, docs_dir, memory_md


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end integration tests for the doc index pipeline."""

    def test_full_pipeline_reindex_to_query(self, tmp_path: Path) -> None:
        """Full pipeline: reindex -> doc_index populated -> daemon queries -> results."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        # Step 1: Reindex docs
        result = reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )
        assert result["total_files"] == 5
        assert result["indexed_rows"] > 0

        # Step 2: Query via GovernorDaemon
        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()

        # Should include at least always-show and frontmatter docs
        doc_paths = [d["doc_path"] for d in docs]
        doc_axes = [d["ccd_axis"] for d in docs]

        assert "always-show" in doc_axes
        assert any("with_frontmatter" in p for p in doc_paths)

    def test_reindex_idempotent(self, tmp_path: Path) -> None:
        """Running reindex_docs() twice produces same row count (DELETE+INSERT refresh)."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        kwargs = dict(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        result1 = reindex_docs(**kwargs)
        result2 = reindex_docs(**kwargs)

        assert result1["indexed_rows"] == result2["indexed_rows"]
        assert result1["total_files"] == result2["total_files"]

        # Verify actual row count in DB matches
        conn = duckdb.connect(db_path, read_only=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM doc_index").fetchone()[0]
        finally:
            conn.close()
        assert count == result2["indexed_rows"]

    def test_tier1_frontmatter_extraction(self, tmp_path: Path) -> None:
        """Doc with frontmatter axes produces association_type='frontmatter', conf=1.0."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT ccd_axis, association_type, extracted_confidence "
                "FROM doc_index WHERE doc_path LIKE '%with_frontmatter%'"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) >= 1
        # Find the deposit-not-detect row
        fm_row = [r for r in rows if r[0] == "deposit-not-detect"]
        assert len(fm_row) == 1
        assert fm_row[0][1] == "frontmatter"
        assert fm_row[0][2] == 1.0

    def test_tier2_header_extraction(self, tmp_path: Path) -> None:
        """Doc with axis in H2 header produces association_type='regex', conf=0.7."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT ccd_axis, association_type, extracted_confidence "
                "FROM doc_index WHERE doc_path LIKE '%with_header%'"
            ).fetchall()
        finally:
            conn.close()

        # Should have identity-firewall matched via regex
        regex_rows = [r for r in rows if r[0] == "identity-firewall"]
        assert len(regex_rows) == 1
        assert regex_rows[0][1] == "regex"
        assert regex_rows[0][2] == pytest.approx(0.7, abs=1e-6)

    def test_tier2_comment_extraction(self, tmp_path: Path) -> None:
        """Doc with HTML CCD comment produces association_type='regex', conf=0.7."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT ccd_axis, association_type, extracted_confidence "
                "FROM doc_index WHERE doc_path LIKE '%with_comment%'"
            ).fetchall()
        finally:
            conn.close()

        # Should have bootstrap-circularity matched via regex
        regex_rows = [r for r in rows if r[0] == "bootstrap-circularity"]
        assert len(regex_rows) == 1
        assert regex_rows[0][1] == "regex"
        assert regex_rows[0][2] == pytest.approx(0.7, abs=1e-6)

    def test_unclassified_stored_in_table(self, tmp_path: Path) -> None:
        """Doc with no axis match gets stored with ccd_axis='unclassified'."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT ccd_axis, association_type FROM doc_index "
                "WHERE doc_path LIKE '%no_match%'"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) == 1
        assert rows[0][0] == "unclassified"
        assert rows[0][1] == "unclassified"

    def test_unclassified_excluded_from_query(self, tmp_path: Path) -> None:
        """GovernorDaemon._query_relevant_docs() excludes unclassified docs."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()

        # No doc in results should have ccd_axis='unclassified'
        for doc in docs:
            assert doc["ccd_axis"] != "unclassified"

        # no_match.md should not appear in results
        doc_paths = [d["doc_path"] for d in docs]
        assert not any("no_match" in p for p in doc_paths)

    def test_always_show_always_delivered(self, tmp_path: Path) -> None:
        """always-show doc appears in query results."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()

        doc_axes = [d["ccd_axis"] for d in docs]
        assert "always-show" in doc_axes

    def test_always_show_first_in_ordering(self, tmp_path: Path) -> None:
        """always-show doc appears first in results from _query_relevant_docs()."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        daemon = GovernorDaemon(db_path=db_path)
        docs = daemon._query_relevant_docs()

        # First doc should be always-show
        assert len(docs) > 0
        assert docs[0]["ccd_axis"] == "always-show"

    def test_max_3_docs_returned(self, tmp_path: Path) -> None:
        """Insert 5 non-unclassified docs directly, verify max 3 returned."""
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

    def test_description_cache_populated(self, tmp_path: Path) -> None:
        """After reindex, doc_index rows have non-empty description_cache."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT doc_path, description_cache FROM doc_index "
                "WHERE association_type != 'unclassified'"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) > 0
        for doc_path, desc in rows:
            assert desc is not None and len(desc) > 0, (
                f"description_cache empty for {doc_path}"
            )

    def test_content_hash_populated(self, tmp_path: Path) -> None:
        """After reindex, doc_index rows have non-empty 16-char hex content_hash."""
        db_path, docs_dir, memory_md = _setup_pipeline(tmp_path)

        reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=str(memory_md),
        )

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT doc_path, content_hash FROM doc_index"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) > 0
        for doc_path, content_hash in rows:
            assert content_hash is not None, f"content_hash is None for {doc_path}"
            assert len(content_hash) == 16, (
                f"content_hash length {len(content_hash)} != 16 for {doc_path}"
            )
            # Verify it's hex
            int(content_hash, 16)

    def test_no_constraint_axis_join(self, tmp_path: Path) -> None:
        """Doc delivery works independently of constraints (no constraint-axis join).

        Creates a populated doc_index but empty constraints.json, calls /api/check
        via TestClient, and verifies relevant_docs are returned even with zero
        constraints.
        """
        from starlette.testclient import TestClient
        from src.pipeline.live.bus.server import create_app
        from src.pipeline.live.bus.schema import create_bus_schema

        db_path = str(tmp_path / "no_join.db")
        constraints_path = str(tmp_path / "constraints.json")

        # Empty constraints
        Path(constraints_path).write_text("[]")

        # Populate doc_index with test docs
        conn = duckdb.connect(db_path)
        create_bus_schema(conn)
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, association_type, "
            "extracted_confidence, description_cache, content_hash) VALUES "
            "('docs/always.md', 'always-show', 'manual', 1.0, 'Essential doc', 'h1'), "
            "('docs/guide.md', 'deposit-not-detect', 'frontmatter', 1.0, 'Guide doc', 'h2')"
        )
        conn.close()

        # Create daemon with empty constraints but populated doc_index
        daemon = GovernorDaemon(
            db_path=db_path, constraints_path=constraints_path
        )
        app = create_app(db_path=db_path, daemon=daemon)
        client = TestClient(app, raise_server_exceptions=True)

        response = client.post(
            "/api/check",
            json={"session_id": "s1", "run_id": "r1"},
        )
        body = response.json()

        # Constraints should be empty
        assert body["constraints"] == []

        # But docs should still be returned (no constraint-axis join!)
        assert len(body["relevant_docs"]) == 2
        doc_axes = [d["ccd_axis"] for d in body["relevant_docs"]]
        assert "always-show" in doc_axes
        assert "deposit-not-detect" in doc_axes
