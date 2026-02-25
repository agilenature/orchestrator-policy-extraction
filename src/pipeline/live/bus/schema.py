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

# -- Phase 20-01: bus_sessions extension columns --------------------------

_BUS_SESSIONS_EXTENSIONS = [
    "ALTER TABLE bus_sessions ADD COLUMN IF NOT EXISTS repo VARCHAR",
    "ALTER TABLE bus_sessions ADD COLUMN IF NOT EXISTS project_dir VARCHAR",
    "ALTER TABLE bus_sessions ADD COLUMN IF NOT EXISTS transcript_path VARCHAR",
    "ALTER TABLE bus_sessions ADD COLUMN IF NOT EXISTS event_count INTEGER",
    "ALTER TABLE bus_sessions ADD COLUMN IF NOT EXISTS outcome VARCHAR",
]


def _alter_bus_sessions(conn: duckdb.DuckDBPyConnection) -> None:
    """Add new columns to bus_sessions idempotently."""
    for ddl in _BUS_SESSIONS_EXTENSIONS:
        conn.execute(ddl)


# -- Phase 20-01: push_links table ---------------------------------------

PUSH_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS push_links (
    link_id               VARCHAR PRIMARY KEY,
    parent_decision_id    VARCHAR NOT NULL,
    child_decision_id     VARCHAR NOT NULL,
    transition_trigger    VARCHAR NOT NULL,
    repo_boundary         VARCHAR,
    migration_run_id      VARCHAR NOT NULL,
    captured_at           TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def create_bus_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create bus tables idempotently. Safe to call on every startup."""
    conn.execute(BUS_SESSIONS_DDL)
    conn.execute(GOVERNANCE_SIGNALS_DDL)
    _alter_bus_sessions(conn)
    conn.execute(PUSH_LINKS_DDL)
