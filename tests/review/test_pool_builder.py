"""Tests for the PoolBuilder.

Verifies:
- PoolBuilder.build() returns instances for all available layers
- Each instance has non-empty externalization properties
- Falls back gracefully when source tables are empty
- max_per_point is respected
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

import duckdb
import pytest

from src.pipeline.review.models import IdentificationLayer, IdentificationPoint
from src.pipeline.review.pool_builder import PoolBuilder


@pytest.fixture
def db_conn():
    """In-memory DuckDB with all source tables populated."""
    conn = duckdb.connect(":memory:")
    _create_source_tables(conn)
    _populate_source_data(conn)
    yield conn
    conn.close()


@pytest.fixture
def empty_db_conn():
    """In-memory DuckDB with all source tables but no data."""
    conn = duckdb.connect(":memory:")
    _create_source_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def constraints_file(tmp_path: Path) -> Path:
    """Temporary constraints.json with test data."""
    constraints = [
        {
            "constraint_id": f"c{i}",
            "text": f"Test constraint {i}",
            "severity": "warning",
            "scope": {"paths": []},
            "detection_hints": [f"hint{i}", f"hint{i+1}"],
            "source_episode_id": f"ep{i}",
            "examples": [{"episode_id": f"ep{i}"}],
            "type": "behavioral_constraint" if i < 8 else "policy_feedback",
        }
        for i in range(15)
    ]
    path = tmp_path / "constraints.json"
    path.write_text(json.dumps(constraints))
    return path


@pytest.fixture
def empty_constraints_file(tmp_path: Path) -> Path:
    """Temporary empty constraints.json."""
    path = tmp_path / "constraints.json"
    path.write_text("[]")
    return path


def _create_source_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all source tables needed by PoolBuilder."""
    conn.execute("""
        CREATE TABLE events (
            event_id VARCHAR PRIMARY KEY, ts_utc TIMESTAMPTZ,
            session_id VARCHAR, actor VARCHAR, event_type VARCHAR,
            primary_tag VARCHAR, primary_tag_confidence FLOAT,
            secondary_tags JSON, payload JSON, links JSON,
            risk_score FLOAT, risk_factors JSON, first_seen TIMESTAMPTZ,
            last_seen TIMESTAMPTZ, ingestion_count INTEGER,
            source_system VARCHAR, source_ref VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE episode_segments (
            segment_id VARCHAR PRIMARY KEY, session_id VARCHAR,
            start_event_id VARCHAR, end_event_id VARCHAR,
            start_ts TIMESTAMPTZ, end_ts TIMESTAMPTZ,
            start_trigger VARCHAR, end_trigger VARCHAR,
            outcome VARCHAR, event_count INTEGER, event_ids JSON,
            complexity VARCHAR, interruption_count INTEGER,
            context_switches INTEGER, config_hash VARCHAR,
            created_at TIMESTAMPTZ
        )
    """)
    conn.execute("""
        CREATE TABLE episodes (
            episode_id VARCHAR PRIMARY KEY, session_id VARCHAR,
            segment_id VARCHAR, timestamp TIMESTAMPTZ,
            mode VARCHAR, risk VARCHAR, reaction_label VARCHAR,
            reaction_confidence FLOAT, outcome_type VARCHAR,
            observation STRUCT(
                repo_state STRUCT(
                    changed_files VARCHAR[],
                    diff_stat STRUCT(files INTEGER, insertions INTEGER, deletions INTEGER)
                ),
                quality_state STRUCT(
                    tests_status VARCHAR, lint_status VARCHAR, build_status VARCHAR
                ),
                context STRUCT(
                    recent_summary VARCHAR, open_questions VARCHAR[],
                    constraints_in_force VARCHAR[]
                )
            ),
            orchestrator_action JSON, outcome JSON, provenance JSON,
            labels JSON, source_files VARCHAR[], config_hash VARCHAR,
            schema_version INTEGER, created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            escalate_block_event_ref VARCHAR,
            escalate_bypass_event_ref VARCHAR,
            escalate_bypassed_constraint_id VARCHAR,
            escalate_approval_status VARCHAR,
            escalate_confidence FLOAT,
            escalate_detector_version VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE session_constraint_eval (
            session_id VARCHAR, constraint_id VARCHAR,
            eval_state VARCHAR, evidence_json JSON,
            scope_matched BOOLEAN, eval_ts TIMESTAMPTZ,
            PRIMARY KEY (session_id, constraint_id)
        )
    """)
    conn.execute("""
        CREATE TABLE amnesia_events (
            amnesia_id VARCHAR PRIMARY KEY, session_id VARCHAR,
            constraint_id VARCHAR, constraint_type VARCHAR,
            severity VARCHAR, evidence_json JSON,
            detected_at TIMESTAMPTZ
        )
    """)
    conn.execute("""
        CREATE TABLE policy_error_events (
            error_id VARCHAR PRIMARY KEY, session_id VARCHAR,
            episode_id VARCHAR, error_type VARCHAR,
            constraint_id VARCHAR, recommendation_mode VARCHAR,
            recommendation_risk VARCHAR, detected_at TIMESTAMPTZ
        )
    """)


