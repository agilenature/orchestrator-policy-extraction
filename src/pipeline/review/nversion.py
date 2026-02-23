"""N-version consistency check for memory_candidates vs MEMORY.md.

Checks that every memory_candidates row with status='validated' has a
corresponding entry in MEMORY.md (identified by ccd_axis match).
This enforces two-representation consistency:
DuckDB (machine-readable) <-> MEMORY.md (AI-readable filing key).

The parser uses the ``**CCD axis:** `name` `` regex to extract axes
from MEMORY.md -- the same format enforced by MEMORY.md's own format
requirement. If the format changes, both the parser and the invariant
fail together -- they are co-dependent by design.

Exports:
    NVersionConsistency
"""

from __future__ import annotations

import re

import duckdb

from src.pipeline.review.invariants import InvariantResult, _now


class NVersionConsistency:
    """Checks DuckDB <-> MEMORY.md consistency for accepted entries.

    Every memory_candidates row with status='validated' must have a
    corresponding ``**CCD axis:** `name` `` entry in MEMORY.md.
    Missing counterparts indicate that an accepted candidate was not
    deposited into the AI-readable filing system.

    Args:
        conn: DuckDB connection with memory_candidates table.
        memory_md_path: Path to the MEMORY.md file to parse.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        memory_md_path: str = "MEMORY.md",
    ):
        self._conn = conn
        self._memory_md_path = memory_md_path

    def check(self) -> InvariantResult:
        """Run the N-version consistency check.

        Returns:
            InvariantResult with violations for any accepted axes
            missing from MEMORY.md.
        """
        accepted_axes = self._get_accepted_axes()
        memory_md_axes = self._parse_memory_md_axes()
        missing = [ax for ax in accepted_axes if ax not in memory_md_axes]
        violations = [
            {
                "ccd_axis": ax,
                "detail": (
                    "accepted memory_candidates entry has no MEMORY.md counterpart"
                ),
            }
            for ax in missing
        ]
        return InvariantResult(
            invariant_name="nversion_consistency",
            passed=len(violations) == 0,
            violations=violations,
            checked_at=_now(),
        )

    def _get_accepted_axes(self) -> list[str]:
        """Get ccd_axis values from accepted (validated) memory_candidates.

        Returns:
            List of non-empty ccd_axis strings with status='validated'.
        """
        rows = self._conn.execute(
            "SELECT ccd_axis FROM memory_candidates WHERE status = 'validated'"
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def _parse_memory_md_axes(self) -> set[str]:
        """Extract ccd_axis values from MEMORY.md.

        Scans for lines matching ``**CCD axis:** `axis-name` `` and
        returns the set of extracted axis names.

        Returns:
            Set of ccd_axis strings found in MEMORY.md.
            Empty set if file not found.
        """
        try:
            with open(self._memory_md_path) as f:
                content = f.read()
        except FileNotFoundError:
            return set()
        return set(re.findall(r"\*\*CCD axis:\*\*\s+`([^`]+)`", content))
