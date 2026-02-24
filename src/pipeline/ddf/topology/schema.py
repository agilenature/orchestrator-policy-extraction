"""DuckDB schema for topological edge-generation (Phase 16.1).

Defines DDL for:
- axis_edges: first-class knowledge artifact storing CCD axis relationships
  with mandatory activation_condition and evidence pointers

The axis_edges table is the terminal deposit target for the topology
sub-system. Every edge carries an activation_condition (structurally
prohibited from null/empty) and evidence grounding.

Exports:
    AXIS_EDGES_DDL
    AXIS_EDGES_INDEXES
    create_topology_schema
"""

from __future__ import annotations

import duckdb


AXIS_EDGES_DDL = """
CREATE TABLE IF NOT EXISTS axis_edges (
    edge_id             VARCHAR PRIMARY KEY,
    axis_a              VARCHAR NOT NULL,
    axis_b              VARCHAR NOT NULL,
    relationship_text   TEXT NOT NULL,
    activation_condition JSON NOT NULL,
    evidence            JSON NOT NULL,
    abstraction_level   INTEGER NOT NULL,
    status              VARCHAR NOT NULL DEFAULT 'candidate'
                        CHECK (status IN ('candidate', 'active', 'superseded')),
    trunk_quality       FLOAT NOT NULL DEFAULT 1.0,
    created_session_id  VARCHAR NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
)
"""

AXIS_EDGES_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_edges_axis_a ON axis_edges(axis_a)",
    "CREATE INDEX IF NOT EXISTS idx_edges_axis_b ON axis_edges(axis_b)",
    "CREATE INDEX IF NOT EXISTS idx_edges_status ON axis_edges(status)",
    "CREATE INDEX IF NOT EXISTS idx_edges_session ON axis_edges(created_session_id)",
]


def create_topology_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create topological edge-generation tables and indexes.

    Uses CREATE TABLE IF NOT EXISTS so this is safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    conn.execute(AXIS_EDGES_DDL)

    for idx_sql in AXIS_EDGES_INDEXES:
        conn.execute(idx_sql)
