"""PremiseRegistry DuckDB CRUD operations.

Provides create, read, update, and query operations for the premise_registry
table. Full implementation in Task 2.

Exports:
    PremiseRegistry: DuckDB CRUD for premise_registry table
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb

from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.schema import PARENT_EPISODE_BACKFILL_SQL


class PremiseRegistry:
    """DuckDB CRUD operations for the premise_registry table.

    Provides register, get, update, stain, and query methods for
    premise records. Does NOT call create_premise_schema -- caller's
    responsibility (matching project pattern where create_schema()
    is called once in runner init).

    Args:
        conn: DuckDB connection with premise_registry table created.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn
