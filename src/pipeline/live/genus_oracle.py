"""Genus oracle -- searches axis_edges for matching genera.

Stub implementation. Full implementation in plan 25-03.
"""

from __future__ import annotations

from typing import Any

import duckdb


class GenusOracleHandler:
    """Searches axis_edges for genus_of entries matching a problem description."""

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def query_genus(self, problem: str, repo: str | None = None) -> dict[str, Any]:
        """Find best-matching genus for a problem description.

        Stub: returns empty response. Full implementation in plan 25-03.
        """
        return {
            "genus": None,
            "instances": [],
            "valid": False,
            "confidence": 0.0,
        }
