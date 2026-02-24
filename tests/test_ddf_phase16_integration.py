"""Integration tests for the full Phase 16 closed loop.

Verifies end-to-end that the entire Phase 16 system works:
- FlameEvent deposits to memory_candidates
- Memory-review CLI accepts candidates and writes to MEMORY.md
- TE computation materializes rows
- Backfill jobs retroactively update pending rows

Tests are organized by DDF requirement number (DDF-06 through DDF-09).
Each test maps to a specific DDF requirement from the roadmap success criteria.

Terminal per deposit-not-detect CCD axis: these tests verify the deposit
chain works, not just the detection scaffolding.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli
from src.pipeline.cli.intelligence import _memory_review_impl
from src.pipeline.ddf.deposit import deposit_to_memory_candidates
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.transport_efficiency import (
    backfill_te_delta,
    backfill_trunk_quality,
    compute_fringe_drift,
    compute_te_for_session,
    write_te_rows,
)


# ============================================================
# Fixtures
# ============================================================


def _make_conn() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with full Phase 16 schema."""
    conn = duckdb.connect(":memory:")
    create_ddf_schema(conn)
    return conn


def _make_file_conn(db_path: str) -> duckdb.DuckDBPyConnection:
    """Create a file-based DuckDB connection with full Phase 16 schema."""
    conn = duckdb.connect(db_path)
    create_ddf_schema(conn)
    return conn


def _insert_flame_event(
    conn: duckdb.DuckDBPyConnection,
    flame_event_id: str,
    session_id: str = "s1",
    human_id: str = "h1",
    prompt_number: int = 1,
    marker_level: int = 0,
    marker_type: str = "trunk_identification",
    subject: str = "human",
    axis_identified: str | None = None,
    flood_confirmed: bool = False,
    detection_source: str = "stub",
    created_at: str | None = None,
) -> None:
    """Insert a flame_event for testing."""
    if created_at:
        conn.execute(
            """
            INSERT INTO flame_events
                (flame_event_id, session_id, human_id, prompt_number,
                 marker_level, marker_type, subject, axis_identified,
                 flood_confirmed, detection_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                flame_event_id, session_id, human_id, prompt_number,
                marker_level, marker_type, subject, axis_identified,
                flood_confirmed, detection_source, created_at,
            ],
        )
    else:
        conn.execute(
            """
            INSERT INTO flame_events
                (flame_event_id, session_id, human_id, prompt_number,
                 marker_level, marker_type, subject, axis_identified,
                 flood_confirmed, detection_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                flame_event_id, session_id, human_id, prompt_number,
                marker_level, marker_type, subject, axis_identified,
                flood_confirmed, detection_source,
            ],
        )


# ============================================================
# DDF-06: Transport Efficiency
# ============================================================


