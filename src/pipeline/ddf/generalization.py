"""GeneralizationRadius computation with stagnation detection (DDF-05).

Computes how broadly a constraint has been applied across different scope
contexts. A constraint that fires only in its original scope (radius=1) with
high firing count is flagged as stagnant -- a potential floating abstraction.

The radius is a count-based proxy: number of distinct scope_path prefixes
where the constraint has fired, derived from session_constraint_eval records.

Exports:
    compute_generalization_radius
    compute_all_metrics
    write_constraint_metrics
    detect_stagnation
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb

from src.pipeline.ddf.models import ConstraintMetric
from src.pipeline.models.config import PipelineConfig


def _extract_scope_prefix(evidence_json_str: str | None) -> str:
    """Extract the first scope path prefix from evidence_json.

    Parses the evidence_json string (JSON), looks for a 'scope_path' field
    in each evidence entry, and returns the first path component.

    If scope_path is empty, null, or evidence_json cannot be parsed,
    returns 'root' as the default prefix.

    Args:
        evidence_json_str: JSON string from session_constraint_eval.evidence_json.

    Returns:
        First path component (e.g., 'src' from 'src/pipeline/foo.py'),
        or 'root' if no scope_path is available.
    """
    if not evidence_json_str:
        return "root"

    try:
        evidence = json.loads(evidence_json_str) if isinstance(evidence_json_str, str) else evidence_json_str
    except (json.JSONDecodeError, TypeError):
        return "root"

    # Evidence can be a list of dicts or a dict
    if isinstance(evidence, dict):
        evidence = [evidence]

    if not isinstance(evidence, list):
        return "root"

    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        scope_path = entry.get("scope_path", "")
        if scope_path:
            # First path component: split on '/' and take the first non-empty part
            parts = [p for p in str(scope_path).split("/") if p]
            if parts:
                return parts[0]

    return "root"


def compute_generalization_radius(
    conn: duckdb.DuckDBPyConnection,
    constraint_id: str,
    config: PipelineConfig | None = None,
) -> ConstraintMetric:
    """Compute the generalization radius for a single constraint.

    Radius = COUNT(DISTINCT scope_path_prefix) from session_constraint_eval.
    Firing count = total evaluations for this constraint.
    Stagnation = radius == 1 AND firing_count >= stagnation_min_firing_count.

    Args:
        conn: DuckDB connection with session_constraint_eval table.
        constraint_id: The constraint to compute metrics for.
        config: Optional pipeline config for stagnation threshold.

    Returns:
        ConstraintMetric with radius, firing_count, and is_stagnant.
    """
    stagnation_threshold = 10
    if config is not None:
        stagnation_threshold = config.ddf.stagnation_min_firing_count

    rows = conn.execute(
        "SELECT evidence_json FROM session_constraint_eval WHERE constraint_id = ?",
        [constraint_id],
    ).fetchall()

    if not rows:
        return ConstraintMetric(
            constraint_id=constraint_id,
            radius=0,
            firing_count=0,
            is_stagnant=False,
        )

    # Extract distinct scope prefixes
    prefixes: set[str] = set()
    for (evidence_json_str,) in rows:
        prefix = _extract_scope_prefix(evidence_json_str)
        prefixes.add(prefix)

    radius = len(prefixes)
    firing_count = len(rows)
    is_stagnant = radius == 1 and firing_count >= stagnation_threshold

    return ConstraintMetric(
        constraint_id=constraint_id,
        radius=radius,
        firing_count=firing_count,
        is_stagnant=is_stagnant,
    )


def compute_all_metrics(
    conn: duckdb.DuckDBPyConnection,
    config: PipelineConfig | None = None,
) -> list[ConstraintMetric]:
    """Compute generalization metrics for ALL constraints in session_constraint_eval.

    Uses a single query for efficiency, then processes Python-side.

    Args:
        conn: DuckDB connection with session_constraint_eval table.
        config: Optional pipeline config for stagnation threshold.

    Returns:
        List of ConstraintMetric for all constraints.
    """
    stagnation_threshold = 10
    if config is not None:
        stagnation_threshold = config.ddf.stagnation_min_firing_count

    rows = conn.execute(
        "SELECT constraint_id, evidence_json FROM session_constraint_eval ORDER BY constraint_id"
    ).fetchall()

    if not rows:
        return []

    # Group by constraint_id
    constraint_data: dict[str, list[str | None]] = {}
    for constraint_id, evidence_json_str in rows:
        constraint_data.setdefault(constraint_id, []).append(evidence_json_str)

    metrics: list[ConstraintMetric] = []
    for cid, evidence_list in constraint_data.items():
        prefixes: set[str] = set()
        for ej in evidence_list:
            prefix = _extract_scope_prefix(ej)
            prefixes.add(prefix)

        radius = len(prefixes)
        firing_count = len(evidence_list)
        is_stagnant = radius == 1 and firing_count >= stagnation_threshold

        metrics.append(
            ConstraintMetric(
                constraint_id=cid,
                radius=radius,
                firing_count=firing_count,
                is_stagnant=is_stagnant,
            )
        )

    return metrics


def write_constraint_metrics(
    conn: duckdb.DuckDBPyConnection,
    metrics: list[ConstraintMetric],
) -> int:
    """Write constraint metrics to the constraint_metrics DuckDB table.

    Uses INSERT OR REPLACE for idempotent writes.

    Args:
        conn: DuckDB connection with constraint_metrics table.
        metrics: List of ConstraintMetric to write.

    Returns:
        Count of metrics written.
    """
    for metric in metrics:
        conn.execute(
            """
            INSERT OR REPLACE INTO constraint_metrics
            (constraint_id, radius, firing_count, is_stagnant, last_computed)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                metric.constraint_id,
                metric.radius,
                metric.firing_count,
                metric.is_stagnant,
                datetime.now(timezone.utc).isoformat(),
            ],
        )

    return len(metrics)


def detect_stagnation(
    conn: duckdb.DuckDBPyConnection,
    config: PipelineConfig | None = None,
) -> list[ConstraintMetric]:
    """Return only stagnant constraints (radius=1, firing_count >= threshold).

    Floating abstractions: constraints that fire repeatedly but only in one context.

    Args:
        conn: DuckDB connection with session_constraint_eval table.
        config: Optional pipeline config for stagnation threshold.

    Returns:
        List of ConstraintMetric where is_stagnant is True.
    """
    all_metrics = compute_all_metrics(conn, config)
    return [m for m in all_metrics if m.is_stagnant]
