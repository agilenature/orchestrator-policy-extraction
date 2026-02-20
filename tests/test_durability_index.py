"""Tests for DurabilityIndex, write_constraint_evals, and write_amnesia_events.

Covers:
- compute_score returns correct score when sessions_active >= 3
- compute_score returns null with insufficient_data when < 3 sessions
- compute_score with zero violations = 1.0 durability
- compute_score with all violations = 0.0 durability
- compute_all_scores returns scores for all constraints
- get_amnesia_events filters by session_id
- write_constraint_evals is idempotent (re-write, no duplicates)
- write_amnesia_events is idempotent
- Uses in-memory DuckDB with create_schema() for test isolation
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.durability.amnesia import AmnesiaEvent
from src.pipeline.durability.evaluator import ConstraintEvalResult
from src.pipeline.durability.index import DurabilityIndex
from src.pipeline.storage.schema import create_schema
from src.pipeline.storage.writer import write_amnesia_events, write_constraint_evals


@pytest.fixture()
def conn():
    """In-memory DuckDB connection with schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


def _insert_eval(conn, session_id: str, constraint_id: str, state: str):
    """Helper to insert an evaluation row directly."""
    conn.execute(
        """
        INSERT OR REPLACE INTO session_constraint_eval
        (session_id, constraint_id, eval_state, evidence_json, scope_matched)
        VALUES (?, ?, ?, '[]', true)
        """,
        [session_id, constraint_id, state],
    )


class TestDurabilityIndexComputeScore:
    """Tests for DurabilityIndex.compute_score()."""

    def test_correct_score_with_sufficient_sessions(self, conn):
        """compute_score returns correct score when >= 3 sessions."""
        # 3 HONORED + 1 VIOLATED = 0.75
        _insert_eval(conn, "s1", "c1", "HONORED")
        _insert_eval(conn, "s2", "c1", "HONORED")
        _insert_eval(conn, "s3", "c1", "HONORED")
        _insert_eval(conn, "s4", "c1", "VIOLATED")

        idx = DurabilityIndex(conn, min_sessions=3)
        score = idx.compute_score("c1")

        assert score["constraint_id"] == "c1"
        assert score["sessions_active"] == 4
        assert score["sessions_honored"] == 3
        assert score["sessions_violated"] == 1
        assert score["durability_score"] == pytest.approx(0.75)
        assert score["insufficient_data"] is False

    def test_null_score_insufficient_sessions(self, conn):
        """compute_score returns null score when < 3 sessions."""
        _insert_eval(conn, "s1", "c1", "HONORED")
        _insert_eval(conn, "s2", "c1", "HONORED")

        idx = DurabilityIndex(conn, min_sessions=3)
        score = idx.compute_score("c1")

        assert score["sessions_active"] == 2
        assert score["durability_score"] is None
        assert score["insufficient_data"] is True

    def test_perfect_score_no_violations(self, conn):
        """compute_score returns 1.0 when all sessions are HONORED."""
        for i in range(5):
            _insert_eval(conn, f"s{i}", "c_perfect", "HONORED")

        idx = DurabilityIndex(conn, min_sessions=3)
        score = idx.compute_score("c_perfect")

        assert score["durability_score"] == pytest.approx(1.0)
        assert score["sessions_violated"] == 0

    def test_zero_score_all_violations(self, conn):
        """compute_score returns 0.0 when all sessions are VIOLATED."""
        for i in range(4):
            _insert_eval(conn, f"s{i}", "c_bad", "VIOLATED")

        idx = DurabilityIndex(conn, min_sessions=3)
        score = idx.compute_score("c_bad")

        assert score["durability_score"] == pytest.approx(0.0)
        assert score["sessions_honored"] == 0

    def test_nonexistent_constraint(self, conn):
        """compute_score for nonexistent constraint returns zero sessions."""
        idx = DurabilityIndex(conn)
        score = idx.compute_score("c_missing")

        assert score["sessions_active"] == 0
        assert score["durability_score"] is None
        assert score["insufficient_data"] is True


class TestDurabilityIndexComputeAll:
    """Tests for DurabilityIndex.compute_all_scores()."""

    def test_returns_scores_for_all_constraints(self, conn):
        """compute_all_scores returns one dict per constraint_id."""
        for i in range(3):
            _insert_eval(conn, f"s{i}", "c1", "HONORED")
            _insert_eval(conn, f"s{i}", "c2", "VIOLATED")

        idx = DurabilityIndex(conn, min_sessions=3)
        scores = idx.compute_all_scores()

        assert len(scores) == 2
        score_map = {s["constraint_id"]: s for s in scores}
        assert score_map["c1"]["durability_score"] == pytest.approx(1.0)
        assert score_map["c2"]["durability_score"] == pytest.approx(0.0)

    def test_empty_table(self, conn):
        """compute_all_scores returns empty list for empty table."""
        idx = DurabilityIndex(conn)
        scores = idx.compute_all_scores()
        assert scores == []


