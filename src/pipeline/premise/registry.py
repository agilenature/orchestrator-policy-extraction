"""PremiseRegistry DuckDB CRUD operations.

Provides create, read, update, and query operations for the premise_registry
table. All methods use parameterized queries (no f-string SQL). JSON columns
are inserted as json.dumps() strings.

Does NOT call create_premise_schema in __init__ -- caller's responsibility
(matching project pattern where create_schema() is called once in runner init).

Exports:
    PremiseRegistry: DuckDB CRUD for premise_registry table
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb

from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.schema import PARENT_EPISODE_BACKFILL_SQL


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _json_or_none(val: dict | list | None) -> str | None:
    """Serialize a dict/list to JSON string, or return None."""
    if val is None:
        return None
    return json.dumps(val)


class PremiseRegistry:
    """DuckDB CRUD operations for the premise_registry table.

    Provides register, get, update, stain, and query methods for
    premise records. Does NOT call create_premise_schema -- caller's
    responsibility (matching project pattern where create_schema()
    is called once in runner init).

    Args:
        conn: DuckDB connection with premise_registry table created.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def register(self, record: PremiseRecord) -> str:
        """Insert or replace a premise record in the registry.

        Uses INSERT OR REPLACE for idempotent upserts on premise_id.

        Args:
            record: PremiseRecord to register.

        Returns:
            The premise_id of the registered record.
        """
        now = _now_iso()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO premise_registry (
                premise_id, claim, validated_by, validation_context,
                foil, distinguishing_prop, staleness_counter,
                staining_record, ground_truth_pointer, project_scope,
                session_id, tool_use_id, foil_path_outcomes,
                divergence_patterns, parent_episode_links,
                derivation_depth, validation_calls_before_claim,
                derivation_chain, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.premise_id,
                record.claim,
                record.validated_by,
                record.validation_context,
                record.foil,
                record.distinguishing_prop,
                record.staleness_counter,
                _json_or_none(record.staining_record),
                _json_or_none(record.ground_truth_pointer),
                record.project_scope,
                record.session_id,
                record.tool_use_id,
                _json_or_none(record.foil_path_outcomes),
                _json_or_none(record.divergence_patterns),
                _json_or_none(record.parent_episode_links),
                record.derivation_depth,
                record.validation_calls_before_claim,
                _json_or_none(record.derivation_chain),
                record.created_at or now,
                record.updated_at or now,
            ],
        )
        return record.premise_id

    def get(self, premise_id: str) -> PremiseRecord | None:
        """Get a premise record by premise_id.

        Args:
            premise_id: The premise ID to look up.

        Returns:
            PremiseRecord if found, None otherwise.
        """
        row = self._conn.execute(
            "SELECT * FROM premise_registry WHERE premise_id = ?",
            [premise_id],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def get_by_session(self, session_id: str) -> list[PremiseRecord]:
        """Get all premises for a session, ordered by created_at.

        Args:
            session_id: Session ID to filter by.

        Returns:
            List of PremiseRecord instances ordered by creation time.
        """
        rows = self._conn.execute(
            "SELECT * FROM premise_registry WHERE session_id = ? ORDER BY created_at",
            [session_id],
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_stained(
        self, project_scope: str | None = None
    ) -> list[PremiseRecord]:
        """Get all stained premises, optionally filtered by project scope.

        A premise is stained when its staining_record contains
        {"stained": true}.

        Args:
            project_scope: Optional project path to filter by.

        Returns:
            List of stained PremiseRecord instances.
        """
        if project_scope is not None:
            rows = self._conn.execute(
                "SELECT * FROM premise_registry "
                "WHERE json_extract_string(staining_record, '$.stained') = 'true' "
                "AND project_scope = ?",
                [project_scope],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM premise_registry "
                "WHERE json_extract_string(staining_record, '$.stained') = 'true'",
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_staleness(self, premise_id: str) -> None:
        """Increment the staleness counter for a premise.

        Called when a premise is reused across sessions without
        revalidation.

        Args:
            premise_id: The premise ID to update.
        """
        self._conn.execute(
            "UPDATE premise_registry "
            "SET staleness_counter = staleness_counter + 1, updated_at = ? "
            "WHERE premise_id = ?",
            [_now_iso(), premise_id],
        )

    def stain(
        self,
        premise_id: str,
        stained_by: str,
        ground_truth_pointer: dict,
    ) -> None:
        """Mark a premise as stained (invalidated by retrospective analysis).

        Sets the staining_record JSON to indicate the premise has been
        invalidated, who/what invalidated it, and the ground truth pointer.

        Args:
            premise_id: The premise ID to stain.
            stained_by: Identifier of what caused the staining (e.g., amnesia_id).
            ground_truth_pointer: Dict pointing to the ground truth evidence.
        """
        staining = {
            "stained": True,
            "stained_by": stained_by,
            "stained_at": _now_iso(),
            "ground_truth_pointer": ground_truth_pointer,
        }
        self._conn.execute(
            "UPDATE premise_registry "
            "SET staining_record = ?, updated_at = ? "
            "WHERE premise_id = ?",
            [json.dumps(staining), _now_iso(), premise_id],
        )

    def find_by_foil(
        self,
        foil_text: str,
        project_scope: str | None = None,
        exclude_session: str | None = None,
        limit: int = 10,
    ) -> list[PremiseRecord]:
        """Find premises whose claim matches the given foil text.

        Used by the foil instantiation lookup (Plan 03) to find historical
        episodes where the foil was the active premise.

        Args:
            foil_text: Text to match against premise claims (ILIKE).
            project_scope: Optional project path filter.
            exclude_session: Optional session ID to exclude from results.
            limit: Maximum number of results to return.

        Returns:
            List of matching PremiseRecord instances, ordered by created_at DESC.
        """
        conditions = ["claim ILIKE ?"]
        params: list = [f"%{foil_text}%"]

        if project_scope is not None:
            conditions.append("project_scope = ?")
            params.append(project_scope)

        if exclude_session is not None:
            conditions.append("session_id != ?")
            params.append(exclude_session)

        where = " AND ".join(conditions)
        params.append(limit)

        rows = self._conn.execute(
            f"SELECT * FROM premise_registry WHERE {where} "
            f"ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_derivation_depth(self, premise_id: str, depth: int) -> None:
        """Update the derivation_depth for a premise.

        Called during staging ingestion after computing chain length.

        Args:
            premise_id: The premise ID to update.
            depth: The computed derivation depth.
        """
        self._conn.execute(
            "UPDATE premise_registry "
            "SET derivation_depth = ?, updated_at = ? "
            "WHERE premise_id = ?",
            [depth, _now_iso(), premise_id],
        )

    def count(self) -> int:
        """Return the total number of premises in the registry.

        Returns:
            Total premise count.
        """
        result = self._conn.execute(
            "SELECT count(*) FROM premise_registry"
        ).fetchone()
        return result[0] if result else 0

    def backfill_parent_episodes(self) -> int:
        """Backfill parent_episode_id for existing episodes using LAG window.

        Assigns parent_episode_id based on temporal ordering within each
        session. The first episode in each session gets None; subsequent
        episodes point to the immediately preceding episode.

        Returns:
            Number of rows affected by the update.
        """
        result = self._conn.execute(PARENT_EPISODE_BACKFILL_SQL)
        # DuckDB execute() on UPDATE returns the connection, not row count.
        # Count episodes with parent_episode_id set to determine rows affected.
        count = self._conn.execute(
            "SELECT count(*) FROM episodes WHERE parent_episode_id IS NOT NULL"
        ).fetchone()
        return count[0] if count else 0

    def _row_to_record(self, row: tuple) -> PremiseRecord:
        """Convert a DuckDB row tuple to a PremiseRecord.

        Handles JSON column deserialization. DuckDB returns JSON columns
        as strings that need json.loads().

        Args:
            row: Tuple from a SELECT * query on premise_registry.

        Returns:
            PremiseRecord instance.
        """
        # Column order matches the DDL in schema.py
        columns = [
            "premise_id",
            "claim",
            "validated_by",
            "validation_context",
            "foil",
            "distinguishing_prop",
            "staleness_counter",
            "staining_record",
            "ground_truth_pointer",
            "project_scope",
            "session_id",
            "tool_use_id",
            "foil_path_outcomes",
            "divergence_patterns",
            "parent_episode_links",
            "derivation_depth",
            "validation_calls_before_claim",
            "derivation_chain",
            "created_at",
            "updated_at",
        ]
        d = dict(zip(columns, row))

        # Deserialize JSON columns
        json_cols = [
            "staining_record",
            "ground_truth_pointer",
            "foil_path_outcomes",
            "divergence_patterns",
            "parent_episode_links",
            "derivation_chain",
        ]
        for col in json_cols:
            val = d.get(col)
            if isinstance(val, str):
                try:
                    d[col] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Convert timestamps to ISO strings
        for ts_col in ("created_at", "updated_at"):
            val = d.get(ts_col)
            if val is not None and not isinstance(val, str):
                d[ts_col] = str(val)

        return PremiseRecord(**d)
