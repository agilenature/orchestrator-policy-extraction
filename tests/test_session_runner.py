"""Tests for AssessmentSessionRunner (Phase 17, Plan 03).

Covers:
- setup_assessment_dir creates scenario files + CLAUDE.md
- setup_assessment_dir with handicap writes handicap CLAUDE.md
- launch_actor constructs correct subprocess command
- launch_actor sets completed status on success
- launch_actor sets failed status on error
- cleanup_session creates tar and removes dir
- derive_jsonl_path encoding
"""

from __future__ import annotations

import os
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from src.pipeline.assessment.models import AssessmentSession, ScenarioSpec
from src.pipeline.assessment.session_runner import AssessmentSessionRunner


@pytest.fixture
def conn():
    """In-memory DuckDB connection with assessment schema."""
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE IF NOT EXISTS project_wisdom (
            wisdom_id VARCHAR PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            description TEXT NOT NULL,
            scenario_seed TEXT,
            ddf_target_level INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS assessment_te_sessions (
            te_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            scenario_id VARCHAR NOT NULL,
            candidate_id VARCHAR NOT NULL,
            candidate_te FLOAT,
            scenario_baseline_te FLOAT,
            candidate_ratio FLOAT,
            raven_depth FLOAT,
            crow_efficiency FLOAT,
            trunk_quality FLOAT,
            trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending',
            fringe_drift_rate FLOAT,
            scenario_ddf_level INTEGER,
            session_artifact_path VARCHAR,
            assessment_date TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    yield c
    c.close()


@pytest.fixture
def scenario_spec_no_handicap():
    """ScenarioSpec without handicap (L3)."""
    return ScenarioSpec(
        scenario_id="test_scenario_001",
        wisdom_id="w-test001",
        ddf_target_level=3,
        entity_type="dead_end",
        title="Test Scenario",
        scenario_context="# Test\n\nThis is a test scenario.",
        broken_impl_filename="broken_impl.py",
        broken_impl_content='def main():\n    raise RuntimeError("broken")\n\nif __name__ == "__main__":\n    main()\n',
        handicap_claude_md=None,
    )


@pytest.fixture
def scenario_spec_with_handicap():
    """ScenarioSpec with handicap (L6)."""
    return ScenarioSpec(
        scenario_id="test_scenario_002",
        wisdom_id="w-test002",
        ddf_target_level=6,
        entity_type="scope_decision",
        title="Handicap Scenario",
        scenario_context="# Handicap\n\nThis tests framing resistance.",
        broken_impl_filename="broken_impl.py",
        broken_impl_content='def main():\n    raise RuntimeError("wrong cause")\n\nif __name__ == "__main__":\n    main()\n',
        handicap_claude_md="# Wrong Analysis\n\nThe issue is in configuration.",
    )


class TestSetupAssessmentDir:
    """Tests for setup_assessment_dir."""

    @patch("src.pipeline.assessment.session_runner._PRODUCTION_MEMORY_PATH", "/nonexistent/MEMORY.md")
    def test_creates_files(self, conn, scenario_spec_no_handicap, tmp_path):
        """setup_assessment_dir creates scenario_context.md, broken_impl, CLAUDE.md."""
        runner = AssessmentSessionRunner(conn)

        with patch(
            "src.pipeline.assessment.session_runner.AssessmentSessionRunner._preseed_memory_md"
        ):
            session = runner.setup_assessment_dir(
                scenario_spec_no_handicap, "test-sess-001"
            )

        assessment_dir = Path(session.assessment_dir)
        try:
            assert assessment_dir.exists()
            assert (assessment_dir / "scenario_context.md").exists()
            assert (assessment_dir / "broken_impl.py").exists()
            assert (assessment_dir / ".claude" / "CLAUDE.md").exists()
            assert session.status == "setup"
        finally:
            import shutil
            if assessment_dir.exists():
                shutil.rmtree(assessment_dir)

    @patch("src.pipeline.assessment.session_runner._PRODUCTION_MEMORY_PATH", "/nonexistent/MEMORY.md")
    def test_handicap_claude_md(self, conn, scenario_spec_with_handicap, tmp_path):
        """setup_assessment_dir writes handicap content to CLAUDE.md for L5+ scenarios."""
        runner = AssessmentSessionRunner(conn)

        with patch(
            "src.pipeline.assessment.session_runner.AssessmentSessionRunner._preseed_memory_md"
        ):
            session = runner.setup_assessment_dir(
                scenario_spec_with_handicap, "test-sess-002"
            )

        assessment_dir = Path(session.assessment_dir)
        try:
            claude_md = (assessment_dir / ".claude" / "CLAUDE.md").read_text()
            assert "Wrong Analysis" in claude_md
            assert "configuration" in claude_md
        finally:
            import shutil
            if assessment_dir.exists():
                shutil.rmtree(assessment_dir)

    @patch("src.pipeline.assessment.session_runner._PRODUCTION_MEMORY_PATH", "/nonexistent/MEMORY.md")
    def test_no_handicap_minimal_claude_md(self, conn, scenario_spec_no_handicap):
        """setup_assessment_dir writes minimal CLAUDE.md when no handicap."""
        runner = AssessmentSessionRunner(conn)

        with patch(
            "src.pipeline.assessment.session_runner.AssessmentSessionRunner._preseed_memory_md"
        ):
            session = runner.setup_assessment_dir(
                scenario_spec_no_handicap, "test-sess-003"
            )

        assessment_dir = Path(session.assessment_dir)
        try:
            claude_md = (assessment_dir / ".claude" / "CLAUDE.md").read_text()
            assert "Assessment Session" in claude_md
        finally:
            import shutil
            if assessment_dir.exists():
                shutil.rmtree(assessment_dir)


class TestLaunchActor:
    """Tests for launch_actor (subprocess mocked)."""

    @patch("subprocess.run")
    def test_command_construction(self, mock_run, conn, scenario_spec_no_handicap):
        """launch_actor command includes cd, unset CLAUDECODE, claude -p, --session-id."""
        mock_run.return_value = MagicMock(returncode=0)

        runner = AssessmentSessionRunner(conn)
        session = AssessmentSession(
            session_id="test-sess-cmd",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/ope_assess_test-sess-cmd",
            status="setup",
        )

        runner.launch_actor(session)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("command", "")

        assert "cd" in cmd
        assert "unset CLAUDECODE" in cmd
        assert "claude -p" in cmd
        assert "--session-id test-sess-cmd" in cmd
        assert "--permission-mode bypassPermissions" in cmd

    @patch("subprocess.run")
    def test_completed_status(self, mock_run, conn):
        """launch_actor sets status='completed' on exit code 0."""
        mock_run.return_value = MagicMock(returncode=0)

        runner = AssessmentSessionRunner(conn)
        session = AssessmentSession(
            session_id="test-sess-ok",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/ope_assess_test-sess-ok",
            status="setup",
        )

        result = runner.launch_actor(session)
        assert result.status == "completed"
        assert result.jsonl_path is not None

    @patch("subprocess.run")
    def test_failed_on_error(self, mock_run, conn):
        """launch_actor sets status='failed' on non-zero exit code."""
        mock_run.return_value = MagicMock(returncode=1)

        runner = AssessmentSessionRunner(conn)
        session = AssessmentSession(
            session_id="test-sess-fail",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/ope_assess_test-sess-fail",
            status="setup",
        )

        result = runner.launch_actor(session)
        assert result.status == "failed"

    @patch("subprocess.run")
    def test_failed_on_timeout(self, mock_run, conn):
        """launch_actor sets status='failed' on timeout."""
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd="claude", timeout=10)

        runner = AssessmentSessionRunner(conn)
        session = AssessmentSession(
            session_id="test-sess-timeout",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/ope_assess_test-sess-timeout",
            status="setup",
        )

        result = runner.launch_actor(session, timeout=10)
        assert result.status == "failed"

    @patch("subprocess.run")
    def test_custom_prompt(self, mock_run, conn):
        """launch_actor uses custom prompt when provided."""
        mock_run.return_value = MagicMock(returncode=0)

        runner = AssessmentSessionRunner(conn)
        session = AssessmentSession(
            session_id="test-sess-prompt",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir="/tmp/ope_assess_test-sess-prompt",
            status="setup",
        )

        runner.launch_actor(session, prompt="Custom prompt here")

        cmd = mock_run.call_args[0][0]
        assert "Custom prompt here" in cmd


class TestCleanupSession:
    """Tests for cleanup_session."""

    def test_creates_tar_and_removes_dir(self, conn, tmp_path):
        """cleanup_session creates tar.gz archive and removes assessment dir."""
        # Create a temp assessment dir with some files
        assess_dir = tmp_path / "ope_assess_test-cleanup"
        assess_dir.mkdir()
        (assess_dir / "scenario_context.md").write_text("test")
        (assess_dir / "broken_impl.py").write_text("def main(): pass")

        session = AssessmentSession(
            session_id="test-cleanup",
            scenario_id="scen001",
            candidate_id="cand001",
            assessment_dir=str(assess_dir),
            status="completed",
        )

        runner = AssessmentSessionRunner(conn)
        result = runner.cleanup_session(session)

        # Dir should be removed
        assert not assess_dir.exists()

        # Tar should exist
        assert result.session_artifact_path is not None
        assert os.path.exists(result.session_artifact_path)

        # Verify tar contents
        with tarfile.open(result.session_artifact_path, "r:gz") as tar:
            names = tar.getnames()
            assert any("scenario_context.md" in n for n in names)

        # Cleanup tar
        os.unlink(result.session_artifact_path)


class TestDeriveJsonlPath:
    """Tests for AssessmentSession.derive_jsonl_path."""

    def test_path_encoding(self):
        """derive_jsonl_path encodes slashes to dashes."""
        path = AssessmentSession.derive_jsonl_path(
            "/tmp/ope_assess_abc123", "session-001"
        )

        assert "-tmp-ope_assess_abc123" in path
        assert "session-001.jsonl" in path
        assert path.startswith(os.path.expanduser("~"))

    def test_trailing_slash_handling(self):
        """derive_jsonl_path strips trailing slash before encoding."""
        path1 = AssessmentSession.derive_jsonl_path(
            "/tmp/ope_assess_abc123/", "session-001"
        )
        path2 = AssessmentSession.derive_jsonl_path(
            "/tmp/ope_assess_abc123", "session-001"
        )
        assert path1 == path2