class TestDurabilityIndexAmnesiaEvents:
    """Tests for DurabilityIndex.get_amnesia_events()."""

    def test_get_all_amnesia_events(self, conn):
        """get_amnesia_events returns all events when no filter."""
        conn.execute(
            """
            INSERT INTO amnesia_events
            (amnesia_id, session_id, constraint_id, constraint_type, severity, evidence_json, detected_at)
            VALUES
            ('a1', 's1', 'c1', 'behavioral_constraint', 'forbidden', '[]', '2026-01-15T00:00:00+00:00'),
            ('a2', 's2', 'c2', 'behavioral_constraint', 'warning', '[]', '2026-01-16T00:00:00+00:00')
            """
        )

        idx = DurabilityIndex(conn)
        events = idx.get_amnesia_events()
        assert len(events) == 2

    def test_filter_by_session_id(self, conn):
        """get_amnesia_events filters by session_id."""
        conn.execute(
            """
            INSERT INTO amnesia_events
            (amnesia_id, session_id, constraint_id, constraint_type, severity, evidence_json, detected_at)
            VALUES
            ('a1', 's1', 'c1', 'behavioral_constraint', 'forbidden', '[]', '2026-01-15T00:00:00+00:00'),
            ('a2', 's2', 'c2', 'behavioral_constraint', 'warning', '[]', '2026-01-16T00:00:00+00:00')
            """
        )

        idx = DurabilityIndex(conn)
        events = idx.get_amnesia_events(session_id="s1")
        assert len(events) == 1
        assert events[0]["session_id"] == "s1"


class TestWriteConstraintEvals:
    """Tests for write_constraint_evals()."""

    def test_writes_eval_results(self, conn):
        """write_constraint_evals writes results to table."""
        results = [
            ConstraintEvalResult(
                session_id="s1",
                constraint_id="c1",
                eval_state="HONORED",
                evidence=[],
            ),
            ConstraintEvalResult(
                session_id="s1",
                constraint_id="c2",
                eval_state="VIOLATED",
                evidence=[{"event_id": "e1", "matched_pattern": "test", "payload_excerpt": "test"}],
            ),
        ]

        stats = write_constraint_evals(conn, results)
        assert stats["written"] == 2

        count = conn.execute(
            "SELECT count(*) FROM session_constraint_eval"
        ).fetchone()[0]
        assert count == 2

    def test_idempotent_rewrites(self, conn):
        """write_constraint_evals is idempotent -- no duplicates on re-write."""
        results = [
            ConstraintEvalResult(
                session_id="s1",
                constraint_id="c1",
                eval_state="HONORED",
            ),
        ]

        write_constraint_evals(conn, results)
        write_constraint_evals(conn, results)  # Re-write same data

        count = conn.execute(
            "SELECT count(*) FROM session_constraint_eval"
        ).fetchone()[0]
        assert count == 1  # No duplicate

    def test_empty_list(self, conn):
        """write_constraint_evals handles empty list."""
        stats = write_constraint_evals(conn, [])
        assert stats["written"] == 0


class TestWriteAmnesiaEvents:
    """Tests for write_amnesia_events()."""

    def test_writes_amnesia_events(self, conn):
        """write_amnesia_events writes events to table."""
        events = [
            AmnesiaEvent(
                amnesia_id="a1",
                session_id="s1",
                constraint_id="c1",
                constraint_type="behavioral_constraint",
                severity="forbidden",
                evidence=[{"event_id": "e1"}],
                detected_at="2026-01-15T00:00:00+00:00",
            ),
        ]

        stats = write_amnesia_events(conn, events)
        assert stats["written"] == 1

        count = conn.execute(
            "SELECT count(*) FROM amnesia_events"
        ).fetchone()[0]
        assert count == 1

    def test_idempotent_rewrites(self, conn):
        """write_amnesia_events is idempotent -- no duplicates on re-write."""
        events = [
            AmnesiaEvent(
                amnesia_id="a1",
                session_id="s1",
                constraint_id="c1",
                detected_at="2026-01-15T00:00:00+00:00",
            ),
        ]

        write_amnesia_events(conn, events)
        write_amnesia_events(conn, events)  # Re-write

        count = conn.execute(
            "SELECT count(*) FROM amnesia_events"
        ).fetchone()[0]
        assert count == 1  # No duplicate

    def test_empty_list(self, conn):
        """write_amnesia_events handles empty list."""
        stats = write_amnesia_events(conn, [])
        assert stats["written"] == 0
