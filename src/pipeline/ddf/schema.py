"""DuckDB schema for the DDF Detection Substrate (Phase 15).

Defines DDL for:
- flame_events: unified table for both human and AI flame markers
- ai_flame_events: convenience view filtering subject='ai'
- axis_hypotheses: candidate CCD axis identifications
- constraint_metrics: constraint radius/stagnation tracking
- memory_candidates extension: source_flame_event_id, fidelity, detection_count

The flame_events table stores DDF markers at all levels (0-7) for both
human and AI subjects. The subject column distinguishes the two; the
ai_flame_events view provides backward-compatible access to AI-only rows.

Exports:
    FLAME_EVENTS_DDL
    AI_FLAME_EVENTS_VIEW_DDL
    AXIS_HYPOTHESES_DDL
    CONSTRAINT_METRICS_DDL
    MEMORY_CANDIDATES_EXTENSIONS
    create_ddf_schema
"""

from __future__ import annotations

import duckdb


FLAME_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS flame_events (
    flame_event_id         VARCHAR PRIMARY KEY,
    session_id             VARCHAR NOT NULL,
    human_id               VARCHAR,
    prompt_number          INTEGER,
    marker_level           INTEGER NOT NULL,
    marker_type            VARCHAR NOT NULL,
    evidence_excerpt       TEXT,
    quality_score          FLOAT,
    axis_identified        VARCHAR,
    flood_confirmed        BOOLEAN DEFAULT FALSE,
    subject                VARCHAR NOT NULL DEFAULT 'human'
                           CHECK (subject IN ('human', 'ai')),
    detection_source       VARCHAR NOT NULL DEFAULT 'stub'
                           CHECK (detection_source IN ('stub', 'opeml')),
    deposited_to_candidates BOOLEAN DEFAULT FALSE,
    source_episode_id      VARCHAR,
    session_event_ref      VARCHAR,
    created_at             TIMESTAMPTZ DEFAULT NOW()
)
"""

FLAME_EVENTS_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_flame_session ON flame_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_flame_level ON flame_events(marker_level)",
    "CREATE INDEX IF NOT EXISTS idx_flame_subject ON flame_events(subject)",
    "CREATE INDEX IF NOT EXISTS idx_flame_marker_type ON flame_events(marker_type)",
]

AI_FLAME_EVENTS_VIEW_DDL = """
CREATE OR REPLACE VIEW ai_flame_events AS
SELECT * FROM flame_events WHERE subject = 'ai'
"""

AXIS_HYPOTHESES_DDL = """
CREATE TABLE IF NOT EXISTS axis_hypotheses (
    hypothesis_id      VARCHAR PRIMARY KEY,
    session_id         VARCHAR NOT NULL,
    episode_id         VARCHAR,
    hypothesized_axis  VARCHAR NOT NULL,
    confidence         FLOAT NOT NULL,
    marker_type        VARCHAR NOT NULL DEFAULT 'false_integration',
    evidence           TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW()
)
"""

CONSTRAINT_METRICS_DDL = """
CREATE TABLE IF NOT EXISTS constraint_metrics (
    constraint_id  VARCHAR PRIMARY KEY,
    radius         INTEGER NOT NULL DEFAULT 0,
    firing_count   INTEGER NOT NULL DEFAULT 0,
    is_stagnant    BOOLEAN DEFAULT FALSE,
    last_computed  TIMESTAMPTZ DEFAULT NOW()
)
"""

# ALTER TABLE extensions for memory_candidates (Phase 15)
# Each tuple: (column_name, column_definition)
MEMORY_CANDIDATES_EXTENSIONS: list[tuple[str, str]] = [
    ("source_flame_event_id", "VARCHAR"),
    ("fidelity", "INTEGER DEFAULT 2"),
    ("detection_count", "INTEGER DEFAULT 1"),
]


def create_ddf_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create DDF Detection Substrate tables, views, and indexes.

    Must be called after create_review_schema() to ensure memory_candidates
    exists before ALTER TABLE extensions. Calls create_review_schema()
    internally as a safety measure.

    Uses CREATE TABLE IF NOT EXISTS and try/except for ALTER TABLE,
    matching the idempotent pattern from src/pipeline/storage/schema.py.

    Safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    # Ensure memory_candidates exists before ALTER TABLE
    from src.pipeline.review.schema import create_review_schema

    create_review_schema(conn)

    # Create flame_events table
    conn.execute(FLAME_EVENTS_DDL)

    # Create indexes on flame_events
    for idx_sql in FLAME_EVENTS_INDEXES:
        conn.execute(idx_sql)

    # Create ai_flame_events convenience view
    conn.execute(AI_FLAME_EVENTS_VIEW_DDL)

    # Create axis_hypotheses table
    conn.execute(AXIS_HYPOTHESES_DDL)

    # Create constraint_metrics table
    conn.execute(CONSTRAINT_METRICS_DDL)

    # Extend memory_candidates with DDF columns (idempotent)
    for col_name, col_def in MEMORY_CANDIDATES_EXTENSIONS:
        try:
            conn.execute(
                f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # Column already exists (idempotent)

    # Phase 16.1: Topological edge-generation tables
    from src.pipeline.ddf.topology.schema import create_topology_schema

    create_topology_schema(conn)

    # Phase 16: Transport Efficiency tables + memory_candidates TE extensions
    from src.pipeline.ddf.transport_efficiency import create_te_schema

    create_te_schema(conn)

    # Phase 17: Assessment tables + extensions
    from src.pipeline.assessment.schema import create_assessment_schema

    create_assessment_schema(conn)

    # Phase 18: Structural Integrity tables
    from src.pipeline.ddf.structural.schema import create_structural_schema

    create_structural_schema(conn)
