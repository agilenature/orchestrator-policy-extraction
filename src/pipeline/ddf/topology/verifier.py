"""Cross-Axis Registry Verification for premise-edge consistency.

Verifies premise claims against recorded cross-axis edges.
Enforces foil level-matching: foil abstraction level must be
<= premise level + 1.

When an edge's abstraction_level exceeds the premise's level by more
than 1, it indicates potential Equivocation -- the edge relationship
operates at a significantly higher abstraction than the premise claim.

Uses read-only DuckDB access with activation_condition filtering.

Exports:
    CrossAxisVerifier
"""

from __future__ import annotations

import json
from itertools import combinations

import duckdb


class CrossAxisVerifier:
    """Verify premise claims against recorded cross-axis edges.

    Checks for foil level mismatches where the edge's abstraction
    level exceeds the premise's abstraction level by more than 1.

    Args:
        conn: DuckDB connection (read-only recommended).
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def verify_premise(
        self,
        premise_axes: list[str],
        premise_claim: str,
        premise_abstraction_level: int | None = None,
        goal_type: str | None = None,
        scope_prefix: str = "",
    ) -> list[str]:
        """Verify a premise claim against recorded cross-axis edges.

        For each pair of premise axes, checks active edges for foil
        level mismatches. An edge with abstraction_level > premise_level + 1
        indicates a potential Equivocation.

        Args:
            premise_axes: CCD axes referenced by the premise.
            premise_claim: The premise claim text.
            premise_abstraction_level: Abstraction level of the premise (0-7).
            goal_type: Current goal type for activation filtering.
            scope_prefix: Current scope prefix for activation filtering.

        Returns:
            List of CROSS_AXIS_WARNING strings for inconsistencies.
        """
        warnings: list[str] = []
        unique_axes = sorted(set(premise_axes))

        if len(unique_axes) < 2:
            return warnings

        for axis_a, axis_b in combinations(unique_axes, 2):
            warnings.extend(
                self._check_pair(
                    axis_a,
                    axis_b,
                    premise_claim,
                    premise_abstraction_level,
                    goal_type,
                    scope_prefix,
                )
            )

        return warnings

    def _check_pair(
        self,
        axis_a: str,
        axis_b: str,
        premise_claim: str,
        premise_level: int | None,
        goal_type: str | None,
        scope_prefix: str,
    ) -> list[str]:
        """Check a single axis pair for foil level mismatches.

        Args:
            axis_a: First axis name.
            axis_b: Second axis name.
            premise_claim: The premise claim text.
            premise_level: Abstraction level of the premise.
            goal_type: Current goal type for activation filtering.
            scope_prefix: Current scope prefix for activation filtering.

        Returns:
            List of CROSS_AXIS_WARNING strings.
        """
        warnings: list[str] = []

        rows = self._conn.execute(
            """SELECT edge_id, relationship_text, activation_condition,
                      abstraction_level, trunk_quality
               FROM axis_edges
               WHERE ((axis_a = ? AND axis_b = ?) OR (axis_a = ? AND axis_b = ?))
               AND status = 'active'""",
            [axis_a, axis_b, axis_b, axis_a],
        ).fetchall()

        for edge_id, rel_text, ac_json, edge_level, trunk_q in rows:
            if not self._activation_matches(ac_json, goal_type, scope_prefix):
                continue

            # Foil level-matching: edge_level > premise_level + 1 = Equivocation
            if premise_level is not None and edge_level is not None:
                if edge_level > premise_level + 1:
                    warnings.append(
                        f"CROSS_AXIS_WARNING: Edge {edge_id} between "
                        f"[{axis_a}] and [{axis_b}] is at abstraction "
                        f"level {edge_level}, but premise is at level "
                        f"{premise_level}. Foil level mismatch "
                        f"(edge level must be <= premise level + 1). "
                        f"Possible Equivocation."
                    )

        return warnings

    def _activation_matches(
        self,
        ac_json: str | dict | None,
        goal_type: str | None,
        scope_prefix: str,
    ) -> bool:
        """Check if an activation_condition matches current context.

        Matches if:
        - edge goal_type contains "any" OR contains the current goal_type
        - edge scope_prefix is empty OR current scope_prefix starts with it

        Args:
            ac_json: Activation condition as JSON string or dict.
            goal_type: Current goal type to match against.
            scope_prefix: Current scope prefix to match against.

        Returns:
            True if the activation condition matches.
        """
        try:
            ac = json.loads(ac_json) if isinstance(ac_json, str) else ac_json
        except (json.JSONDecodeError, TypeError):
            return False

        edge_goals = ac.get("goal_type", ["any"])
        if "any" not in edge_goals:
            if goal_type and goal_type not in edge_goals:
                return False

        edge_prefix = ac.get("scope_prefix", "")
        if edge_prefix:
            if not scope_prefix.startswith(edge_prefix):
                return False

        return True
