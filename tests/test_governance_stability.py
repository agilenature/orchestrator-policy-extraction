"""Tests for the stability check runner (Phase 12, Plan 03).

Tests cover: pass/fail/timeout/error outcomes, DuckDB persistence,
multiple checks, output truncation, missing validation flagging,
validated marking, empty config, real subprocess execution, and
actor info retrieval.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.governance.stability import StabilityOutcome, StabilityRunner
from src.pipeline.models.config import GovernanceConfig, StabilityCheckDef
from src.pipeline.storage.schema import create_schema, get_connection


# --- Helpers ---


def make_config(
    checks: list[StabilityCheckDef] | None = None,
) -> GovernanceConfig:
    """Create a GovernanceConfig with given or default stability checks."""
    if checks is None:
        checks = [
            StabilityCheckDef(
                id="test-check", command=["echo", "hello"], description="test"
            )
        ]
    return GovernanceConfig(stability_checks=checks)


def make_conn():
    """Create an in-memory DuckDB connection with schema applied."""
    conn = get_connection(":memory:")
    create_schema(conn)
    return conn


def insert_episode(
    conn,
    episode_id: str,
    session_id: str = "sess-1",
    requires_stability_check: bool = True,
    stability_check_status: str | None = None,
) -> None:
    """Insert a minimal episode row for testing governance columns."""
    conn.execute(
        """
        INSERT INTO episodes (episode_id, session_id, segment_id, timestamp,
                              requires_stability_check, stability_check_status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            episode_id,
            session_id,
            f"seg-{episode_id}",
            datetime.now(timezone.utc).isoformat(),
            requires_stability_check,
            stability_check_status,
        ],
    )


def make_subprocess_result(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# --- Tests ---


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_passing_command(mock_run):
    """A command returning rc=0 should produce status='pass'."""
    mock_run.return_value = make_subprocess_result(returncode=0, stdout="ok\n")
    conn = make_conn()
    runner = StabilityRunner(conn, make_config())

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes) == 1
    assert outcomes[0].status == "pass"
    assert outcomes[0].exit_code == 0
    assert outcomes[0].check_id == "test-check"


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_failing_command(mock_run):
    """A command returning rc=1 should produce status='fail'."""
    mock_run.return_value = make_subprocess_result(
        returncode=1, stderr="error occurred"
    )
    conn = make_conn()
    runner = StabilityRunner(conn, make_config())

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes) == 1
    assert outcomes[0].status == "fail"
    assert outcomes[0].exit_code == 1


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_timeout(mock_run):
    """A timed-out command should produce status='error' with descriptive stderr."""
    # First two calls succeed (git config for actor info), third raises timeout
    mock_run.side_effect = [
        make_subprocess_result(returncode=0, stdout="Test User"),
        make_subprocess_result(returncode=0, stdout="test@example.com"),
        subprocess.TimeoutExpired("cmd", 30),
    ]
    conn = make_conn()
    config = make_config(
        [StabilityCheckDef(id="slow-check", command=["sleep", "999"], timeout_seconds=30)]
    )
    runner = StabilityRunner(conn, config)

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes) == 1
    assert outcomes[0].status == "error"
    assert outcomes[0].exit_code == -1
    assert "Timeout" in outcomes[0].stderr
    assert "30" in outcomes[0].stderr


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_generic_error(mock_run):
    """A generic exception should produce status='error'."""
    mock_run.side_effect = [
        make_subprocess_result(returncode=0, stdout="Test User"),
        make_subprocess_result(returncode=0, stdout="test@example.com"),
        RuntimeError("unexpected failure"),
    ]
    conn = make_conn()
    runner = StabilityRunner(conn, make_config())

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes) == 1
    assert outcomes[0].status == "error"
    assert outcomes[0].exit_code == -1
    assert "unexpected failure" in outcomes[0].stderr


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_writes_to_duckdb(mock_run):
    """Outcomes should be persisted to stability_outcomes table."""
    mock_run.return_value = make_subprocess_result(returncode=0, stdout="all good")
    conn = make_conn()
    runner = StabilityRunner(conn, make_config())

    runner.run_checks("/tmp", session_id="sess-42")

    rows = conn.execute("SELECT * FROM stability_outcomes").fetchall()
    assert len(rows) == 1
    row = rows[0]
    # row: run_id, check_id, session_id, status, exit_code, stdout, stderr,
    #      started_at, ended_at, actor_name, actor_email
    assert row[1] == "test-check"  # check_id
    assert row[2] == "sess-42"  # session_id
    assert row[3] == "pass"  # status
    assert row[4] == 0  # exit_code


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_multiple_checks(mock_run):
    """Multiple configured checks should produce multiple outcomes and DB rows."""
    mock_run.return_value = make_subprocess_result(returncode=0)
    conn = make_conn()
    config = make_config(
        [
            StabilityCheckDef(id="check-a", command=["echo", "a"]),
            StabilityCheckDef(id="check-b", command=["echo", "b"]),
        ]
    )
    runner = StabilityRunner(conn, config)

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes) == 2
    assert {o.check_id for o in outcomes} == {"check-a", "check-b"}
    row_count = conn.execute("SELECT COUNT(*) FROM stability_outcomes").fetchone()[0]
    assert row_count == 2


