"""Tests for the audit CLI commands.

Tests audit session and audit durability subcommands using Click's
CliRunner for isolated invocation with tmp_path DuckDB databases.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.audit import audit_group
from src.pipeline.storage.schema import create_schema


# --- Fixtures ---


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary DuckDB database with schema."""
    path = str(tmp_path / "test.db")
    conn = duckdb.connect(path)
    create_schema(conn)
    conn.close()
    return path


@pytest.fixture
def constraints_path(tmp_path):
    """Create a temporary constraints.json with test data."""
    constraints = [
        {
            "constraint_id": "c001",
            "text": "Never commit directly to main branch",
            "severity": "forbidden",
            "type": "behavioral_constraint",
            "scope": {"paths": ["src/"]},
            "status": "active",
            "status_history": [
                {"status": "active", "changed_at": "2020-01-01T00:00:00+00:00"}
            ],
            "detection_hints": ["git push origin main", "git commit.*main"],
            "created_at": "2020-01-01T00:00:00+00:00",
            "examples": [],
        },
        {
            "constraint_id": "c002",
            "text": "Always run tests before deploying",
            "severity": "requires_approval",
            "type": "behavioral_constraint",
            "scope": {"paths": []},
            "status": "active",
            "status_history": [
                {"status": "active", "changed_at": "2020-01-01T00:00:00+00:00"}
            ],
            "detection_hints": [],
            "created_at": "2020-01-01T00:00:00+00:00",
            "examples": [],
        },
    ]
    path = tmp_path / "constraints.json"
    path.write_text(json.dumps(constraints, indent=2))
    return str(path)


@pytest.fixture
def schema_path(tmp_path):
    """Create a minimal constraint schema for validation."""
    # Copy real schema or create minimal one
    real_schema = Path("data/schemas/constraint.schema.json")
    if real_schema.exists():
        import shutil
        dest = tmp_path / "schemas" / "constraint.schema.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(real_schema, dest)
        return str(dest)
    return None


@pytest.fixture
def config_path():
    """Path to the pipeline config."""
    return "data/config.yaml"


@pytest.fixture
def populated_db(tmp_path, constraints_path):
    """Create DB with events for two sessions, one with violation hints."""
    db_file = str(tmp_path / "populated.db")
    conn = duckdb.connect(db_file)
    create_schema(conn)

    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Session 1: clean session (no violation hints in events)
    for i in range(5):
        conn.execute(
            """INSERT INTO events (event_id, ts_utc, session_id, actor, event_type,
               payload, source_system, source_ref)
               VALUES (?, ?, 'sess-clean', 'human_orchestrator', 'user_msg',
               ?, 'test', 'test')""",
            [
                f"ev-clean-{i}",
                now.isoformat(),
                json.dumps({"common": {"text": f"Normal message {i}"}}),
            ],
        )

    # Session 2: session with a violation hint matching c001
    for i in range(5):
        text = f"Running git push origin main --force" if i == 2 else f"Working on task {i}"
        conn.execute(
            """INSERT INTO events (event_id, ts_utc, session_id, actor, event_type,
               payload, source_system, source_ref)
               VALUES (?, ?, 'sess-dirty', 'human_orchestrator', 'user_msg',
               ?, 'test', 'test')""",
            [
                f"ev-dirty-{i}",
                now.isoformat(),
                json.dumps({"common": {"text": text}, "details": {"file_path": "src/main.py"}}),
            ],
        )

    conn.close()
    return db_file


# --- audit session tests ---


