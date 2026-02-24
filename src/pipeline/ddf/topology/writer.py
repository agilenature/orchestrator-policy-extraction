"""DuckDB writer for axis_edges table (Phase 16.1).

Writes EdgeRecord Pydantic models to the DuckDB axis_edges table
using INSERT OR REPLACE for idempotent writes. Enforces activation_condition
non-emptiness at write time.

Provides degradation and retirement operations for edge lifecycle
management: edges degrade as their trunk_quality decreases, and
retire (status='superseded') when quality falls below threshold.

Exports:
    EdgeWriter
"""

from __future__ import annotations

import json

import duckdb

from src.pipeline.ddf.topology.models import EdgeRecord


class EdgeWriter:
    """Writer for axis_edges table with lifecycle management.

    Handles CRUD operations on CCD axis edges including:
    - Idempotent writes (INSERT OR REPLACE)
    - Activation condition enforcement at write boundary
    - Quality degradation and automatic retirement

    Args:
        conn: DuckDB connection with axis_edges table created.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def write_edge(self, edge: EdgeRecord) -> dict[str, int]:
        """Write an EdgeRecord to axis_edges table.

        Uses INSERT OR REPLACE for idempotent writes -- re-inserting an
        edge with the same edge_id overwrites the existing row.

        Validates activation_condition is not empty at write time. The
        ActivationCondition model ensures structural validity; this check
        prevents serialization to an empty JSON object.

        Args:
            edge: EdgeRecord Pydantic model to write.

        Returns:
            Dict with 'written' key indicating number of edges processed.

        Raises:
            ValueError: If activation_condition serializes to empty/null.
        """
        ac_dict = edge.activation_condition.model_dump()
        if not ac_dict:
            raise ValueError(
                "activation_condition must not be empty -- "
                "EdgeRecord requires a valid ActivationCondition"
            )

        self._conn.execute(
            """
            INSERT OR REPLACE INTO axis_edges (
                edge_id, axis_a, axis_b, relationship_text,
                activation_condition, evidence, abstraction_level,
                status, trunk_quality, created_session_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                edge.edge_id,
                edge.axis_a,
                edge.axis_b,
                edge.relationship_text,
                json.dumps(ac_dict),
                json.dumps(edge.evidence),
                edge.abstraction_level,
                edge.status,
                edge.trunk_quality,
                edge.created_session_id,
                edge.created_at.isoformat() if edge.created_at else None,
            ],
        )

        return {"written": 1}

    def degrade_edge(self, edge_id: str, amount: float) -> float:
        """Decrement trunk_quality for an edge.

        Clamps the result to [0.0, 1.0].

        Args:
            edge_id: The edge to degrade.
            amount: Amount to subtract from trunk_quality.

        Returns:
            New trunk_quality value after degradation.

        Raises:
            ValueError: If edge_id not found.
        """
        row = self._conn.execute(
            "SELECT trunk_quality FROM axis_edges WHERE edge_id = ?",
            [edge_id],
        ).fetchone()

        if row is None:
            raise ValueError(f"Edge not found: {edge_id}")

        new_quality = max(0.0, row[0] - amount)
        self._conn.execute(
            "UPDATE axis_edges SET trunk_quality = ? WHERE edge_id = ?",
            [new_quality, edge_id],
        )

        return new_quality

    def retire_edge(self, edge_id: str) -> None:
        """Set an edge's status to 'superseded'.

        Args:
            edge_id: The edge to retire.

        Raises:
            ValueError: If edge_id not found.
        """
        row = self._conn.execute(
            "SELECT edge_id FROM axis_edges WHERE edge_id = ?",
            [edge_id],
        ).fetchone()

        if row is None:
            raise ValueError(f"Edge not found: {edge_id}")

        self._conn.execute(
            "UPDATE axis_edges SET status = 'superseded' WHERE edge_id = ?",
            [edge_id],
        )

    def degrade_and_maybe_retire(
        self,
        edge_id: str,
        amount: float,
        threshold: float = 0.3,
    ) -> tuple[float, bool]:
        """Degrade trunk_quality and auto-retire if below threshold.

        Combines degrade_edge and retire_edge into a single operation.

        Args:
            edge_id: The edge to degrade.
            amount: Amount to subtract from trunk_quality.
            threshold: Quality below which edge is retired. Default 0.3.

        Returns:
            Tuple of (new_quality, was_retired).
        """
        new_quality = self.degrade_edge(edge_id, amount)
        retired = False

        if new_quality < threshold:
            self.retire_edge(edge_id)
            retired = True

        return new_quality, retired

    def find_edges_for_axis_pair(
        self,
        axis_a: str,
        axis_b: str,
        status: str = "active",
    ) -> list[dict]:
        """Find edges connecting two axes in either direction.

        Searches for edges where (axis_a, axis_b) matches in either
        order, filtered by status.

        Args:
            axis_a: First axis name.
            axis_b: Second axis name.
            status: Edge status to filter by. Default 'active'.

        Returns:
            List of edge rows as dicts.
        """
        rows = self._conn.execute(
            """
            SELECT edge_id, axis_a, axis_b, relationship_text,
                   activation_condition, evidence, abstraction_level,
                   status, trunk_quality, created_session_id, created_at
            FROM axis_edges
            WHERE status = ?
              AND (
                  (axis_a = ? AND axis_b = ?)
                  OR (axis_a = ? AND axis_b = ?)
              )
            """,
            [status, axis_a, axis_b, axis_b, axis_a],
        ).fetchall()

        columns = [
            "edge_id", "axis_a", "axis_b", "relationship_text",
            "activation_condition", "evidence", "abstraction_level",
            "status", "trunk_quality", "created_session_id", "created_at",
        ]

        return [dict(zip(columns, row)) for row in rows]
