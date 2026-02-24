"""End-to-end integration tests for Phase 16.1 topology pipeline.

15 tests covering:
- End-to-end deposit flow (detector -> generator -> writer) [tests 1-5]
- Frontier warning flow (fire/suppress/restore) [tests 6-9]
- Retirement flow (degrade -> retire -> frontier restored) [tests 10-12]
- CLI commands (list, show, edges) [tests 13-15]
"""

from __future__ import annotations

import json

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.topology.detector import (
    ConjunctiveFlameDetector,
    ConjunctiveTrigger,
)
from src.pipeline.ddf.topology.generator import EdgeGenerator
from src.pipeline.ddf.topology.models import ActivationCondition, EdgeRecord
from src.pipeline.ddf.topology.writer import EdgeWriter
from src.pipeline.ddf.topology.frontier import FrontierChecker
from src.pipeline.storage.schema import create_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


@pytest.fixture
def db_path(tmp_path):
    """File-based DuckDB for CLI tests."""
    path = str(tmp_path / "test.db")
    c = duckdb.connect(path)
    create_schema(c)
    c.close()
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TWO_AXES = ["deposit-not-detect", "ground-truth-pointer"]
THREE_AXES = ["deposit-not-detect", "ground-truth-pointer", "identity-firewall"]
ONE_AXIS = ["deposit-not-detect"]


def _make_flame(
    session_id: str = "sess-int-001",
    prompt_number: int = 1,
    marker_level: int = 2,
    marker_type: str = "trunk_identification",
    axis_identified: str | None = None,
) -> FlameEvent:
    """Create a FlameEvent with deterministic ID."""
    return FlameEvent(
        flame_event_id=FlameEvent.make_id(session_id, prompt_number, marker_type),
        session_id=session_id,
        prompt_number=prompt_number,
        marker_level=marker_level,
        marker_type=marker_type,
        axis_identified=axis_identified,
    )


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
            "session_id": "sess-int-001",
            "episode_id": "ep-001",
            "flame_event_ids": ["fe-001", "fe-002"],
        },
        abstraction_level=5,
        created_session_id="sess-int-001",
    )
    defaults.update(kwargs)
    return EdgeRecord(**defaults)


def _insert_active_edge(
    conn: duckdb.DuckDBPyConnection,
    axis_a: str = "axis-a",
    axis_b: str = "axis-b",
    goal_type: list[str] | None = None,
) -> str:
    """Insert an active edge directly into axis_edges, return edge_id."""
    rel_text = f"{axis_a} constrains {axis_b}"
    edge_id = EdgeRecord.make_id(axis_a, axis_b, rel_text)
    ac = {"goal_type": goal_type or ["any"], "scope_prefix": "", "min_axes_simultaneously_active": 2}
    ev = {"session_id": "sess-int-001", "episode_id": "ep-001", "flame_event_ids": ["fe-001"]}
    conn.execute(
        "INSERT OR REPLACE INTO axis_edges "
        "(edge_id, axis_a, axis_b, relationship_text, activation_condition, "
        "evidence, abstraction_level, status, trunk_quality, created_session_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1.0, ?)",
        [edge_id, axis_a, axis_b, rel_text, json.dumps(ac), json.dumps(ev), 5, "sess-int-001"],
    )
    return edge_id


# ===========================================================================
# End-to-end deposit flow (tests 1-5)
# ===========================================================================


