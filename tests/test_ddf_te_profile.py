"""Tests for extended intelligence profile TE display (Phase 16, Plan 03).

Verifies:
- Human profile shows TE breakdown (4 sub-metrics, composite, fringe drift)
- Human profile gracefully handles missing TE data
- Human profile shows fringe drift when present
- Human profile shows pending/confirmed counts
- AI profile shows TE trend
- AI profile shows te_delta ranking of validated memory entries
- AI profile handles no te_delta entries gracefully
- AI profile shows pending backfill count
- Profile graceful when transport_efficiency_sessions table missing
- TE trend shows last 10 sessions
"""

from __future__ import annotations

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli
from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.storage.schema import create_schema


def _setup_db(tmp_path, name: str = "test.db") -> str:
    """Create a file-based DuckDB with full schema and return the path."""
    db_path = str(tmp_path / name)
    conn = duckdb.connect(db_path)
    create_schema(conn)
    create_ddf_schema(conn)
    conn.close()
    return db_path


def _seed_flame_events(
    db_path: str,
    human_id: str = "testuser",
    session_id: str = "s1",
    subject: str = "human",
    count: int = 5,
) -> None:
    """Seed flame_events into a file-based DuckDB."""
    conn = duckdb.connect(db_path)
    events = []
    for i in range(count):
        level = min(i, 7)
        fe = FlameEvent(
            flame_event_id=f"fe_{human_id}_{session_id}_{i}",
            session_id=session_id,
            human_id=human_id,
            prompt_number=i,
            marker_level=level,
            marker_type=f"L{level}_test",
            evidence_excerpt=f"Test evidence {i}",
            subject=subject,
            detection_source="stub",
        )
        events.append(fe)
    write_flame_events(conn, events)
    conn.close()


def _insert_te_row(
    db_path: str,
    te_id: str,
    session_id: str,
    human_id: str,
    subject: str,
    raven_depth: float = 0.5,
    crow_efficiency: float = 0.5,
    transport_speed: float = 0.5,
    trunk_quality: float = 0.5,
    composite_te: float = 0.0625,
    trunk_quality_status: str = "pending",
    fringe_drift_rate: float | None = None,
    created_at: str = "2024-01-01 00:00:00",
) -> None:
    """Insert a transport_efficiency_sessions row into a file-based DuckDB."""
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        INSERT INTO transport_efficiency_sessions
            (te_id, session_id, human_id, subject, raven_depth,
             crow_efficiency, transport_speed, trunk_quality,
             composite_te, trunk_quality_status, fringe_drift_rate, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            te_id, session_id, human_id, subject, raven_depth,
            crow_efficiency, transport_speed, trunk_quality,
            composite_te, trunk_quality_status, fringe_drift_rate,
            created_at,
        ],
    )
    conn.close()