class TestDDF06_TransportEfficiency:
    """Integration tests for DDF-06: TE composite computed per session."""

    def test_te_computed_for_human_session(self):
        """Insert human flame_events at various levels, verify all 4 sub-metrics computed."""
        conn = _make_conn()

        # Insert flame_events at levels 0, 3, 5, 7
        _insert_flame_event(conn, "fe1", marker_level=0, axis_identified="ax1", flood_confirmed=True)
        _insert_flame_event(conn, "fe2", marker_level=3, axis_identified="ax2", flood_confirmed=False)
        _insert_flame_event(conn, "fe3", marker_level=5, axis_identified=None, flood_confirmed=True)
        _insert_flame_event(conn, "fe4", marker_level=7, axis_identified="ax3", flood_confirmed=False)

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 1
        row = rows[0]

        # All 4 sub-metrics computed
        assert row["raven_depth"] is not None
        assert row["crow_efficiency"] is not None
        assert row["transport_speed"] is not None
        assert row["trunk_quality"] is not None

        # raven_depth = MAX(7) / 7.0 = 1.0
        assert row["raven_depth"] == pytest.approx(1.0)
        # crow_efficiency = 3 with axis / 4 total = 0.75
        assert row["crow_efficiency"] == pytest.approx(0.75)
        # transport_speed = 2 flood / 4 total = 0.5
        assert row["transport_speed"] == pytest.approx(0.5)
        # trunk_quality = 0.5 (pending sentinel)
        assert row["trunk_quality"] == pytest.approx(0.5)

        # composite = product of 4
        expected_composite = 1.0 * 0.75 * 0.5 * 0.5
        assert row["composite_te"] == pytest.approx(expected_composite)

        conn.close()

    def test_te_computed_for_ai_session(self):
        """Insert AI flame_events, verify subject='ai' rows produced."""
        conn = _make_conn()

        _insert_flame_event(conn, "fe1", subject="ai", marker_level=4, axis_identified="ax1")
        _insert_flame_event(conn, "fe2", subject="ai", marker_level=6, flood_confirmed=True)

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 1
        assert rows[0]["subject"] == "ai"
        assert rows[0]["raven_depth"] == pytest.approx(6.0 / 7.0)

        conn.close()

    def test_te_unified_formula_both_subjects(self):
        """Both human and AI in same session get identical formula (2 rows)."""
        conn = _make_conn()

        _insert_flame_event(conn, "fe1", subject="human", marker_level=5, axis_identified="ax1", flood_confirmed=True)
        _insert_flame_event(conn, "fe2", subject="ai", marker_level=5, axis_identified="ax1", flood_confirmed=True)

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 2
        subjects = {r["subject"] for r in rows}
        assert subjects == {"human", "ai"}

        # Both use the same formula: raven_depth * crow_eff * transport_speed * trunk_quality
        for row in rows:
            expected = row["raven_depth"] * row["crow_efficiency"] * row["transport_speed"] * row["trunk_quality"]
            assert row["composite_te"] == pytest.approx(expected)

        conn.close()

    def test_te_materialized_not_view(self):
        """After write_te_rows(), verify SELECT returns data (not a view)."""
        conn = _make_conn()

        _insert_flame_event(conn, "fe1", marker_level=5, axis_identified="ax1", flood_confirmed=True)
        rows = compute_te_for_session(conn, "s1")
        write_te_rows(conn, rows)

        # SELECT from the table (not a view)
        stored = conn.execute(
            "SELECT te_id, session_id, subject, composite_te "
            "FROM transport_efficiency_sessions"
        ).fetchall()
        assert len(stored) == 1
        assert stored[0][1] == "s1"

        # Verify it is a table, not a view
        table_info = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'transport_efficiency_sessions' AND table_type = 'BASE TABLE'"
        ).fetchall()
        assert len(table_info) == 1

        conn.close()

    def test_te_composite_formula_correct(self):
        """Known flame_events with exact expected sub-metrics and composite."""
        conn = _make_conn()

        # 2 events: max level=4, 1 with axis, 1 flood_confirmed
        _insert_flame_event(
            conn, "fe1", marker_level=4,
            axis_identified="test-axis", flood_confirmed=False,
        )
        _insert_flame_event(
            conn, "fe2", marker_level=2,
            axis_identified=None, flood_confirmed=True,
        )

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 1
        row = rows[0]

        # raven_depth = 4/7
        assert row["raven_depth"] == pytest.approx(4.0 / 7.0)
        # crow_efficiency = 1/2 = 0.5 (1 has axis)
        assert row["crow_efficiency"] == pytest.approx(0.5)
        # transport_speed = 1/2 = 0.5 (1 flood_confirmed)
        assert row["transport_speed"] == pytest.approx(0.5)
        # trunk_quality = 0.5 (pending)
        assert row["trunk_quality"] == pytest.approx(0.5)

        # composite_te = (4/7) * 0.5 * 0.5 * 0.5
        expected_composite = (4.0 / 7.0) * 0.5 * 0.5 * 0.5
        assert row["composite_te"] == pytest.approx(expected_composite)

        conn.close()


# ============================================================
# DDF-07: MEMORY.md Closed Loop
# ============================================================


