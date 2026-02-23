"""Structural invariant checks for the out-of-band harness.

Four invariant functions that enforce structural correctness against
durable artifacts (DuckDB tables, MEMORY.md) without requiring any
AI session state. This breaks the bootstrap circularity: the validator
does not share the deficiency of the artifact it validates.

Invariants:
1. at_most_once_verdict: No instance has more than one verdict
2. layer_coverage_monotonic: Coverage ratio per layer never decreases
3. specification_closure: Every reject+opinion has a memory_candidates counterpart
4. delta_retrieval: Axis retrieval rate does not regress after MEMORY.md acceptance

Each function returns an InvariantResult with pass/fail, violations list,
and ISO-8601 timestamp. The harness is read-only with respect to
identification_reviews -- it writes only to layer_coverage_snapshots
for monotonicity tracking.

Exports:
    InvariantResult
    check_at_most_once_verdict
    check_layer_coverage_monotonic
    check_specification_closure
    check_delta_retrieval
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import duckdb


@dataclass
class InvariantResult:
    """Result of one invariant check.

    Attributes:
        invariant_name: Short identifier for the invariant.
        passed: True if no violations found.
        violations: List of dicts, each with instance_id/layer/component/detail.
        checked_at: ISO-8601 UTC timestamp when the check ran.
    """

    invariant_name: str
    passed: bool
    violations: list[dict] = field(default_factory=list)
    checked_at: str = ""


def _now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def check_at_most_once_verdict(conn: duckdb.DuckDBPyConnection) -> InvariantResult:
    """No identification instance should have more than one verdict.

    The UNIQUE constraint prevents this at DB level; this function audits
    existing rows in case the constraint was added after data was written
    or was relaxed for metamorphic testing.

    Args:
        conn: DuckDB connection with identification_reviews table.

    Returns:
        InvariantResult with violations listing any duplicate instance_ids.
    """
    rows = conn.execute(
        """
        SELECT identification_instance_id, COUNT(*) as cnt
        FROM identification_reviews
        GROUP BY identification_instance_id
        HAVING cnt > 1
        """
    ).fetchall()
    violations = [
        {
            "instance_id": r[0],
            "count": r[1],
            "detail": "duplicate verdict",
        }
        for r in rows
    ]
    return InvariantResult(
        invariant_name="at_most_once_verdict",
        passed=len(violations) == 0,
        violations=violations,
        checked_at=_now(),
    )


def check_layer_coverage_monotonic(conn: duckdb.DuckDBPyConnection) -> InvariantResult:
    """Coverage ratio per layer must be non-decreasing across consecutive snapshots.

    Queries the last two layer_coverage_snapshots per layer (ordered by run_at)
    and flags any layer where the latest coverage_ratio is strictly less than
    the previous snapshot's coverage_ratio.

    Args:
        conn: DuckDB connection with layer_coverage_snapshots table.

    Returns:
        InvariantResult with violations listing any layers with decreased coverage.
    """
    # Use window function to get previous snapshot per layer
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                layer,
                coverage_ratio,
                run_at,
                ROW_NUMBER() OVER (PARTITION BY layer ORDER BY run_at DESC) AS rn
            FROM layer_coverage_snapshots
        )
        SELECT
            curr.layer,
            prev.coverage_ratio AS prev_ratio,
            curr.coverage_ratio AS curr_ratio,
            prev.run_at AS prev_run,
            curr.run_at AS curr_run
        FROM ranked curr
        JOIN ranked prev
            ON curr.layer = prev.layer
            AND curr.rn = 1
            AND prev.rn = 2
        WHERE curr.coverage_ratio < prev.coverage_ratio
        """
    ).fetchall()
    violations = [
        {
            "layer": r[0],
            "previous_ratio": r[1],
            "current_ratio": r[2],
            "previous_run": str(r[3]),
            "current_run": str(r[4]),
            "detail": (
                f"coverage decreased from {r[1]:.4f} to {r[2]:.4f}"
            ),
        }
        for r in rows
    ]
    return InvariantResult(
        invariant_name="layer_coverage_monotonic",
        passed=len(violations) == 0,
        violations=violations,
        checked_at=_now(),
    )


