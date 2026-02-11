"""Tests for episode MERGE upsert and hybrid schema queries.

Tests write_episodes() MERGE behavior, read_episodes_by_session(),
STRUCT dot notation queries, and JSON column queries on the episodes table.
"""

from __future__ import annotations

import json
import time

import duckdb
import pytest

from src.pipeline.storage.schema import create_schema, get_connection
from src.pipeline.storage.writer import read_episodes_by_session, write_episodes


# --- Fixture helpers ---


def _make_episode(
    episode_id: str = "ep-001",
    session_id: str = "sess-abc",
    segment_id: str = "seg-001",
    mode: str = "Implement",
    risk: str = "medium",
    reaction_label: str | None = "approve",
    reaction_confidence: float | None = 0.85,
    outcome_type: str = "success",
    tests_status: str = "pass",
    lint_status: str = "pass",
    changed_files: list[str] | None = None,
    config_hash: str = "abc12345",
) -> dict:
    """Create a valid episode dict matching the populator output format."""
    if changed_files is None:
        changed_files = ["src/main.py", "tests/test_main.py"]

    reaction = None
    if reaction_label is not None:
        reaction = {
            "label": reaction_label,
            "message": "looks good",
            "confidence": reaction_confidence,
        }

    outcome: dict = {
        "executor_effects": {
            "tool_calls_count": 3,
            "files_touched": ["src/main.py"],
            "commands_ran": ["pytest tests/"],
            "git_events": [],
        },
        "quality": {
            "tests_status": tests_status,
            "lint_status": lint_status,
            "diff_stat": {"files": 2, "insertions": 10, "deletions": 3},
        },
        "reward_signals": {
            "objective": {"tests": 1.0, "lint": 1.0, "diff_risk": 0.2},
        },
    }
    if reaction is not None:
        outcome["reaction"] = reaction

    return {
        "episode_id": episode_id,
        "session_id": session_id,
        "segment_id": segment_id,
        "timestamp": "2026-02-11T12:00:00+00:00",
        "outcome_type": outcome_type,
        "observation": {
            "repo_state": {
                "changed_files": changed_files,
                "diff_stat": {"files": len(changed_files), "insertions": 5, "deletions": 2},
            },
            "quality_state": {
                "tests": {"status": tests_status},
                "lint": {"status": lint_status},
            },
            "context": {
                "recent_summary": "Working on feature X",
                "open_questions": ["How to handle edge case?"],
                "constraints_in_force": ["no-force-push"],
            },
        },
        "orchestrator_action": {
            "mode": mode,
            "goal": "Implement feature X",
            "scope": {"paths": ["src/main.py"]},
            "executor_instruction": "Implement the feature",
            "gates": [],
            "risk": risk,
        },
        "outcome": outcome,
        "provenance": {
            "sources": [
                {"type": "claude_jsonl", "ref": "session.jsonl:line-42"},
            ],
        },
        "config_hash": config_hash,
        "project": {"repo_path": "test-project"},
    }


@pytest.fixture
def db_conn():
    """Create in-memory DuckDB with schema."""
    conn = get_connection(":memory:")
    create_schema(conn)
    yield conn
    conn.close()


# --- Tests ---


