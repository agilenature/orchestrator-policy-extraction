"""Tests for AssessmentObserver (Phase 17, Plan 03).

Covers:
- Observer tags flame_events with assessment_session_id
- Observer raises FileNotFoundError on missing JSONL
- Observer returns pipeline stats
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import duckdb
import pytest

from src.pipeline.assessment.models import AssessmentSession
from src.pipeline.assessment.observer import AssessmentObserver


@pytest.fixture
def db_path(tmp_path):
    """Create a DuckDB file with flame_events schema."""
    path = str(tmp_path / "test_observer.db")
    conn = duckdb.connect(path)
    conn.execute("""
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
    # Insert test flame_events
    conn.execute(
        "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
        "human_id, marker_level) VALUES (?, ?, ?, ?, ?, ?)",
        ["fe-001", "sess-obs-001", 1, "human", "david", 3],
    )
    conn.execute(
        "INSERT INTO flame_events (event_id, session_id, prompt_number, subject, "
        "human_id, marker_level) VALUES (?, ?, ?, ?, ?, ?)",
        ["fe-002", "sess-obs-001", 2, "human", "david", 5],
    )
    conn.close()
    return path


class TestObserverTagging:
    """Tests for assessment_session_id tagging."""

    @patch("src.pipeline.runner.PipelineRunner")
    @patch("src.pipeline.models.config.load_config")
    def test_tags_flame_events(self, mock_load_config, mock_runner_cls, db_path):
        """Observer sets assessment_session_id on flame_events for the session."""
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        mock_runner = MagicMock()
        mock_runner.run_session.return_value = {"event_count": 2}
        mock_runner_cls.return_value = mock_runner

        # Create a session with a JSONL path that exists
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            f.write('{"type": "test"}\n')
            jsonl_path = f.name

        try:
            session = AssessmentSession(
                session_id="sess-obs-001",
                scenario_id="scen001",
                candidate_id="cand001",
                assessment_dir="/tmp/test",
                jsonl_path=jsonl_path,
                status="completed",
            )

            observer = AssessmentObserver(db_path=db_path)
            observer.run_observation(session)

            # Verify tagging
            conn = duckdb.connect(db_path)
            rows = conn.execute(
                "SELECT assessment_session_id FROM flame_events "
                "WHERE session_id = 'sess-obs-001'"
            ).fetchall()
            conn.close()

            assert all(r[0] == "sess-obs-001" for r in rows)
        finally:
            import os

            os.unlink(jsonl_path)


class TestObserverErrors:
    """Tests for observer error handling."""

    def test_raises_on_missing_jsonl(self, db_path):
        """Observer raises FileNotFoundError when JSONL doesn't exist."""
        session = AssessmentSession(
            session_id="sess-missing",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/test",
            jsonl_path="/nonexistent/path.jsonl",
            status="completed",
        )

        observer = AssessmentObserver(db_path=db_path)
        with pytest.raises(FileNotFoundError):
            observer.run_observation(session)

    def test_raises_on_none_jsonl_path(self, db_path):
        """Observer raises FileNotFoundError when jsonl_path is None."""
        session = AssessmentSession(
            session_id="sess-none",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/test",
            jsonl_path=None,
            status="completed",
        )

        observer = AssessmentObserver(db_path=db_path)
        with pytest.raises(FileNotFoundError):
            observer.run_observation(session)


class TestObserverStats:
    """Tests for observer returning pipeline stats."""

    @patch("src.pipeline.runner.PipelineRunner")
    @patch("src.pipeline.models.config.load_config")
    def test_returns_pipeline_stats(self, mock_load_config, mock_runner_cls, db_path):
        """Observer returns stats dict from PipelineRunner."""
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        expected_stats = {
            "session_id": "sess-stats",
            "event_count": 42,
            "episode_count": 5,
        }
        mock_runner = MagicMock()
        mock_runner.run_session.return_value = expected_stats
        mock_runner_cls.return_value = mock_runner

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            f.write('{"type": "test"}\n')
            jsonl_path = f.name

        try:
            session = AssessmentSession(
                session_id="sess-stats",
                scenario_id="scen001",
                candidate_id="cand001",
                assessment_dir="/tmp/test",
                jsonl_path=jsonl_path,
                status="completed",
            )

            observer = AssessmentObserver(db_path=db_path)
            stats = observer.run_observation(session)

            assert stats["event_count"] == 42
            assert stats["episode_count"] == 5
        finally:
            import os

            os.unlink(jsonl_path)