class TestEndToEndDepositFlow:
    """Tests for the full pipeline: Detector -> Generator -> Writer."""

    def test_e2e_conjunctive_trigger_to_edge_deposit(self, conn) -> None:
        """Test 1: Level 5 event with two active axes -> edge deposited."""
        detector = ConjunctiveFlameDetector()
        generator = EdgeGenerator()
        writer = EdgeWriter(conn)

        # Build baseline: 10 events at level 2 -> median = 2.0
        for i in range(10):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Triggering event: level 5, delta = 5 - 2 = 3, two axes
        trigger_event = _make_flame(marker_level=5, prompt_number=100)
        trigger = detector.check_conjunctive(
            trigger_event, TWO_AXES, episode_id="ep-001"
        )

        assert trigger is not None
        assert isinstance(trigger, ConjunctiveTrigger)
        assert trigger.delta == 3.0
        assert len(trigger.active_axes) == 2

        # Generate edge records
        records = generator.generate(trigger)
        assert len(records) == 1  # C(2,2) = 1

        # Write to axis_edges
        result = writer.write_edge(records[0])
        assert result == {"written": 1}

        # Verify in DB
        count = conn.execute("SELECT COUNT(*) FROM axis_edges").fetchone()[0]
        assert count == 1

    def test_e2e_conjunctive_rejects_insufficient_level(self, conn) -> None:
        """Test 2: Level 3 event -> no trigger -> no edge."""
        detector = ConjunctiveFlameDetector()

        # Build baseline: 10 events at level 2 -> median = 2.0
        for i in range(10):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 3 < MIN_LEVEL=5
        event = _make_flame(marker_level=3, prompt_number=100)
        trigger = detector.check_conjunctive(event, TWO_AXES, episode_id="ep-001")

        assert trigger is None

        # No edges should exist
        count = conn.execute("SELECT COUNT(*) FROM axis_edges").fetchone()[0]
        assert count == 0

    def test_e2e_conjunctive_rejects_insufficient_delta(self, conn) -> None:
        """Test 3: High baseline, low delta -> no trigger."""
        detector = ConjunctiveFlameDetector()

        # Build baseline at level 4 -> median = 4.0
        for i in range(10):
            event = _make_flame(marker_level=4, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 5, delta = 5 - 4 = 1.0 < MIN_DELTA=2.0
        event = _make_flame(marker_level=5, prompt_number=100)
        trigger = detector.check_conjunctive(event, TWO_AXES, episode_id="ep-001")

        assert trigger is None

        count = conn.execute("SELECT COUNT(*) FROM axis_edges").fetchone()[0]
        assert count == 0

    def test_e2e_conjunctive_rejects_single_axis(self, conn) -> None:
        """Test 4: Level 5, high delta, but only 1 axis -> no trigger."""
        detector = ConjunctiveFlameDetector()

        # Build baseline: 10 events at level 2 -> median = 2.0
        for i in range(10):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 5, delta = 3, but only 1 axis
        event = _make_flame(marker_level=5, prompt_number=100)
        trigger = detector.check_conjunctive(event, ONE_AXIS, episode_id="ep-001")

        assert trigger is None

        count = conn.execute("SELECT COUNT(*) FROM axis_edges").fetchone()[0]
        assert count == 0

    def test_e2e_three_axes_three_edges(self, conn) -> None:
        """Test 5: 3 axes -> C(3,2) = 3 edge records deposited."""
        detector = ConjunctiveFlameDetector()
        generator = EdgeGenerator()
        writer = EdgeWriter(conn)

        # Build baseline: 10 events at level 2
        for i in range(10):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 6, delta = 4, three axes
        trigger_event = _make_flame(marker_level=6, prompt_number=100)
        trigger = detector.check_conjunctive(
            trigger_event, THREE_AXES, episode_id="ep-001"
        )

        assert trigger is not None
        assert len(trigger.active_axes) == 3

        records = generator.generate(trigger)
        assert len(records) == 3  # C(3,2) = 3

        for record in records:
            writer.write_edge(record)

        count = conn.execute("SELECT COUNT(*) FROM axis_edges").fetchone()[0]
        assert count == 3


# ===========================================================================
# Frontier warning flow (tests 6-9)
# ===========================================================================


class TestFrontierWarningFlow:
    """Tests for frontier warning fire/suppress/restore lifecycle."""

    def test_e2e_frontier_warning_fires_no_edges(self, conn) -> None:
        """Test 6: Two known axes, no edges -> FRONTIER_WARNING fires."""
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(["axis-a", "axis-b"])

        assert len(warnings) == 1
        assert "FRONTIER_WARNING" in warnings[0]
        assert "axis-a" in warnings[0]
        assert "axis-b" in warnings[0]

    def test_e2e_frontier_warning_suppressed_by_active_edge(self, conn) -> None:
        """Test 7: Active edge for pair -> no FRONTIER_WARNING."""
        _insert_active_edge(conn, "axis-a", "axis-b")

        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(["axis-a", "axis-b"])

        assert len(warnings) == 0

    def test_e2e_frontier_warning_not_suppressed_by_superseded_edge(self, conn) -> None:
        """Test 8: Superseded edge -> FRONTIER_WARNING still fires."""
        edge_id = _insert_active_edge(conn, "axis-a", "axis-b")

        # Supersede the edge
        conn.execute(
            "UPDATE axis_edges SET status = 'superseded' WHERE edge_id = ?",
            [edge_id],
        )

        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(["axis-a", "axis-b"])

        assert len(warnings) == 1
        assert "FRONTIER_WARNING" in warnings[0]

    def test_e2e_frontier_warning_activation_condition_mismatch(self, conn) -> None:
        """Test 9: Active edge with goal_type=refactor, query with document -> warning fires."""
        _insert_active_edge(conn, "axis-a", "axis-b", goal_type=["refactor"])

        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            ["axis-a", "axis-b"], goal_type="document"
        )

        assert len(warnings) == 1
        assert "FRONTIER_WARNING" in warnings[0]