class TestDDF07_MemoryMDClosedLoop:
    """Integration tests for DDF-07: Level 6 deposit -> review -> MEMORY.md."""

    def test_level6_deposits_to_candidates(self):
        """Create Level 6 flood_confirmed FlameEvent, deposit to memory_candidates."""
        conn = _make_conn()

        _insert_flame_event(
            conn, "fe_l6", marker_level=6,
            axis_identified="test-axis", flood_confirmed=True,
        )

        candidate_id = deposit_to_memory_candidates(
            conn,
            ccd_axis="test-axis",
            scope_rule="When X happens, apply Y",
            flood_example="In session Z, X happened and Y was applied",
            source_flame_event_id="fe_l6",
        )

        assert candidate_id is not None

        # Verify row in memory_candidates with status='pending'
        row = conn.execute(
            "SELECT id, status, ccd_axis, scope_rule, flood_example, source_flame_event_id "
            "FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()

        assert row is not None
        assert row[1] == "pending"
        assert row[2] == "test-axis"
        assert row[3] == "When X happens, apply Y"
        assert row[4] == "In session Z, X happened and Y was applied"
        assert row[5] == "fe_l6"

        conn.close()

    def test_memory_review_accept_writes_to_file(self, tmp_path):
        """Accept via memory-review writes CCD-format entry to MEMORY.md."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        # Create initial MEMORY.md
        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\nExisting content.\n")

        conn = _make_file_conn(db_path)

        # Insert pending candidate
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status, pipeline_component)
            VALUES ('mc1', 'deposit-not-detect', 'Every component is evaluated by deposit',
                    'FlameEvents write-on-detect is load-bearing', 'pending', 'ddf_tier2')
            """
        )
        conn.close()

        # Simulate accept via CLI
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "memory-review", "--db", db_path, "--memory-file", memory_path],
            input="a\n",
        )

        assert result.exit_code == 0
        assert "ACCEPTED" in result.output

        # Verify MEMORY.md contains CCD-format entry
        with open(memory_path) as f:
            content = f.read()

        assert "## deposit-not-detect" in content
        assert "**CCD axis:** deposit-not-detect" in content
        assert "**Scope rule:** Every component is evaluated by deposit" in content
        assert "**Flood example:** FlameEvents write-on-detect is load-bearing" in content

        # Verify status updated to 'validated'
        conn2 = duckdb.connect(db_path)
        row = conn2.execute(
            "SELECT status FROM memory_candidates WHERE id = 'mc1'"
        ).fetchone()
        assert row[0] == "validated"
        conn2.close()

    def test_memory_review_reject_updates_status(self, tmp_path):
        """Reject via memory-review updates status to 'rejected'."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n")

        conn = _make_file_conn(db_path)
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status, pipeline_component)
            VALUES ('mc1', 'bad-axis', 'not a real scope rule',
                    'not a real flood example', 'pending', 'ddf_tier2')
            """
        )
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "memory-review", "--db", db_path, "--memory-file", memory_path],
            input="r\n",
        )

        assert result.exit_code == 0
        assert "REJECTED" in result.output

        conn2 = duckdb.connect(db_path)
        row = conn2.execute(
            "SELECT status FROM memory_candidates WHERE id = 'mc1'"
        ).fetchone()
        assert row[0] == "rejected"
        conn2.close()

    def test_closed_loop_end_to_end(self, tmp_path):
        """Full path: flame_event -> deposit -> review accept -> MEMORY.md -> status validated.

        This is the terminal test: the deposit chain works from detection to
        persistent MEMORY.md entry.
        """
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = _make_file_conn(db_path)

        # Step 1: Create flame_event (Level 6, flood confirmed)
        _insert_flame_event(
            conn, "fe_terminal", session_id="s_terminal",
            marker_level=6, axis_identified="ground-truth-pointer",
            flood_confirmed=True,
        )

        # Step 2: Deposit to memory_candidates
        candidate_id = deposit_to_memory_candidates(
            conn,
            ccd_axis="ground-truth-pointer",
            scope_rule="Every abstraction must carry a pointer to its perceptual ground",
            flood_example="MEMORY.md entries without source_session_id are floating abstractions",
            source_flame_event_id="fe_terminal",
        )
        assert candidate_id is not None

        # Verify pending
        row = conn.execute(
            "SELECT status FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0] == "pending"
        conn.close()

        # Step 3: Accept via memory-review CLI
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "memory-review", "--db", db_path, "--memory-file", memory_path],
            input="a\n",
        )
        assert result.exit_code == 0
        assert "ACCEPTED" in result.output

        # Step 4: Verify MEMORY.md content
        with open(memory_path) as f:
            content = f.read()
        assert "## ground-truth-pointer" in content
        assert "**CCD axis:** ground-truth-pointer" in content

        # Step 5: Verify status='validated'
        conn2 = duckdb.connect(db_path)
        row = conn2.execute(
            "SELECT status FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0] == "validated"
        conn2.close()

    def test_dedup_warning_on_existing_axis(self, tmp_path):
        """Pre-populated MEMORY.md with axis text triggers dedup warning."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        # Pre-populate MEMORY.md with an entry containing the axis
        with open(memory_path, "w") as f:
            f.write(
                "# Project Memory\n\n"
                "## deposit-not-detect\n\n"
                "**CCD axis:** deposit-not-detect\n"
                "**Scope rule:** existing scope rule\n"
            )

        conn = _make_file_conn(db_path)
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status, pipeline_component)
            VALUES ('mc_dup', 'deposit-not-detect', 'new scope rule',
                    'new flood example', 'pending', 'ddf_tier2')
            """
        )
        conn.close()

        # Input: 'a' to accept, then 'n' to decline the duplicate warning
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "memory-review", "--db", db_path, "--memory-file", memory_path],
            input="a\nn\n",
        )

        assert result.exit_code == 0
        assert "WARNING" in result.output
        assert "already appears in MEMORY.md" in result.output


