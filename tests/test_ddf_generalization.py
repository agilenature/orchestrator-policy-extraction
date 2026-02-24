"""Tests for GeneralizationRadius, spiral tracking, and spiral-to-wisdom promotion.

Covers DDF-05 (GeneralizationRadius + stagnation) and DDF-06 (spiral tracking
with project_wisdom promotion).

Tests use in-memory DuckDB connections with manually created tables matching
the production schema. WisdomStore tests use tmp_path for file-based DuckDB.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from src.pipeline.ddf.generalization import (
    compute_all_metrics,
    compute_generalization_radius,
    detect_stagnation,
    write_constraint_metrics,
)
from src.pipeline.ddf.spiral import (
    compute_spiral_depth,
    detect_spirals,
    get_spiral_promotion_candidates,
    promote_spirals_to_wisdom,
)
from src.pipeline.models.config import PipelineConfig


def _create_eval_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create session_constraint_eval table matching production schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_constraint_eval (
            session_id VARCHAR NOT NULL,
            constraint_id VARCHAR NOT NULL,
            eval_state VARCHAR NOT NULL,
            evidence_json JSON,
            scope_matched BOOLEAN NOT NULL DEFAULT TRUE,
            eval_ts TIMESTAMPTZ DEFAULT current_timestamp,
            PRIMARY KEY (session_id, constraint_id)
        )
    """)


