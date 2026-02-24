"""DuckDB schema for the Candidate Assessment System (Phase 17).

Defines DDL for:
- assessment_te_sessions: per-assessment TE scores for candidates
- assessment_baselines: per-scenario baseline statistics
- ALTER TABLE extensions for memory_candidates, flame_events, project_wisdom

The assessment_te_sessions table stores per-assessment Transport Efficiency
scores for candidates evaluated against specific scenarios. Each row captures
the candidate's TE metrics during a controlled assessment session.

The assessment_baselines table tracks per-scenario statistics used to
normalize candidate scores against the population.

ALTER TABLE extensions add:
- memory_candidates.source_type: distinguishes production vs assessment data
- flame_events.assessment_session_id: links flame events to assessment sessions
- project_wisdom.scenario_seed: seed text for scenario generation
- project_wisdom.ddf_target_level: target DDF level for assessment scenarios

Exports:
    ASSESSMENT_TE_SESSIONS_DDL
    ASSESSMENT_BASELINES_DDL
    ASSESSMENT_TE_INDEXES
    ASSESSMENT_ALTER_EXTENSIONS
    create_assessment_schema
"""

from __future__ import annotations

import duckdb


ASSESSMENT_TE_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS assessment_te_sessions (
    te_id                VARCHAR PRIMARY KEY,
    session_id           VARCHAR NOT NULL,
    scenario_id          VARCHAR NOT NULL,
    candidate_id         VARCHAR NOT NULL,
    candidate_te         FLOAT,
    scenario_baseline_te FLOAT,
    candidate_ratio      FLOAT,
    raven_depth          FLOAT,
    crow_efficiency      FLOAT,
    trunk_quality        FLOAT,
    trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending'
                         CHECK (trunk_quality_status IN ('pending', 'confirmed')),
    fringe_drift_rate    FLOAT,
    scenario_ddf_level   INTEGER,
    session_artifact_path VARCHAR,
    assessment_date      TIMESTAMPTZ DEFAULT NOW()
)
"""

ASSESSMENT_BASELINES_DDL = """
CREATE TABLE IF NOT EXISTS assessment_baselines (
    scenario_id    VARCHAR PRIMARY KEY,
    n_assessments  INTEGER NOT NULL DEFAULT 0,
    mean_ratio     FLOAT,
    stddev_ratio   FLOAT,
    last_updated   TIMESTAMPTZ DEFAULT NOW()
)
"""

ASSESSMENT_TE_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_assess_te_session ON assessment_te_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_assess_te_scenario ON assessment_te_sessions(scenario_id)",
    "CREATE INDEX IF NOT EXISTS idx_assess_te_candidate ON assessment_te_sessions(candidate_id)",
]

# ALTER TABLE extensions for existing tables (Phase 17)
# Each tuple: (table_name, column_name, column_definition)
# NOTE: No CHECK constraint on source_type -- DuckDB ALTER TABLE limitation.
# Validation is enforced in Pydantic models (AssessmentReport.source_type).
ASSESSMENT_ALTER_EXTENSIONS: list[tuple[str, str, str]] = [
    ("memory_candidates", "source_type", "VARCHAR DEFAULT 'production'"),
    ("flame_events", "assessment_session_id", "VARCHAR"),
    ("project_wisdom", "scenario_seed", "TEXT"),
    ("project_wisdom", "ddf_target_level", "INTEGER"),
]


def create_assessment_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create Candidate Assessment System tables, indexes, and extensions.

    Must be called after create_te_schema() to ensure flame_events and
    memory_candidates exist before ALTER TABLE extensions. Called at the
    end of create_ddf_schema() in the schema chain.

    Uses CREATE TABLE IF NOT EXISTS and try/except for ALTER TABLE,
    matching the idempotent pattern from src/pipeline/ddf/schema.py.

    Safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    # Create assessment_te_sessions table
    conn.execute(ASSESSMENT_TE_SESSIONS_DDL)

    # Create assessment_baselines table
    conn.execute(ASSESSMENT_BASELINES_DDL)

    # Create indexes on assessment_te_sessions
    for idx_sql in ASSESSMENT_TE_INDEXES:
        conn.execute(idx_sql)

    # Extend existing tables with assessment columns (idempotent)
    for table_name, col_name, col_def in ASSESSMENT_ALTER_EXTENSIONS:
        try:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # Column already exists (idempotent)