# ===========================================================================
# Retirement flow (tests 10-12)
# ===========================================================================


class TestRetirementFlow:
    """Tests for edge degradation, retirement, and frontier restoration."""

    def test_e2e_edge_retirement_restores_frontier(self, conn) -> None:
        """Test 10: Active edge -> degrade+retire -> frontier warning returns."""
        edge_id = _insert_active_edge(conn, "axis-a", "axis-b")

        checker = FrontierChecker(conn)
        writer = EdgeWriter(conn)

        # Before retirement: no warnings
        warnings_before = checker.check_frontier(["axis-a", "axis-b"])
        assert len(warnings_before) == 0

        # Degrade and retire (amount=0.8, quality 1.0 - 0.8 = 0.2 < 0.3 threshold)
        new_q, retired = writer.degrade_and_maybe_retire(edge_id, 0.8)
        assert new_q == pytest.approx(0.2, abs=0.01)
        assert retired is True

        # After retirement: frontier warning fires again
        warnings_after = checker.check_frontier(["axis-a", "axis-b"])
        assert len(warnings_after) == 1
        assert "FRONTIER_WARNING" in warnings_after[0]

    def test_e2e_degrade_multiple_steps(self, conn) -> None:
        """Test 11: Multiple degradation steps, then retirement."""
        edge_id = _insert_active_edge(conn, "axis-a", "axis-b")
        writer = EdgeWriter(conn)

        # Three degradation steps of 0.1 each: 1.0 -> 0.9 -> 0.8 -> 0.7
        for _ in range(3):
            new_q = writer.degrade_edge(edge_id, 0.1)
        assert new_q == pytest.approx(0.7, abs=0.01)

        # Verify still active
        status = conn.execute(
            "SELECT status FROM axis_edges WHERE edge_id = ?", [edge_id]
        ).fetchone()[0]
        assert status == "active"

        # Large degradation: 0.7 - 0.5 = 0.2 < 0.3 -> retired
        new_q, retired = writer.degrade_and_maybe_retire(edge_id, 0.5)
        assert new_q == pytest.approx(0.2, abs=0.01)
        assert retired is True

        status = conn.execute(
            "SELECT status FROM axis_edges WHERE edge_id = ?", [edge_id]
        ).fetchone()[0]
        assert status == "superseded"

    def test_e2e_edge_idempotent_write(self, conn) -> None:
        """Test 12: Writing same EdgeRecord twice -> 1 row (idempotent)."""
        writer = EdgeWriter(conn)
        edge = _make_edge()

        writer.write_edge(edge)
        writer.write_edge(edge)

        count = conn.execute("SELECT COUNT(*) FROM axis_edges").fetchone()[0]
        assert count == 1


# ===========================================================================
# CLI tests (tests 13-15)
# ===========================================================================


class TestEdgesCLI:
    """Tests for intelligence edges CLI commands."""

    def test_cli_edges_list_empty(self, db_path) -> None:
        """Test 13: edges list on empty DB -> 'No active edges found'."""
        from src.pipeline.cli.intelligence import intelligence_group

        runner = CliRunner()
        result = runner.invoke(
            intelligence_group,
            ["edges", "list", "--db", db_path],
            catch_exceptions=False,
        )

        assert "No active edges found" in result.output

    def test_cli_edges_list_with_data(self, db_path) -> None:
        """Test 14: edges list with data -> shows axis names."""
        # Insert an active edge
        c = duckdb.connect(db_path)
        ac = json.dumps({"goal_type": ["any"], "scope_prefix": "", "min_axes_simultaneously_active": 2})
        ev = json.dumps({"session_id": "s1", "episode_id": "e1", "flame_event_ids": ["f1"]})
        c.execute(
            "INSERT INTO axis_edges "
            "(edge_id, axis_a, axis_b, relationship_text, activation_condition, "
            "evidence, abstraction_level, status, trunk_quality, created_session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1.0, ?)",
            ["test-edge-001", "deposit-not-detect", "ground-truth-pointer",
             "test relationship text", ac, ev, 5, "sess-001"],
        )
        c.close()

        from src.pipeline.cli.intelligence import intelligence_group

        runner = CliRunner()
        result = runner.invoke(
            intelligence_group,
            ["edges", "list", "--db", db_path],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "deposit-not-detect" in result.output
        assert "ground-truth-pointer" in result.output
        assert "Total active edges: 1" in result.output

    def test_cli_edges_show_not_found(self, db_path) -> None:
        """Test 15: edges show nonexistent -> error message."""
        from src.pipeline.cli.intelligence import intelligence_group

        runner = CliRunner()
        result = runner.invoke(
            intelligence_group,
            ["edges", "show", "nonexistent123", "--db", db_path],
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "edge not found" in result.output.lower()