def _populate_source_data(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert test data into all source tables."""
    # Events: 20 rows, some with tags
    for i in range(20):
        tag = "X_ASK" if i % 3 == 0 else ("O_DIR" if i % 3 == 1 else None)
        conf = 0.85 if tag else None
        conn.execute(
            """
            INSERT INTO events VALUES (
                ?, '2026-01-01', 'sess1', 'executor', 'assistant_text',
                ?, ?, '["secondary"]', NULL, NULL, 0.0, NULL, NULL, NULL,
                1, 'test', 'ref1'
            )
            """,
            [f"evt{i}", tag, conf],
        )

    # Episode segments: 10 rows
    for i in range(10):
        end_trigger = "timeout" if i == 0 else "T_GIT_COMMIT"
        outcome = "committed" if i < 8 else "superseded"
        conn.execute(
            """
            INSERT INTO episode_segments VALUES (
                ?, 'sess1', ?, ?,
                '2026-01-01', '2026-01-01 01:00:00',
                'O_DIR', ?, ?, 5, '["e1","e2"]',
                'complex', 1, 0, 'cfg1', '2026-01-01'
            )
            """,
            [f"seg{i}", f"evt{i}", f"evt{i+1}", end_trigger, outcome],
        )

    # Episodes: 10 rows
    for i in range(10):
        block_ref = f"blk{i}" if i < 3 else None
        bypass_ref = f"byp{i}" if i < 2 else None
        bypassed_id = f"c{i}" if i == 1 else None
        conn.execute(
            f"""
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp,
                mode, risk, reaction_label, reaction_confidence,
                outcome_type,
                observation,
                orchestrator_action, outcome, provenance,
                labels, source_files, config_hash, schema_version,
                created_at, updated_at,
                escalate_block_event_ref, escalate_bypass_event_ref,
                escalate_bypassed_constraint_id, escalate_approval_status,
                escalate_confidence
            ) VALUES (
                'ep{i}', 'sess1', 'seg{i}', '2026-01-01',
                'Plan', 'low', 'approve', 0.75, 'committed',
                ROW(
                    ROW(ARRAY['file.py'], ROW(1, 10, 5)),
                    ROW('pass', 'pass', 'pass'),
                    ROW('summary text', ARRAY['q1'], ARRAY['c1'])
                ),
                '{{"type": "direction"}}', '{{"result": "ok"}}',
                '{{"source": "test"}}',
                NULL, NULL, 'cfg1', 1,
                '2026-01-01', '2026-01-01',
                {f"'{block_ref}'" if block_ref else 'NULL'},
                {f"'{bypass_ref}'" if bypass_ref else 'NULL'},
                {f"'{bypassed_id}'" if bypassed_id else 'NULL'},
                {'NULL' if not bypass_ref else "'approved'"},
                {0.9 if bypass_ref else 'NULL'}
            )
            """,
        )

    # session_constraint_eval: 5 rows
    for i in range(5):
        conn.execute(
            """
            INSERT INTO session_constraint_eval VALUES (
                'sess1', ?, ?, '{"evidence": "test"}', TRUE, '2026-01-01'
            )
            """,
            [f"c{i}", "HONORED" if i < 3 else "VIOLATED"],
        )

    # amnesia_events: 3 rows
    for i in range(3):
        conn.execute(
            """
            INSERT INTO amnesia_events VALUES (
                ?, 'sess1', ?, 'behavioral', 'warning',
                '{"reason": "forgotten"}', '2026-01-01'
            )
            """,
            [f"amn{i}", f"c{i}"],
        )

    # policy_error_events: 2 rows
    conn.execute(
        """
        INSERT INTO policy_error_events VALUES (
            'pe1', 'sess1', 'ep1', 'suppressed', 'c1', 'Plan', 'low', '2026-01-01'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO policy_error_events VALUES (
            'pe2', 'sess1', 'ep2', 'surfaced_and_blocked', 'c2', 'Integrate', 'medium',
            '2026-01-01'
        )
        """
    )


class TestPoolBuilderBuild:
    """PoolBuilder.build() returns instances for all available layers."""

    def test_returns_instances_for_all_layers(
        self, db_conn: duckdb.DuckDBPyConnection, constraints_file: Path
    ):
        pb = PoolBuilder(db_conn, max_per_point=5, constraints_path=constraints_file)
        pool = pb.build()

        layers_present = {p.layer for p in pool}
        # All 8 layers should have instances (we populated all source tables)
        assert IdentificationLayer.L1_EVENT_FILTER in layers_present
        assert IdentificationLayer.L2_TAGGING in layers_present
        assert IdentificationLayer.L3_SEGMENTATION in layers_present
        assert IdentificationLayer.L4_EPISODE_POPULATION in layers_present
        assert IdentificationLayer.L5_CONSTRAINT_EXTRACTION in layers_present
        assert IdentificationLayer.L6_CONSTRAINT_EVALUATION in layers_present
        assert IdentificationLayer.L7_ESCALATION_DETECTION in layers_present
        assert IdentificationLayer.L8_POLICY_FEEDBACK in layers_present

    def test_all_instances_have_required_fields(
        self, db_conn: duckdb.DuckDBPyConnection, constraints_file: Path
    ):
        pb = PoolBuilder(db_conn, max_per_point=5, constraints_path=constraints_file)
        pool = pb.build()

        for point in pool:
            assert point.trigger, f"Empty trigger on {point.instance_id}"
            assert point.observation_state, f"Empty obs on {point.instance_id}"
            assert point.action_taken, f"Empty action on {point.instance_id}"
            assert point.downstream_impact, f"Empty impact on {point.instance_id}"
            assert point.provenance_pointer, f"Empty provenance on {point.instance_id}"

    def test_max_per_point_respected(
        self, db_conn: duckdb.DuckDBPyConnection, constraints_file: Path
    ):
        max_n = 3
        pb = PoolBuilder(db_conn, max_per_point=max_n, constraints_path=constraints_file)
        pool = pb.build()

        point_counts = Counter(p.point_id for p in pool)
        for point_id, count in point_counts.items():
            assert count <= max_n, (
                f"point_id {point_id} has {count} instances, "
                f"exceeding max_per_point={max_n}"
            )

    def test_instance_ids_are_unique(
        self, db_conn: duckdb.DuckDBPyConnection, constraints_file: Path
    ):
        pb = PoolBuilder(db_conn, max_per_point=5, constraints_path=constraints_file)
        pool = pb.build()
        ids = [p.instance_id for p in pool]
        assert len(ids) == len(set(ids)), "Duplicate instance_ids found"


class TestPoolBuilderGracefulDegradation:
    """PoolBuilder handles empty source tables gracefully."""

    def test_empty_tables_no_crash(
        self, empty_db_conn: duckdb.DuckDBPyConnection, empty_constraints_file: Path
    ):
        pb = PoolBuilder(
            empty_db_conn,
            max_per_point=5,
            constraints_path=empty_constraints_file,
        )
        pool = pb.build()
        assert isinstance(pool, list)
        assert len(pool) == 0

    def test_missing_constraints_file(
        self, db_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ):
        """Missing constraints.json just means no L5 points."""
        missing_path = tmp_path / "nonexistent.json"
        pb = PoolBuilder(db_conn, max_per_point=5, constraints_path=missing_path)
        pool = pb.build()
        l5_points = [p for p in pool if p.layer == IdentificationLayer.L5_CONSTRAINT_EXTRACTION]
        assert len(l5_points) == 0
        # Other layers should still have data
        assert len(pool) > 0

    def test_partial_data_returns_available_layers(
        self, empty_db_conn: duckdb.DuckDBPyConnection, constraints_file: Path
    ):
        """With only constraints.json, only L5 and L8 should have data."""
        pb = PoolBuilder(
            empty_db_conn,
            max_per_point=5,
            constraints_path=constraints_file,
        )
        pool = pb.build()
        layers_present = {p.layer for p in pool}
        # L5 should be present from constraints.json
        assert IdentificationLayer.L5_CONSTRAINT_EXTRACTION in layers_present
        # L8-3 should be present from policy_feedback constraints
        assert IdentificationLayer.L8_POLICY_FEEDBACK in layers_present
        # No DuckDB data, so L1-L4, L6, L7 should be absent
        assert IdentificationLayer.L1_EVENT_FILTER not in layers_present
        assert IdentificationLayer.L3_SEGMENTATION not in layers_present
