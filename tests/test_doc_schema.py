"""Tests for the doc_index schema and CheckResponse extension (Phase 21-01).

Covers DuckDB doc_index table creation, idempotency, constraint enforcement,
default values, integration with create_bus_schema(), and CheckResponse
relevant_docs field behavior.

Uses in-memory DuckDB connections for isolation.
"""

from __future__ import annotations

import pytest
import duckdb

from src.pipeline.live.bus.doc_schema import create_doc_schema, DOC_INDEX_DDL
from src.pipeline.live.bus.schema import create_bus_schema
from src.pipeline.live.bus.models import CheckResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory DuckDB connection with doc_index schema only."""
    c = duckdb.connect(":memory:")
    create_doc_schema(c)
    return c


@pytest.fixture
def bus_conn():
    """In-memory DuckDB connection with full bus schema (including doc_index)."""
    c = duckdb.connect(":memory:")
    create_bus_schema(c)
    return c


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_doc_index_ddl_creates_table(conn):
    """create_doc_schema() creates doc_index table with 8 columns."""
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'doc_index' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert len(col_names) == 8
    assert col_names == [
        "doc_path",
        "ccd_axis",
        "association_type",
        "extracted_confidence",
        "description_cache",
        "section_anchor",
        "content_hash",
        "indexed_at",
    ]


def test_doc_index_ddl_idempotent(conn):
    """Calling create_doc_schema() twice does not raise."""
    create_doc_schema(conn)  # already called in fixture; second call
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'doc_index'"
    ).fetchall()
    assert len(tables) == 1


def test_doc_index_primary_key(conn):
    """Primary key (doc_path, ccd_axis) enforces uniqueness.

    Same (doc_path, ccd_axis) pair rejects; same doc_path with different
    ccd_axis succeeds (multi-axis documents).
    """
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, content_hash) "
        "VALUES ('docs/a.md', 'deposit-not-detect', 'abc123')"
    )
    # Duplicate (doc_path, ccd_axis) should fail
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, content_hash) "
            "VALUES ('docs/a.md', 'deposit-not-detect', 'def456')"
        )
    # Same doc_path, different ccd_axis should succeed
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, content_hash) "
        "VALUES ('docs/a.md', 'ground-truth-pointer', 'abc123')"
    )
    rows = conn.execute(
        "SELECT doc_path, ccd_axis FROM doc_index WHERE doc_path = 'docs/a.md' "
        "ORDER BY ccd_axis"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0] == ("docs/a.md", "deposit-not-detect")
    assert rows[1] == ("docs/a.md", "ground-truth-pointer")


def test_doc_index_association_type_check(conn):
    """CHECK constraint rejects invalid association_type values."""
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            "INSERT INTO doc_index (doc_path, ccd_axis, association_type, content_hash) "
            "VALUES ('docs/b.md', 'axis-1', 'invalid', 'hash1')"
        )


def test_doc_index_defaults(conn):
    """Insert with only required fields verifies defaults.

    association_type defaults to 'frontmatter', extracted_confidence to 1.0,
    indexed_at is not null.
    """
    conn.execute(
        "INSERT INTO doc_index (doc_path, ccd_axis, content_hash) "
        "VALUES ('docs/c.md', 'axis-2', 'hash2')"
    )
    row = conn.execute(
        "SELECT association_type, extracted_confidence, indexed_at "
        "FROM doc_index WHERE doc_path = 'docs/c.md'"
    ).fetchone()
    assert row is not None
    assert row[0] == "frontmatter"
    assert row[1] == 1.0
    assert row[2] is not None  # indexed_at should be set by default


def test_create_bus_schema_includes_doc_index(bus_conn):
    """create_bus_schema() creates doc_index alongside bus_sessions, governance_signals, push_links."""
    tables = bus_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "bus_sessions" in table_names
    assert "governance_signals" in table_names
    assert "push_links" in table_names
    assert "doc_index" in table_names


# ---------------------------------------------------------------------------
# CheckResponse model tests
# ---------------------------------------------------------------------------


def test_check_response_relevant_docs_field():
    """CheckResponse() has relevant_docs=[], and accepts populated list."""
    cr_empty = CheckResponse()
    assert cr_empty.relevant_docs == []

    cr_populated = CheckResponse(
        relevant_docs=[{"doc_path": "docs/guide.md", "ccd_axis": "deposit-not-detect"}]
    )
    assert len(cr_populated.relevant_docs) == 1
    assert cr_populated.relevant_docs[0]["doc_path"] == "docs/guide.md"


def test_check_response_serialization_with_docs():
    """CheckResponse with populated relevant_docs serializes via model_dump()."""
    cr = CheckResponse(
        constraints=[{"id": "c1"}],
        relevant_docs=[
            {"doc_path": "docs/a.md", "ccd_axis": "axis-1", "confidence": 0.9},
            {"doc_path": "docs/b.md", "ccd_axis": "axis-2", "confidence": 1.0},
        ],
    )
    data = cr.model_dump()
    assert "relevant_docs" in data
    assert len(data["relevant_docs"]) == 2
    assert data["relevant_docs"][0]["doc_path"] == "docs/a.md"
    assert data["constraints"] == [{"id": "c1"}]
    # Verify all fields present
    assert "interventions" in data
    assert "epistemological_signals" in data
