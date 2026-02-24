"""Transport Efficiency schema and memory_candidates TE extensions.

Defines DDL for:
- transport_efficiency_sessions: per-session TE scores for human and AI subjects
- memory_candidates TE extensions: pre_te_avg, post_te_avg, te_delta columns
- memory_candidates review extensions: confidence, subject, session_id columns
  (required by the memory-review CLI for candidate display and filtering)

The transport_efficiency_sessions table stores per-session Transport Efficiency
scores, decomposed into four sub-metrics: raven_depth, crow_efficiency,
transport_speed, and trunk_quality. The composite_te is a weighted aggregate.
trunk_quality_status tracks whether the trunk quality has been human-confirmed.

Exports:
    TRANSPORT_EFFICIENCY_DDL
    TRANSPORT_EFFICIENCY_INDEXES
    MEMORY_CANDIDATES_TE_EXTENSIONS
    MEMORY_CANDIDATES_REVIEW_EXTENSIONS
    create_te_schema
"""

from __future__ import annotations

import duckdb


TRANSPORT_EFFICIENCY_DDL = """
CREATE TABLE IF NOT EXISTS transport_efficiency_sessions (
    te_id                VARCHAR PRIMARY KEY,
    session_id           VARCHAR NOT NULL,
    human_id             VARCHAR,
    subject              VARCHAR NOT NULL CHECK (subject IN ('human', 'ai')),
    raven_depth          FLOAT,
    crow_efficiency      FLOAT,
    transport_speed      FLOAT,
    trunk_quality        FLOAT,
    composite_te         FLOAT,
    trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending'
                         CHECK (trunk_quality_status IN ('pending', 'confirmed')),
    fringe_drift_rate    FLOAT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
)
"""

TRANSPORT_EFFICIENCY_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_te_session ON transport_efficiency_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_te_subject ON transport_efficiency_sessions(subject)",
]

# ALTER TABLE extensions for memory_candidates (Phase 16 TE delta tracking)
# Each tuple: (column_name, column_definition)
MEMORY_CANDIDATES_TE_EXTENSIONS: list[tuple[str, str]] = [
    ("pre_te_avg", "FLOAT"),
    ("post_te_avg", "FLOAT"),
    ("te_delta", "FLOAT"),
]

# ALTER TABLE extensions for memory_candidates (review CLI support)
# These columns are required by the memory-review CLI for candidate display.
# Added here because they are not in the base memory_candidates DDL but are
# needed for the deposit-to-review workflow.
MEMORY_CANDIDATES_REVIEW_EXTENSIONS: list[tuple[str, str]] = [
    ("confidence", "FLOAT"),
    ("subject", "VARCHAR"),
    ("session_id", "VARCHAR"),
]


def create_te_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create Transport Efficiency tables, indexes, and memory_candidates extensions.

    Must be called after create_ddf_schema() base tables are created
    (memory_candidates must exist for ALTER TABLE).

    Uses CREATE TABLE IF NOT EXISTS and try/except for ALTER TABLE,
    matching the idempotent pattern from src/pipeline/ddf/schema.py.

    Safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    # Create transport_efficiency_sessions table
    conn.execute(TRANSPORT_EFFICIENCY_DDL)

    # Create indexes on transport_efficiency_sessions
    for idx_sql in TRANSPORT_EFFICIENCY_INDEXES:
        conn.execute(idx_sql)

    # Extend memory_candidates with TE delta columns (idempotent)
    for col_name, col_def in MEMORY_CANDIDATES_TE_EXTENSIONS:
        try:
            conn.execute(
                f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # Column already exists (idempotent)

    # Extend memory_candidates with review CLI columns (idempotent)
    for col_name, col_def in MEMORY_CANDIDATES_REVIEW_EXTENSIONS:
        try:
            conn.execute(
                f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # Column already exists (idempotent)
