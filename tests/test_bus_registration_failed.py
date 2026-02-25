"""Tests for BUS_REGISTRATION_FAILED event and openclaw_unavailable flag (Phase 20-02).

Covers:
- BUS_REGISTRATION_FAILED emission to JSONL staging when bus is unreachable
- openclaw_unavailable flag in register payload when OPE_RUN_ID absent
- repo/project_dir/transcript_path inclusion in register payload
- Fail-open behavior preserved (exit 0, staging write failure safe)
"""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from src.pipeline.live.hooks import session_start as ss


# ---------------------------------------------------------------------------
# BUS_REGISTRATION_FAILED emission tests
# ---------------------------------------------------------------------------


def test_bus_unavailable_emits_registration_failed(tmp_path):
    """Bus down (mock _post_json returns {}), verify BUS_REGISTRATION_FAILED
    event written to staging JSONL with session_id, run_id, attempted_at."""
    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", return_value={}),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    lines = (tmp_path / "staging.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_type"] == "BUS_REGISTRATION_FAILED"
    assert event["session_id"] == "test-s1"
    assert event["run_id"] == "run-42"
    assert "attempted_at" in event


def test_bus_available_no_registration_failed_event(tmp_path):
    """Bus up (mock returns proper response), verify no BUS_REGISTRATION_FAILED
    event in staging."""
    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", return_value={"status": "registered"}),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    # Staging file should not exist (no events written)
    assert not (tmp_path / "staging.jsonl").exists()


def test_registration_failed_event_has_required_fields(tmp_path):
    """Verify BUS_REGISTRATION_FAILED event has all 5 required fields:
    event_type, session_id, run_id, attempted_at, openclaw_unavailable."""
    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", return_value={}),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    event = json.loads((tmp_path / "staging.jsonl").read_text().strip())
    required_fields = {"event_type", "session_id", "run_id", "attempted_at",
                       "openclaw_unavailable"}
    assert required_fields.issubset(event.keys()), (
        f"Missing fields: {required_fields - event.keys()}"
    )


def test_registration_failed_still_exits_zero():
    """Run session_start.py as subprocess (bus not running), verify exit code 0."""
    result = subprocess.run(
        [sys.executable, "src/pipeline/live/hooks/session_start.py"],
        capture_output=True,
        cwd="/Users/david/projects/orchestrator-policy-extraction",
    )
    assert result.returncode == 0


def test_staging_write_failure_does_not_crash(tmp_path):
    """Mock staging path to unwritable location, verify main() does not raise."""
    # Use a path that cannot be created (file as parent)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    staging = str(blocker / "nested" / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", return_value={}),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()  # must not raise


# ---------------------------------------------------------------------------
# openclaw_unavailable flag tests
# ---------------------------------------------------------------------------


def test_openclaw_unavailable_true_when_run_id_absent(tmp_path):
    """When OPE_RUN_ID is empty, register payload must carry
    openclaw_unavailable: True."""
    calls = []

    def mock_post(path, payload):
        calls.append((path, payload))
        return {"status": "registered"}

    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", side_effect=mock_post),
        patch.object(ss, "_OPE_RUN_ID", ""),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    register_calls = [(p, pl) for p, pl in calls if p == "/api/register"]
    assert len(register_calls) == 1
    payload = register_calls[0][1]
    assert payload["openclaw_unavailable"] is True


def test_openclaw_unavailable_absent_when_run_id_present(tmp_path):
    """When OPE_RUN_ID is set, register payload must NOT contain
    openclaw_unavailable key."""
    calls = []

    def mock_post(path, payload):
        calls.append((path, payload))
        return {"status": "registered"}

    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", side_effect=mock_post),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    register_calls = [(p, pl) for p, pl in calls if p == "/api/register"]
    assert len(register_calls) == 1
    payload = register_calls[0][1]
    assert "openclaw_unavailable" not in payload


def test_registration_failed_event_includes_openclaw_unavailable(tmp_path):
    """Bus down, OPE_RUN_ID absent: BUS_REGISTRATION_FAILED event must carry
    openclaw_unavailable: True."""
    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", return_value={}),
        patch.object(ss, "_OPE_RUN_ID", ""),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    event = json.loads((tmp_path / "staging.jsonl").read_text().strip())
    assert event["openclaw_unavailable"] is True


# ---------------------------------------------------------------------------
# Register payload metadata tests
# ---------------------------------------------------------------------------


def test_register_includes_repo_when_env_set(tmp_path):
    """When OPE_REPO, OPE_PROJECT_DIR, OPE_TRANSCRIPT_PATH env vars are set,
    register payload must contain those fields."""
    calls = []

    def mock_post(path, payload):
        calls.append((path, payload))
        return {"status": "registered"}

    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", side_effect=mock_post),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_OPE_REPO", "my-org/my-repo"),
        patch.object(ss, "_OPE_PROJECT_DIR", "/home/user/project"),
        patch.object(ss, "_OPE_TRANSCRIPT_PATH", "/tmp/transcript.jsonl"),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    register_calls = [(p, pl) for p, pl in calls if p == "/api/register"]
    payload = register_calls[0][1]
    assert payload["repo"] == "my-org/my-repo"
    assert payload["project_dir"] == "/home/user/project"
    assert payload["transcript_path"] == "/tmp/transcript.jsonl"


def test_register_omits_repo_when_env_absent(tmp_path):
    """When OPE_REPO is empty, register payload must NOT contain repo key."""
    calls = []

    def mock_post(path, payload):
        calls.append((path, payload))
        return {"status": "registered"}

    staging = str(tmp_path / "staging.jsonl")
    with (
        patch.object(ss, "_post_json", side_effect=mock_post),
        patch.object(ss, "_OPE_RUN_ID", "run-42"),
        patch.object(ss, "_OPE_SESSION_ID", "test-s1"),
        patch.object(ss, "_OPE_REPO", ""),
        patch.object(ss, "_OPE_PROJECT_DIR", ""),
        patch.object(ss, "_OPE_TRANSCRIPT_PATH", ""),
        patch.object(ss, "_STAGING_PATH", staging),
    ):
        ss.main()
    register_calls = [(p, pl) for p, pl in calls if p == "/api/register"]
    payload = register_calls[0][1]
    assert "repo" not in payload
    assert "project_dir" not in payload
    assert "transcript_path" not in payload
