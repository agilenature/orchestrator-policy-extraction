"""Tests for Phase 16.1 topology schema, models, and writer."""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.ddf.topology.models import ActivationCondition, EdgeRecord
from src.pipeline.ddf.topology.schema import create_topology_schema
from src.pipeline.ddf.topology.writer import EdgeWriter
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


def _make_edge(
    axis_a: str = "deposit-not-detect",
    axis_b: str = "ground-truth-pointer",
    relationship_text: str = "deposit requires ground-truth pointer for validation",
    **kwargs,
) -> EdgeRecord:
    """Helper to create a valid EdgeRecord with sensible defaults."""
    edge_id = EdgeRecord.make_id(axis_a, axis_b, relationship_text)
    defaults = dict(
        edge_id=edge_id,
        axis_a=axis_a,
        axis_b=axis_b,
        relationship_text=relationship_text,
        activation_condition=ActivationCondition(),
        evidence={
            "session_id": "sess-001",
            "episode_id": "ep-001",
            "flame_event_ids": ["fe-001", "fe-002"],
        },
        abstraction_level=5,
        created_session_id="sess-001",
    )
    defaults.update(kwargs)
    return EdgeRecord(**defaults)


# -- Test 1: axis_edges table exists --


def test_axis_edges_table_exists(conn):
    """Verify axis_edges table is created by the schema chain."""
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'axis_edges'"
    ).fetchall()
    assert len(tables) == 1
    assert tables[0][0] == "axis_edges"


# -- Test 2: axis_edges columns --


def test_axis_edges_columns(conn):
    """Verify key columns present in axis_edges table."""
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'axis_edges' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]

    expected = [
        "edge_id",
        "axis_a",
        "axis_b",
        "relationship_text",
        "activation_condition",
        "evidence",
        "abstraction_level",
        "status",
        "trunk_quality",
        "created_session_id",
        "created_at",
    ]
    assert col_names == expected
    assert len(col_names) == 11


# -- Test 3: status CHECK constraint --


def test_axis_edges_status_check_constraint(conn):
    """INSERT with status='invalid' must raise an error."""
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            "INSERT INTO axis_edges (edge_id, axis_a, axis_b, "
            "relationship_text, activation_condition, evidence, "
            "abstraction_level, status, trunk_quality, created_session_id) "
            "VALUES ('e1', 'a', 'b', 'rel', '{\"x\":1}', '{\"y\":2}', "
            "3, 'invalid', 1.0, 's1')"
        )


# -- Test 4: activation_condition NOT NULL --


def test_axis_edges_activation_condition_not_null(conn):
    """INSERT with NULL activation_condition must raise an error."""
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            "INSERT INTO axis_edges (edge_id, axis_a, axis_b, "
            "relationship_text, activation_condition, evidence, "
            "abstraction_level, status, trunk_quality, created_session_id) "
            "VALUES ('e1', 'a', 'b', 'rel', NULL, '{\"y\":2}', "
            "3, 'candidate', 1.0, 's1')"
        )


# -- Test 5: EdgeRecord.make_id deterministic --


def test_edge_record_make_id():
    """Verify deterministic ID: same inputs produce same 16-char hex."""
    id1 = EdgeRecord.make_id(
        "deposit-not-detect",
        "ground-truth-pointer",
        "deposit requires ground-truth",
    )
    id2 = EdgeRecord.make_id(
        "deposit-not-detect",
        "ground-truth-pointer",
        "deposit requires ground-truth",
    )
    id3 = EdgeRecord.make_id(
        "deposit-not-detect",
        "identity-firewall",
        "deposit requires ground-truth",
    )

    assert id1 == id2, "Same inputs must produce same ID"
    assert id1 != id3, "Different inputs must produce different IDs"
    assert len(id1) == 16, "ID must be 16 hex characters"
    # Verify it's valid hex
    int(id1, 16)


# -- Test 6: EdgeRecord frozen --


def test_edge_record_frozen():
    """Verify assignment to field raises error."""
    edge = _make_edge()
    with pytest.raises(Exception):  # ValidationError for frozen model
        edge.axis_a = "something-else"


