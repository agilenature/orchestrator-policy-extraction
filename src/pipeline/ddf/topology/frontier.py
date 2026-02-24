"""Frontier Warning detector for uncharted axis pairs.

Queries axis_edges to detect when two simultaneously active CCD axes
have no recorded active edge. Frontier Warnings prompt the human to
generate edges where the topology map has blank spaces.

Uses read-only DuckDB access with activation_condition filtering
by goal_type and scope_prefix.

Exports:
    FrontierChecker
"""

from __future__ import annotations

import json
from itertools import combinations

import duckdb


class FrontierChecker:
    """Detect uncharted axis pairs (no active edge in axis_edges).

    Queries the axis_edges table for active edges matching the given
    axis pair, filtering by activation_condition goal_type and scope_prefix.

    Args:
        conn: DuckDB connection (read-only recommended).
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def check_frontier(
        self,
        active_axes: list[str],
        goal_type: str | None = None,
        scope_prefix: str = "",
    ) -> list[str]:
        """Check for axis pairs with no active edge.

        For each unique pair of active axes, checks whether an active
        edge exists with a matching activation_condition. If not,
        emits a FRONTIER_WARNING.

        Args:
            active_axes: List of CCD axis names currently active.
            goal_type: Current goal type for activation filtering.
            scope_prefix: Current scope prefix for activation filtering.

        Returns:
            List of FRONTIER_WARNING strings for uncharted pairs.
        """
        warnings: list[str] = []
        unique_axes = sorted(set(active_axes))

        if len(unique_axes) < 2:
            return warnings

        for axis_a, axis_b in combinations(unique_axes, 2):
            if not self._has_active_edge(axis_a, axis_b, goal_type, scope_prefix):
                warnings.append(
                    f"FRONTIER_WARNING: Operating between [{axis_a}] and "
                    f"[{axis_b}] with no recorded relationship -- "
                    f"Frontier territory. Geological Drill zone."
                )

        return warnings

    def _has_active_edge(
        self,
        axis_a: str,
        axis_b: str,
        goal_type: str | None,
        scope_prefix: str,
    ) -> bool:
        """Check if an active edge exists for the axis pair.

        Searches both directions (axis_a, axis_b) and (axis_b, axis_a)
        with status='active', then filters by activation_condition.

        Args:
            axis_a: First axis name.
            axis_b: Second axis name.
            goal_type: Current goal type for filtering.
            scope_prefix: Current scope prefix for filtering.

        Returns:
            True if at least one matching active edge exists.
        """
        rows = self._conn.execute(
            """SELECT activation_condition FROM axis_edges
               WHERE ((axis_a = ? AND axis_b = ?) OR (axis_a = ? AND axis_b = ?))
               AND status = 'active'""",
            [axis_a, axis_b, axis_b, axis_a],
        ).fetchall()

        for (ac_json,) in rows:
            if self._activation_matches(ac_json, goal_type, scope_prefix):
                return True

        return False

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

    def find_frontier_pairs(
        self,
        active_axes: list[str],
        goal_type: str | None = None,
        scope_prefix: str = "",
    ) -> list[tuple[str, str]]:
        """Return uncharted axis pairs as (axis_a, axis_b) tuples.

        Convenience method returning structured data instead of
        warning strings.

        Args:
            active_axes: List of CCD axis names currently active.
            goal_type: Current goal type for activation filtering.
            scope_prefix: Current scope prefix for activation filtering.

        Returns:
            List of (axis_a, axis_b) tuples with no active edge.
        """
        pairs: list[tuple[str, str]] = []
        unique_axes = sorted(set(active_axes))

        for axis_a, axis_b in combinations(unique_axes, 2):
            if not self._has_active_edge(axis_a, axis_b, goal_type, scope_prefix):
                pairs.append((axis_a, axis_b))

        return pairs