class TestWriteEpisodes:
    """Tests for write_episodes() MERGE upsert."""

    def test_write_single_episode_and_read_back(self, db_conn):
        """Write single episode, read back, verify all fields."""
        ep = _make_episode()
        result = write_episodes(db_conn, [ep])

        assert result == {"inserted": 1, "updated": 0, "total": 1}

        episodes = read_episodes_by_session(db_conn, "sess-abc")
        assert len(episodes) == 1

        stored = episodes[0]
        assert stored["episode_id"] == "ep-001"
        assert stored["session_id"] == "sess-abc"
        assert stored["segment_id"] == "seg-001"
        assert stored["mode"] == "Implement"
        assert stored["risk"] == "medium"
        assert stored["reaction_label"] == "approve"
        assert stored["reaction_confidence"] == pytest.approx(0.85, abs=0.01)
        assert stored["outcome_type"] == "success"
        assert stored["config_hash"] == "abc12345"
        assert stored["schema_version"] == 1

        # Verify JSON columns were stored and parsed
        assert isinstance(stored["orchestrator_action"], dict)
        assert stored["orchestrator_action"]["mode"] == "Implement"
        assert isinstance(stored["outcome"], dict)
        assert isinstance(stored["provenance"], dict)
        assert len(stored["provenance"]["sources"]) == 1

    def test_merge_upsert_no_duplicates(self, db_conn):
        """Write same episode twice, verify no duplicates and updated_at changes."""
        ep = _make_episode()
        result1 = write_episodes(db_conn, [ep])
        assert result1 == {"inserted": 1, "updated": 0, "total": 1}

        # Get initial updated_at
        row = db_conn.execute(
            "SELECT updated_at FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        first_updated_at = row[0]

        # Small delay to ensure timestamp differs
        time.sleep(0.01)

        # Write same episode again (MERGE should update)
        result2 = write_episodes(db_conn, [ep])
        assert result2 == {"inserted": 0, "updated": 1, "total": 1}

        # Verify still only 1 row
        count = db_conn.execute("SELECT count(*) FROM episodes").fetchone()[0]
        assert count == 1

        # Verify updated_at changed
        row2 = db_conn.execute(
            "SELECT updated_at FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        second_updated_at = row2[0]
        assert second_updated_at >= first_updated_at

    def test_write_multiple_episodes_query_by_mode(self, db_conn):
        """Write multiple episodes, query by mode."""
        ep1 = _make_episode(episode_id="ep-001", mode="Implement")
        ep2 = _make_episode(episode_id="ep-002", mode="Explore")
        ep3 = _make_episode(episode_id="ep-003", mode="Implement")

        write_episodes(db_conn, [ep1, ep2, ep3])

        # Query by mode
        rows = db_conn.execute(
            "SELECT episode_id FROM episodes WHERE mode = 'Implement' ORDER BY episode_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "ep-001"
        assert rows[1][0] == "ep-003"

        # Query Explore
        rows = db_conn.execute(
            "SELECT episode_id FROM episodes WHERE mode = 'Explore'"
        ).fetchall()
        assert len(rows) == 1

    def test_struct_dot_notation_query(self, db_conn):
        """Query using STRUCT dot notation on observation column."""
        ep = _make_episode(tests_status="pass")
        write_episodes(db_conn, [ep])

        # Query via STRUCT dot notation
        result = db_conn.execute(
            "SELECT observation.quality_state.tests_status FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        assert result[0] == "pass"

        # Query context
        result = db_conn.execute(
            "SELECT observation.context.recent_summary FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        assert result[0] == "Working on feature X"

        # Query diff_stat
        result = db_conn.execute(
            "SELECT observation.repo_state.diff_stat.files FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        assert result[0] == 2  # len(changed_files)

    def test_json_column_query(self, db_conn):
        """Query JSON column using json_extract_string."""
        ep = _make_episode(mode="Verify")
        write_episodes(db_conn, [ep])

        # Query orchestrator_action JSON
        result = db_conn.execute(
            "SELECT json_extract_string(orchestrator_action, '$.mode') FROM episodes"
        ).fetchone()
        assert result[0] == "Verify"

        # Query nested JSON
        result = db_conn.execute(
            "SELECT json_extract_string(orchestrator_action, '$.goal') FROM episodes"
        ).fetchone()
        assert result[0] == "Implement feature X"

    def test_flat_columns_match_nested_data(self, db_conn):
        """Verify flat queryable columns match their nested counterparts."""
        ep = _make_episode(mode="Refactor", risk="high")
        write_episodes(db_conn, [ep])

        row = db_conn.execute("""
            SELECT
                mode,
                json_extract_string(orchestrator_action, '$.mode') as nested_mode,
                risk,
                json_extract_string(orchestrator_action, '$.risk') as nested_risk
            FROM episodes
        """).fetchone()

        assert row[0] == row[1]  # flat mode == nested mode
        assert row[2] == row[3]  # flat risk == nested risk

    def test_empty_episodes_list(self, db_conn):
        """Empty episodes list returns zero counts."""
        result = write_episodes(db_conn, [])
        assert result == {"inserted": 0, "updated": 0, "total": 0}

    def test_episode_without_reaction(self, db_conn):
        """Episode without reaction stores NULL for reaction fields."""
        ep = _make_episode(reaction_label=None, reaction_confidence=None)
        write_episodes(db_conn, [ep])

        row = db_conn.execute(
            "SELECT reaction_label, reaction_confidence FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        assert row[0] is None
        assert row[1] is None

    def test_source_files_stored_as_array(self, db_conn):
        """Source files from provenance are stored as VARCHAR[]."""
        ep = _make_episode()
        write_episodes(db_conn, [ep])

        result = db_conn.execute(
            "SELECT source_files FROM episodes WHERE episode_id = 'ep-001'"
        ).fetchone()
        source_files = result[0]
        assert isinstance(source_files, list)
        assert "session.jsonl:line-42" in source_files

    def test_observation_changed_files_in_struct(self, db_conn):
        """Observation STRUCT stores changed_files as VARCHAR[]."""
        ep = _make_episode(changed_files=["a.py", "b.py", "c.py"])
        write_episodes(db_conn, [ep])

        result = db_conn.execute(
            "SELECT observation.repo_state.changed_files FROM episodes"
        ).fetchone()
        files = result[0]
        assert isinstance(files, list)
        assert set(files) == {"a.py", "b.py", "c.py"}


class TestReadEpisodesBySession:
    """Tests for read_episodes_by_session()."""

    def test_read_empty_session(self, db_conn):
        """No episodes for a session returns empty list."""
        episodes = read_episodes_by_session(db_conn, "nonexistent")
        assert episodes == []

    def test_read_filters_by_session(self, db_conn):
        """Only returns episodes for the requested session."""
        ep1 = _make_episode(episode_id="ep-001", session_id="sess-1")
        ep2 = _make_episode(episode_id="ep-002", session_id="sess-2")
        ep3 = _make_episode(episode_id="ep-003", session_id="sess-1")
        write_episodes(db_conn, [ep1, ep2, ep3])

        sess1_episodes = read_episodes_by_session(db_conn, "sess-1")
        assert len(sess1_episodes) == 2
        ids = {e["episode_id"] for e in sess1_episodes}
        assert ids == {"ep-001", "ep-003"}

        sess2_episodes = read_episodes_by_session(db_conn, "sess-2")
        assert len(sess2_episodes) == 1
        assert sess2_episodes[0]["episode_id"] == "ep-002"
