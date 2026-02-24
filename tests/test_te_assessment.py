"""Tests for te_assessment (Phase 17, Plan 03).

Covers:
- compute_assessment_te: 3-metric formula
- compute_assessment_te: returns None for no events
- compute_candidate_ratio: normal division and None for zero baseline
- write_assessment_te_row: idempotent (write twice, no error)
- update_assessment_baselines: mean/stddev computation
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.assessment.te_assessment import (
    compute_assessment_te,
    compute_candidate_ratio,
    update_assessment_baselines,
    write_assessment_te_row,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection with flame_events and assessment tables."""
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE IF NOT EXISTS flame_events (
            event_id VARCHAR PRIMARY KEY,
            session_id VARCHAR,
            prompt_number INTEGER,
            subject VARCHAR,
            human_id VARCHAR,
            marker_level INTEGER,
            axis_identified VARCHAR,
            ccd_axis VARCHAR,
            differential VARCHAR,
            scope_rule VARCHAR,
            flood_example VARCHAR,
            confidence FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            assessment_session_id VARCHAR
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS assessment_te_sessions (
            te_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            scenario_id VARCHAR NOT NULL,
            candidate_id VARCHAR NOT NULL,
            candidate_te FLOAT,
            scenario_baseline_te FLOAT,
            candidate_ratio FLOAT,
            raven_depth FLOAT,
            crow_efficiency FLOAT,
            trunk_quality FLOAT,
            trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending',
            fringe_drift_rate FLOAT,
            scenario_ddf_level INTEGER,
            session_artifact_path VARCHAR,
            assessment_date TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS assessment_baselines (
            scenario_id VARCHAR PRIMARY KEY,
            n_assessments INTEGER NOT NULL DEFAULT 0,
            mean_ratio FLOAT,
            stddev_ratio FLOAT,
            last_updated TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    yield c
    c.close()


class TestComputeAssessmentTE:
    """Tests for compute_assessment_te."""

    def test_3_metrics(self, conn):
        """Assessment TE = raven_depth * crow_efficiency * trunk_quality."""
        # Insert flame_events: 4 human events, max level=5, 3 with axis
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-te-001", "sess-te", 1, "human", "david", 3, "axis-1"],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-te-002", "sess-te", 2, "human", "david", 5, "axis-2"],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-te-003", "sess-te", 3, "human", "david", 4, "axis-3"],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-te-004", "sess-te", 4, "human", "david", 2, None],
        )

        result = compute_assessment_te(conn, "sess-te")
        assert result is not None

        # raven_depth = 5/7 = ~0.7143
        assert abs(result["raven_depth"] - 5 / 7) < 0.001

        # crow_efficiency = 3/4 = 0.75
        assert abs(result["crow_efficiency"] - 0.75) < 0.001

        # trunk_quality = 0.5 (placeholder)
        assert result["trunk_quality"] == 0.5

        # candidate_te = (5/7) * 0.75 * 0.5 = ~0.2679
        expected_te = (5 / 7) * 0.75 * 0.5
        assert abs(result["candidate_te"] - expected_te) < 0.01

    def test_no_events_returns_none(self, conn):
        """Returns None when no flame_events for session."""
        result = compute_assessment_te(conn, "nonexistent-session")
        assert result is None

    def test_all_events_with_axis(self, conn):
        """crow_efficiency = 1.0 when all events have axis_identified."""
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-all-axis-1", "sess-all-axis", 1, "human", "david", 7, "axis-a"],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-all-axis-2", "sess-all-axis", 2, "human", "david", 7, "axis-b"],
        )

        result = compute_assessment_te(conn, "sess-all-axis")
        assert result is not None
        assert result["crow_efficiency"] == 1.0
        assert result["raven_depth"] == 1.0  # 7/7

    def test_only_ai_events_ignored(self, conn):
        """AI flame_events are excluded from assessment TE."""
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, "
            "subject, human_id, marker_level, axis_identified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["fe-ai-001", "sess-ai-only", 1, "ai", None, 7, "axis-a"],
        )

        result = compute_assessment_te(conn, "sess-ai-only")
        assert result is None


class TestComputeCandidateRatio:
    """Tests for compute_candidate_ratio."""

    def test_normal_division(self):
        """Returns ratio when both values valid."""
        result = compute_candidate_ratio(0.5, 0.25)
        assert result == 2.0

    def test_zero_baseline_returns_none(self):
        """Returns None when baseline is 0."""
        result = compute_candidate_ratio(0.5, 0.0)
        assert result is None

    def test_none_baseline_returns_none(self):
        """Returns None when baseline is None."""
        result = compute_candidate_ratio(0.5, None)
        assert result is None

    def test_equal_te_returns_one(self):
        """Returns 1.0 when candidate_te == baseline."""
        result = compute_candidate_ratio(0.5, 0.5)
        assert result == 1.0