# ============================================================
# DDF-08: Fringe Drift
# ============================================================


class TestDDF08_FringeDrift:
    """Integration tests for DDF-08: fringe drift rate computation."""

    def test_fringe_drift_zero_when_concept_named(self):
        """Fringe events + flood-confirmed L6+ in same session -> 0.0."""
        conn = _make_conn()

        # L1 fringe event
        _insert_flame_event(conn, "fe_fringe", marker_level=1, subject="human")
        # L6 flood-confirmed (concept was named)
        _insert_flame_event(
            conn, "fe_flood", marker_level=6, subject="human",
            flood_confirmed=True,
        )

        result = compute_fringe_drift(conn, "s1", "human")
        assert result == 0.0

        conn.close()

    def test_fringe_drift_one_when_drifted(self):
        """Fringe events (L2) but no flood-confirmed L6+ -> 1.0."""
        conn = _make_conn()

        _insert_flame_event(conn, "fe_fringe", marker_level=2, subject="human")
        # L4 event but no L6+ flood_confirmed
        _insert_flame_event(conn, "fe_mid", marker_level=4, subject="human")

        result = compute_fringe_drift(conn, "s1", "human")
        assert result == 1.0

        conn.close()

    def test_fringe_drift_null_no_fringe(self):
        """Only L4+ events (no L1-2 fringe) -> None."""
        conn = _make_conn()

        _insert_flame_event(conn, "fe1", marker_level=4, subject="human")
        _insert_flame_event(conn, "fe2", marker_level=6, subject="human", flood_confirmed=True)

        result = compute_fringe_drift(conn, "s1", "human")
        assert result is None

        conn.close()

    def test_fringe_drift_stored_on_te_row(self):
        """After compute_te_for_session, fringe_drift_rate is populated on result."""
        conn = _make_conn()

        # L1 fringe + L6 flood -> fringe_drift = 0.0
        _insert_flame_event(conn, "fe1", marker_level=1, subject="human")
        _insert_flame_event(
            conn, "fe2", marker_level=6, subject="human",
            flood_confirmed=True,
        )

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 1
        assert rows[0]["fringe_drift_rate"] == 0.0

        # Write and verify stored
        write_te_rows(conn, rows)
        stored = conn.execute(
            "SELECT fringe_drift_rate FROM transport_efficiency_sessions WHERE session_id = 's1'"
        ).fetchone()
        assert stored[0] == pytest.approx(0.0)

        conn.close()


# ============================================================
# DDF-09: Trunk Quality
# ============================================================


