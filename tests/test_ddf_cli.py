"""Tests for DDF Intelligence CLI commands (Phase 15, Plan 06).

Verifies:
- intelligence group is registered in cli
- profile command displays human IntelligenceProfile
- profile command displays AI profile
- profile command handles missing data
- stagnant command lists/reports stagnant constraints
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli
from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.storage.schema import create_schema


def _seed_flame_events(
    conn: duckdb.DuckDBPyConnection,
    human_id: str = "test_human",
    session_id: str = "session_01",
    count: int = 5,
    subject: str = "human",
) -> None:
    """Seed flame_events for testing."""
    events = []
    for i in range(count):
        level = min(i, 7)  # L0 through L7
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


def _seed_stagnant_constraint(
    conn: duckdb.DuckDBPyConnection,
    constraint_id: str = "stagnant_c1",
    firing_count: int = 15,
) -> None:
    """Seed session_constraint_eval data that will produce a stagnant metric."""
    # All evaluations have the same scope prefix -> radius=1 -> stagnant
    for i in range(firing_count):
        evidence = f'{{"scope_path": "src/pipeline/foo.py"}}'
        conn.execute(
            """
            INSERT INTO session_constraint_eval
            (session_id, constraint_id, eval_state, evidence_json, eval_ts)
            VALUES (?, ?, 'HONORED', ?, NOW())
            """,
            [f"session_{i:03d}", constraint_id, evidence],
        )


class TestIntelligenceGroupRegistered:
    """Verify intelligence group is registered in CLI."""

    def test_intelligence_group_registered(self):
        """intelligence should be a registered command group."""
        assert "intelligence" in cli.commands

    def test_intelligence_has_profile(self):
        """intelligence group should have profile command."""
        from src.pipeline.cli.intelligence import intelligence_group
        assert "profile" in intelligence_group.commands

    def test_intelligence_has_stagnant(self):
        """intelligence group should have stagnant command."""
        from src.pipeline.cli.intelligence import intelligence_group
        assert "stagnant" in intelligence_group.commands


class TestProfileCommand:
    """Test intelligence profile command."""

    def test_profile_human_displays(self, tmp_path):
        """Profile command should display metrics for a seeded human."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_flame_events(conn, human_id="test_human", count=10)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "profile", "test_human", "--db", db_path])
        assert result.exit_code == 0
        assert "Intelligence Profile: test_human" in result.output
        assert "Sessions:" in result.output
        assert "Flame Frequency:" in result.output
        assert "Avg Marker Level:" in result.output
        assert "Max Marker Level:" in result.output
        assert "Spiral Depth:" in result.output
        assert "Flood Rate:" in result.output

    def test_profile_ai_displays(self, tmp_path):
        """Profile command with --ai should display AI profile."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_flame_events(conn, human_id="default_human", subject="ai", count=5)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "profile", "ai", "--ai", "--db", db_path])
        assert result.exit_code == 0
        assert "Intelligence Profile: AI" in result.output

    def test_profile_no_data(self, tmp_path):
        """Profile for unknown human should display 'No flame events found'."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "profile", "unknown_human", "--db", db_path])
        assert result.exit_code == 0
        assert "No flame events found for human_id: unknown_human" in result.output

    def test_profile_formats_flood_rate(self, tmp_path):
        """Flood rate should be displayed as a decimal with percentage."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        # Seed events including some Level 6+
        events = []
        for i in range(10):
            level = 6 if i >= 7 else i  # 3 out of 10 are L6+
            fe = FlameEvent(
                flame_event_id=f"fe_flood_{i}",
                session_id="session_01",
                human_id="flood_human",
                prompt_number=i,
                marker_level=level,
                marker_type=f"L{level}_test",
                subject="human",
                detection_source="stub",
            )
            events.append(fe)
        write_flame_events(conn, events)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "profile", "flood_human", "--db", db_path])
        assert result.exit_code == 0
        assert "Flood Rate:" in result.output
        # Should show percentage like "30%"
        assert "%" in result.output

    def test_profile_read_only_db(self, tmp_path):
        """Profile command should work with a pre-existing database."""
        db_path = str(tmp_path / "readonly_test.db")
        # First create and seed the DB
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_flame_events(conn, human_id="readonly_human", count=3)
        conn.close()

        # Now invoke CLI which opens read-only
        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "profile", "readonly_human", "--db", db_path])
        assert result.exit_code == 0
        assert "readonly_human" in result.output


class TestStagnantCommand:
    """Test intelligence stagnant command."""

    def test_stagnant_lists_constraints(self, tmp_path):
        """Stagnant command should list stagnant constraints."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_stagnant_constraint(conn, "stagnant_c1", firing_count=15)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "stagnant", "--db", db_path])
        assert result.exit_code == 0
        assert "stagnant_c1" in result.output
        assert "Total stagnant:" in result.output

    def test_stagnant_none_found(self, tmp_path):
        """Stagnant command with no stagnant constraints should display message."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["intelligence", "stagnant", "--db", db_path])
        assert result.exit_code == 0
        assert "No stagnant constraints detected." in result.output
