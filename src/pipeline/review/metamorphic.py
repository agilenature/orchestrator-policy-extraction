"""Metamorphic testing for identification review consistency.

Tests that the same identification instance, presented in two different
sessions, receives an equivalent verdict. Violations indicate that
Agent B's classification is session-state-dependent -- i.e., the memory
issue is affecting verdict consistency.

Full metamorphic testing requires a test harness that drives two
``review next`` sessions with the same instance. This module provides
the violation-detection logic that queries results after such sessions
have been run.

In practice, metamorphic testing uses a separate
``metamorphic_test_reviews`` table (or relaxes the UNIQUE constraint
on identification_instance_id for test sessions) so that the same
instance can receive multiple verdicts.

Exports:
    MetamorphicTester
    MetamorphicViolation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import duckdb


@dataclass
class MetamorphicViolation:
    """A single metamorphic testing violation.

    Attributes:
        instance_id: The identification instance that received inconsistent verdicts.
        verdicts: List of distinct verdicts received (e.g. ['accept', 'reject']).
        session_ids: List of session_ids where the verdicts were recorded.
        detail: Human-readable description of the inconsistency.
    """

    instance_id: str
    verdicts: list[str]
    session_ids: list[str]
    detail: str


class MetamorphicTester:
    """Detects verdict inconsistency across multiple review sessions.

    Metamorphic property: if instance X is reviewed twice (in different
    sessions), the verdicts should be equivalent (both accept or both
    reject). Violations indicate that Agent B's classification is
    session-state-dependent.

    This tester queries a dedicated metamorphic_test_reviews table
    (schema identical to identification_reviews but without the UNIQUE
    constraint on identification_instance_id). The table must be
    populated by an external test harness that presents the same pool
    instance to two separate CLI sessions.

    Args:
        conn: DuckDB connection. Must have either metamorphic_test_reviews
            or identification_reviews table.
        table: Table name to query. Defaults to 'metamorphic_test_reviews'.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        table: str = "metamorphic_test_reviews",
    ):
        self._conn = conn
        self._table = table

    def ensure_table(self) -> None:
        """Create the metamorphic_test_reviews table if it does not exist.

        Schema is identical to identification_reviews except:
        - No UNIQUE constraint on identification_instance_id
          (allows multiple verdicts per instance for testing)
        """
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
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
                session_id                 VARCHAR
            )
            """
        )

    def find_violations(self) -> list[MetamorphicViolation]:
        """Find instances with inconsistent verdicts across sessions.

        Queries the test table for instances that received more than one
        distinct verdict. Each such instance represents a metamorphic
        violation: the same input produced different outputs depending
        on session state.

        Returns:
            List of MetamorphicViolation, one per inconsistent instance.
            Empty list if no violations (or no data).
        """
        # Check if the table exists
        tables = self._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?",
            [self._table],
        ).fetchall()
        if not tables:
            return []

        rows = self._conn.execute(
            f"""
            SELECT
                identification_instance_id,
                LIST(DISTINCT verdict) AS verdicts,
                LIST(DISTINCT session_id) AS sessions,
                COUNT(DISTINCT verdict) AS distinct_count
            FROM {self._table}
            GROUP BY identification_instance_id
            HAVING COUNT(DISTINCT verdict) > 1
            """
        ).fetchall()

        violations = []
        for r in rows:
            instance_id = r[0]
            verdicts = r[1] if r[1] else []
            sessions = r[2] if r[2] else []
            violations.append(
                MetamorphicViolation(
                    instance_id=instance_id,
                    verdicts=verdicts,
                    session_ids=[s for s in sessions if s is not None],
                    detail=(
                        f"instance received inconsistent verdicts: "
                        f"{', '.join(verdicts)} across {len(sessions)} session(s)"
                    ),
                )
            )

        return violations