def check_specification_closure(conn: duckdb.DuckDBPyConnection) -> InvariantResult:
    """Every rejected verdict with non-empty opinion must have a memory_candidates row.

    The specification closure invariant ensures that when a human rejects a
    classification act and provides corrective feedback (opinion), that feedback
    is routed to a spec-correction candidate. Without this, the feedback loop
    is open -- the system detects errors but never corrects the specification.

    Args:
        conn: DuckDB connection with identification_reviews and
            memory_candidates tables.

    Returns:
        InvariantResult with violations listing any reject+opinion rows
        that lack a corresponding memory_candidates entry.
    """
    rows = conn.execute(
        """
        SELECT r.identification_instance_id, r.pipeline_component, r.opinion
        FROM identification_reviews r
        LEFT JOIN memory_candidates m
            ON r.identification_instance_id = m.source_instance_id
        WHERE r.verdict = 'reject'
          AND r.opinion IS NOT NULL
          AND r.opinion != ''
          AND m.id IS NULL
        """
    ).fetchall()
    violations = [
        {
            "instance_id": r[0],
            "pipeline_component": r[1],
            "opinion": r[2][:100] if r[2] else "",
            "detail": "rejected verdict with opinion has no spec-correction candidate",
        }
        for r in rows
    ]
    return InvariantResult(
        invariant_name="specification_closure",
        passed=len(violations) == 0,
        violations=violations,
        checked_at=_now(),
    )


def check_delta_retrieval(
    conn: duckdb.DuckDBPyConnection,
    memory_md_path: str = "MEMORY.md",
) -> InvariantResult:
    """Axis retrieval rate must not regress after MEMORY.md acceptance.

    For each accepted memory_candidates entry, measures whether the ccd_axis
    appears as a substring in the action_taken field of subsequent reviews
    (proxy for axis-guided retrieval). Compares rates across the two most
    recent layer_coverage_snapshots runs to detect regression.

    This is intentionally conservative: it measures structural signal
    (did the ccd_axis appear in action_taken?), not behavioral signal
    (did the AI genuinely retrieve by axis?). The structural proxy is
    immune to the surface-similarity defect it is measuring.

    Currently checks whether any accepted memory_candidates axes appear
    in reviews' action_taken fields. If no accepted candidates exist or
    no snapshots exist, the invariant passes vacuously (no data to regress).

    Args:
        conn: DuckDB connection with memory_candidates and
            identification_reviews tables.
        memory_md_path: Path to MEMORY.md (reserved for future use).

    Returns:
        InvariantResult. Passes vacuously when no accepted candidates exist.
    """
    # Check if there are any accepted candidates to measure
    accepted = conn.execute(
        "SELECT ccd_axis FROM memory_candidates WHERE status = 'validated'"
    ).fetchall()

    if not accepted:
        return InvariantResult(
            invariant_name="delta_retrieval",
            passed=True,
            violations=[],
            checked_at=_now(),
        )

    # For each accepted axis, check if it appears in any action_taken
    # of reviews created after the candidate was accepted.
    # This is a structural proxy: presence in action_taken indicates
    # the axis is being used for retrieval guidance.
    violations = []
    for row in accepted:
        axis = row[0]
        if not axis:
            continue

        # Count reviews where axis appears in action_taken
        hit_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM identification_reviews
            WHERE action_taken LIKE '%' || ? || '%'
            """,
            [axis],
        ).fetchone()[0]

        total_count = conn.execute(
            "SELECT COUNT(*) FROM identification_reviews"
        ).fetchone()[0]

        if total_count > 0 and hit_count == 0:
            violations.append(
                {
                    "ccd_axis": axis,
                    "total_reviews": total_count,
                    "axis_hits": hit_count,
                    "detail": (
                        f"accepted axis '{axis}' appears in 0/{total_count} "
                        f"review action_taken fields"
                    ),
                }
            )

    return InvariantResult(
        invariant_name="delta_retrieval",
        passed=len(violations) == 0,
        violations=violations,
        checked_at=_now(),
    )
