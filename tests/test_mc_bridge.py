"""Tests for the DuckDB-SQLite Mission Control bridge reader.

Verifies that MCBridgeReader can:
- Attach/detach MC's SQLite database via DuckDB
- Query episodes with JSON column parsing
- Import episodes as validated Pydantic Episode models
- Query episode events with parsed payloads
- Query constraints with parsed JSON arrays
- Handle invalid data gracefully (warnings, not exceptions)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from pathlib import Path

import duckdb
import pytest

from src.pipeline.bridge.mc_reader import MCBridgeReader
from src.pipeline.models.episodes import Episode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Replicate the SQLite DDL from mission-control/src/lib/db/schema-episodes.ts
MC_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT,
    timestamp TEXT NOT NULL,
    mode TEXT CHECK (mode IN ('Explore','Plan','Implement','Verify','Integrate','Triage','Refactor')),
    risk TEXT CHECK (risk IN ('low','medium','high','critical')),
    reaction_label TEXT CHECK (reaction_label IN ('approve','correct','redirect','block','question','unknown')),
    reaction_confidence REAL,
    status TEXT DEFAULT 'in_progress' CHECK (status IN ('pending','in_progress','review','completed')),
    observation TEXT,
    orchestrator_action TEXT,
    outcome TEXT,
    provenance TEXT,
    constraints_extracted TEXT,
    labels TEXT,
    project_repo_path TEXT,
    project_branch TEXT,
    project_commit_head TEXT,
    phase TEXT,
    schema_version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS episode_events (
    event_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'tool_call','tool_result','file_touch','command_run',
        'test_result','git_event','lint_result','build_result',
        'lifecycle'
    )),
    payload TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE TABLE IF NOT EXISTS constraints (
    constraint_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning','requires_approval','forbidden')),
    scope_paths TEXT NOT NULL,
    detection_hints TEXT,
    source_episode_id TEXT,
    source_reaction_label TEXT,
    examples TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (source_episode_id) REFERENCES episodes(episode_id)
);
"""


def _make_valid_observation() -> dict:
    """Create a valid observation matching the Pydantic Observation model."""
    return {
        "repo_state": {
            "changed_files": ["src/main.py", "tests/test_main.py"],
            "diff_stat": {"files": 2, "insertions": 45, "deletions": 10},
            "hotspots": [],
        },
        "quality_state": {
            "tests": {"status": "pass", "last_command": "pytest", "failing": []},
            "lint": {"status": "pass", "last_command": "ruff check", "issues_count": 0},
            "build": None,
        },
        "context": {
            "recent_summary": "Implemented feature X and updated tests",
            "open_questions": [],
            "constraints_in_force": [],
        },
    }


def _make_valid_action() -> dict:
    """Create a valid orchestrator_action matching the Pydantic model."""
    return {
        "mode": "Implement",
        "goal": "Add user authentication endpoint",
        "scope": {"paths": ["src/auth/"], "avoid": ["src/legacy/"]},
        "executor_instruction": "Create login and logout endpoints",
        "gates": [{"type": "run_tests"}],
        "risk": "medium",
        "expected_artifacts": ["src/auth/login.py"],
    }


def _make_valid_outcome(with_reaction: bool = True) -> dict:
    """Create a valid outcome matching the Pydantic Outcome model."""
    outcome = {
        "executor_effects": {
            "tool_calls_count": 15,
            "files_touched": ["src/auth/login.py", "tests/test_auth.py"],
            "commands_ran": ["pytest tests/", "ruff check src/"],
            "git_events": [{"type": "commit", "message": "feat: add auth"}],
        },
        "quality": {
            "tests_status": "pass",
            "lint_status": "pass",
            "diff_stat": {"files": 2, "insertions": 80, "deletions": 5},
        },
        "reward_signals": {
            "objective": {"tests": 1.0, "lint": 1.0, "diff_risk": 0.3},
        },
    }
    if with_reaction:
        outcome["reaction"] = {
            "label": "approve",
            "message": "Looks good, well structured",
            "confidence": 0.95,
        }
    return outcome


def _make_valid_provenance() -> dict:
    """Create a valid provenance matching the Pydantic Provenance model."""
    return {
        "sources": [
            {"type": "claude_jsonl", "ref": "sessions/abc123/conversation.jsonl:100-200"}
        ]
    }


