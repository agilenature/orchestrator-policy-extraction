"""DuckDB schema for structural integrity detection (Phase 18).

Defines DDL for:
- structural_events: stores bridge-warden structural integrity signals
  with CHECK constraints on subject, signal_type, and op8_status

Exports:
    STRUCTURAL_EVENTS_DDL
    STRUCTURAL_EVENTS_INDEXES
    create_structural_schema
"""

from __future__ import annotations

import duckdb


STRUCTURAL_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS structural_events (
    event_id                    VARCHAR PRIMARY KEY,
    session_id                  VARCHAR NOT NULL,
    assessment_session_id       VARCHAR,
    prompt_number               INTEGER NOT NULL,
    subject                     VARCHAR NOT NULL
                                CHECK (subject IN ('human', 'ai')),
    signal_type                 VARCHAR NOT NULL
                                CHECK (signal_type IN (
                                    'gravity_check', 'main_cable',
                                    'dependency_sequencing', 'spiral_reinforcement'
                                )),
    structural_role             VARCHAR,
    evidence                    VARCHAR,
    signal_passed               BOOLEAN NOT NULL,
    score_contribution          FLOAT,
    contributing_flame_event_ids VARCHAR[],
    op8_status                  VARCHAR
                                CHECK (op8_status IN ('pass', 'fail', 'na')
                                       OR op8_status IS NULL),
    op8_correction_candidate_id VARCHAR,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
)
"""

STRUCTURAL_EVENTS_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_structural_session ON structural_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_structural_signal ON structural_events(signal_type)",
    "CREATE INDEX IF NOT EXISTS idx_structural_subject ON structural_events(subject)",
]


def create_structural_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create structural integrity tables and indexes.

    Uses CREATE TABLE IF NOT EXISTS so this is safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    conn.execute(STRUCTURAL_EVENTS_DDL)

    for idx_sql in STRUCTURAL_EVENTS_INDEXES:
        conn.execute(idx_sql)