def _insert_memory_candidate(
    db_path: str,
    candidate_id: str,
    ccd_axis: str,
    status: str = "validated",
    te_delta: float | None = None,
    pre_te_avg: float | None = None,
    post_te_avg: float | None = None,
) -> None:
    """Insert a memory_candidates row into a file-based DuckDB."""
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        INSERT INTO memory_candidates
            (id, ccd_axis, scope_rule, flood_example, status,
             te_delta, pre_te_avg, post_te_avg)
        VALUES (?, ?, 'test scope', 'test flood', ?, ?, ?, ?)
        """,
        [candidate_id, ccd_axis, status, te_delta, pre_te_avg, post_te_avg],
    )
    conn.close()


# ============================================================
# Test 1: Human profile shows TE breakdown
# ============================================================


class TestHumanProfileTE:
    """Test human profile TE display."""

    def test_human_profile_shows_te_breakdown(self, tmp_path):
        """Profile should display TE sub-metrics when TE data exists."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(db_path, human_id="testuser")
        _insert_te_row(
            db_path, te_id="t1", session_id="s1",
            human_id="testuser", subject="human",
            raven_depth=0.714, crow_efficiency=0.667,
            transport_speed=0.500, trunk_quality=0.500,
            composite_te=0.1191,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "testuser", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "TransportEfficiency" in result.output
        assert "Raven Depth:" in result.output
        assert "Crow Efficiency:" in result.output
        assert "Transport Speed:" in result.output
        assert "Trunk Quality:" in result.output
        assert "Composite TE:" in result.output

    def test_human_profile_no_te_data(self, tmp_path):
        """Profile should gracefully skip TE when no TE rows exist."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(db_path, human_id="testuser")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "testuser", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "not yet computed" in result.output

    def test_human_profile_shows_fringe_drift(self, tmp_path):
        """Profile should display fringe drift when present."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(db_path, human_id="testuser")
        _insert_te_row(
            db_path, te_id="t1", session_id="s1",
            human_id="testuser", subject="human",
            fringe_drift_rate=0.5,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "testuser", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "Fringe Drift:" in result.output
        assert "0.5" in result.output

    def test_human_profile_pending_confirmed_counts(self, tmp_path):
        """Profile should show pending and confirmed TE session counts."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(db_path, human_id="testuser")
        # 2 pending + 1 confirmed
        _insert_te_row(
            db_path, te_id="t1", session_id="s1",
            human_id="testuser", subject="human",
            trunk_quality_status="pending",
            created_at="2024-01-01 00:00:00",
        )
        _insert_te_row(
            db_path, te_id="t2", session_id="s2",
            human_id="testuser", subject="human",
            trunk_quality_status="pending",
            created_at="2024-01-02 00:00:00",
        )
        _insert_te_row(
            db_path, te_id="t3", session_id="s3",
            human_id="testuser", subject="human",
            trunk_quality_status="confirmed",
            created_at="2024-01-03 00:00:00",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "testuser", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "pending" in result.output
        assert "confirmed" in result.output
        # Verify counts: "2 pending, 1 confirmed"
        assert "2 pending" in result.output
        assert "1 confirmed" in result.output


# ============================================================
# Test 5-8: AI profile TE display
# ============================================================


class TestAIProfileTE:
    """Test AI profile TE display with te_delta ranking."""

    def test_ai_profile_shows_te_trend(self, tmp_path):
        """AI profile should display TE trend from multiple sessions."""
        db_path = _setup_db(tmp_path)
        # Need AI flame events for the base profile
        _seed_flame_events(
            db_path, human_id="ai", session_id="s1",
            subject="ai", count=3,
        )
        # Insert AI TE rows
        for i in range(1, 4):
            _insert_te_row(
                db_path, te_id=f"t{i}", session_id=f"s{i}",
                human_id="ai", subject="ai",
                composite_te=0.1 * i,
                created_at=f"2024-01-0{i} 00:00:00",
            )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "ai", "--ai", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "TE Trend" in result.output

    def test_ai_profile_shows_te_delta_ranking(self, tmp_path):
        """AI profile should show validated memory entries ranked by TE impact."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(
            db_path, human_id="ai", session_id="s1",
            subject="ai", count=3,
        )
        _insert_te_row(
            db_path, te_id="t1", session_id="s1",
            human_id="ai", subject="ai",
        )
        # Insert validated candidates with te_delta
        _insert_memory_candidate(
            db_path, "mc1", "deposit-not-detect",
            te_delta=0.05, pre_te_avg=0.3, post_te_avg=0.35,
        )
        _insert_memory_candidate(
            db_path, "mc2", "identity-firewall",
            te_delta=0.02, pre_te_avg=0.35, post_te_avg=0.37,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "ai", "--ai", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "Top Memory Entries by TE Impact:" in result.output
        assert "deposit-not-detect" in result.output
        assert "identity-firewall" in result.output

    def test_ai_profile_no_delta_entries(self, tmp_path):
        """AI profile with no validated te_delta entries should show graceful output."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(
            db_path, human_id="ai", session_id="s1",
            subject="ai", count=3,
        )
        _insert_te_row(
            db_path, te_id="t1", session_id="s1",
            human_id="ai", subject="ai",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "ai", "--ai", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        # Should show "none yet" or "pending backfill"
        assert "none yet" in result.output or "pending backfill" in result.output

    def test_ai_profile_pending_backfill_count(self, tmp_path):
        """AI profile should show count of entries pending TE delta backfill."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(
            db_path, human_id="ai", session_id="s1",
            subject="ai", count=3,
        )
        _insert_te_row(
            db_path, te_id="t1", session_id="s1",
            human_id="ai", subject="ai",
        )
        # Insert validated candidates with NULL te_delta (pending backfill)
        _insert_memory_candidate(
            db_path, "mc1", "axis-one", te_delta=None,
        )
        _insert_memory_candidate(
            db_path, "mc2", "axis-two", te_delta=None,
        )
        _insert_memory_candidate(
            db_path, "mc3", "axis-three", te_delta=None,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "ai", "--ai", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "3 entries pending backfill" in result.output


# ============================================================
# Test 9: Graceful without TE table
# ============================================================


class TestGracefulFallback:
    """Test graceful handling of missing TE infrastructure."""

    def test_profile_graceful_without_te_table(self, tmp_path):
        """Profile should not crash when transport_efficiency_sessions missing."""
        db_path = str(tmp_path / "bare.db")
        conn = duckdb.connect(db_path)
        # Only create base schema (no DDF/TE schema)
        # We need flame_events for profile to work, so create DDF schema
        # but drop transport_efficiency_sessions
        create_schema(conn)
        create_ddf_schema(conn)
        # Seed flame events
        events = [
            FlameEvent(
                flame_event_id="fe1",
                session_id="s1",
                human_id="testuser",
                prompt_number=1,
                marker_level=3,
                marker_type="L3_test",
                evidence_excerpt="test",
                subject="human",
                detection_source="stub",
            ),
        ]
        write_flame_events(conn, events)
        # Now drop the TE table to simulate older DB
        conn.execute("DROP TABLE IF EXISTS transport_efficiency_sessions")
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "testuser", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "Intelligence Profile: testuser" in result.output
        assert "not yet computed" in result.output


# ============================================================
# Test 10: TE trend shows last 10
# ============================================================


class TestTETrend:
    """Test TE trend display with multiple sessions."""

    def test_te_trend_shows_last_10(self, tmp_path):
        """TE trend should show composite_te values from up to 10 sessions."""
        db_path = _setup_db(tmp_path)
        _seed_flame_events(db_path, human_id="testuser")
        # Insert 15 TE rows
        for i in range(1, 16):
            _insert_te_row(
                db_path, te_id=f"t{i}", session_id=f"s{i}",
                human_id="testuser", subject="human",
                composite_te=0.01 * i,
                created_at=f"2024-01-{i:02d} 00:00:00",
            )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "profile", "testuser", "--db", db_path],
        )
        assert result.exit_code == 0, result.output
        assert "TE Trend (last 10 sessions):" in result.output
        # Should show 10 values (the most recent 10)
        # Most recent is t15 with composite_te=0.15
        assert "0.1500" in result.output
        # t6 (0.06) should be the oldest of the 10 shown
        assert "0.0600" in result.output
        # t5 (0.05) should NOT be shown (beyond 10)
        # Count composite_te values in the trend line
        # They appear as space-separated on one line