@pytest.fixture
def mc_db_path(tmp_path: Path) -> str:
    """Create a temporary SQLite database with the MC episode schema."""
    db_path = str(tmp_path / "mission-control.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(MC_SCHEMA_DDL)
    conn.close()
    return db_path


@pytest.fixture
def duckdb_conn() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection for testing."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def populated_mc_db(mc_db_path: str) -> str:
    """MC database with a sample episode and events inserted."""
    conn = sqlite3.connect(mc_db_path)

    # Insert a completed episode with all valid fields
    conn.execute(
        """
        INSERT INTO episodes (
            episode_id, task_id, session_id, timestamp,
            mode, risk, reaction_label, reaction_confidence, status,
            observation, orchestrator_action, outcome, provenance,
            constraints_extracted, labels,
            project_repo_path, project_branch, project_commit_head, phase
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ep-001", "task-001", "sess-001", "2026-02-10T14:30:00Z",
            "Implement", "medium", "approve", 0.95, "completed",
            json.dumps(_make_valid_observation()),
            json.dumps(_make_valid_action()),
            json.dumps(_make_valid_outcome()),
            json.dumps(_make_valid_provenance()),
            json.dumps([]),
            json.dumps({"episode_type": "decision_point", "notes": "Test episode"}),
            "/home/user/project", "main", "abc123def", "01",
        ),
    )

    # Insert a second episode without reaction (in_progress)
    conn.execute(
        """
        INSERT INTO episodes (
            episode_id, task_id, session_id, timestamp,
            mode, risk, status,
            observation, orchestrator_action,
            project_repo_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ep-002", "task-002", "sess-002", "2026-02-10T15:00:00Z",
            "Explore", "low", "in_progress",
            json.dumps(_make_valid_observation()),
            json.dumps(_make_valid_action()),
            "/home/user/project",
        ),
    )

    # Insert episode events for ep-001
    conn.execute(
        """
        INSERT INTO episode_events (event_id, episode_id, timestamp, received_at, event_type, payload)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "evt-001", "ep-001", "2026-02-10T14:30:01Z", "2026-02-10T14:30:01Z",
            "tool_call",
            json.dumps({"tool_name": "Read", "tool_input": {"file_path": "src/main.py"}}),
        ),
    )
    conn.execute(
        """
        INSERT INTO episode_events (event_id, episode_id, timestamp, received_at, event_type, payload)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "evt-002", "ep-001", "2026-02-10T14:30:05Z", "2026-02-10T14:30:05Z",
            "command_run",
            json.dumps({"command": "pytest tests/", "exit_code": 0}),
        ),
    )

    # Insert a constraint
    conn.execute(
        """
        INSERT INTO constraints (
            constraint_id, text, severity, scope_paths,
            detection_hints, source_episode_id, source_reaction_label, examples
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "c-001", "Never modify production config directly",
            "forbidden", json.dumps(["config/production/"]),
            json.dumps(["production", "config"]),
            "ep-001", "block",
            json.dumps([{"episode_id": "ep-001", "violation_description": "Edited prod config"}]),
        ),
    )

    conn.commit()
    conn.close()
    return mc_db_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMCBridgeAttachDetach:
    """Tests for attach/detach lifecycle."""

    def test_context_manager_attach_detach(
        self, mc_db_path: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Context manager attaches on enter and detaches on exit."""
        reader = MCBridgeReader(mc_db_path, duckdb_conn)
        assert not reader._attached

        with reader:
            assert reader._attached

        assert not reader._attached

    def test_manual_attach_detach(
        self, mc_db_path: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Manual attach/detach works correctly."""
        reader = MCBridgeReader(mc_db_path, duckdb_conn)
        reader.attach()
        assert reader._attached

        reader.detach()
        assert not reader._attached

    def test_double_attach_is_idempotent(
        self, mc_db_path: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Calling attach() twice does not raise."""
        reader = MCBridgeReader(mc_db_path, duckdb_conn)
        reader.attach()
        reader.attach()  # Should not raise
        assert reader._attached
        reader.detach()

    def test_double_detach_is_idempotent(
        self, mc_db_path: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Calling detach() twice does not raise."""
        reader = MCBridgeReader(mc_db_path, duckdb_conn)
        reader.attach()
        reader.detach()
        reader.detach()  # Should not raise
        assert not reader._attached

    def test_query_without_attach_raises(
        self, mc_db_path: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Calling a query method without attach raises RuntimeError."""
        reader = MCBridgeReader(mc_db_path, duckdb_conn)
        with pytest.raises(RuntimeError, match="not attached"):
            reader.list_episodes()


class TestListEpisodes:
    """Tests for list_episodes query."""

    def test_list_completed_episodes_with_reaction(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Returns only completed episodes with reactions."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            episodes = reader.list_episodes(status="completed", has_reaction=True)

        assert len(episodes) == 1
        ep = episodes[0]
        assert ep["episode_id"] == "ep-001"
        assert ep["mode"] == "Implement"
        assert ep["risk"] == "medium"
        assert ep["reaction_label"] == "approve"
        assert ep["reaction_confidence"] == pytest.approx(0.95)

    def test_json_columns_parsed(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """JSON columns are parsed into dicts/lists, not raw strings."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            episodes = reader.list_episodes(status="completed", has_reaction=True)

        ep = episodes[0]
        # observation should be a parsed dict
        assert isinstance(ep["observation"], dict)
        assert "repo_state" in ep["observation"]
        assert ep["observation"]["repo_state"]["changed_files"] == [
            "src/main.py", "tests/test_main.py"
        ]

        # orchestrator_action should be a parsed dict
        assert isinstance(ep["orchestrator_action"], dict)
        assert ep["orchestrator_action"]["mode"] == "Implement"

        # outcome should be a parsed dict
        assert isinstance(ep["outcome"], dict)
        assert ep["outcome"]["executor_effects"]["tool_calls_count"] == 15

    def test_list_all_episodes(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Listing with no status filter returns all episodes."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            episodes = reader.list_episodes(status="", has_reaction=False)

        assert len(episodes) == 2


class TestImportEpisodes:
    """Tests for import_episodes (Pydantic validation)."""

    def test_import_valid_episode(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Completed episode with valid data imports as Pydantic Episode."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            episodes = reader.import_episodes()

        assert len(episodes) == 1
        ep = episodes[0]
        assert isinstance(ep, Episode)
        assert ep.episode_id == "ep-001"
        assert ep.orchestrator_action.mode == "Implement"
        assert ep.outcome.quality.tests_status == "pass"
        assert ep.outcome.reaction is not None
        assert ep.outcome.reaction.label == "approve"

    def test_invalid_episode_logs_warning_no_raise(
        self, mc_db_path: str, duckdb_conn: duckdb.DuckDBPyConnection, caplog
    ) -> None:
        """Invalid episode data logs warning but does not raise."""
        # Insert an episode with invalid observation (missing required fields)
        conn = sqlite3.connect(mc_db_path)
        conn.execute(
            """
            INSERT INTO episodes (
                episode_id, task_id, timestamp,
                mode, risk, reaction_label, reaction_confidence, status,
                observation, orchestrator_action, outcome, provenance,
                project_repo_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ep-bad", "task-bad", "2026-02-10T16:00:00Z",
                "Implement", "low", "approve", 0.8, "completed",
                json.dumps({"invalid": "data"}),  # Missing required observation fields
                json.dumps(_make_valid_action()),
                json.dumps(_make_valid_outcome()),
                json.dumps(_make_valid_provenance()),
                "/home/user/project",
            ),
        )
        conn.commit()
        conn.close()

        with caplog.at_level(logging.WARNING):
            with MCBridgeReader(mc_db_path, duckdb_conn) as reader:
                episodes = reader.import_episodes()

        # Should not include the bad episode
        bad_ids = [ep.episode_id for ep in episodes if ep.episode_id == "ep-bad"]
        assert len(bad_ids) == 0
        # Should have logged a warning
        assert any("ep-bad" in record.message for record in caplog.records)


class TestEpisodeEvents:
    """Tests for get_episode_events."""

    def test_get_episode_events(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Returns events for a given episode with parsed payloads."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            events = reader.get_episode_events("ep-001")

        assert len(events) == 2

        # First event: tool_call
        assert events[0]["event_id"] == "evt-001"
        assert events[0]["event_type"] == "tool_call"
        assert isinstance(events[0]["payload"], dict)
        assert events[0]["payload"]["tool_name"] == "Read"

        # Second event: command_run
        assert events[1]["event_id"] == "evt-002"
        assert events[1]["event_type"] == "command_run"
        assert events[1]["payload"]["command"] == "pytest tests/"
        assert events[1]["payload"]["exit_code"] == 0

    def test_get_events_for_nonexistent_episode(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Returns empty list for episode with no events."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            events = reader.get_episode_events("ep-nonexistent")

        assert events == []


class TestConstraints:
    """Tests for get_constraints."""

    def test_get_constraints(
        self, populated_mc_db: str, duckdb_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Returns constraints with parsed JSON arrays."""
        with MCBridgeReader(populated_mc_db, duckdb_conn) as reader:
            constraints = reader.get_constraints()

        assert len(constraints) == 1
        c = constraints[0]
        assert c["constraint_id"] == "c-001"
        assert c["text"] == "Never modify production config directly"
        assert c["severity"] == "forbidden"

        # scope_paths should be parsed from JSON
        assert isinstance(c["scope_paths"], list)
        assert c["scope_paths"] == ["config/production/"]

        # detection_hints should be parsed from JSON
        assert isinstance(c["detection_hints"], list)
        assert "production" in c["detection_hints"]

        # examples should be parsed from JSON
        assert isinstance(c["examples"], list)
        assert len(c["examples"]) == 1
        assert c["examples"][0]["episode_id"] == "ep-001"
