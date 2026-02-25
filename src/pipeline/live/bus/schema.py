"""DuckDB schema definitions for the OPE Governance Bus.

Provides DDL for bus_sessions and governance_signals tables, plus an
idempotent create_bus_schema() function called at server startup.
"""

from __future__ import annotations

import duckdb

BUS_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS bus_sessions (
    session_id    VARCHAR PRIMARY KEY,
    run_id        VARCHAR NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ,
    status        VARCHAR NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'deregistered'))
)
"""

GOVERNANCE_SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS governance_signals (
    signal_id           VARCHAR PRIMARY KEY,
    session_id          VARCHAR NOT NULL,
    run_id              VARCHAR NOT NULL,
    signal_type         VARCHAR NOT NULL,
    boundary_dependency VARCHAR NOT NULL
        CHECK (boundary_dependency IN ('event_level', 'episode_level')),
    payload_json        JSON,
    emitted_at          TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def create_bus_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create bus tables idempotently. Safe to call on every startup."""
    conn.execute(BUS_SESSIONS_DDL)
    conn.execute(GOVERNANCE_SIGNALS_DDL)
