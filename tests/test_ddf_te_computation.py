"""Tests for Transport Efficiency computation engine (Phase 16, Plan 02).

Verifies:
- compute_te_for_session with human-only, human+AI, and empty flame_events
- raven_depth = MAX(marker_level) / 7.0
- crow_efficiency = fraction with axis_identified
- transport_speed = fraction with flood_confirmed
- trunk_quality defaults to 0.5 with pending status
- composite_te = product of 4 sub-metrics
- compute_fringe_drift binary values (0.0, 1.0, None)
- write_te_rows INSERT OR REPLACE idempotency
- backfill_trunk_quality with 3+ newer sessions
- backfill_trunk_quality stays pending with < 3 newer sessions
- backfill_te_delta with 5+ post-acceptance sessions
- backfill_te_delta stays NULL with < 5 post-acceptance sessions
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.transport_efficiency import (
    backfill_te_delta,
    backfill_trunk_quality,
    compute_fringe_drift,
    compute_te_for_session,
    write_te_rows,
)


def _make_conn() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with full schema."""
    conn = duckdb.connect(":memory:")
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
) -> None:
    """Insert a flame_event for testing."""
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
# compute_te_for_session Tests
# ============================================================


class TestComputeTEForSession:
    """Test compute_te_for_session with various flame_event configurations."""

    def test_human_only_flame_events(self):
        """Should produce one row for human subject."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", subject="human", marker_level=3)
        _insert_flame_event(conn, "fe2", session_id="s1", subject="human", marker_level=5)

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 1
        assert rows[0]["subject"] == "human"
        conn.close()

    def test_human_and_ai_flame_events(self):
        """Should produce two rows: one human, one AI."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", subject="human", marker_level=3)
        _insert_flame_event(conn, "fe2", session_id="s1", subject="ai", marker_level=4)

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 2
        subjects = {r["subject"] for r in rows}
        assert subjects == {"human", "ai"}
        conn.close()

    def test_no_flame_events_returns_empty(self):
        """Should return empty list when no flame_events for session."""
        conn = _make_conn()
        rows = compute_te_for_session(conn, "nonexistent")
        assert rows == []
        conn.close()

    def test_raven_depth_calculation(self):
        """raven_depth should be MAX(marker_level) / 7.0."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", marker_level=0)
        _insert_flame_event(conn, "fe2", session_id="s1", marker_level=3)
        _insert_flame_event(conn, "fe3", session_id="s1", marker_level=7)

        rows = compute_te_for_session(conn, "s1")
        assert len(rows) == 1
        assert rows[0]["raven_depth"] == pytest.approx(7.0 / 7.0)
        conn.close()

    def test_raven_depth_partial(self):
        """raven_depth should be 3/7 when max level is 3."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", marker_level=1)
        _insert_flame_event(conn, "fe2", session_id="s1", marker_level=3)

        rows = compute_te_for_session(conn, "s1")
        assert rows[0]["raven_depth"] == pytest.approx(3.0 / 7.0)
        conn.close()

    def test_crow_efficiency_with_mix(self):
        """crow_efficiency = fraction with axis_identified non-NULL."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", marker_level=2, axis_identified="ax1")
        _insert_flame_event(conn, "fe2", session_id="s1", marker_level=3, axis_identified=None)
        _insert_flame_event(conn, "fe3", session_id="s1", marker_level=4, axis_identified="ax2")

        rows = compute_te_for_session(conn, "s1")
        # 2 out of 3 have axis_identified
        assert rows[0]["crow_efficiency"] == pytest.approx(2.0 / 3.0)
        conn.close()

    def test_transport_speed_with_mix(self):
        """transport_speed = fraction with flood_confirmed true."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", marker_level=6, flood_confirmed=True)
        _insert_flame_event(conn, "fe2", session_id="s1", marker_level=5, flood_confirmed=False)
        _insert_flame_event(conn, "fe3", session_id="s1", marker_level=6, flood_confirmed=True)
        _insert_flame_event(conn, "fe4", session_id="s1", marker_level=4, flood_confirmed=False)

        rows = compute_te_for_session(conn, "s1")
        # 2 out of 4 flood_confirmed
        assert rows[0]["transport_speed"] == pytest.approx(2.0 / 4.0)
        conn.close()

    def test_trunk_quality_defaults_to_pending(self):
        """trunk_quality should be 0.5 with 'pending' status."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", marker_level=3)

        rows = compute_te_for_session(conn, "s1")
        assert rows[0]["trunk_quality"] == 0.5
        assert rows[0]["trunk_quality_status"] == "pending"
        conn.close()

    def test_composite_te_is_product(self):
        """composite_te = raven_depth * crow_efficiency * transport_speed * trunk_quality."""
        conn = _make_conn()
        # Level 7 (raven_depth=1.0), all have axis (crow=1.0), all flood (transport=1.0)
        _insert_flame_event(
            conn, "fe1", session_id="s1", marker_level=7,
            axis_identified="ax1", flood_confirmed=True,
        )

        rows = compute_te_for_session(conn, "s1")
        # 1.0 * 1.0 * 1.0 * 0.5 = 0.5
        assert rows[0]["composite_te"] == pytest.approx(0.5)
        conn.close()

    def test_composite_te_mixed_values(self):
        """composite_te with partial sub-metrics."""
        conn = _make_conn()
        # 2 events: level 3 and level 5
        # axis_identified: one with, one without -> crow = 0.5
        # flood_confirmed: one true, one false -> transport = 0.5
        _insert_flame_event(
            conn, "fe1", session_id="s1", marker_level=3,
            axis_identified="ax1", flood_confirmed=True,
        )
        _insert_flame_event(
            conn, "fe2", session_id="s1", marker_level=5,
            axis_identified=None, flood_confirmed=False,
        )

        rows = compute_te_for_session(conn, "s1")
        # raven_depth = 5/7, crow = 0.5, transport = 0.5, trunk = 0.5
        expected = (5.0 / 7.0) * 0.5 * 0.5 * 0.5
        assert rows[0]["composite_te"] == pytest.approx(expected)
        conn.close()


# ============================================================
# compute_fringe_drift Tests
# ============================================================


class TestComputeFringeDrift:
    """Test compute_fringe_drift binary detection."""

    def test_fringe_with_flood_returns_zero(self):
        """Should return 0.0 when fringe events + flood-confirmed Level 6+ exist."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", subject="human", marker_level=1)
        _insert_flame_event(
            conn, "fe2", session_id="s1", subject="human",
            marker_level=6, flood_confirmed=True,
        )

        result = compute_fringe_drift(conn, "s1", "human")
        assert result == 0.0
        conn.close()

    def test_fringe_without_flood_returns_one(self):
        """Should return 1.0 when fringe events exist but no flood-confirmed."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", subject="human", marker_level=2)
        _insert_flame_event(conn, "fe2", session_id="s1", subject="human", marker_level=4)

        result = compute_fringe_drift(conn, "s1", "human")
        assert result == 1.0
        conn.close()

    def test_no_fringe_returns_none(self):
        """Should return None when no Level 1-2 events exist."""
        conn = _make_conn()
        _insert_flame_event(conn, "fe1", session_id="s1", subject="human", marker_level=5)

        result = compute_fringe_drift(conn, "s1", "human")
        assert result is None
        conn.close()

    def test_no_events_returns_none(self):
        """Should return None when no events at all."""
        conn = _make_conn()
        result = compute_fringe_drift(conn, "nonexistent", "human")
        assert result is None
        conn.close()


# ============================================================
# write_te_rows Tests
# ============================================================


class TestWriteTERows:
    """Test write_te_rows INSERT OR REPLACE."""

    def test_write_rows(self):
        """Should insert TE rows and return count."""
        conn = _make_conn()
        rows = [
            {
                "te_id": "t1",
                "session_id": "s1",
                "human_id": "h1",
                "subject": "human",
                "raven_depth": 0.5,
                "crow_efficiency": 0.8,
                "transport_speed": 0.6,
                "trunk_quality": 0.5,
                "composite_te": 0.12,
                "trunk_quality_status": "pending",
                "fringe_drift_rate": 1.0,
            }
        ]
        count = write_te_rows(conn, rows)
        assert count == 1

        stored = conn.execute(
            "SELECT te_id, raven_depth FROM transport_efficiency_sessions"
        ).fetchall()
        assert len(stored) == 1
        assert stored[0][0] == "t1"
        assert stored[0][1] == pytest.approx(0.5)
        conn.close()

    def test_replace_idempotency(self):
        """Writing same te_id twice should replace, not duplicate."""
        conn = _make_conn()
        row = {
            "te_id": "t1",
            "session_id": "s1",
            "human_id": "h1",
            "subject": "human",
            "raven_depth": 0.5,
            "crow_efficiency": 0.8,
            "transport_speed": 0.6,
            "trunk_quality": 0.5,
            "composite_te": 0.12,
            "trunk_quality_status": "pending",
            "fringe_drift_rate": None,
        }
        write_te_rows(conn, [row])

        # Write again with updated value
        row["raven_depth"] = 0.9
        write_te_rows(conn, [row])

        stored = conn.execute(
            "SELECT raven_depth FROM transport_efficiency_sessions WHERE te_id = 't1'"
        ).fetchone()
        assert stored[0] == pytest.approx(0.9)

        total = conn.execute(
            "SELECT COUNT(*) FROM transport_efficiency_sessions"
        ).fetchone()
        assert total[0] == 1
        conn.close()

    def test_write_empty_list(self):
        """Writing empty list should return 0."""
        conn = _make_conn()
        count = write_te_rows(conn, [])
        assert count == 0
        conn.close()


# ============================================================
# backfill_trunk_quality Tests
# ============================================================


class TestBackfillTrunkQuality:
    """Test backfill_trunk_quality with newer session conditions."""

    def test_confirms_with_3_newer_sessions(self):
        """Should confirm trunk_quality when 3+ newer sessions exist."""
        conn = _make_conn()

        # Original session with pending trunk_quality
        _insert_flame_event(
            conn, "fe_orig", session_id="s1", subject="human",
            marker_level=0, axis_identified="ax1", human_id="h1",
        )
        # Seed TE row for s1 (pending)
        conn.execute(
            """
            INSERT INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, created_at)
            VALUES ('t1', 's1', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                    'pending', '2024-01-01 00:00:00')
            """
        )

        # 3 newer sessions with Level 5+ axes matching
        for i in range(2, 5):
            sid = f"s{i}"
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('t{i}', '{sid}', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                        'confirmed', '2024-01-0{i} 00:00:00')
                """
            )
            # Level 5+ event with matching axis in newer session
            _insert_flame_event(
                conn, f"fe_s{i}", session_id=sid, subject="human",
                marker_level=5, axis_identified="ax1", human_id="h1",
            )

        result = backfill_trunk_quality(conn)
        assert result == 1

        # Verify status changed to confirmed
        row = conn.execute(
            "SELECT trunk_quality_status FROM transport_efficiency_sessions WHERE te_id = 't1'"
        ).fetchone()
        assert row[0] == "confirmed"
        conn.close()

    def test_stays_pending_with_fewer_than_3(self):
        """Should stay pending when < 3 newer sessions exist."""
        conn = _make_conn()

        # Original session
        conn.execute(
            """
            INSERT INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, created_at)
            VALUES ('t1', 's1', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                    'pending', '2024-01-01 00:00:00')
            """
        )

        # Only 2 newer sessions
        for i in range(2, 4):
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('t{i}', 's{i}', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                        'confirmed', '2024-01-0{i} 00:00:00')
                """
            )

        result = backfill_trunk_quality(conn)
        assert result == 0

        row = conn.execute(
            "SELECT trunk_quality_status FROM transport_efficiency_sessions WHERE te_id = 't1'"
        ).fetchone()
        assert row[0] == "pending"
        conn.close()

    def test_no_level0_events_stays_half_but_confirms(self):
        """No Level 0 events: trunk_quality stays 0.5 but status becomes confirmed."""
        conn = _make_conn()

        # Original session with no Level 0 events (Level 3 instead)
        _insert_flame_event(
            conn, "fe_orig", session_id="s1", subject="human",
            marker_level=3, axis_identified="ax1", human_id="h1",
        )
        conn.execute(
            """
            INSERT INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, created_at)
            VALUES ('t1', 's1', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                    'pending', '2024-01-01 00:00:00')
            """
        )

        # 3 newer sessions
        for i in range(2, 5):
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('t{i}', 's{i}', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                        'confirmed', '2024-01-0{i} 00:00:00')
                """
            )

        result = backfill_trunk_quality(conn)
        assert result == 1

        row = conn.execute(
            "SELECT trunk_quality, trunk_quality_status FROM transport_efficiency_sessions WHERE te_id = 't1'"
        ).fetchone()
        assert row[0] == pytest.approx(0.5)
        assert row[1] == "confirmed"
        conn.close()

    def test_backfill_recalculates_composite_te(self):
        """Backfill should recalculate composite_te with new trunk_quality."""
        conn = _make_conn()

        # Original session with Level 0 axis
        _insert_flame_event(
            conn, "fe_orig", session_id="s1", subject="human",
            marker_level=0, axis_identified="test-axis", human_id="h1",
        )
        conn.execute(
            """
            INSERT INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, created_at)
            VALUES ('t1', 's1', 'h1', 'human', 1.0, 1.0, 1.0, 0.5, 0.5,
                    'pending', '2024-01-01 00:00:00')
            """
        )

        # 3 newer sessions, all with matching axis at Level 5+
        for i in range(2, 5):
            sid = f"s{i}"
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('t{i}', '{sid}', 'h1', 'human', 0.5, 0.5, 0.5, 0.5, 0.0625,
                        'confirmed', '2024-01-0{i} 00:00:00')
                """
            )
            _insert_flame_event(
                conn, f"fe_s{i}", session_id=sid, subject="human",
                marker_level=5, axis_identified="test-axis", human_id="h1",
            )

        backfill_trunk_quality(conn)

        row = conn.execute(
            "SELECT trunk_quality, composite_te FROM transport_efficiency_sessions WHERE te_id = 't1'"
        ).fetchone()
        # All 3 sessions have the axis at Level 5+, so trunk_quality = 3/3 = 1.0
        assert row[0] == pytest.approx(1.0)
        # composite_te = 1.0 * 1.0 * 1.0 * 1.0 = 1.0
        assert row[1] == pytest.approx(1.0)
        conn.close()


# ============================================================
# backfill_te_delta Tests
# ============================================================


class TestBackfillTEDelta:
    """Test backfill_te_delta with memory_candidates."""

    def test_computes_delta_with_sufficient_sessions(self):
        """Should compute te_delta when 5+ post-acceptance AI sessions exist."""
        conn = _make_conn()

        # Insert validated candidate
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status, created_at, reviewed_at)
            VALUES ('mc1', 'ax1', 'scope', 'flood', 'validated',
                    '2024-01-10 00:00:00', '2024-01-15 00:00:00')
            """
        )

        # 5 pre-acceptance AI TE sessions
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

        # 5 post-acceptance AI TE sessions
        for i in range(1, 6):
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('post_{i}', 'post_s{i}', 'h1', 'ai', 0.8, 0.8, 0.8, 0.8,
                        0.6, 'confirmed', '2024-01-{16 + i} 00:00:00')
                """
            )

        result = backfill_te_delta(conn)
        assert result == 1

        row = conn.execute(
            "SELECT pre_te_avg, post_te_avg, te_delta FROM memory_candidates WHERE id = 'mc1'"
        ).fetchone()
        assert row[0] == pytest.approx(0.3)  # pre_te_avg
        assert row[1] == pytest.approx(0.6)  # post_te_avg
        assert row[2] == pytest.approx(0.3)  # te_delta = 0.6 - 0.3
        conn.close()

    def test_stays_null_with_fewer_than_5_post_sessions(self):
        """Should stay NULL when < 5 post-acceptance AI sessions exist."""
        conn = _make_conn()

        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status, created_at, reviewed_at)
            VALUES ('mc1', 'ax1', 'scope', 'flood', 'validated',
                    '2024-01-10 00:00:00', '2024-01-15 00:00:00')
            """
        )

        # 5 pre-acceptance sessions
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

        # Only 3 post-acceptance sessions (need 5)
        for i in range(1, 4):
            conn.execute(
                f"""
                INSERT INTO transport_efficiency_sessions
                    (te_id, session_id, human_id, subject, raven_depth,
                     crow_efficiency, transport_speed, trunk_quality,
                     composite_te, trunk_quality_status, created_at)
                VALUES ('post_{i}', 'post_s{i}', 'h1', 'ai', 0.8, 0.8, 0.8, 0.8,
                        0.6, 'confirmed', '2024-01-{16 + i} 00:00:00')
                """
            )

        result = backfill_te_delta(conn)
        assert result == 0

        row = conn.execute(
            "SELECT te_delta FROM memory_candidates WHERE id = 'mc1'"
        ).fetchone()
        assert row[0] is None
        conn.close()

    def test_skips_non_validated_candidates(self):
        """Should only process validated candidates."""
        conn = _make_conn()

        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status, created_at, reviewed_at)
            VALUES ('mc_pending', 'ax1', 'scope', 'flood', 'pending',
                    '2024-01-10 00:00:00', NULL)
            """
        )

        result = backfill_te_delta(conn)
        assert result == 0
        conn.close()

    def test_skips_already_backfilled(self):
        """Should skip candidates that already have te_delta."""
        conn = _make_conn()

        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status,
                 created_at, reviewed_at, te_delta)
            VALUES ('mc1', 'ax1', 'scope', 'flood', 'validated',
                    '2024-01-10 00:00:00', '2024-01-15 00:00:00', 0.2)
            """
        )

        result = backfill_te_delta(conn)
        assert result == 0
        conn.close()
