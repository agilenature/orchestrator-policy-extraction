"""Spiral tracking with project_wisdom promotion (DDF-06).

Detects ascending scope diversity patterns on constraints (spirals) and
auto-promotes spiral candidates to project_wisdom for review.

A spiral occurs when a constraint is evaluated across increasing numbers
of distinct scope_path prefixes over successive sessions -- indicating
the constraint is genuinely generalizing rather than stagnating.

DDF-06's terminal act: auto-promoting spiral candidates to project_wisdom
for review via WisdomStore.

Exports:
    detect_spirals
    compute_spiral_depth
    get_spiral_promotion_candidates
    promote_spirals_to_wisdom
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb


def _extract_scope_prefixes_from_evidence(evidence_json_str: str | None) -> set[str]:
    """Extract scope path prefixes from evidence_json.

    Args:
        evidence_json_str: JSON string from session_constraint_eval.evidence_json.

    Returns:
        Set of scope path prefixes found, or {'root'} if none found.
    """
    if not evidence_json_str:
        return {"root"}

    try:
        evidence = json.loads(evidence_json_str) if isinstance(evidence_json_str, str) else evidence_json_str
    except (json.JSONDecodeError, TypeError):
        return {"root"}

    if isinstance(evidence, dict):
        evidence = [evidence]

    if not isinstance(evidence, list):
        return {"root"}

    prefixes: set[str] = set()
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        scope_path = entry.get("scope_path", "")
        if scope_path:
            parts = [p for p in str(scope_path).split("/") if p]
            if parts:
                prefixes.add(parts[0])

    return prefixes if prefixes else {"root"}


def detect_spirals(
    conn: duckdb.DuckDBPyConnection,
    session_id: str | None = None,
) -> list[dict]:
    """Detect constraints with ascending scope diversity across sessions.

    A spiral is detected when a constraint's scope_path prefix set
    grows monotonically (non-decreasing) across sessions ordered by eval_ts.

    The scope_path count must be strictly increasing at least once
    (not just constant).

    Args:
        conn: DuckDB connection with session_constraint_eval table.
        session_id: Optional filter to only consider sessions up to this one.

    Returns:
        List of dicts: {constraint_id, scope_path_history, spiral_length, current_radius}.
    """
    if session_id:
        rows = conn.execute(
            """
            SELECT constraint_id, session_id, evidence_json, eval_ts
            FROM session_constraint_eval
            WHERE eval_ts <= (
                SELECT MAX(eval_ts) FROM session_constraint_eval WHERE session_id = ?
            )
            ORDER BY constraint_id, eval_ts
            """,
            [session_id],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT constraint_id, session_id, evidence_json, eval_ts
            FROM session_constraint_eval
            ORDER BY constraint_id, eval_ts
            """
        ).fetchall()

    if not rows:
        return []

    # Group by constraint_id, maintaining session order
    constraint_sessions: dict[str, list[tuple[str, str | None]]] = {}
    for cid, sid, evidence_json, eval_ts in rows:
        constraint_sessions.setdefault(cid, []).append((sid, evidence_json))

    spirals: list[dict] = []

    for cid, session_list in constraint_sessions.items():
        # Build cumulative scope prefix sets per session
        cumulative_prefixes: set[str] = set()
        scope_path_history: list[set[str]] = []
        ascending = True
        had_growth = False

        for i, (sid, evidence_json) in enumerate(session_list):
            new_prefixes = _extract_scope_prefixes_from_evidence(evidence_json)
            previous_size = len(cumulative_prefixes)
            cumulative_prefixes = cumulative_prefixes | new_prefixes
            current_size = len(cumulative_prefixes)

            scope_path_history.append(set(cumulative_prefixes))

            # Skip growth check on first session (baseline)
            if i == 0:
                continue

            if current_size < previous_size:
                ascending = False
                break
            if current_size > previous_size:
                had_growth = True

        if ascending and had_growth and len(scope_path_history) >= 2:
            spirals.append({
                "constraint_id": cid,
                "scope_path_history": [sorted(s) for s in scope_path_history],
                "spiral_length": len(scope_path_history),
                "current_radius": len(cumulative_prefixes),
            })

    return spirals


