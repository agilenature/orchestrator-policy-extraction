"""Tests for Candidate Assessment System schema (Phase 17, Plan 01).

Covers:
- assessment_te_sessions and assessment_baselines table creation
- Schema idempotency (double create_ddf_schema)
- ALTER TABLE extensions on memory_candidates, flame_events, project_wisdom
- Insert/query roundtrips
- CHECK constraint enforcement on trunk_quality_status
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


# ── Test 1: assessment tables created via schema chain ──


def test_create_assessment_schema_creates_tables(conn):
    """Verify assessment_te_sessions and assessment_baselines exist after create_schema."""
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    ]
    assert "assessment_te_sessions" in tables
    assert "assessment_baselines" in tables


# ── Test 2: schema idempotency ──


def test_create_assessment_schema_idempotent():
    """Calling create_ddf_schema twice must not raise errors."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    # Second call to create_ddf_schema (first is inside create_schema)
    create_ddf_schema(c)
    # Verify tables still exist
    tables = [
        r[0]
        for r in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    ]
    assert "assessment_te_sessions" in tables
    assert "assessment_baselines" in tables
    c.close()


# ── Test 3: source_type column on memory_candidates ──


def test_alter_table_source_type_on_memory_candidates(conn):
    """Verify source_type column exists on memory_candidates with default 'production'."""
    cols = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'memory_candidates'"
        ).fetchall()
    ]
    assert "source_type" in cols

    # Insert a row without specifying source_type, verify default
    conn.execute(
        "INSERT INTO memory_candidates (id, ccd_axis, scope_rule, flood_example) "
        "VALUES ('test-mc-1', 'test-axis', 'test-scope', 'test-flood')"
    )
    result = conn.execute(
        "SELECT source_type FROM memory_candidates WHERE id = 'test-mc-1'"
    ).fetchone()
    assert result[0] == "production"


# ── Test 4: assessment_session_id column on flame_events ──


def test_alter_table_assessment_session_id_on_flame_events(conn):
    """Verify assessment_session_id column exists on flame_events and is nullable."""
    cols = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'flame_events'"
        ).fetchall()
    ]
    assert "assessment_session_id" in cols

    # Insert a row without assessment_session_id (should be nullable)
    conn.execute(
        "INSERT INTO flame_events (flame_event_id, session_id, marker_level, "
        "marker_type, subject) VALUES ('fe-test-1', 's1', 3, 'trunk_id', 'human')"
    )
    result = conn.execute(
        "SELECT assessment_session_id FROM flame_events WHERE flame_event_id = 'fe-test-1'"
    ).fetchone()
    assert result[0] is None


# ── Test 5: scenario columns on project_wisdom ──


def test_alter_table_scenario_columns_on_project_wisdom_standalone():
    """Verify scenario_seed and ddf_target_level columns added to project_wisdom.

    Creates project_wisdom inline to test create_assessment_schema directly
    without requiring WisdomStore or the full schema chain.
    """
    c = duckdb.connect(":memory:")
    # Create minimal project_wisdom table inline
    c.execute(
        "CREATE TABLE IF NOT EXISTS project_wisdom "
        "(wisdom_id VARCHAR PRIMARY KEY, title VARCHAR)"
    )
    # Also create memory_candidates and flame_events for the ALTER extensions
    c.execute(
        "CREATE TABLE IF NOT EXISTS memory_candidates "
        "(id VARCHAR PRIMARY KEY, ccd_axis TEXT, scope_rule TEXT, flood_example TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS flame_events "
        "(flame_event_id VARCHAR PRIMARY KEY, session_id VARCHAR, "
        "marker_level INTEGER, marker_type VARCHAR)"
    )

    from src.pipeline.assessment.schema import create_assessment_schema

    create_assessment_schema(c)

    cols = [
        r[0]
        for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'project_wisdom'"
        ).fetchall()
    ]
    assert "scenario_seed" in cols
    assert "ddf_target_level" in cols
    c.close()


# ── Test 6: assessment_te_sessions insert and query ──


def test_assessment_te_sessions_insert_and_query(conn):
    """Insert a row into assessment_te_sessions, query it back, verify values."""
    conn.execute(
        "INSERT INTO assessment_te_sessions "
        "(te_id, session_id, scenario_id, candidate_id, candidate_te, "
        "scenario_baseline_te, candidate_ratio, raven_depth, crow_efficiency, "
        "trunk_quality, trunk_quality_status, fringe_drift_rate, scenario_ddf_level, "
        "session_artifact_path) "
        "VALUES ('te-1', 's1', 'sc-1', 'c-1', 0.85, 0.70, 1.21, 0.9, 0.8, "
        "0.7, 'pending', 0.05, 5, '/tmp/artifacts/s1.jsonl')"
    )
    row = conn.execute(
        "SELECT te_id, session_id, scenario_id, candidate_id, candidate_te, "
        "candidate_ratio, trunk_quality_status, scenario_ddf_level "
        "FROM assessment_te_sessions WHERE te_id = 'te-1'"
    ).fetchone()
    assert row[0] == "te-1"
    assert row[1] == "s1"
    assert row[2] == "sc-1"
    assert row[3] == "c-1"
    assert abs(row[4] - 0.85) < 0.001
    assert abs(row[5] - 1.21) < 0.001
    assert row[6] == "pending"
    assert row[7] == 5


# ── Test 7: assessment_baselines insert and query ──


def test_assessment_baselines_insert_and_query(conn):
    """Insert a row into assessment_baselines, query it back."""
    conn.execute(
        "INSERT INTO assessment_baselines "
        "(scenario_id, n_assessments, mean_ratio, stddev_ratio) "
        "VALUES ('sc-1', 10, 1.15, 0.12)"
    )
    row = conn.execute(
        "SELECT scenario_id, n_assessments, mean_ratio, stddev_ratio "
        "FROM assessment_baselines WHERE scenario_id = 'sc-1'"
    ).fetchone()
    assert row[0] == "sc-1"
    assert row[1] == 10
    assert abs(row[2] - 1.15) < 0.001
    assert abs(row[3] - 0.12) < 0.001


# ── Test 8: CHECK constraint on trunk_quality_status ──


def test_assessment_te_sessions_check_constraint(conn):
    """Verify trunk_quality_status only accepts 'pending' or 'confirmed'."""
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            "INSERT INTO assessment_te_sessions "
            "(te_id, session_id, scenario_id, candidate_id, trunk_quality_status) "
            "VALUES ('te-bad', 's1', 'sc-1', 'c-1', 'invalid')"
        )
