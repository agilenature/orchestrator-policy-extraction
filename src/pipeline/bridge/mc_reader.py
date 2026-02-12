"""DuckDB-SQLite bridge reader for Mission Control episodes.

Reads Mission Control's SQLite database using DuckDB's SQLite extension.
Provides zero-copy cross-database queries: MC writes to SQLite, the
Python analytics pipeline reads via DuckDB ATTACH.

Uses short-lived attach/query/detach cycles to avoid holding SQLite locks
(per research Pitfall 6 guidance).

Exports:
    MCBridgeReader
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import duckdb

from src.pipeline.models.episodes import Episode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MCBridgeReader:
    """Reads Mission Control's SQLite episode database via DuckDB.

    Usage as context manager (recommended -- auto attach/detach):

        with MCBridgeReader(mc_db_path, ope_conn) as reader:
            episodes = reader.import_episodes()

    Or manually:

        reader = MCBridgeReader(mc_db_path, ope_conn)
        reader.attach()
        episodes = reader.list_episodes()
        reader.detach()

    Args:
        mc_db_path: Path to Mission Control's SQLite database file.
        ope_conn: An existing DuckDB connection (the analytics pipeline DB).
    """

    def __init__(
        self,
        mc_db_path: str,
        ope_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        self._mc_db_path = mc_db_path
        self._conn = ope_conn
        self._attached = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> MCBridgeReader:
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.detach()

    # ------------------------------------------------------------------
    # Attach / Detach
    # ------------------------------------------------------------------

    def attach(self) -> None:
        """Attach Mission Control's SQLite database as schema 'mc'.

        Installs and loads the DuckDB SQLite extension if needed.
        Safe to call multiple times (idempotent).
        """
        if self._attached:
            return

        # Install/load the SQLite extension
        try:
            self._conn.execute("INSTALL sqlite; LOAD sqlite;")
        except Exception:
            # Extension may already be installed/loaded
            try:
                self._conn.execute("LOAD sqlite;")
            except Exception:
                pass

        self._conn.execute(
            f"ATTACH '{self._mc_db_path}' AS mc (TYPE sqlite)"
        )
        self._attached = True

    def detach(self) -> None:
        """Detach the Mission Control database.

        Safe to call multiple times (idempotent).
        """
        if not self._attached:
            return

        try:
            self._conn.execute("DETACH mc")
        except Exception:
            # Already detached or connection closed
            pass
        self._attached = False

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def list_episodes(
        self,
        status: str = "completed",
        has_reaction: bool = True,
    ) -> list[dict]:
        """Query episodes from MC's SQLite database.

        Parses JSON columns (observation, orchestrator_action, outcome,
        provenance, constraints_extracted, labels) via json.loads.

        Args:
            status: Filter by episode status. Default: 'completed'.
            has_reaction: If True, only return episodes with a reaction_label.

        Returns:
            List of episode dicts with parsed JSON fields.
        """
        self._ensure_attached()

        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if has_reaction:
            conditions.append("reaction_label IS NOT NULL")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = self._conn.execute(
            f"""
            SELECT
                episode_id, task_id, session_id, timestamp,
                mode, risk, reaction_label, reaction_confidence, status,
                observation, orchestrator_action, outcome,
                provenance, constraints_extracted, labels,
                project_repo_path, project_branch, project_commit_head,
                phase, schema_version, created_at, updated_at
            FROM mc.episodes
            {where}
            ORDER BY timestamp DESC
            """,
            params,
        ).fetchall()

        columns = [
            "episode_id", "task_id", "session_id", "timestamp",
            "mode", "risk", "reaction_label", "reaction_confidence", "status",
            "observation", "orchestrator_action", "outcome",
            "provenance", "constraints_extracted", "labels",
            "project_repo_path", "project_branch", "project_commit_head",
            "phase", "schema_version", "created_at", "updated_at",
        ]

        json_columns = {
            "observation", "orchestrator_action", "outcome",
            "provenance", "constraints_extracted", "labels",
        }

        result = []
        for row in rows:
            episode = {}
            for i, col in enumerate(columns):
                val = row[i]
                if col in json_columns and val is not None:
                    try:
                        val = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
                episode[col] = val
            result.append(episode)

        return result

    def import_episodes(self) -> list[Episode]:
        """Import completed episodes with reactions as Pydantic Episode models.

        Reads from MC's SQLite database, validates each against the
        Pydantic Episode model. Invalid episodes are logged as warnings
        but not raised.

        Returns:
            List of validated Episode instances.
        """
        self._ensure_attached()

        raw_episodes = self.list_episodes(status="completed", has_reaction=True)
        validated: list[Episode] = []

        for raw in raw_episodes:
            try:
                ep = Episode(
                    episode_id=raw["episode_id"],
                    timestamp=raw["timestamp"],
                    project={
                        "repo_path": raw.get("project_repo_path") or "",
                        "branch": raw.get("project_branch"),
                        "commit_head": raw.get("project_commit_head"),
                    },
                    observation=raw.get("observation"),
                    orchestrator_action=raw.get("orchestrator_action"),
                    outcome=raw.get("outcome"),
                    provenance=raw.get("provenance") or {
                        "sources": [
                            {
                                "type": "claude_jsonl",
                                "ref": f"mc:task:{raw.get('task_id', 'unknown')}",
                            }
                        ]
                    },
                    task_id=raw.get("task_id"),
                    phase=raw.get("phase"),
                    constraints_extracted=raw.get("constraints_extracted") or [],
                    labels=raw.get("labels"),
                )
                validated.append(ep)
            except Exception as e:
                logger.warning(
                    "Episode %s failed Pydantic validation: %s",
                    raw.get("episode_id", "unknown"),
                    e,
                )

        return validated

    def get_episode_events(self, episode_id: str) -> list[dict]:
        """Get all events for a given episode from MC's SQLite database.

        Parses the JSON payload column for each event.

        Args:
            episode_id: The episode ID to query events for.

        Returns:
            List of event dicts with parsed payload.
        """
        self._ensure_attached()

        rows = self._conn.execute(
            """
            SELECT event_id, episode_id, timestamp, received_at,
                   event_type, payload
            FROM mc.episode_events
            WHERE episode_id = ?
            ORDER BY timestamp ASC
            """,
            [episode_id],
        ).fetchall()

        columns = [
            "event_id", "episode_id", "timestamp", "received_at",
            "event_type", "payload",
        ]

        result = []
        for row in rows:
            event = {}
            for i, col in enumerate(columns):
                val = row[i]
                if col == "payload" and val is not None:
                    try:
                        val = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
                event[col] = val
            result.append(event)

        return result

    def get_constraints(self) -> list[dict]:
        """Get all constraints from MC's SQLite database.

        Parses JSON array columns (scope_paths, detection_hints, examples).

        Returns:
            List of constraint dicts with parsed JSON arrays.
        """
        self._ensure_attached()

        rows = self._conn.execute(
            """
            SELECT constraint_id, text, severity, scope_paths,
                   detection_hints, source_episode_id,
                   source_reaction_label, examples, created_at
            FROM mc.constraints
            ORDER BY created_at DESC
            """,
        ).fetchall()

        columns = [
            "constraint_id", "text", "severity", "scope_paths",
            "detection_hints", "source_episode_id",
            "source_reaction_label", "examples", "created_at",
        ]

        json_columns = {"scope_paths", "detection_hints", "examples"}

        result = []
        for row in rows:
            constraint = {}
            for i, col in enumerate(columns):
                val = row[i]
                if col in json_columns and val is not None:
                    try:
                        val = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
                constraint[col] = val
            result.append(constraint)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_attached(self) -> None:
        """Raise if the MC database is not attached."""
        if not self._attached:
            raise RuntimeError(
                "MC database not attached. Call attach() or use as context manager."
            )
