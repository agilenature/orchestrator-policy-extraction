"""DuckDB schema creation and connection management.

Creates the events, episode_segments, episodes, episode_search_text,
episode_embeddings, and shadow_mode_results tables with correct column
types matching the Pydantic data models. Supports both in-memory (for
testing) and on-disk databases.

Schema follows the research spec with:
- 17-column events table with deterministic event_id primary key
- 15-column episode_segments table
- episodes table with flat + STRUCT + JSON hybrid columns
- episode_search_text table for BM25 FTS retrieval
- episode_embeddings table for cosine similarity search (384-dim)
- shadow_mode_results table for shadow mode evaluation data
- Indexes for session, tag, timestamp, mode, risk, and reaction queries
- Ingestion metadata columns (first_seen, last_seen, ingestion_count) per Q13

Exports:
    get_connection: Get a DuckDB connection
    create_schema: Create tables and indexes
    drop_schema: Drop all tables (for testing)
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def get_connection(db_path: str = "data/ope.db") -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection.

    Creates parent directories if needed (for on-disk databases).
    Use ':memory:' for in-memory databases (testing).

    Args:
        db_path: Path to the DuckDB file, or ':memory:' for in-memory.

    Returns:
        DuckDB connection instance.
    """
    if db_path != ":memory:":
        parent = Path(db_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    return duckdb.connect(db_path)


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the events, episode_segments, and episodes tables with indexes.

    Uses CREATE TABLE IF NOT EXISTS so this is safe to call multiple times.
    Schema columns match the Pydantic models in events.py, segments.py,
    and episodes.py.

    Args:
        conn: DuckDB connection to create tables in.
    """
    # Events table: stores normalized canonical events
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id VARCHAR PRIMARY KEY,
            ts_utc TIMESTAMPTZ NOT NULL,
            session_id VARCHAR NOT NULL,
            actor VARCHAR NOT NULL,
            event_type VARCHAR NOT NULL,
            primary_tag VARCHAR,
            primary_tag_confidence FLOAT,
            secondary_tags JSON,
            payload JSON,
            links JSON,
            risk_score FLOAT DEFAULT 0.0,
            risk_factors JSON,
            first_seen TIMESTAMPTZ DEFAULT current_timestamp,
            last_seen TIMESTAMPTZ DEFAULT current_timestamp,
            ingestion_count INTEGER DEFAULT 1,
            source_system VARCHAR NOT NULL,
            source_ref VARCHAR NOT NULL
        )
    """)

    # Episode segments table: stores boundary detection results
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episode_segments (
            segment_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            start_event_id VARCHAR NOT NULL,
            end_event_id VARCHAR,
            start_ts TIMESTAMPTZ NOT NULL,
            end_ts TIMESTAMPTZ,
            start_trigger VARCHAR NOT NULL,
            end_trigger VARCHAR,
            outcome VARCHAR,
            event_count INTEGER NOT NULL,
            event_ids JSON NOT NULL,
            complexity VARCHAR DEFAULT 'simple',
            interruption_count INTEGER DEFAULT 0,
            context_switches INTEGER DEFAULT 0,
            config_hash VARCHAR,
            created_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)

    # Indexes for common query patterns
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_tag ON events(primary_tag)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_segments_session ON episode_segments(session_id)"
    )

    # Episodes table: hybrid flat + STRUCT + JSON storage
    # Flat columns for fast filtering, STRUCT for typed nested queries,
    # JSON for flexible nested data
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            -- Identity (flat, queryable)
            episode_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            segment_id VARCHAR NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,

            -- Flat queryable columns (duplicated from nested for fast filtering)
            mode VARCHAR,
            risk VARCHAR,
            reaction_label VARCHAR,
            reaction_confidence FLOAT,
            outcome_type VARCHAR,

            -- STRUCT for typed nested data (queryable via dot notation)
            observation STRUCT(
                repo_state STRUCT(
                    changed_files VARCHAR[],
                    diff_stat STRUCT(files INTEGER, insertions INTEGER, deletions INTEGER)
                ),
                quality_state STRUCT(
                    tests_status VARCHAR,
                    lint_status VARCHAR,
                    build_status VARCHAR
                ),
                context STRUCT(
                    recent_summary VARCHAR,
                    open_questions VARCHAR[],
                    constraints_in_force VARCHAR[]
                )
            ),

            -- JSON for flexible nested data
            orchestrator_action JSON,
            outcome JSON,
            provenance JSON,
            labels JSON,

            -- Provenance flat columns
            source_files VARCHAR[],
            config_hash VARCHAR,

            -- Metadata
            schema_version INTEGER DEFAULT 1,
            created_at TIMESTAMPTZ DEFAULT current_timestamp,
            updated_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)

    # Episodes indexes
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_mode ON episodes(mode)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_risk ON episodes(risk)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_reaction ON episodes(reaction_label)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(timestamp)"
    )

    # Episode search text table for BM25 FTS retrieval
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episode_search_text (
            episode_id VARCHAR PRIMARY KEY,
            search_text VARCHAR
        )
    """)

    # Episode embeddings table for cosine similarity search
    # VSS extension needed for FLOAT[384] array operations
    try:
        conn.execute("INSTALL vss; LOAD vss;")
    except Exception:
        # Extension may already be installed/loaded
        try:
            conn.execute("LOAD vss;")
        except Exception:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS episode_embeddings (
            episode_id VARCHAR PRIMARY KEY,
            embedding FLOAT[384],
            model_name VARCHAR DEFAULT 'all-MiniLM-L6-v2',
            created_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)

    # Shadow mode results table for leave-one-out evaluation
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_mode_results (
            shadow_run_id VARCHAR PRIMARY KEY,
            episode_id VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,
            human_mode VARCHAR NOT NULL,
            human_risk VARCHAR NOT NULL,
            human_reaction_label VARCHAR,
            shadow_mode VARCHAR NOT NULL,
            shadow_risk VARCHAR NOT NULL,
            shadow_confidence FLOAT,
            mode_agrees BOOLEAN NOT NULL,
            risk_agrees BOOLEAN NOT NULL,
            scope_overlap FLOAT,
            gate_agrees BOOLEAN,
            is_dangerous BOOLEAN NOT NULL DEFAULT FALSE,
            danger_reasons JSON,
            source_episode_ids JSON,
            retrieval_scores JSON,
            run_batch_id VARCHAR,
            created_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_session "
        "ON shadow_mode_results(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_batch "
        "ON shadow_mode_results(run_batch_id)"
    )

    # Phase 9: Escalation-specific columns (nullable, backward-compatible)
    escalation_columns = [
        ("escalate_block_event_ref", "VARCHAR"),
        ("escalate_bypass_event_ref", "VARCHAR"),
        ("escalate_bypassed_constraint_id", "VARCHAR"),
        ("escalate_approval_status", "VARCHAR"),
        ("escalate_confidence", "FLOAT"),
        ("escalate_detector_version", "VARCHAR"),
    ]
    for col_name, col_type in escalation_columns:
        try:
            conn.execute(
                f"ALTER TABLE episodes ADD COLUMN {col_name} {col_type}"
            )
        except Exception:
            pass  # Column already exists (idempotent)


def drop_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop all pipeline tables (for testing).

    Drops tables in reverse dependency order. RAG tables first,
    then episodes, segments, events.

    Args:
        conn: DuckDB connection to drop tables from.
    """
    conn.execute("DROP TABLE IF EXISTS shadow_mode_results")
    conn.execute("DROP TABLE IF EXISTS episode_embeddings")
    conn.execute("DROP TABLE IF EXISTS episode_search_text")
    conn.execute("DROP TABLE IF EXISTS episodes")
    conn.execute("DROP TABLE IF EXISTS episode_segments")
    conn.execute("DROP TABLE IF EXISTS events")
