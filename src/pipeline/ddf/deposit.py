"""Memory candidates deposit function for DDF Detection Substrate.

Deposits CCD-format (ccd_axis, scope_rule, flood_example) entries
into the memory_candidates table with soft deduplication on the
(ccd_axis, scope_rule) pair, normalized for case and whitespace.

Duplicate deposits increment detection_count rather than creating
new rows -- this tracks how many times the same axis+scope has been
independently detected.

Exports:
    deposit_to_memory_candidates
    mark_deposited
"""

from __future__ import annotations

import hashlib

import duckdb


def deposit_to_memory_candidates(
    conn: duckdb.DuckDBPyConnection,
    ccd_axis: str,
    scope_rule: str,
    flood_example: str,
    source_flame_event_id: str | None = None,
    pipeline_component: str = "ddf_tier2",
    fidelity: int = 2,
) -> str | None:
    """Deposit a CCD entry to memory_candidates with soft dedup.

    Deduplicates on (ccd_axis, scope_rule) after case+whitespace
    normalization. If a matching entry exists, increments its
    detection_count and returns None. Otherwise creates a new entry
    and returns the candidate_id.

    Args:
        conn: DuckDB connection with memory_candidates table.
        ccd_axis: The CCD axis name (e.g. 'ground-truth-pointer').
        scope_rule: The scope rule text.
        flood_example: The flood example text.
        source_flame_event_id: ID of the FlameEvent that triggered deposit.
        pipeline_component: Component that produced this candidate.
        fidelity: Fidelity level (default 2).

    Returns:
        candidate_id if new entry created, None if existing updated.
    """
    # Normalize for dedup comparison
    norm_axis = ccd_axis.strip().lower()
    norm_scope = scope_rule.strip().lower()

    # Check for existing entry
    existing = conn.execute(
        """
        SELECT id FROM memory_candidates
        WHERE LOWER(TRIM(ccd_axis)) = ? AND LOWER(TRIM(scope_rule)) = ?
        """,
        [norm_axis, norm_scope],
    ).fetchone()

    if existing:
        # Update detection_count
        conn.execute(
            """
            UPDATE memory_candidates SET detection_count = detection_count + 1
            WHERE LOWER(TRIM(ccd_axis)) = ? AND LOWER(TRIM(scope_rule)) = ?
            """,
            [norm_axis, norm_scope],
        )
        return None

    # Generate deterministic ID
    key = (ccd_axis + scope_rule + (source_flame_event_id or "")).encode("utf-8")
    candidate_id = hashlib.sha256(key).hexdigest()[:16]

    conn.execute(
        """
        INSERT INTO memory_candidates (
            id, source_instance_id, ccd_axis, scope_rule, flood_example,
            pipeline_component, status, source_flame_event_id, fidelity,
            detection_count
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, 1)
        """,
        [
            candidate_id,
            source_flame_event_id,
            ccd_axis,
            scope_rule,
            flood_example,
            pipeline_component,
            source_flame_event_id,
            fidelity,
        ],
    )

    return candidate_id


def mark_deposited(
    conn: duckdb.DuckDBPyConnection,
    flame_event_id: str,
) -> None:
    """Mark a flame_event as deposited to memory_candidates.

    Sets the deposited_to_candidates flag to TRUE for the given
    flame_event_id.

    Args:
        conn: DuckDB connection with flame_events table.
        flame_event_id: ID of the flame event to mark.
    """
    conn.execute(
        "UPDATE flame_events SET deposited_to_candidates = TRUE "
        "WHERE flame_event_id = ?",
        [flame_event_id],
    )
