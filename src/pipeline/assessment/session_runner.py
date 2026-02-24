"""Assessment session lifecycle: setup, launch, cleanup (Phase 17, Plan 03).

Manages the end-to-end lifecycle of an assessment session:
1. Setup: Create /tmp assessment directory with scenario files + CLAUDE.md + MEMORY.md
2. Launch: Run Actor Claude Code via subprocess with CLAUDECODE unset
3. Cleanup: Archive assessment dir to tar.gz, remove temp files

The session runner never runs the OPE pipeline itself -- that's the
AssessmentObserver's job. This module handles only the physical session
lifecycle.

Exports:
    AssessmentSessionRunner
    setup_assessment_dir
    launch_actor
    cleanup_session
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.pipeline.assessment.models import AssessmentSession, ScenarioSpec
from src.pipeline.assessment.scenario_generator import ScenarioGenerator

logger = logging.getLogger(__name__)

# Default production MEMORY.md path
_PRODUCTION_MEMORY_PATH = os.path.expanduser(
    "~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction"
    "/memory/MEMORY.md"
)


class AssessmentSessionRunner:
    """Assessment session lifecycle management.

    Handles directory setup (with scenario files and pre-seeded
    CLAUDE.md/MEMORY.md), Actor Claude Code launch via subprocess,
    and post-session cleanup (tar archive + temp dir removal).

    Args:
        conn: DuckDB connection for schema/data operations.
        db_path: DuckDB database path for session artifact updates.
    """

    def __init__(
        self, conn: duckdb.DuckDBPyConnection, db_path: str = "data/ope.db"
    ) -> None:
        self._conn = conn
        self._db_path = db_path

    def setup_assessment_dir(
        self, scenario_spec: ScenarioSpec, session_id: str
    ) -> AssessmentSession:
        """Create assessment directory with scenario files and pre-seeded configs.

        1. Creates /tmp/ope_assess_{session_id}/
        2. Writes scenario files (context + broken impl + optional handicap)
        3. Pre-seeds CLAUDE.md in assessment dir's .claude/ directory
        4. Pre-seeds MEMORY.md from production MEMORY.md

        Args:
            scenario_spec: ScenarioSpec with scenario content.
            session_id: Unique session identifier.

        Returns:
            AssessmentSession with status='setup' and paths populated.
        """
        assessment_dir = f"/tmp/ope_assess_{session_id}"
        output_dir = Path(assessment_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write scenario files using ScenarioGenerator
        gen = ScenarioGenerator(self._conn)
        gen.generate_scenario_files(scenario_spec, output_dir)

        # Pre-seed CLAUDE.md
        if scenario_spec.handicap_claude_md:
            # Handicap scenario: write handicap content as CLAUDE.md
            claude_dir = output_dir / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            claude_md_path = claude_dir / "CLAUDE.md"
            claude_md_path.write_text(
                scenario_spec.handicap_claude_md, encoding="utf-8"
            )
        else:
            # No handicap: write minimal assessment CLAUDE.md
            claude_dir = output_dir / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            claude_md_path = claude_dir / "CLAUDE.md"
            claude_md_path.write_text(
                "# Assessment Session\n\n"
                "This is a controlled assessment environment.\n",
                encoding="utf-8",
            )

        # Pre-seed MEMORY.md from production
        self._preseed_memory_md(assessment_dir)

        return AssessmentSession(
            session_id=session_id,
            scenario_id=scenario_spec.scenario_id,
            candidate_id="",  # Set by caller
            assessment_dir=assessment_dir,
            status="setup",
        )

    def launch_actor(
        self,
        session: AssessmentSession,
        prompt: str | None = None,
        timeout: int = 1800,
    ) -> AssessmentSession:
        """Launch Actor Claude Code in the assessment directory.

        Runs Claude Code via subprocess with:
        - CLAUDECODE environment variable unset
        - CWD set to the assessment directory
        - --session-id for deterministic JSONL path
        - --permission-mode bypassPermissions

        Args:
            session: AssessmentSession with status='setup'.
            prompt: Custom prompt. Defaults to standard assessment prompt.
            timeout: Subprocess timeout in seconds (default 1800).

        Returns:
            Updated AssessmentSession with status='completed' or 'failed',
            jsonl_path populated.
        """
        default_prompt = (
            "Read scenario_context.md to understand the problem, "
            "then diagnose and fix the broken implementation file."
        )
        actual_prompt = prompt or default_prompt

        command = (
            f'cd "{session.assessment_dir}" && '
            f"unset CLAUDECODE && "
            f'claude -p "{actual_prompt}" '
            f"--session-id {session.session_id} "
            f"--permission-mode bypassPermissions"
        )

        logger.info(
            "Launching Actor for session %s in %s",
            session.session_id,
            session.assessment_dir,
        )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
            )
            status = "completed" if result.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            logger.warning(
                "Actor timed out after %ds for session %s",
                timeout,
                session.session_id,
            )
            status = "failed"
        except Exception as e:
            logger.error(
                "Actor launch failed for session %s: %s",
                session.session_id,
                e,
            )
            status = "failed"

        jsonl_path = AssessmentSession.derive_jsonl_path(
            session.assessment_dir, session.session_id
        )

        return AssessmentSession(
            session_id=session.session_id,
            scenario_id=session.scenario_id,
            candidate_id=session.candidate_id,
            assessment_dir=session.assessment_dir,
            jsonl_path=jsonl_path,
            status=status,
            handicap_level=session.handicap_level,
            started_at=session.started_at,
            completed_at=datetime.now(timezone.utc),
        )

    def cleanup_session(self, session: AssessmentSession) -> AssessmentSession:
        """Archive and remove assessment directory.

        1. Tar the assessment dir to /tmp/ope_assess_{session_id}.tar.gz
        2. Update session_artifact_path in assessment_te_sessions
        3. Remove assessment dir
        4. Remove ~/.claude/projects/{encoded}/ directory

        Args:
            session: AssessmentSession to clean up.

        Returns:
            Updated AssessmentSession with session_artifact_path set.
        """
        tar_path = f"/tmp/ope_assess_{session.session_id}.tar.gz"

        # Archive assessment dir
        if os.path.isdir(session.assessment_dir):
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(
                    session.assessment_dir,
                    arcname=os.path.basename(session.assessment_dir),
                )

        # Update session_artifact_path in DB
        try:
            self._conn.execute(
                "UPDATE assessment_te_sessions "
                "SET session_artifact_path = ? "
                "WHERE session_id = ?",
                [tar_path, session.session_id],
            )
        except Exception:
            pass  # Table may not exist yet or no row for this session

        # Remove assessment dir
        if os.path.isdir(session.assessment_dir):
            shutil.rmtree(session.assessment_dir)

        # Remove ~/.claude/projects/{encoded}/ directory
        clean_dir = session.assessment_dir.rstrip("/")
        encoded = clean_dir.replace("/", "-")
        claude_projects_dir = os.path.expanduser(
            f"~/.claude/projects/{encoded}"
        )
        if os.path.isdir(claude_projects_dir):
            shutil.rmtree(claude_projects_dir)

        return AssessmentSession(
            session_id=session.session_id,
            scenario_id=session.scenario_id,
            candidate_id=session.candidate_id,
            assessment_dir=session.assessment_dir,
            jsonl_path=session.jsonl_path,
            status=session.status,
            handicap_level=session.handicap_level,
            session_artifact_path=tar_path,
            started_at=session.started_at,
            completed_at=session.completed_at,
        )

    def _preseed_memory_md(self, assessment_dir: str) -> None:
        """Pre-seed MEMORY.md from production MEMORY.md.

        Copies production MEMORY.md content to the assessment-specific
        MEMORY.md path that Claude Code will read.

        Path: ~/.claude/projects/{encoded_dir}/memory/MEMORY.md
        """
        clean_dir = assessment_dir.rstrip("/")
        encoded = clean_dir.replace("/", "-")
        memory_dir = os.path.expanduser(
            f"~/.claude/projects/{encoded}/memory"
        )
        memory_path = os.path.join(memory_dir, "MEMORY.md")

        os.makedirs(memory_dir, exist_ok=True)

        # Copy production MEMORY.md if it exists
        if os.path.exists(_PRODUCTION_MEMORY_PATH):
            with open(_PRODUCTION_MEMORY_PATH, encoding="utf-8") as f:
                content = f.read()
            with open(memory_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Pre-seeded MEMORY.md at %s", memory_path)
        else:
            # Write minimal MEMORY.md
            with open(memory_path, "w", encoding="utf-8") as f:
                f.write("# Project Memory\n\nNo production MEMORY.md found.\n")
            logger.warning(
                "Production MEMORY.md not found at %s, wrote minimal stub",
                _PRODUCTION_MEMORY_PATH,
            )


# Convenience wrappers


def setup_assessment_dir(
    conn: duckdb.DuckDBPyConnection,
    scenario_spec: ScenarioSpec,
    session_id: str,
    db_path: str = "data/ope.db",
) -> AssessmentSession:
    """Convenience: create assessment directory with scenario files.

    Args:
        conn: DuckDB connection.
        scenario_spec: ScenarioSpec with scenario content.
        session_id: Unique session identifier.
        db_path: DuckDB database path.

    Returns:
        AssessmentSession with status='setup'.
    """
    runner = AssessmentSessionRunner(conn, db_path)
    return runner.setup_assessment_dir(scenario_spec, session_id)


def launch_actor(
    conn: duckdb.DuckDBPyConnection,
    session: AssessmentSession,
    prompt: str | None = None,
    db_path: str = "data/ope.db",
) -> AssessmentSession:
    """Convenience: launch Actor Claude Code.

    Args:
        conn: DuckDB connection.
        session: AssessmentSession with status='setup'.
        prompt: Custom prompt.
        db_path: DuckDB database path.

    Returns:
        Updated AssessmentSession.
    """
    runner = AssessmentSessionRunner(conn, db_path)
    return runner.launch_actor(session, prompt)


def cleanup_session(
    conn: duckdb.DuckDBPyConnection,
    session: AssessmentSession,
    db_path: str = "data/ope.db",
) -> AssessmentSession:
    """Convenience: archive and cleanup assessment directory.

    Args:
        conn: DuckDB connection.
        session: AssessmentSession to clean up.
        db_path: DuckDB database path.

    Returns:
        Updated AssessmentSession with session_artifact_path.
    """
    runner = AssessmentSessionRunner(conn, db_path)
    return runner.cleanup_session(session)