class TestAuditSession:
    """Tests for the audit session CLI command."""

    def test_audit_session_produces_output(self, runner, populated_db, constraints_path, config_path):
        """Audit session with pre-populated DB produces output."""
        result = runner.invoke(
            audit_group,
            ["session", "--db", populated_db, "--constraints", constraints_path, "--config", config_path],
        )
        # Should not crash (exit code 0 or 2)
        assert result.exit_code in (0, 2), f"Exit code: {result.exit_code}, Output: {result.output}"
        assert "Session:" in result.output or "Total amnesia" in result.output

    def test_audit_session_filter_by_id(self, runner, populated_db, constraints_path, config_path):
        """Audit session --session-id filters to single session."""
        result = runner.invoke(
            audit_group,
            [
                "session",
                "--session-id", "sess-clean",
                "--db", populated_db,
                "--constraints", constraints_path,
                "--config", config_path,
            ],
        )
        assert result.exit_code in (0, 2), f"Exit code: {result.exit_code}, Output: {result.output}"
        # Should only show sess-clean, not sess-dirty
        if "Session:" in result.output:
            assert "sess-clean" in result.output

    def test_audit_session_json_output(self, runner, populated_db, constraints_path, config_path):
        """Audit session --json produces valid JSON output."""
        result = runner.invoke(
            audit_group,
            [
                "session",
                "--json",
                "--db", populated_db,
                "--constraints", constraints_path,
                "--config", config_path,
            ],
        )
        assert result.exit_code in (0, 2), f"Exit code: {result.exit_code}, Output: {result.output}"
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        if parsed:
            assert "session_id" in parsed[0]
            assert "constraints_evaluated" in parsed[0]
            assert "honored" in parsed[0]
            assert "violated" in parsed[0]
            assert "amnesia_events" in parsed[0]

    def test_audit_session_exit_code_2_on_amnesia(self, runner, populated_db, constraints_path, config_path):
        """Audit session exits with code 2 when amnesia events are detected."""
        # sess-dirty has "git push origin main" matching c001's detection_hints
        result = runner.invoke(
            audit_group,
            [
                "session",
                "--session-id", "sess-dirty",
                "--db", populated_db,
                "--constraints", constraints_path,
                "--config", config_path,
            ],
        )
        # c001 should be VIOLATED due to detection hint match
        assert result.exit_code == 2, f"Expected exit code 2, got {result.exit_code}. Output: {result.output}"

    def test_audit_session_exit_code_0_no_amnesia(self, runner, populated_db, constraints_path, config_path):
        """Audit session exits with code 0 when no amnesia events."""
        # sess-clean has no violation hints, but c002 has no detection_hints
        # and empty scope (repo-wide) so it will be HONORED
        # We need a session where all constraints are honored and none violated
        # Use sess-clean which has no matching hints for c001 and
        # c002 has no hints, so both should be HONORED
        # But c001 scope is src/ and sess-clean events have no file_path details
        # so scope won't overlap -- c001 will be excluded (UNKNOWN).
        # c002 has empty scope (repo-wide) and no hints -> HONORED -> exit 0
        result = runner.invoke(
            audit_group,
            [
                "session",
                "--session-id", "sess-clean",
                "--db", populated_db,
                "--constraints", constraints_path,
                "--config", config_path,
            ],
        )
        assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"

    def test_audit_session_no_constraints(self, runner, db_path, tmp_path, config_path):
        """Audit session with no constraints reports nothing to audit."""
        empty_constraints = tmp_path / "empty.json"
        empty_constraints.write_text("[]")
        result = runner.invoke(
            audit_group,
            ["session", "--db", db_path, "--constraints", str(empty_constraints), "--config", config_path],
        )
        assert result.exit_code == 0
        assert "No constraints" in result.output

    def test_audit_session_no_sessions(self, runner, db_path, constraints_path, config_path):
        """Audit session with no sessions in DB reports no sessions."""
        result = runner.invoke(
            audit_group,
            ["session", "--db", db_path, "--constraints", constraints_path, "--config", config_path],
        )
        assert result.exit_code == 0
        assert "No sessions" in result.output


# --- audit durability tests ---


