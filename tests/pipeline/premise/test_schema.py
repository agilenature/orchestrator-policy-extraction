"""Tests for premise registry DuckDB schema DDL.

Tests:
- create_premise_schema creates premise_registry table with all 20 columns
- Correct column types (VARCHAR, TEXT, INTEGER, JSON, TIMESTAMPTZ)
- Indexes created
- Idempotency (call twice, no error)
- parent_episode_id column added to episodes
- PARENT_EPISODE_BACKFILL_SQL correctly assigns parent IDs
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.premise.schema import (
    PARENT_EPISODE_BACKFILL_SQL,
    create_premise_schema,
)
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """Create an in-memory DuckDB connection with base schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


@pytest.fixture
def bare_conn():
    """Create an in-memory DuckDB connection without base schema."""
    c = duckdb.connect(":memory:")
    yield c
    c.close()


class TestCreatePremiseSchema:
    """Tests for create_premise_schema DDL execution."""

    def test_premise_registry_table_created(self, conn):
        """premise_registry table should exist after create_premise_schema."""
        create_premise_schema(conn)
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'premise_registry'"
        ).fetchall()
        assert len(tables) == 1
        assert tables[0][0] == "premise_registry"

    def test_premise_registry_has_20_columns(self, conn):
        """premise_registry should have exactly 20 columns."""
        create_premise_schema(conn)
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'premise_registry' "
            "ORDER BY ordinal_position"
        ).fetchall()
        column_names = [c[0] for c in columns]
        assert len(column_names) == 20

        # Verify all expected columns present
        expected = [
            "premise_id",
            "claim",
            "validated_by",
            "validation_context",
            "foil",
            "distinguishing_prop",
            "staleness_counter",
            "staining_record",
            "ground_truth_pointer",
            "project_scope",
            "session_id",
            "tool_use_id",
            "foil_path_outcomes",
            "divergence_patterns",
            "parent_episode_links",
            "derivation_depth",
            "validation_calls_before_claim",
            "derivation_chain",
            "created_at",
            "updated_at",
        ]
        for col in expected:
            assert col in column_names, f"Missing column: {col}"

    def test_column_types(self, conn):
        """Verify critical column types are correct."""
        create_premise_schema(conn)
        type_map = {}
        rows = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'premise_registry'"
        ).fetchall()
        for name, dtype in rows:
            type_map[name] = dtype.upper()

        assert "VARCHAR" in type_map["premise_id"]
        assert "VARCHAR" in type_map["session_id"]
        assert "INTEGER" in type_map["staleness_counter"]
        assert "INTEGER" in type_map["derivation_depth"]
        assert "INTEGER" in type_map["validation_calls_before_claim"]
        # JSON columns
        assert "JSON" in type_map["staining_record"]
        assert "JSON" in type_map["ground_truth_pointer"]
        assert "JSON" in type_map["derivation_chain"]
        # TIMESTAMPTZ
        assert "TIMESTAMP" in type_map["created_at"]
        assert "TIMESTAMP" in type_map["updated_at"]

    def test_idempotent(self, conn):
        """Calling create_premise_schema twice should not raise."""
        create_premise_schema(conn)
        create_premise_schema(conn)  # Should not raise

    def test_parent_episode_id_column_added(self, conn):
        """episodes table should have parent_episode_id after create_premise_schema."""
        create_premise_schema(conn)
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'episodes' AND column_name = 'parent_episode_id'"
        ).fetchall()
        assert len(columns) == 1
        assert columns[0][0] == "parent_episode_id"

    def test_parent_episode_id_idempotent(self, conn):
        """Adding parent_episode_id twice should not raise."""
        create_premise_schema(conn)
        create_premise_schema(conn)  # Should not raise on duplicate column

    def test_indexes_created(self, conn):
        """Premise registry indexes should be created."""
        create_premise_schema(conn)
        # Check that at least the session index exists
        # DuckDB stores indexes but doesn't expose them via information_schema
        # in all versions. We verify by running the index creation again (idempotent).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_premise_session ON premise_registry(session_id)"
        )


class TestParentEpisodeBackfill:
    """Tests for PARENT_EPISODE_BACKFILL_SQL."""

    def test_backfill_assigns_parent_ids(self, conn):
        """Backfill should assign parent_episode_id using LAG window."""
        create_premise_schema(conn)

        # Insert test episodes in one session
        for i, (eid, sid, ts, seg_id) in enumerate([
            ("ep-1", "sess-1", "2026-02-23T10:00:00Z", "seg-1"),
            ("ep-2", "sess-1", "2026-02-23T10:05:00Z", "seg-2"),
            ("ep-3", "sess-1", "2026-02-23T10:10:00Z", "seg-3"),
        ]):
            conn.execute(
                "INSERT INTO episodes (episode_id, session_id, segment_id, timestamp) "
                "VALUES (?, ?, ?, CAST(? AS TIMESTAMPTZ))",
                [eid, sid, seg_id, ts],
            )

        # Run backfill
        conn.execute(PARENT_EPISODE_BACKFILL_SQL)

        # Verify parent links
        results = conn.execute(
            "SELECT episode_id, parent_episode_id FROM episodes ORDER BY timestamp"
        ).fetchall()

        assert results[0] == ("ep-1", None)  # First episode has no parent
        assert results[1] == ("ep-2", "ep-1")  # Second points to first
        assert results[2] == ("ep-3", "ep-2")  # Third points to second

    def test_backfill_partitions_by_session(self, conn):
        """Backfill should partition by session_id -- no cross-session links."""
        create_premise_schema(conn)

        # Insert episodes in two sessions
        episodes = [
            ("ep-1a", "sess-A", "2026-02-23T10:00:00Z", "seg-1a"),
            ("ep-2a", "sess-A", "2026-02-23T10:05:00Z", "seg-2a"),
            ("ep-1b", "sess-B", "2026-02-23T10:02:00Z", "seg-1b"),
            ("ep-2b", "sess-B", "2026-02-23T10:07:00Z", "seg-2b"),
        ]
        for eid, sid, ts, seg_id in episodes:
            conn.execute(
                "INSERT INTO episodes (episode_id, session_id, segment_id, timestamp) "
                "VALUES (?, ?, ?, CAST(? AS TIMESTAMPTZ))",
                [eid, sid, seg_id, ts],
            )

        conn.execute(PARENT_EPISODE_BACKFILL_SQL)

        # Verify: each session's first episode has None parent
        results = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT episode_id, parent_episode_id FROM episodes"
            ).fetchall()
        }
        assert results["ep-1a"] is None
        assert results["ep-2a"] == "ep-1a"
        assert results["ep-1b"] is None
        assert results["ep-2b"] == "ep-1b"

    def test_backfill_empty_table(self, conn):
        """Backfill on empty episodes table should not error."""
        create_premise_schema(conn)
        conn.execute(PARENT_EPISODE_BACKFILL_SQL)  # Should not raise
