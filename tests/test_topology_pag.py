"""Tests for Phase 16.1 PAG gate topology extensions.

Covers:
- FrontierChecker: frontier detection (5 tests)
- CrossAxisVerifier: foil level-matching (4 tests)
- Integration / extraction / edge cases (3 tests)

Total: 12 tests.
"""

import json
import hashlib

import duckdb
import pytest

from src.pipeline.storage.schema import create_schema
from src.pipeline.ddf.topology.frontier import FrontierChecker
from src.pipeline.ddf.topology.verifier import CrossAxisVerifier


@pytest.fixture
def conn():
    """In-memory DuckDB with full schema including axis_edges."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


def insert_active_edge(
    conn,
    axis_a: str,
    axis_b: str,
    goal_type: list[str] | None = None,
    scope_prefix: str = "",
    abstraction_level: int = 5,
) -> str:
    """Helper to insert an active edge into axis_edges.

    Returns the generated edge_id.
    """
    rel_text = f"{axis_a} constrains {axis_b}"
    edge_id = hashlib.sha256(
        f"{axis_a}|{axis_b}|{rel_text}".encode()
    ).hexdigest()[:16]
    ac = json.dumps(
        {
            "goal_type": goal_type or ["any"],
            "scope_prefix": scope_prefix,
            "min_axes_simultaneously_active": 2,
        }
    )
    conn.execute(
        """INSERT INTO axis_edges (
            edge_id, axis_a, axis_b, relationship_text,
            activation_condition, evidence, abstraction_level,
            status, trunk_quality, created_session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1.0, 'test')""",
        [
            edge_id,
            axis_a,
            axis_b,
            rel_text,
            ac,
            json.dumps(
                {
                    "session_id": "s1",
                    "episode_id": "e1",
                    "flame_event_ids": [],
                }
            ),
            abstraction_level,
        ],
    )
    return edge_id


# ================================================================
# FrontierChecker tests (5)
# ================================================================


class TestFrontierChecker:
    """FrontierChecker detects uncharted axis pairs."""

    def test_frontier_no_edges_two_axes(self, conn):
        """Two active axes, no edges -> 1 FRONTIER_WARNING."""
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"]
        )
        assert len(warnings) == 1
        assert "FRONTIER_WARNING" in warnings[0]
        assert "deposit-not-detect" in warnings[0]
        assert "terminal-vs-instrumental" in warnings[0]

    def test_frontier_edge_exists_suppresses_warning(self, conn):
        """Active edge exists for pair -> no warning."""
        insert_active_edge(
            conn, "deposit-not-detect", "terminal-vs-instrumental"
        )
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"]
        )
        assert len(warnings) == 0

    def test_frontier_edge_wrong_activation_condition(self, conn):
        """Edge exists but goal_type mismatch -> FRONTIER_WARNING."""
        insert_active_edge(
            conn,
            "deposit-not-detect",
            "terminal-vs-instrumental",
            goal_type=["refactor"],
        )
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"],
            goal_type="document",
        )
        assert len(warnings) == 1
        assert "FRONTIER_WARNING" in warnings[0]

    def test_frontier_single_axis_no_warning(self, conn):
        """Only 1 active axis -> no warning (need 2+ for pairs)."""
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(["deposit-not-detect"])
        assert len(warnings) == 0

    def test_frontier_three_axes_two_missing(self, conn):
        """3 axes, 1 edge for (a,b), pairs (a,c) and (b,c) missing -> 2 warnings."""
        insert_active_edge(
            conn, "deposit-not-detect", "terminal-vs-instrumental"
        )
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            [
                "deposit-not-detect",
                "terminal-vs-instrumental",
                "ground-truth-pointer",
            ]
        )
        # (deposit-not-detect, terminal-vs-instrumental) has edge -> no warning
        # (deposit-not-detect, ground-truth-pointer) has no edge -> warning
        # (ground-truth-pointer, terminal-vs-instrumental) has no edge -> warning
        assert len(warnings) == 2
        assert all("FRONTIER_WARNING" in w for w in warnings)


# ================================================================
# CrossAxisVerifier tests (4)
# ================================================================


class TestCrossAxisVerifier:
    """CrossAxisVerifier checks premise-edge consistency."""

    def test_verifier_no_edges_no_warning(self, conn):
        """No edges for pair -> no warning."""
        verifier = CrossAxisVerifier(conn)
        warnings = verifier.verify_premise(
            premise_axes=["deposit-not-detect", "terminal-vs-instrumental"],
            premise_claim="Deposit takes priority over detection",
            premise_abstraction_level=4,
        )
        assert len(warnings) == 0

    def test_verifier_foil_level_mismatch(self, conn):
        """Edge at level 7, premise at level 4 -> CROSS_AXIS_WARNING (7 > 4+1)."""
        insert_active_edge(
            conn,
            "deposit-not-detect",
            "terminal-vs-instrumental",
            abstraction_level=7,
        )
        verifier = CrossAxisVerifier(conn)
        warnings = verifier.verify_premise(
            premise_axes=["deposit-not-detect", "terminal-vs-instrumental"],
            premise_claim="Deposit takes priority over detection",
            premise_abstraction_level=4,
        )
        assert len(warnings) == 1
        assert "CROSS_AXIS_WARNING" in warnings[0]
        assert "Foil level mismatch" in warnings[0]
        assert "Possible Equivocation" in warnings[0]

    def test_verifier_foil_level_ok(self, conn):
        """Edge at level 5, premise at level 5 -> no warning (5 <= 5+1)."""
        insert_active_edge(
            conn,
            "deposit-not-detect",
            "terminal-vs-instrumental",
            abstraction_level=5,
        )
        verifier = CrossAxisVerifier(conn)
        warnings = verifier.verify_premise(
            premise_axes=["deposit-not-detect", "terminal-vs-instrumental"],
            premise_claim="Deposit takes priority",
            premise_abstraction_level=5,
        )
        assert len(warnings) == 0

    def test_verifier_activation_condition_filters(self, conn):
        """Edge with goal_type=["refactor"], query with goal_type="document" -> not checked."""
        insert_active_edge(
            conn,
            "deposit-not-detect",
            "terminal-vs-instrumental",
            goal_type=["refactor"],
            abstraction_level=7,
        )
        verifier = CrossAxisVerifier(conn)
        # Even though level mismatch would fire, activation_condition filters the edge out
        warnings = verifier.verify_premise(
            premise_axes=["deposit-not-detect", "terminal-vs-instrumental"],
            premise_claim="Deposit takes priority",
            premise_abstraction_level=4,
            goal_type="document",
        )
        assert len(warnings) == 0


# ================================================================
# Integration / extraction tests (3)
# ================================================================


class TestIntegration:
    """Integration tests for frontier warning format, activation matching, and superseded edges."""

    def test_frontier_warning_text_format(self, conn):
        """FRONTIER_WARNING text contains both axis names and key phrases."""
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            ["bootstrap-circularity", "identity-firewall"]
        )
        assert len(warnings) == 1
        w = warnings[0]
        assert "FRONTIER_WARNING" in w
        assert "bootstrap-circularity" in w
        assert "identity-firewall" in w
        assert "Frontier territory" in w
        assert "Geological Drill zone" in w

    def test_activation_matches_any_goal_type(self, conn):
        """Edge with goal_type=["any"] matches any current goal_type."""
        insert_active_edge(
            conn,
            "deposit-not-detect",
            "terminal-vs-instrumental",
            goal_type=["any"],
        )
        checker = FrontierChecker(conn)

        # Should match with goal_type="refactor"
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"],
            goal_type="refactor",
        )
        assert len(warnings) == 0

        # Should match with goal_type="document"
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"],
            goal_type="document",
        )
        assert len(warnings) == 0

        # Should match with goal_type=None
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"],
            goal_type=None,
        )
        assert len(warnings) == 0

    def test_frontier_superseded_edge_not_suppressing(self, conn):
        """Superseded edge does not suppress FRONTIER_WARNING."""
        edge_id = insert_active_edge(
            conn, "deposit-not-detect", "terminal-vs-instrumental"
        )
        # Transition to superseded
        conn.execute(
            "UPDATE axis_edges SET status='superseded' WHERE edge_id=?",
            [edge_id],
        )
        checker = FrontierChecker(conn)
        warnings = checker.check_frontier(
            ["deposit-not-detect", "terminal-vs-instrumental"]
        )
        # Superseded edge should NOT suppress the warning
        assert len(warnings) == 1
        assert "FRONTIER_WARNING" in warnings[0]