class TestAuditDurability:
    """Tests for the audit durability CLI command."""

    def test_audit_durability_shows_scores(self, runner, tmp_path):
        """Audit durability shows scores for all constraints with eval data."""
        db_file = str(tmp_path / "dur.db")
        conn = duckdb.connect(db_file)
        create_schema(conn)

        # Insert eval results for 4 sessions (above min_sessions=3)
        for i in range(4):
            conn.execute(
                "INSERT INTO session_constraint_eval (session_id, constraint_id, eval_state) "
                "VALUES (?, 'c001', ?)",
                [f"sess-{i}", "HONORED" if i < 3 else "VIOLATED"],
            )
        conn.close()

        result = runner.invoke(audit_group, ["durability", "--db", db_file])
        assert result.exit_code == 0
        assert "c001" in result.output
        assert "0.75" in result.output  # 3/4 honored

    def test_audit_durability_filter_by_constraint_id(self, runner, tmp_path):
        """Audit durability --constraint-id filters to single constraint."""
        db_file = str(tmp_path / "dur2.db")
        conn = duckdb.connect(db_file)
        create_schema(conn)

        for i in range(3):
            conn.execute(
                "INSERT INTO session_constraint_eval (session_id, constraint_id, eval_state) "
                "VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )
            conn.execute(
                "INSERT INTO session_constraint_eval (session_id, constraint_id, eval_state) "
                "VALUES (?, 'c002', 'VIOLATED')",
                [f"sess-{i}"],
            )
        conn.close()

        result = runner.invoke(
            audit_group, ["durability", "--constraint-id", "c001", "--db", db_file]
        )
        assert result.exit_code == 0
        assert "c001" in result.output

    def test_audit_durability_json_output(self, runner, tmp_path):
        """Audit durability --json produces valid JSON output."""
        db_file = str(tmp_path / "dur3.db")
        conn = duckdb.connect(db_file)
        create_schema(conn)

        for i in range(3):
            conn.execute(
                "INSERT INTO session_constraint_eval (session_id, constraint_id, eval_state) "
                "VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )
        conn.close()

        result = runner.invoke(
            audit_group, ["durability", "--json", "--db", db_file]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["constraint_id"] == "c001"
        assert parsed[0]["durability_score"] == 1.0

    def test_audit_durability_insufficient_data(self, runner, tmp_path):
        """Audit durability shows insufficient data for < 3 sessions."""
        db_file = str(tmp_path / "dur4.db")
        conn = duckdb.connect(db_file)
        create_schema(conn)

        # Only 2 sessions (below min_sessions=3)
        for i in range(2):
            conn.execute(
                "INSERT INTO session_constraint_eval (session_id, constraint_id, eval_state) "
                "VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )
        conn.close()

        result = runner.invoke(audit_group, ["durability", "--db", db_file])
        assert result.exit_code == 0
        assert "need >= 3" in result.output

    def test_audit_durability_no_data(self, runner, db_path):
        """Audit durability with no data shows appropriate message."""
        result = runner.invoke(audit_group, ["durability", "--db", db_path])
        assert result.exit_code == 0
        assert "No constraint evaluations" in result.output


# --- Help text tests ---


class TestAuditHelp:
    """Tests for audit command help text."""

    def test_audit_help_shows_subcommands(self, runner):
        """Audit --help shows session and durability subcommands."""
        result = runner.invoke(audit_group, ["--help"])
        assert result.exit_code == 0
        assert "session" in result.output
        assert "durability" in result.output

    def test_audit_session_help(self, runner):
        """Audit session --help shows options."""
        result = runner.invoke(audit_group, ["session", "--help"])
        assert result.exit_code == 0
        assert "--session-id" in result.output
        assert "--json" in result.output
        assert "--db" in result.output
        assert "--constraints" in result.output

    def test_audit_durability_help(self, runner):
        """Audit durability --help shows options."""
        result = runner.invoke(audit_group, ["durability", "--help"])
        assert result.exit_code == 0
        assert "--constraint-id" in result.output
        assert "--json" in result.output
        assert "--db" in result.output