def _create_constraint_metrics_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create constraint_metrics table matching production schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS constraint_metrics (
            constraint_id VARCHAR PRIMARY KEY,
            radius INTEGER NOT NULL DEFAULT 0,
            firing_count INTEGER NOT NULL DEFAULT 0,
            is_stagnant BOOLEAN DEFAULT FALSE,
            last_computed TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def _create_flame_events_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create flame_events table matching production schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flame_events (
            flame_event_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            human_id VARCHAR,
            prompt_number INTEGER,
            marker_level INTEGER NOT NULL,
            marker_type VARCHAR NOT NULL,
            evidence_excerpt TEXT,
            quality_score FLOAT,
            axis_identified VARCHAR,
            flood_confirmed BOOLEAN DEFAULT FALSE,
            subject VARCHAR NOT NULL DEFAULT 'human',
            detection_source VARCHAR NOT NULL DEFAULT 'stub',
            deposited_to_candidates BOOLEAN DEFAULT FALSE,
            source_episode_id VARCHAR,
            session_event_ref VARCHAR,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def _insert_eval(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    constraint_id: str,
    eval_state: str = "HONORED",
    scope_path: str | None = None,
    eval_ts: str | None = None,
) -> None:
    """Insert a session_constraint_eval row with optional scope_path in evidence."""
    evidence = []
    if scope_path:
        evidence = [{"scope_path": scope_path, "event_id": "test"}]

    ts = eval_ts or datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO session_constraint_eval
        (session_id, constraint_id, eval_state, evidence_json, scope_matched, eval_ts)
        VALUES (?, ?, ?, ?, TRUE, ?::TIMESTAMPTZ)
        """,
        [session_id, constraint_id, eval_state, json.dumps(evidence), ts],
    )


# --- GeneralizationRadius tests ---


class TestGeneralizationRadius:
    """Tests for compute_generalization_radius and related functions."""

    def test_radius_single_scope(self):
        """1 distinct scope prefix -> radius=1."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        _insert_eval(conn, "s1", "c1", scope_path="src/pipeline/foo.py")

        metric = compute_generalization_radius(conn, "c1")
        assert metric.radius == 1
        assert metric.firing_count == 1
        assert metric.constraint_id == "c1"

    def test_radius_multiple_scopes(self):
        """3 distinct prefixes -> radius=3."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        _insert_eval(conn, "s1", "c1", scope_path="src/pipeline/foo.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="tests/test_foo.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "s3", "c1", scope_path="data/config.yaml", eval_ts="2026-01-03T00:00:00Z")

        metric = compute_generalization_radius(conn, "c1")
        assert metric.radius == 3
        assert metric.firing_count == 3

    def test_radius_null_scope_uses_root(self):
        """null scope_path -> 'root' prefix, radius=1."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        _insert_eval(conn, "s1", "c1", scope_path=None)

        metric = compute_generalization_radius(conn, "c1")
        assert metric.radius == 1  # 'root' prefix
        assert metric.firing_count == 1

    def test_stagnation_detected(self):
        """radius=1, firing_count=10 -> is_stagnant=True."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        for i in range(10):
            _insert_eval(conn, f"s{i}", "c1", scope_path="src/same/file.py", eval_ts=f"2026-01-{i+1:02d}T00:00:00Z")

        metric = compute_generalization_radius(conn, "c1")
        assert metric.radius == 1  # All 'src' prefix
        assert metric.firing_count == 10
        assert metric.is_stagnant is True

    def test_no_stagnation_low_count(self):
        """radius=1, firing_count=5 -> is_stagnant=False."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        for i in range(5):
            _insert_eval(conn, f"s{i}", "c1", scope_path="src/same/file.py", eval_ts=f"2026-01-{i+1:02d}T00:00:00Z")

        metric = compute_generalization_radius(conn, "c1")
        assert metric.radius == 1
        assert metric.firing_count == 5
        assert metric.is_stagnant is False

    def test_no_stagnation_high_radius(self):
        """radius=3, firing_count=15 -> is_stagnant=False."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        for i in range(5):
            _insert_eval(conn, f"sa{i}", "c1", scope_path="src/a.py", eval_ts=f"2026-01-{i+1:02d}T00:00:00Z")
        for i in range(5):
            _insert_eval(conn, f"sb{i}", "c1", scope_path="tests/b.py", eval_ts=f"2026-02-{i+1:02d}T00:00:00Z")
        for i in range(5):
            _insert_eval(conn, f"sc{i}", "c1", scope_path="data/c.yaml", eval_ts=f"2026-03-{i+1:02d}T00:00:00Z")

        metric = compute_generalization_radius(conn, "c1")
        assert metric.radius == 3
        assert metric.firing_count == 15
        assert metric.is_stagnant is False

    def test_compute_all_metrics(self):
        """Multiple constraints computed in one call."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)
        _insert_eval(conn, "s1", "c1", scope_path="src/a.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="tests/b.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "s1", "c2", scope_path="src/a.py", eval_ts="2026-01-01T00:00:00Z")

        metrics = compute_all_metrics(conn)
        assert len(metrics) == 2

        by_id = {m.constraint_id: m for m in metrics}
        assert by_id["c1"].radius == 2
        assert by_id["c1"].firing_count == 2
        assert by_id["c2"].radius == 1
        assert by_id["c2"].firing_count == 1


class TestWriteConstraintMetrics:
    """Tests for write_constraint_metrics."""

    def test_write_constraint_metrics(self):
        """Metrics written to DuckDB table."""
        conn = duckdb.connect(":memory:")
        _create_constraint_metrics_table(conn)
        _create_eval_table(conn)
        _insert_eval(conn, "s1", "c1", scope_path="src/a.py")

        metrics = compute_all_metrics(conn)
        count = write_constraint_metrics(conn, metrics)
        assert count == 1

        row = conn.execute(
            "SELECT constraint_id, radius, firing_count, is_stagnant FROM constraint_metrics WHERE constraint_id = 'c1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "c1"
        assert row[1] == 1  # radius
        assert row[2] == 1  # firing_count
        assert row[3] is False  # is_stagnant

    def test_write_constraint_metrics_idempotent(self):
        """Write same metrics twice, no duplicates."""
        conn = duckdb.connect(":memory:")
        _create_constraint_metrics_table(conn)
        _create_eval_table(conn)
        _insert_eval(conn, "s1", "c1", scope_path="src/a.py")

        metrics = compute_all_metrics(conn)
        write_constraint_metrics(conn, metrics)
        write_constraint_metrics(conn, metrics)  # second write

        count = conn.execute(
            "SELECT COUNT(*) FROM constraint_metrics WHERE constraint_id = 'c1'"
        ).fetchone()[0]
        assert count == 1


class TestDetectStagnation:
    """Tests for detect_stagnation."""

    def test_detect_stagnation_returns_only_stagnant(self):
        """Only is_stagnant=True returned."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)

        # c1: stagnant (10+ firings, 1 scope)
        for i in range(10):
            _insert_eval(conn, f"s{i}", "c1", scope_path="src/same.py", eval_ts=f"2026-01-{i+1:02d}T00:00:00Z")

        # c2: not stagnant (3 scopes)
        _insert_eval(conn, "sa", "c2", scope_path="src/a.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "sb", "c2", scope_path="tests/b.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "sc", "c2", scope_path="data/c.yaml", eval_ts="2026-01-03T00:00:00Z")

        stagnant = detect_stagnation(conn)
        assert len(stagnant) == 1
        assert stagnant[0].constraint_id == "c1"
        assert stagnant[0].is_stagnant is True


# --- Spiral tracking tests ---


class TestSpiralTracking:
    """Tests for detect_spirals and related functions."""

    def test_spiral_ascending_scopes(self):
        """[A] -> [A,B] -> [A,B,C] detected as spiral."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)

        _insert_eval(conn, "s1", "c1", scope_path="alpha/x.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="beta/y.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "s3", "c1", scope_path="gamma/z.py", eval_ts="2026-01-03T00:00:00Z")

        spirals = detect_spirals(conn)
        assert len(spirals) == 1
        assert spirals[0]["constraint_id"] == "c1"
        assert spirals[0]["spiral_length"] == 3
        assert spirals[0]["current_radius"] == 3

    def test_spiral_non_ascending_not_detected(self):
        """Same scope across sessions is not a spiral (no growth)."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)

        _insert_eval(conn, "s1", "c1", scope_path="alpha/x.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="alpha/y.py", eval_ts="2026-01-02T00:00:00Z")

        spirals = detect_spirals(conn)
        # Both sessions have same prefix 'alpha' -> no growth -> not a spiral
        assert len(spirals) == 0

    def test_spiral_single_session_not_detected(self):
        """A single session cannot form a spiral."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)

        _insert_eval(conn, "s1", "c1", scope_path="src/foo.py", eval_ts="2026-01-01T00:00:00Z")

        spirals = detect_spirals(conn)
        assert len(spirals) == 0


class TestSpiralDepth:
    """Tests for compute_spiral_depth."""

    def test_spiral_depth_ascending_levels(self):
        """L1, L2, L3 streak -> depth=3."""
        conn = duckdb.connect(":memory:")
        _create_flame_events_table(conn)

        for i, level in enumerate([1, 2, 3]):
            conn.execute(
                """
                INSERT INTO flame_events (flame_event_id, session_id, marker_level, marker_type, created_at)
                VALUES (?, 'sess1', ?, 'test', ?::TIMESTAMPTZ)
                """,
                [f"fe{i}", level, f"2026-01-01T0{i}:00:00Z"],
            )

        depth = compute_spiral_depth(conn, "sess1")
        assert depth == 3

    def test_spiral_depth_non_ascending(self):
        """L3, L1, L2 -> depth=2 (only L1->L2 ascending)."""
        conn = duckdb.connect(":memory:")
        _create_flame_events_table(conn)

        for i, level in enumerate([3, 1, 2]):
            conn.execute(
                """
                INSERT INTO flame_events (flame_event_id, session_id, marker_level, marker_type, created_at)
                VALUES (?, 'sess1', ?, 'test', ?::TIMESTAMPTZ)
                """,
                [f"fe{i}", level, f"2026-01-01T0{i}:00:00Z"],
            )

        depth = compute_spiral_depth(conn, "sess1")
        assert depth == 2  # L1->L2 = 1 transition + 1 = 2

    def test_spiral_depth_no_ascending(self):
        """L3, L2, L1 -> depth=0 (no ascending)."""
        conn = duckdb.connect(":memory:")
        _create_flame_events_table(conn)

        for i, level in enumerate([3, 2, 1]):
            conn.execute(
                """
                INSERT INTO flame_events (flame_event_id, session_id, marker_level, marker_type, created_at)
                VALUES (?, 'sess1', ?, 'test', ?::TIMESTAMPTZ)
                """,
                [f"fe{i}", level, f"2026-01-01T0{i}:00:00Z"],
            )

        depth = compute_spiral_depth(conn, "sess1")
        assert depth == 0

    def test_spiral_depth_empty_session(self):
        """No flame events -> depth=0."""
        conn = duckdb.connect(":memory:")
        _create_flame_events_table(conn)

        depth = compute_spiral_depth(conn, "nonexistent")
        assert depth == 0


class TestSpiralPromotionCandidates:
    """Tests for get_spiral_promotion_candidates."""

    def test_spiral_promotion_candidates(self):
        """spiral_length >= 3 returned."""
        conn = duckdb.connect(":memory:")
        _create_eval_table(conn)

        # c1: 3-session spiral (qualifies)
        _insert_eval(conn, "s1", "c1", scope_path="alpha/x.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="beta/y.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "s3", "c1", scope_path="gamma/z.py", eval_ts="2026-01-03T00:00:00Z")

        # c2: 2-session spiral (does not qualify)
        _insert_eval(conn, "s1", "c2", scope_path="alpha/a.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c2", scope_path="beta/b.py", eval_ts="2026-01-02T00:00:00Z")

        candidates = get_spiral_promotion_candidates(conn, min_spiral_length=3)
        assert "c1" in candidates
        assert "c2" not in candidates


class TestPromoteSpiralsToWisdom:
    """Tests for promote_spirals_to_wisdom."""

    def test_promote_spirals_to_wisdom_writes_project_wisdom(self, tmp_path):
        """Verify WisdomStore.upsert called, project_wisdom table has row."""
        db_path = tmp_path / "test.db"
        conn = duckdb.connect(str(db_path))
        _create_eval_table(conn)

        # Create a 3-session spiral
        _insert_eval(conn, "s1", "c1", scope_path="alpha/x.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="beta/y.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "s3", "c1", scope_path="gamma/z.py", eval_ts="2026-01-03T00:00:00Z")

        count = promote_spirals_to_wisdom(conn, db_path, min_spiral_length=3)
        assert count == 1

        # Verify project_wisdom has the entry via the same connection
        rows = conn.execute(
            "SELECT wisdom_id, entity_type, title, confidence, source_phase FROM project_wisdom"
        ).fetchall()
        assert len(rows) >= 1

        row = rows[0]
        assert row[1] == "breakthrough"
        assert "Spiral:" in row[2]
        assert row[3] == 0.7
        assert row[4] == 15

        conn.close()

    def test_promote_spirals_to_wisdom_idempotent(self, tmp_path):
        """Calling twice does not create duplicates (upsert)."""
        db_path = tmp_path / "test_idem.db"
        conn = duckdb.connect(str(db_path))
        _create_eval_table(conn)

        _insert_eval(conn, "s1", "c1", scope_path="alpha/x.py", eval_ts="2026-01-01T00:00:00Z")
        _insert_eval(conn, "s2", "c1", scope_path="beta/y.py", eval_ts="2026-01-02T00:00:00Z")
        _insert_eval(conn, "s3", "c1", scope_path="gamma/z.py", eval_ts="2026-01-03T00:00:00Z")

        # Promote twice
        count1 = promote_spirals_to_wisdom(conn, db_path, min_spiral_length=3)
        count2 = promote_spirals_to_wisdom(conn, db_path, min_spiral_length=3)

        assert count1 == 1
        assert count2 == 1  # Same count (processed again)

        # Verify only 1 entry in project_wisdom (upsert dedups)
        verify_conn = duckdb.connect(str(db_path))
        total = verify_conn.execute(
            "SELECT COUNT(*) FROM project_wisdom"
        ).fetchone()[0]
        assert total == 1

        verify_conn.close()
        conn.close()

    def test_promote_no_candidates(self, tmp_path):
        """No qualifying spirals -> 0 promoted."""
        db_path = tmp_path / "test_empty.db"
        conn = duckdb.connect(str(db_path))
        _create_eval_table(conn)

        _insert_eval(conn, "s1", "c1", scope_path="alpha/x.py", eval_ts="2026-01-01T00:00:00Z")

        count = promote_spirals_to_wisdom(conn, db_path, min_spiral_length=3)
        assert count == 0
        conn.close()
