"""Tests for RejectionDetector (Phase 17, Plan 03).

Covers:
- classify_rejection: L5 above threshold
- classify_rejection: stubbornness below threshold
- classify_rejection: fringe_L5 bypasses outcome gate
- classify_rejection: None TE -> conservative stubbornness
- classify_rejection: boundary exactly 0.9 -> stubbornness (strict >)
- detect_rejections integration
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.assessment.rejection_detector import RejectionDetector


@pytest.fixture
def conn():
    """In-memory DuckDB connection with flame_events schema."""
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE IF NOT EXISTS flame_events (
            event_id VARCHAR PRIMARY KEY,
            session_id VARCHAR,
            prompt_number INTEGER,
            subject VARCHAR,
            human_id VARCHAR,
            marker_level INTEGER,
            axis_identified VARCHAR,
            ccd_axis VARCHAR,
            differential VARCHAR,
            scope_rule VARCHAR,
            flood_example VARCHAR,
            confidence FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            assessment_session_id VARCHAR
        )
    """)
    yield c
    c.close()


class TestClassifyRejection:
    """Tests for RejectionDetector.classify_rejection."""

    def test_l5_above_threshold(self, conn):
        """candidate_te > threshold returns 'L5'."""
        det = RejectionDetector(conn)
        # 0.5 > (0.5 * 0.9 = 0.45) -> L5
        result = det.classify_rejection(0.5, 0.5, False)
        assert result == "L5"

    def test_stubbornness_below_threshold(self, conn):
        """candidate_te < threshold returns 'stubbornness'."""
        det = RejectionDetector(conn)
        # 0.3 < (0.5 * 0.9 = 0.45) -> stubbornness
        result = det.classify_rejection(0.3, 0.5, False)
        assert result == "stubbornness"

    def test_fringe_bypasses_gate(self, conn):
        """is_fringe=True returns 'fringe_L5' regardless of TE."""
        det = RejectionDetector(conn)
        # Even with low TE, fringe bypasses
        result = det.classify_rejection(0.1, 0.5, True)
        assert result == "fringe_L5"

    def test_none_te_conservative(self, conn):
        """candidate_te=None returns 'stubbornness' (conservative)."""
        det = RejectionDetector(conn)
        result = det.classify_rejection(None, 0.5, False)
        assert result == "stubbornness"

    def test_boundary_exactly_0_9(self, conn):
        """candidate_te == threshold (0.9 * baseline) -> stubbornness (strict >)."""
        det = RejectionDetector(conn)
        # 0.45 == (0.5 * 0.9 = 0.45), NOT > -> stubbornness
        result = det.classify_rejection(0.45, 0.5, False)
        assert result == "stubbornness"

    def test_fringe_with_none_te(self, conn):
        """Fringe with None TE still returns fringe_L5."""
        det = RejectionDetector(conn)
        result = det.classify_rejection(None, 0.5, True)
        assert result == "fringe_L5"

    def test_just_above_threshold(self, conn):
        """candidate_te just above threshold returns L5."""
        det = RejectionDetector(conn)
        # 0.4501 > (0.5 * 0.9 = 0.45) -> L5
        result = det.classify_rejection(0.4501, 0.5, False)
        assert result == "L5"

    def test_zero_baseline(self, conn):
        """Zero baseline TE: threshold is 0, any positive TE -> L5."""
        det = RejectionDetector(conn)
        result = det.classify_rejection(0.1, 0.0, False)
        assert result == "L5"


class TestDetectRejections:
    """Integration tests for detect_rejections."""

    def test_detect_rejections_with_events(self, conn):
        """detect_rejections finds L5+ events and classifies them."""
        # Insert flame_events: L3 (below threshold) and L5 (above)
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
            "human_id, marker_level, axis_identified, ccd_axis) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["fe-001", "sess-rej-001", 1, "human", "david", 3, None, None],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
            "human_id, marker_level, axis_identified, ccd_axis) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["fe-002", "sess-rej-001", 2, "human", "david", 5, "test-axis", "test-axis"],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
            "human_id, marker_level, axis_identified, ccd_axis) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["fe-003", "sess-rej-001", 3, "human", "david", 6, "novel-axis", None],
        )

        det = RejectionDetector(conn)
        rejections = det.detect_rejections("sess-rej-001", 0.5)

        # Should find 2 rejections (L5 and L6 events, not L3)
        assert len(rejections) == 2

        # L5 event with matching ccd_axis -> not fringe
        rej_l5 = rejections[0]
        assert rej_l5["marker_level"] == 5
        assert rej_l5["is_fringe"] is False

        # L6 event with axis_identified but no ccd_axis -> fringe
        rej_l6 = rejections[1]
        assert rej_l6["marker_level"] == 6
        assert rej_l6["is_fringe"] is True
        assert rej_l6["rejection_type"] == "fringe_L5"

    def test_no_rejections_for_low_level_session(self, conn):
        """No rejections when all events are below L5."""
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
            "human_id, marker_level) VALUES (?, ?, ?, ?, ?, ?)",
            ["fe-low-001", "sess-low", 1, "human", "david", 2],
        )
        conn.execute(
            "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
            "human_id, marker_level) VALUES (?, ?, ?, ?, ?, ?)",
            ["fe-low-002", "sess-low", 2, "human", "david", 4],
        )

        det = RejectionDetector(conn)
        rejections = det.detect_rejections("sess-low", 0.5)
        assert len(rejections) == 0

    def test_empty_session(self, conn):
        """No rejections for session with no flame_events."""
        det = RejectionDetector(conn)
        rejections = det.detect_rejections("nonexistent-session", 0.5)
        assert len(rejections) == 0
