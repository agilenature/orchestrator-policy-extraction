"""Parquet export via DuckDB native COPY TO.

Exports validated episodes to Parquet format for ML training pipelines
without requiring pyarrow as a dependency.

Exports:
    export_parquet: Single-file Parquet export
    export_parquet_partitioned: Partitioned Parquet export
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from loguru import logger


def export_parquet(
    conn: duckdb.DuckDBPyConnection,
    output_path: str | Path,
    query: str | None = None,
) -> int:
    """Export episodes to a single Parquet file using DuckDB native COPY.

    Args:
        conn: DuckDB connection with episodes table.
        output_path: Path for the output .parquet file.
        query: Optional custom SQL query. Defaults to selecting all episodes
            with a non-null reaction_label.

    Returns:
        Number of rows exported.
    """
    if query is None:
        query = "SELECT * FROM episodes WHERE reaction_label IS NOT NULL"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Count rows first
    count_result = conn.execute(f"SELECT count(*) FROM ({query})").fetchone()
    row_count = count_result[0] if count_result else 0

    if row_count == 0:
        logger.warning("No rows to export to Parquet")
        return 0

    # DuckDB native COPY TO Parquet
    conn.execute(
        f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET)"
    )

    logger.info("Exported {} rows to {}", row_count, output_path)
    return row_count


def export_parquet_partitioned(
    conn: duckdb.DuckDBPyConnection,
    output_dir: str | Path,
    partition_by: str = "mode",
) -> int:
    """Export episodes to partitioned Parquet files using DuckDB native COPY.

    Creates a directory structure partitioned by the specified column.

    Args:
        conn: DuckDB connection with episodes table.
        output_dir: Root directory for partitioned output.
        partition_by: Column name to partition by (default: mode).

    Returns:
        Total number of rows exported.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Count total rows
    count_result = conn.execute("SELECT count(*) FROM episodes").fetchone()
    row_count = count_result[0] if count_result else 0

    if row_count == 0:
        logger.warning("No episodes to export")
        return 0

    # DuckDB native partitioned COPY TO
    conn.execute(
        f"COPY episodes TO '{output_dir}' (FORMAT PARQUET, PARTITION_BY ({partition_by}))"
    )

    logger.info(
        "Exported {} rows partitioned by {} to {}",
        row_count,
        partition_by,
        output_dir,
    )
    return row_count