class TestWriteAssessmentTeRow:
    """Tests for write_assessment_te_row."""

    def test_write_and_read(self, conn):
        """Write a row and verify it's in the table."""
        te_id = write_assessment_te_row(
            conn,
            session_id="sess-write",
            scenario_id="scen-001",
            candidate_id="cand-001",
            candidate_te=0.35,
            scenario_baseline_te=0.5,
            raven_depth=0.7,
            crow_efficiency=0.8,
            trunk_quality=0.5,
            fringe_drift_rate=0.1,
            scenario_ddf_level=3,
        )

        assert len(te_id) == 16

        row = conn.execute(
            "SELECT candidate_te, raven_depth, crow_efficiency, trunk_quality "
            "FROM assessment_te_sessions WHERE te_id = ?",
            [te_id],
        ).fetchone()

        assert row is not None
        assert abs(row[0] - 0.35) < 0.001
        assert abs(row[1] - 0.7) < 0.001

    def test_idempotent_write(self, conn):
        """Writing twice with same IDs doesn't error."""
        te_id1 = write_assessment_te_row(
            conn,
            session_id="sess-idem",
            scenario_id="scen-001",
            candidate_id="cand-001",
            candidate_te=0.35,
            scenario_baseline_te=0.5,
            raven_depth=0.7,
            crow_efficiency=0.8,
            trunk_quality=0.5,
            fringe_drift_rate=None,
            scenario_ddf_level=3,
        )
        te_id2 = write_assessment_te_row(
            conn,
            session_id="sess-idem",
            scenario_id="scen-001",
            candidate_id="cand-001",
            candidate_te=0.40,
            scenario_baseline_te=0.5,
            raven_depth=0.8,
            crow_efficiency=0.9,
            trunk_quality=0.5,
            fringe_drift_rate=None,
            scenario_ddf_level=3,
        )

        # Same te_id (deterministic)
        assert te_id1 == te_id2

        # Should have the latest values
        row = conn.execute(
            "SELECT candidate_te FROM assessment_te_sessions WHERE te_id = ?",
            [te_id1],
        ).fetchone()
        assert abs(row[0] - 0.40) < 0.001

        # Only one row
        count = conn.execute(
            "SELECT COUNT(*) FROM assessment_te_sessions WHERE te_id = ?",
            [te_id1],
        ).fetchone()[0]
        assert count == 1


class TestUpdateAssessmentBaselines:
    """Tests for update_assessment_baselines."""

    def test_compute_mean_stddev(self, conn):
        """Computes mean and stddev from multiple assessment rows."""
        # Insert assessment rows with candidate_ratios
        write_assessment_te_row(
            conn, "sess-b1", "scen-base", "cand-a", 0.5, 0.5,
            0.7, 0.8, 0.5, None, 3,
        )
        write_assessment_te_row(
            conn, "sess-b2", "scen-base", "cand-b", 0.3, 0.5,
            0.5, 0.6, 0.5, None, 3,
        )
        write_assessment_te_row(
            conn, "sess-b3", "scen-base", "cand-c", 0.7, 0.5,
            0.9, 0.9, 0.5, None, 3,
        )

        update_assessment_baselines(conn, "scen-base")

        row = conn.execute(
            "SELECT n_assessments, mean_ratio, stddev_ratio "
            "FROM assessment_baselines WHERE scenario_id = ?",
            ["scen-base"],
        ).fetchone()

        assert row is not None
        assert row[0] == 3  # n_assessments
        assert row[1] is not None  # mean_ratio
        assert row[2] is not None  # stddev_ratio

    def test_single_row_zero_stddev(self, conn):
        """Single assessment -> stddev=0."""
        write_assessment_te_row(
            conn, "sess-single", "scen-single", "cand-only", 0.5, 0.5,
            0.7, 0.8, 0.5, None, 3,
        )

        update_assessment_baselines(conn, "scen-single")

        row = conn.execute(
            "SELECT n_assessments, stddev_ratio "
            "FROM assessment_baselines WHERE scenario_id = ?",
            ["scen-single"],
        ).fetchone()

        assert row is not None
        assert row[0] == 1
        assert row[1] == 0.0

    def test_no_rows_does_nothing(self, conn):
        """No assessment rows -> no baseline entry."""
        update_assessment_baselines(conn, "scen-empty")

        row = conn.execute(
            "SELECT * FROM assessment_baselines WHERE scenario_id = ?",
            ["scen-empty"],
        ).fetchone()

        assert row is None

    def test_idempotent_update(self, conn):
        """Calling update twice produces same result."""
        write_assessment_te_row(
            conn, "sess-idem-base", "scen-idem", "cand-a", 0.5, 0.5,
            0.7, 0.8, 0.5, None, 3,
        )

        update_assessment_baselines(conn, "scen-idem")
        update_assessment_baselines(conn, "scen-idem")

        count = conn.execute(
            "SELECT COUNT(*) FROM assessment_baselines WHERE scenario_id = ?",
            ["scen-idem"],
        ).fetchone()[0]
        assert count == 1
