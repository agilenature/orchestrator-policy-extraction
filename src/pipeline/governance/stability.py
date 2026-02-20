"""Stability check runner for governance protocol integration.

Executes config-registered stability commands via subprocess, records
outcomes in DuckDB, and flags episodes that required stability checks
but never received them.

Implements GOVERN-02: stability check execution and missing validation
detection.

Exports:
    StabilityOutcome: Dataclass for individual check results
    StabilityRunner: Orchestrates check execution and DuckDB persistence
"""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.pipeline.models.config import GovernanceConfig


@dataclass
class StabilityOutcome:
    """Result of a single stability check execution."""

    run_id: str
    check_id: str
    status: str  # "pass", "fail", "error"
    exit_code: int
    stdout: str
    stderr: str
    started_at: str  # ISO 8601
    ended_at: str  # ISO 8601
    session_id: str | None = None
    actor_name: str | None = None
    actor_email: str | None = None


class StabilityRunner:
    """Executes stability checks and records outcomes in DuckDB.

    Runs each command defined in GovernanceConfig.stability_checks via
    subprocess.run with explicit timeout handling. Results are persisted
    to the stability_outcomes DuckDB table.

    Args:
        conn: DuckDB connection for writing outcomes.
        config: Governance configuration with stability check definitions.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        config: GovernanceConfig,
    ) -> None:
        self._conn = conn
        self._config = config
        self._actor_name, self._actor_email = self._get_git_actor()

    def _get_git_actor(self) -> tuple[str | None, str | None]:
        """Retrieve git user.name and user.email from local config.

        Returns (None, None) on any error (no git, no config set, etc).
        """
        try:
            name_result = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            email_result = subprocess.run(
                ["git", "config", "user.email"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return (
                name_result.stdout.strip() if name_result.returncode == 0 else None,
                email_result.stdout.strip() if email_result.returncode == 0 else None,
            )
        except Exception:
            return (None, None)

    def run_checks(
        self,
        repo_root: str | Path,
        session_id: str | None = None,
    ) -> list[StabilityOutcome]:
        """Execute all configured stability checks.

        For each check in config.stability_checks:
        1. Runs the command via subprocess with the configured timeout.
        2. Captures exit code, stdout, stderr.
        3. Determines status: pass (rc=0), fail (rc!=0), error (exception).
        4. Truncates stdout/stderr to 10000 chars to prevent storage bloat.
        5. Writes all outcomes to the stability_outcomes DuckDB table.

        Args:
            repo_root: Working directory for command execution.
            session_id: Optional session ID to associate with outcomes.

        Returns:
            List of StabilityOutcome for each configured check.
        """
        outcomes: list[StabilityOutcome] = []

        for check in self._config.stability_checks:
            run_id = str(uuid.uuid4())
            started_at = datetime.now(timezone.utc).isoformat()

            try:
                result = subprocess.run(
                    check.command,
                    capture_output=True,
                    text=True,
                    timeout=check.timeout_seconds,
                    cwd=str(repo_root),
                )
                ended_at = datetime.now(timezone.utc).isoformat()
                status = "pass" if result.returncode == 0 else "fail"
                exit_code = result.returncode
                stdout = result.stdout[:10000]
                stderr = result.stderr[:10000]
            except subprocess.TimeoutExpired:
                ended_at = datetime.now(timezone.utc).isoformat()
                status = "error"
                exit_code = -1
                stdout = ""
                stderr = f"Timeout after {check.timeout_seconds}s"
            except Exception as e:
                ended_at = datetime.now(timezone.utc).isoformat()
                status = "error"
                exit_code = -1
                stdout = ""
                stderr = str(e)

            outcome = StabilityOutcome(
                run_id=run_id,
                check_id=check.id,
                status=status,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                ended_at=ended_at,
                session_id=session_id,
                actor_name=self._actor_name,
                actor_email=self._actor_email,
            )
            outcomes.append(outcome)

        # Write all outcomes to DuckDB
        for o in outcomes:
            self._conn.execute(
                "INSERT INTO stability_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    o.run_id,
                    o.check_id,
                    o.session_id,
                    o.status,
                    o.exit_code,
                    o.stdout,
                    o.stderr,
                    o.started_at,
                    o.ended_at,
                    o.actor_name,
                    o.actor_email,
                ],
            )

        return outcomes

    def flag_missing_validation(
        self, conn: duckdb.DuckDBPyConnection | None = None
    ) -> int:
        """Flag episodes that require stability checks but have none.

        Updates episodes where requires_stability_check=TRUE and
        stability_check_status is NULL, setting status to 'missing'.

        Args:
            conn: Optional alternate connection (defaults to instance conn).

        Returns:
            Count of episodes flagged as 'missing'.
        """
        c = conn if conn is not None else self._conn
        count = c.execute(
            """
            SELECT COUNT(*) FROM episodes
            WHERE requires_stability_check = TRUE
              AND stability_check_status IS NULL
            """
        ).fetchone()[0]
        c.execute(
            """
            UPDATE episodes
            SET stability_check_status = 'missing'
            WHERE requires_stability_check = TRUE
              AND stability_check_status IS NULL
            """
        )
        return count

    def mark_validated(
        self, conn: duckdb.DuckDBPyConnection | None = None
    ) -> int:
        """Mark flagged episodes as validated after checks pass.

        Updates episodes where requires_stability_check=TRUE and
        stability_check_status is NULL or 'missing', setting to 'validated'.

        Args:
            conn: Optional alternate connection (defaults to instance conn).

        Returns:
            Count of episodes marked as 'validated'.
        """
        c = conn if conn is not None else self._conn
        count = c.execute(
            """
            SELECT COUNT(*) FROM episodes
            WHERE requires_stability_check = TRUE
              AND (stability_check_status IS NULL OR stability_check_status = 'missing')
            """
        ).fetchone()[0]
        c.execute(
            """
            UPDATE episodes
            SET stability_check_status = 'validated'
            WHERE requires_stability_check = TRUE
              AND (stability_check_status IS NULL OR stability_check_status = 'missing')
            """
        )
        return count