@patch("src.pipeline.governance.stability.subprocess.run")
def test_run_checks_truncates_output(mock_run):
    """stdout longer than 10000 chars should be truncated."""
    long_output = "x" * 20000
    mock_run.return_value = make_subprocess_result(returncode=0, stdout=long_output)
    conn = make_conn()
    runner = StabilityRunner(conn, make_config())

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes[0].stdout) == 10000
    # Verify truncated value persisted to DB
    db_stdout = conn.execute(
        "SELECT stdout FROM stability_outcomes"
    ).fetchone()[0]
    assert len(db_stdout) == 10000


@patch("src.pipeline.governance.stability.subprocess.run")
def test_flag_missing_validation(mock_run):
    """Episodes with requires_stability_check=TRUE and NULL status get flagged 'missing'."""
    mock_run.return_value = make_subprocess_result(returncode=0)
    conn = make_conn()
    insert_episode(conn, "ep-1", requires_stability_check=True, stability_check_status=None)
    runner = StabilityRunner(conn, make_config())

    count = runner.flag_missing_validation()

    assert count == 1
    status = conn.execute(
        "SELECT stability_check_status FROM episodes WHERE episode_id = 'ep-1'"
    ).fetchone()[0]
    assert status == "missing"


@patch("src.pipeline.governance.stability.subprocess.run")
def test_flag_missing_does_not_touch_validated(mock_run):
    """Episodes already validated should not be re-flagged."""
    mock_run.return_value = make_subprocess_result(returncode=0)
    conn = make_conn()
    insert_episode(
        conn, "ep-2", requires_stability_check=True, stability_check_status="validated"
    )
    runner = StabilityRunner(conn, make_config())

    count = runner.flag_missing_validation()

    assert count == 0
    status = conn.execute(
        "SELECT stability_check_status FROM episodes WHERE episode_id = 'ep-2'"
    ).fetchone()[0]
    assert status == "validated"


@patch("src.pipeline.governance.stability.subprocess.run")
def test_mark_validated(mock_run):
    """mark_validated should upgrade both NULL and 'missing' to 'validated'."""
    mock_run.return_value = make_subprocess_result(returncode=0)
    conn = make_conn()
    insert_episode(conn, "ep-a", requires_stability_check=True, stability_check_status=None)
    insert_episode(
        conn, "ep-b", requires_stability_check=True, stability_check_status="missing"
    )
    runner = StabilityRunner(conn, make_config())

    count = runner.mark_validated()

    assert count == 2
    statuses = conn.execute(
        "SELECT stability_check_status FROM episodes WHERE requires_stability_check = TRUE ORDER BY episode_id"
    ).fetchall()
    assert all(s[0] == "validated" for s in statuses)


@patch("src.pipeline.governance.stability.subprocess.run")
def test_mark_validated_does_not_touch_non_flagged(mock_run):
    """Episodes without requires_stability_check should not be touched."""
    mock_run.return_value = make_subprocess_result(returncode=0)
    conn = make_conn()
    insert_episode(
        conn, "ep-nf", requires_stability_check=False, stability_check_status=None
    )
    runner = StabilityRunner(conn, make_config())

    count = runner.mark_validated()

    assert count == 0
    status = conn.execute(
        "SELECT stability_check_status FROM episodes WHERE episode_id = 'ep-nf'"
    ).fetchone()[0]
    assert status is None


@patch("src.pipeline.governance.stability.subprocess.run")
def test_empty_stability_checks_config(mock_run):
    """Config with no checks should return empty list and write no rows."""
    mock_run.return_value = make_subprocess_result(returncode=0)
    conn = make_conn()
    runner = StabilityRunner(conn, GovernanceConfig(stability_checks=[]))

    outcomes = runner.run_checks("/tmp")

    assert outcomes == []
    row_count = conn.execute("SELECT COUNT(*) FROM stability_outcomes").fetchone()[0]
    assert row_count == 0


def test_real_command_execution():
    """Run an actual echo command without mocking to validate real subprocess integration."""
    conn = make_conn()
    config = make_config(
        [StabilityCheckDef(id="echo-test", command=["echo", "hello"])]
    )
    runner = StabilityRunner(conn, config)

    outcomes = runner.run_checks("/tmp")

    assert len(outcomes) == 1
    assert outcomes[0].status == "pass"
    assert outcomes[0].exit_code == 0
    assert "hello" in outcomes[0].stdout


@patch("src.pipeline.governance.stability.subprocess.run")
def test_actor_info(mock_run):
    """Git actor info should be populated in outcomes when git config succeeds."""
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First two calls are git config (in __init__)
        if call_count == 1:
            return make_subprocess_result(returncode=0, stdout="Alice\n")
        elif call_count == 2:
            return make_subprocess_result(returncode=0, stdout="alice@example.com\n")
        else:
            # Actual stability check
            return make_subprocess_result(returncode=0, stdout="ok")

    mock_run.side_effect = side_effect
    conn = make_conn()
    runner = StabilityRunner(conn, make_config())

    outcomes = runner.run_checks("/tmp")

    assert outcomes[0].actor_name == "Alice"
    assert outcomes[0].actor_email == "alice@example.com"
