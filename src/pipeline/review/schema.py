"""DuckDB schema for the identification review system.

Defines DDL for:
- identification_reviews: append-only table storing Agent B verdicts
- memory_candidates: new table for spec-correction candidates with CCD format constraint
- layer_coverage_snapshots: harness invariant tracking table
- identification_rule_trust: per-classification-rule trust accumulation

The identification_reviews table enforces at-most-once semantics via
UNIQUE constraint on identification_instance_id. Append-only behavior
is enforced in code (writer.py never issues UPDATE/DELETE).

The memory_candidates table enforces the CCD format structurally:
entries must have non-empty ccd_axis, scope_rule, and flood_example
fields -- making the trusted minimal core (is_valid_ccd) a schema
invariant rather than a convention.

The identification_rule_trust table tracks accepted/rejected verdict
counts per (pipeline_component, point_id) pair, computing a trust_level
(established/provisional/unverified) from accumulated evidence.

Exports:
    IDENTIFICATION_REVIEWS_DDL
    MEMORY_CANDIDATES_DDL
    LAYER_COVERAGE_SNAPSHOTS_DDL
    IDENTIFICATION_RULE_TRUST_DDL
    create_review_schema: Apply all DDL to a connection
"""

from __future__ import annotations

import duckdb


IDENTIFICATION_REVIEWS_DDL = """
CREATE TABLE IF NOT EXISTS identification_reviews (
    review_id                  VARCHAR PRIMARY KEY,
    identification_instance_id VARCHAR NOT NULL,
    layer                      VARCHAR NOT NULL,
    point_id                   VARCHAR NOT NULL,
    pipeline_component         VARCHAR NOT NULL,
    trigger_text               TEXT NOT NULL,
    observation_state          TEXT NOT NULL,
    action_taken               TEXT NOT NULL,
    downstream_impact          TEXT NOT NULL,
    provenance_pointer         TEXT NOT NULL,
    verdict                    VARCHAR NOT NULL CHECK (verdict IN ('accept', 'reject')),
    opinion                    TEXT,
    reviewed_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id                 VARCHAR,
    -- append-only: code must enforce no UPDATE/DELETE
    UNIQUE (identification_instance_id)  -- one verdict per instance
);
"""

MEMORY_CANDIDATES_DDL = """
CREATE TABLE IF NOT EXISTS memory_candidates (
    id                    VARCHAR PRIMARY KEY,
    source_instance_id    VARCHAR,
    ccd_axis              TEXT NOT NULL,
    scope_rule            TEXT NOT NULL,
    flood_example         TEXT NOT NULL,
    pipeline_component    VARCHAR,
    heuristic_description TEXT,
    status                VARCHAR NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'validated', 'suspended', 'rejected', 'split_required')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at           TIMESTAMPTZ,
    -- CCD format structural constraint: the trusted minimal core
    CHECK (LENGTH(TRIM(ccd_axis)) > 0),
    CHECK (LENGTH(TRIM(scope_rule)) > 0),
    CHECK (LENGTH(TRIM(flood_example)) > 0)
);
"""

LAYER_COVERAGE_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS layer_coverage_snapshots (
    snapshot_id    VARCHAR PRIMARY KEY,
    run_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    layer          VARCHAR NOT NULL,
    reviewed_count INTEGER NOT NULL,
    pool_count     INTEGER NOT NULL,
    coverage_ratio DOUBLE PRECISION NOT NULL
);
"""


IDENTIFICATION_RULE_TRUST_DDL = """
CREATE TABLE IF NOT EXISTS identification_rule_trust (
    rule_id            VARCHAR PRIMARY KEY,
    pipeline_component VARCHAR NOT NULL,
    point_id           VARCHAR NOT NULL,
    accept_count       INTEGER NOT NULL DEFAULT 0,
    reject_count       INTEGER NOT NULL DEFAULT 0,
    trust_level        VARCHAR NOT NULL DEFAULT 'unverified'
                       CHECK (trust_level IN ('established', 'provisional', 'unverified')),
    last_updated       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def create_review_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply all review system DDL to the given connection.

    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).

    Args:
        conn: DuckDB connection to create tables in.
    """
    conn.execute(IDENTIFICATION_REVIEWS_DDL)
    conn.execute(MEMORY_CANDIDATES_DDL)
    conn.execute(LAYER_COVERAGE_SNAPSHOTS_DDL)
    conn.execute(IDENTIFICATION_RULE_TRUST_DDL)