# -- Test 7: ActivationCondition defaults --


def test_activation_condition_defaults():
    """Verify default ActivationCondition has expected values."""
    ac = ActivationCondition()
    assert ac.goal_type == ["any"]
    assert ac.scope_prefix == ""
    assert ac.min_axes_simultaneously_active == 2


# -- Test 8: EdgeWriter write and read --


def test_edge_writer_write_and_read(conn):
    """Write an EdgeRecord, SELECT it back, verify fields."""
    writer = EdgeWriter(conn)
    edge = _make_edge()

    result = writer.write_edge(edge)
    assert result == {"written": 1}

    row = conn.execute(
        "SELECT edge_id, axis_a, axis_b, relationship_text, "
        "activation_condition, evidence, abstraction_level, status, "
        "trunk_quality, created_session_id "
        "FROM axis_edges WHERE edge_id = ?",
        [edge.edge_id],
    ).fetchone()

    assert row is not None
    assert row[0] == edge.edge_id
    assert row[1] == "deposit-not-detect"
    assert row[2] == "ground-truth-pointer"
    assert row[3] == "deposit requires ground-truth pointer for validation"
    # activation_condition is stored as JSON string
    ac = json.loads(row[4]) if isinstance(row[4], str) else row[4]
    assert ac["goal_type"] == ["any"]
    assert ac["min_axes_simultaneously_active"] == 2
    assert row[6] == 5  # abstraction_level
    assert row[7] == "candidate"  # default status
    assert row[8] == 1.0  # default trunk_quality


# -- Test 9: EdgeWriter idempotent --


def test_edge_writer_idempotent(conn):
    """Write same edge twice, verify only 1 row."""
    writer = EdgeWriter(conn)
    edge = _make_edge()

    writer.write_edge(edge)
    writer.write_edge(edge)

    count = conn.execute(
        "SELECT COUNT(*) FROM axis_edges WHERE edge_id = ?",
        [edge.edge_id],
    ).fetchone()[0]
    assert count == 1


# -- Test 10: degrade and retire --


def test_edge_writer_degrade_and_retire(conn):
    """Degrade to below 0.3, verify status becomes 'superseded'."""
    writer = EdgeWriter(conn)
    edge = _make_edge()
    writer.write_edge(edge)

    # Degrade by 0.8 (1.0 - 0.8 = 0.2 < 0.3 threshold)
    new_quality, retired = writer.degrade_and_maybe_retire(
        edge.edge_id, amount=0.8
    )
    assert new_quality == pytest.approx(0.2)
    assert retired is True

    # Verify status in database
    status = conn.execute(
        "SELECT status FROM axis_edges WHERE edge_id = ?",
        [edge.edge_id],
    ).fetchone()[0]
    assert status == "superseded"


# -- Test 11: find_edges_for_axis_pair bidirectional --


def test_edge_writer_find_edges_bidirectional(conn):
    """find_edges_for_axis_pair returns edge regardless of axis order."""
    writer = EdgeWriter(conn)
    edge = _make_edge(status="active")
    writer.write_edge(edge)

    # Search with original order
    results_fwd = writer.find_edges_for_axis_pair(
        "deposit-not-detect", "ground-truth-pointer", status="active"
    )
    assert len(results_fwd) == 1
    assert results_fwd[0]["edge_id"] == edge.edge_id

    # Search with reversed order
    results_rev = writer.find_edges_for_axis_pair(
        "ground-truth-pointer", "deposit-not-detect", status="active"
    )
    assert len(results_rev) == 1
    assert results_rev[0]["edge_id"] == edge.edge_id


# -- Test 12: create_topology_schema idempotent --


def test_create_topology_schema_idempotent(conn):
    """Call create_topology_schema twice, verify no error."""
    # Already called once via create_schema -> create_ddf_schema chain
    create_topology_schema(conn)
    # Third call for good measure
    create_topology_schema(conn)

    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'axis_edges'"
    ).fetchall()
    assert len(tables) == 1
