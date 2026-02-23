"""DuckDB schema DDL for the premise registry and episode causal links.

Defines:
- PREMISE_REGISTRY_DDL: CREATE TABLE for premise_registry (20 columns)
- PREMISE_REGISTRY_INDEXES: Three index creation statements
- EPISODES_PARENT_EPISODE_DDL: ALTER TABLE to add parent_episode_id
- EPISODES_PARENT_EPISODE_INDEX: Index on parent_episode_id
- PARENT_EPISODE_BACKFILL_SQL: LAG window function backfill query
- create_premise_schema: Apply all DDL to a DuckDB connection

The premise_registry table stores every PREMISE declaration seen across
sessions, with validation state, foil outcomes, staining records, and
derivation chain metadata. JSON columns use DuckDB's JSON type (not JSONB --
DuckDB has no JSONB type).

The parent_episode_id column on the episodes table links each episode to
the prior episode in the same session, enabling causal chain traversal
(PREMISE-05).

Exports:
    PREMISE_REGISTRY_DDL
    PREMISE_REGISTRY_INDEXES
    EPISODES_PARENT_EPISODE_DDL
    EPISODES_PARENT_EPISODE_INDEX
    PARENT_EPISODE_BACKFILL_SQL
    create_premise_schema
"""

from __future__ import annotations

import duckdb


PREMISE_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS premise_registry (
    premise_id                    VARCHAR PRIMARY KEY,
    claim                         TEXT NOT NULL,
    validated_by                  TEXT,
    validation_context            TEXT,
    foil                          TEXT,
    distinguishing_prop           TEXT,
    staleness_counter             INTEGER DEFAULT 0,
    staining_record               JSON,
    ground_truth_pointer          JSON,
    project_scope                 VARCHAR,
    session_id                    VARCHAR NOT NULL,
    tool_use_id                   VARCHAR,
    foil_path_outcomes            JSON,
    divergence_patterns           JSON,
    parent_episode_links          JSON,
    derivation_depth              INTEGER DEFAULT 0,
    validation_calls_before_claim INTEGER DEFAULT 0,
    derivation_chain              JSON,
    created_at                    TIMESTAMPTZ DEFAULT NOW(),
    updated_at                    TIMESTAMPTZ DEFAULT NOW()
)
"""

PREMISE_REGISTRY_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_premise_session ON premise_registry(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_premise_scope ON premise_registry(project_scope)",
    # Note: DuckDB does not support expression indexes on json_extract_string().
    # Stained premise queries use WHERE clause filtering on staining_record instead.
]

EPISODES_PARENT_EPISODE_DDL = "ALTER TABLE episodes ADD COLUMN parent_episode_id VARCHAR"

EPISODES_PARENT_EPISODE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_episodes_parent ON episodes(parent_episode_id)"
)

# Backfill query: assign parent_episode_id to existing episodes using
# LAG window function. Partitions by session_id, orders by timestamp
# with segment_id as tie-breaker for deterministic ordering.
PARENT_EPISODE_BACKFILL_SQL = """
WITH ordered AS (
    SELECT
        episode_id,
        session_id,
        timestamp,
        LAG(episode_id) OVER (
            PARTITION BY session_id
            ORDER BY timestamp, segment_id
        ) AS prev_id
    FROM episodes
)
UPDATE episodes
SET parent_episode_id = ordered.prev_id
FROM ordered
WHERE episodes.episode_id = ordered.episode_id
"""


def create_premise_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the premise_registry table, indexes, and episodes parent link.

    Uses CREATE TABLE IF NOT EXISTS and try/except for ALTER TABLE,
    matching the idempotent pattern from src/pipeline/storage/schema.py
    (Phase 9 escalation columns, Phase 12 governance columns).

    Safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    # Create premise_registry table
    conn.execute(PREMISE_REGISTRY_DDL)

    # Create indexes
    for idx_sql in PREMISE_REGISTRY_INDEXES:
        conn.execute(idx_sql)

    # Add parent_episode_id to episodes table (idempotent)
    try:
        conn.execute(EPISODES_PARENT_EPISODE_DDL)
    except Exception:
        pass  # Column already exists (idempotent)

    # Create index on parent_episode_id
    conn.execute(EPISODES_PARENT_EPISODE_INDEX)