def compute_spiral_depth(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> int:
    """Compute spiral depth for a session from flame_events marker levels.

    Python-side computation (not SQL window functions):
    - Fetch all flame_events for session_id ordered by created_at.
    - Find the longest ascending streak of marker_levels.

    Used by IntelligenceProfile and CLI.

    Args:
        conn: DuckDB connection with flame_events table.
        session_id: Session to compute depth for.

    Returns:
        Length of the longest ascending marker_level streak.
    """
    try:
        rows = conn.execute(
            """
            SELECT marker_level
            FROM flame_events
            WHERE session_id = ?
            ORDER BY created_at
            """,
            [session_id],
        ).fetchall()
    except Exception:
        return 0

    if not rows:
        return 0

    levels = [row[0] for row in rows]
    max_streak = 0
    current_streak = 0

    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1]:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    # A streak of N transitions means N+1 ascending levels, but
    # we report the streak length (number of ascending transitions)
    # plus 1 to represent the count of ascending levels.
    # However, the plan says "return length of the longest ascending streak"
    # which means transitions. But if there are 0 transitions and 1+ levels,
    # depth is 0 (no ascending movement). If L1,L2,L3 -> 2 transitions -> depth=2.
    # Actually re-reading the plan: "L1, L2, L3 streak -> depth=3" --
    # so depth counts the levels, not transitions. So add 1 if there's a streak.
    if max_streak > 0:
        return max_streak + 1

    return 0


def get_spiral_promotion_candidates(
    conn: duckdb.DuckDBPyConnection,
    min_spiral_length: int = 3,
) -> list[str]:
    """Return constraint_ids with spiral_length >= min_spiral_length.

    Args:
        conn: DuckDB connection with session_constraint_eval table.
        min_spiral_length: Minimum spiral length to qualify.

    Returns:
        List of constraint_ids that qualify for promotion.
    """
    spirals = detect_spirals(conn)
    return [
        s["constraint_id"]
        for s in spirals
        if s["spiral_length"] >= min_spiral_length
    ]


def promote_spirals_to_wisdom(
    conn: duckdb.DuckDBPyConnection,
    db_path: Path,
    min_spiral_length: int = 3,
) -> int:
    """Promote spiral candidates to project_wisdom via WisdomStore.

    For each constraint with spiral_length >= min_spiral_length:
    - Read constraint details from constraints table or constraints.json
    - Create a WisdomEntity with entity_type='breakthrough'
    - Upsert into project_wisdom (avoids duplicate errors on re-run)

    Uses lazy import of WisdomStore and WisdomEntity to keep the dependency
    optional at module-import time.

    Args:
        conn: DuckDB connection with session_constraint_eval table.
        db_path: Path to DuckDB database file for WisdomStore.
        min_spiral_length: Minimum spiral length to qualify.

    Returns:
        Count of candidates promoted.
    """
    spirals = detect_spirals(conn)
    candidates = [s for s in spirals if s["spiral_length"] >= min_spiral_length]

    if not candidates:
        return 0

    # Lazy import to keep wisdom dependency optional
    from src.pipeline.wisdom.models import WisdomEntity
    from src.pipeline.wisdom.store import WisdomStore

    store = WisdomStore(db_path)
    promoted = 0

    for spiral in candidates:
        cid = spiral["constraint_id"]
        spiral_length = spiral["spiral_length"]
        scope_path_history = spiral["scope_path_history"]

        # Try to get constraint text from DuckDB constraints table or use ID
        constraint_text = cid
        try:
            row = conn.execute(
                "SELECT text FROM constraints WHERE constraint_id = ?",
                [cid],
            ).fetchone()
            if row:
                constraint_text = row[0]
        except Exception:
            pass  # Table may not exist; use constraint_id as fallback

        title = f"Spiral: {constraint_text[:80]}"
        description = (
            f"Constraint {cid} showed ascending scope diversity across "
            f"{spiral_length} sessions. Scope path history: "
            f"{json.dumps(scope_path_history)}. "
            f"Auto-promoted from DDF-06 spiral tracking."
        )

        # Flatten all scope paths from history
        all_paths: list[str] = []
        for path_set in scope_path_history:
            for p in path_set:
                if p not in all_paths:
                    all_paths.append(p)

        entity = WisdomEntity.create(
            entity_type="breakthrough",
            title=title,
            description=description,
            context_tags=["ddf-06", "spiral-promotion", "auto-detected"],
            scope_paths=all_paths,
            confidence=0.7,
            source_phase=15,
            metadata={
                "source_constraint_id": cid,
                "spiral_length": spiral_length,
                "promotion_source": "ddf_spiral_tracking",
            },
        )

        store.upsert(entity)
        promoted += 1

    return promoted