class TestDDF09_TrunkQuality:
    """Integration tests for DDF-09: trunk quality backfill and te_delta."""

    def test_trunk_quality_pending_on_initial_compute(self):
        """compute_te_for_session() sets trunk_quality=0.5, status='pending'."""
        conn = _make_conn()

        _insert_flame_event(conn, "fe1", marker_level=3)
        rows = compute_te_for_session(conn, "s1")

        assert len(rows) == 1
        assert rows[0]["trunk_quality"] == pytest.approx(0.5)
        assert rows[0]["trunk_quality_status"] == "pending"

        conn.close()

    def test_trunk_quality_backfill_with_3_sessions(self):
        """L0 trunk event + 3 downstream sessions with same axis at L5+ -> confirmed."""
        conn = _make_conn()

        # Session 1: L0 trunk event with axis_identified='test-axis'
        _insert_flame_event(
            conn, "fe_trunk", session_id="s1", subject="human",
            marker_level=0, axis_identified="test-axis", human_id="h1",
        )

        # Write TE row for s1 with explicit early timestamp
        conn.execute(
            """
            INSERT INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, created_at)
            VALUES ('te_s1', 's1', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                    'pending', '2024-01-01 00:00:00')
            """
        )

        # Sessions 2, 3, 4: L5+ events with same axis
        for i in range(2, 5):
            sid = f"s{i}"
            _insert_flame_event(
                conn, f"fe_s{i}", session_id=sid, subject="human",
                marker_level=5, axis_identified="test-axis", human_id="h1",
            )
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('te_s{i}', '{sid}', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                        'confirmed', '2024-01-0{i} 00:00:00')
                """
            )

        result = backfill_trunk_quality(conn)
        assert result == 1

        # Verify status changed to confirmed
        row = conn.execute(
            "SELECT trunk_quality_status, trunk_quality "
            "FROM transport_efficiency_sessions WHERE te_id = 'te_s1'"
        ).fetchone()
        assert row[0] == "confirmed"
        # trunk_quality should be > 0 (axis reappeared in downstream sessions)
        assert row[1] > 0

        conn.close()

    def test_trunk_quality_stays_pending_insufficient_sessions(self):
        """Only 2 downstream sessions -> trunk_quality stays pending."""
        conn = _make_conn()

        _insert_flame_event(
            conn, "fe_trunk", session_id="s1", subject="human",
            marker_level=0, axis_identified="test-axis", human_id="h1",
        )

        conn.execute(
            """
            INSERT INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, created_at)
            VALUES ('te_s1', 's1', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                    'pending', '2024-01-01 00:00:00')
            """
        )

        # Only 2 newer sessions (need 3)
        for i in range(2, 4):
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('te_s{i}', 's{i}', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                        'confirmed', '2024-01-0{i} 00:00:00')
                """
            )

        result = backfill_trunk_quality(conn)
        assert result == 0

        row = conn.execute(
            "SELECT trunk_quality_status FROM transport_efficiency_sessions WHERE te_id = 'te_s1'"
        ).fetchone()
        assert row[0] == "pending"

        conn.close()

    def test_te_delta_backfill_with_5_ai_sessions(self):
        """Validated candidate + 5 pre/5 post AI TE sessions -> te_delta computed."""
        conn = _make_conn()

        # Insert validated memory_candidate
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status,
                 created_at, reviewed_at)
            VALUES ('mc_delta', 'test-delta-axis', 'scope for delta test',
                    'flood for delta test', 'validated',
                    '2024-01-10 00:00:00', '2024-01-15 00:00:00')
            """
        )

        # 5 pre-acceptance AI TE sessions (composite_te = 0.3 each)
        for i in range(1, 6):
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('pre_{i}', 'pre_s{i}', 'h1', 'ai', 0.5, 0.5, 0.5, 0.5,
                        0.3, 'confirmed', '2024-01-0{i} 00:00:00')
                """
            )

        # 5 post-acceptance AI TE sessions (composite_te = 0.6 each)
        for i in range(1, 6):
            day = 16 + i
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('post_{i}', 'post_s{i}', 'h1', 'ai', 0.8, 0.8, 0.8, 0.8,
                        0.6, 'confirmed', '2024-01-{day} 00:00:00')
                """
            )

        result = backfill_te_delta(conn)
        assert result == 1

        row = conn.execute(
            "SELECT pre_te_avg, post_te_avg, te_delta FROM memory_candidates WHERE id = 'mc_delta'"
        ).fetchone()

        assert row[0] == pytest.approx(0.3)   # pre_te_avg
        assert row[1] == pytest.approx(0.6)   # post_te_avg
        assert row[2] == pytest.approx(0.3)   # te_delta = 0.6 - 0.3

        conn.close()
