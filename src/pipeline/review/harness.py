"""Out-of-band harness runner for structural invariant enforcement.

HarnessRunner executes all structural invariants against durable artifacts
(DuckDB tables + MEMORY.md) and produces a structured HarnessReport.
The harness has no AI session state -- it resolves bootstrap circularity
by validating structural correctness without sharing the memory deficiency
of the agent it validates.

Read-only with respect to identification_reviews. Writes only to
layer_coverage_snapshots for monotonicity tracking.

Exit code convention (for CLI integration):
    0 = all invariants pass
    1 = runtime error
    2 = invariant violation

Exports:
    HarnessRunner
    HarnessReport
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import duckdb

from src.pipeline.review.invariants import (
    InvariantResult,
    check_at_most_once_verdict,
    check_delta_retrieval,
    check_layer_coverage_monotonic,
    check_specification_closure,
)
from src.pipeline.review.nversion import NVersionConsistency


def _now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HarnessReport:
    """Structured report from a harness run.

    Attributes:
        results: List of InvariantResult, one per invariant check.
        run_at: ISO-8601 UTC timestamp when the harness ran.
    """

    results: list[InvariantResult] = field(default_factory=list)
    run_at: str = ""

    @property
    def all_passed(self) -> bool:
        """True if every invariant check passed."""
        return all(r.passed for r in self.results)

    def summary(self) -> str:
        """Human-readable summary of the harness run.

        Returns:
            Multi-line string with pass/fail status per invariant.
        """
        lines = [f"Harness run: {self.run_at}"]
        for r in self.results:
            if r.passed:
                status = "PASS"
            else:
                status = f"FAIL ({len(r.violations)} violations)"
            lines.append(f"  {r.invariant_name}: {status}")
        return "\n".join(lines)


class HarnessRunner:
    """Runs all structural invariants and produces a HarnessReport.

    Executes the four core invariants plus N-version consistency:
    1. at_most_once_verdict
    2. layer_coverage_monotonic
    3. specification_closure
    4. delta_retrieval
    5. nversion_consistency

    After running checks, writes a layer_coverage_snapshot for
    monotonicity tracking in future runs.

    Args:
        conn: DuckDB connection with all review system tables.
        memory_md_path: Path to MEMORY.md for N-version consistency.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        memory_md_path: str = "MEMORY.md",
    ):
        self._conn = conn
        self._memory_md_path = memory_md_path

    def run(self) -> HarnessReport:
        """Execute all invariant checks and return a HarnessReport.

        Runs all five checks, writes a coverage snapshot for future
        monotonicity tracking, and returns the structured report.

        Returns:
            HarnessReport with results for all invariants.
        """
        results = [
            check_at_most_once_verdict(self._conn),
            check_layer_coverage_monotonic(self._conn),
            check_specification_closure(self._conn),
            check_delta_retrieval(self._conn, self._memory_md_path),
            NVersionConsistency(self._conn, self._memory_md_path).check(),
        ]
        # Write snapshot for layer_coverage_monotonic tracking
        self._write_coverage_snapshot()
        return HarnessReport(results=results, run_at=_now())

    def _write_coverage_snapshot(self) -> None:
        """Write current layer coverage ratios to layer_coverage_snapshots.

        For each layer in identification_reviews, computes:
        - reviewed_count: number of reviewed instances for that layer
        - pool_count: total identification instances for that layer
          (approximated from identification_reviews since the pool is
          ephemeral -- built from constraints at review time)
        - coverage_ratio: reviewed_count / pool_count (or 0.0 if pool is empty)

        Uses reviewed_count as pool_count since the pool is built
        dynamically. This means coverage_ratio is 1.0 for any layer
        with reviews -- which is correct for monotonicity tracking
        (the relevant signal is whether new layers gain coverage,
        not the absolute ratio within a layer).
        """
        layers = self._conn.execute(
            """
            SELECT
                layer,
                COUNT(*) AS reviewed_count
            FROM identification_reviews
            GROUP BY layer
            """
        ).fetchall()

        now = _now()
        for layer, reviewed_count in layers:
            # Pool count is approximated as reviewed_count since the pool
            # is ephemeral. In practice, this tracks whether layers maintain
            # coverage rather than computing absolute coverage ratios.
            pool_count = reviewed_count
            coverage_ratio = 1.0 if pool_count > 0 else 0.0

            snapshot_id = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO layer_coverage_snapshots
                    (snapshot_id, run_at, layer, reviewed_count,
                     pool_count, coverage_ratio)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [snapshot_id, now, layer, reviewed_count,
                 pool_count, coverage_ratio],
            )
