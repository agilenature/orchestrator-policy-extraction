"""Test helpers for review CLI integration tests.

Seeds a minimal DuckDB with enough data for the PoolBuilder to produce
at least one IdentificationPoint instance.

Not shipped as production code -- used only by tests.

Exports:
    seed_minimal_pool
"""

from __future__ import annotations

import duckdb


def seed_minimal_pool(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed minimal data so PoolBuilder produces at least one instance.

    Creates the events table with one row, which the PoolBuilder's
    L1-1 (record meaningfulness) query will pick up.

    Args:
        conn: DuckDB connection to seed.
    """
    # Create a minimal events table matching what PoolBuilder queries
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id VARCHAR PRIMARY KEY,
            session_id VARCHAR,
            actor VARCHAR,
            event_type VARCHAR,
            primary_tag VARCHAR,
            primary_tag_confidence DOUBLE,
            secondary_tags VARCHAR,
            source_ref VARCHAR
        )
    """)
    conn.execute("""
        INSERT INTO events (
            event_id, session_id, actor, event_type,
            primary_tag, primary_tag_confidence, source_ref
        ) VALUES (
            'evt-test-001', 'sess-test-001', 'orchestrator', 'tool_use',
            'delegation', 0.85, 'test_source:line1'
        )
    """)
