"""Transport Efficiency schema, computation engine, and backfill jobs.

Defines DDL for:
- transport_efficiency_sessions: per-session TE scores for human and AI subjects
- memory_candidates TE extensions: pre_te_avg, post_te_avg, te_delta columns
- memory_candidates review extensions: confidence, subject, session_id columns
  (required by the memory-review CLI for candidate display and filtering)

The transport_efficiency_sessions table stores per-session Transport Efficiency
scores, decomposed into four sub-metrics: raven_depth, crow_efficiency,
transport_speed, and trunk_quality. The composite_te is a weighted aggregate.
trunk_quality_status tracks whether the trunk quality has been human-confirmed.

Computation engine (Plan 02):
- compute_te_for_session: derives TE sub-metrics from flame_events per session
- compute_fringe_drift: binary fringe drift detection per session+subject
- write_te_rows: INSERT OR REPLACE materialization
- backfill_trunk_quality: confirms pending trunk_quality when 3+ newer sessions exist
- backfill_te_delta: computes pre/post TE rolling average for validated candidates

Exports:
    TRANSPORT_EFFICIENCY_DDL
    TRANSPORT_EFFICIENCY_INDEXES
    MEMORY_CANDIDATES_TE_EXTENSIONS
    MEMORY_CANDIDATES_REVIEW_EXTENSIONS
    create_te_schema
    compute_te_for_session
    compute_fringe_drift
    write_te_rows
    backfill_trunk_quality
    backfill_te_delta
"""

from __future__ import annotations

import hashlib

import duckdb


TRANSPORT_EFFICIENCY_DDL = """
CREATE TABLE IF NOT EXISTS transport_efficiency_sessions (
    te_id                VARCHAR PRIMARY KEY,
    session_id           VARCHAR NOT NULL,
    human_id             VARCHAR,
    subject              VARCHAR NOT NULL CHECK (subject IN ('human', 'ai')),
    raven_depth          FLOAT,
    crow_efficiency      FLOAT,
    transport_speed      FLOAT,
    trunk_quality        FLOAT,
    composite_te         FLOAT,
    trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending'
                         CHECK (trunk_quality_status IN ('pending', 'confirmed')),
    fringe_drift_rate    FLOAT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
)
"""

TRANSPORT_EFFICIENCY_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_te_session ON transport_efficiency_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_te_subject ON transport_efficiency_sessions(subject)",
]

# ALTER TABLE extensions for memory_candidates (Phase 16 TE delta tracking)
# Each tuple: (column_name, column_definition)
MEMORY_CANDIDATES_TE_EXTENSIONS: list[tuple[str, str]] = [
    ("pre_te_avg", "FLOAT"),
    ("post_te_avg", "FLOAT"),
    ("te_delta", "FLOAT"),
]

# ALTER TABLE extensions for memory_candidates (review CLI support)
# These columns are required by the memory-review CLI for candidate display.
# Added here because they are not in the base memory_candidates DDL but are
# needed for the deposit-to-review workflow.
MEMORY_CANDIDATES_REVIEW_EXTENSIONS: list[tuple[str, str]] = [
    ("confidence", "FLOAT"),
    ("subject", "VARCHAR"),
    ("session_id", "VARCHAR"),
]


def create_te_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create Transport Efficiency tables, indexes, and memory_candidates extensions.

    Must be called after create_ddf_schema() base tables are created
    (memory_candidates must exist for ALTER TABLE).

    Uses CREATE TABLE IF NOT EXISTS and try/except for ALTER TABLE,
    matching the idempotent pattern from src/pipeline/ddf/schema.py.

    Safe to call multiple times.

    Args:
        conn: DuckDB connection to create schema in.
    """
    # Create transport_efficiency_sessions table
    conn.execute(TRANSPORT_EFFICIENCY_DDL)

    # Create indexes on transport_efficiency_sessions
    for idx_sql in TRANSPORT_EFFICIENCY_INDEXES:
        conn.execute(idx_sql)

    # Extend memory_candidates with TE delta columns (idempotent)
    for col_name, col_def in MEMORY_CANDIDATES_TE_EXTENSIONS:
        try:
            conn.execute(
                f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # Column already exists (idempotent)

    # Extend memory_candidates with review CLI columns (idempotent)
    for col_name, col_def in MEMORY_CANDIDATES_REVIEW_EXTENSIONS:
        try:
            conn.execute(
                f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # Column already exists (idempotent)


# ============================================================
# TE Computation Engine (Phase 16, Plan 02)
# ============================================================


def _make_te_id(session_id: str, subject: str) -> str:
    """Generate deterministic te_id from session_id + subject.

    Returns first 16 hex chars of SHA-256 hash.
    """
    raw = f"{session_id}:{subject}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def compute_fringe_drift(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    subject: str,
) -> float | None:
    """Compute fringe drift rate for a session+subject.

    Per Q3 locked decision:
    - 0.0 if fringe events exist AND flood-confirmed Level 6+ exists (concept named)
    - 1.0 if fringe events exist but NO flood-confirmed Level 6+ (drift)
    - None if no fringe events (Levels 1-2)

    Args:
        conn: DuckDB connection.
        session_id: Session to compute for.
        subject: 'human' or 'ai'.

    Returns:
        Float (0.0 or 1.0) or None.
    """
    row = conn.execute(
        """
        SELECT
            CASE WHEN COUNT(*) FILTER (WHERE marker_level IN (1, 2)) > 0
                THEN CASE WHEN COUNT(*) FILTER (
                    WHERE marker_level >= 6 AND flood_confirmed = true
                ) > 0
                    THEN 0.0
                    ELSE 1.0
                END
                ELSE NULL
            END AS fringe_drift_rate
        FROM flame_events
        WHERE session_id = ? AND subject = ?
        """,
        [session_id, subject],
    ).fetchone()
    if row is None:
        return None
    return row[0]


def compute_te_for_session(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> list[dict]:
    """Compute Transport Efficiency for all subjects in a session.

    Derives sub-metrics from flame_events:
    - raven_depth: MAX(marker_level) / 7.0
    - crow_efficiency: fraction of events with axis_identified
    - transport_speed: fraction of events with flood_confirmed
    - trunk_quality: 0.5 sentinel (pending)

    composite_te = raven_depth * crow_efficiency * transport_speed * trunk_quality

    Args:
        conn: DuckDB connection with flame_events table populated.
        session_id: Session to compute TE for.

    Returns:
        List of row dicts ready for INSERT into transport_efficiency_sessions.
        Empty list if no flame_events for session.
    """
    rows = conn.execute(
        """
        SELECT
            session_id,
            subject,
            human_id,
            MAX(marker_level) / 7.0 AS raven_depth,
            CAST(COUNT(*) FILTER (WHERE axis_identified IS NOT NULL) AS FLOAT)
                / NULLIF(COUNT(*), 0) AS crow_efficiency,
            CAST(COUNT(*) FILTER (WHERE flood_confirmed = true) AS FLOAT)
                / NULLIF(COUNT(*), 0) AS transport_speed,
            0.5 AS trunk_quality,
            'pending' AS trunk_quality_status
        FROM flame_events
        WHERE session_id = ?
        GROUP BY session_id, subject, human_id
        """,
        [session_id],
    ).fetchall()

    result = []
    for row in rows:
        sid, subject, human_id, raven_depth, crow_eff, transport_spd, trunk_q, tq_status = row

        # Cast to float (DuckDB may return Decimal for literal values)
        raven_depth = float(raven_depth) if raven_depth is not None else 0.0
        crow_eff = float(crow_eff) if crow_eff is not None else 0.0
        transport_spd = float(transport_spd) if transport_spd is not None else 0.0
        trunk_q = float(trunk_q) if trunk_q is not None else 0.5

        composite_te = raven_depth * crow_eff * transport_spd * trunk_q
        fringe_drift = compute_fringe_drift(conn, session_id, subject)
        te_id = _make_te_id(session_id, subject)

        result.append({
            "te_id": te_id,
            "session_id": sid,
            "human_id": human_id,
            "subject": subject,
            "raven_depth": raven_depth,
            "crow_efficiency": crow_eff,
            "transport_speed": transport_spd,
            "trunk_quality": trunk_q,
            "composite_te": composite_te,
            "trunk_quality_status": tq_status,
            "fringe_drift_rate": fringe_drift,
        })

    return result


def write_te_rows(
    conn: duckdb.DuckDBPyConnection,
    rows: list[dict],
) -> int:
    """INSERT OR REPLACE TE rows into transport_efficiency_sessions.

    Args:
        conn: DuckDB connection.
        rows: List of row dicts from compute_te_for_session().

    Returns:
        Count of rows written.
    """
    if not rows:
        return 0

    count = 0
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO transport_efficiency_sessions
                (te_id, session_id, human_id, subject, raven_depth,
                 crow_efficiency, transport_speed, trunk_quality,
                 composite_te, trunk_quality_status, fringe_drift_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["te_id"],
                row["session_id"],
                row["human_id"],
                row["subject"],
                row["raven_depth"],
                row["crow_efficiency"],
                row["transport_speed"],
                row["trunk_quality"],
                row["composite_te"],
                row["trunk_quality_status"],
                row["fringe_drift_rate"],
            ],
        )
        count += 1

    return count


def backfill_trunk_quality(conn: duckdb.DuckDBPyConnection) -> int:
    """Backfill pending trunk_quality rows when 3+ newer sessions exist.

    Per Q2 locked decision: trunk_quality cannot be known at initial pipeline
    run time. This backfill checks if sufficient downstream data exists to
    compute actual trunk_quality (ratio of Level 0 axes reappearing at Level 5+
    in subsequent sessions).

    If no Level 0 events exist in the original session, trunk_quality stays 0.5.

    Args:
        conn: DuckDB connection.

    Returns:
        Count of rows backfilled (status changed to 'confirmed').
    """
    # Find pending rows
    pending = conn.execute(
        """
        SELECT te_id, session_id, subject, human_id, created_at
        FROM transport_efficiency_sessions
        WHERE trunk_quality_status = 'pending'
        """
    ).fetchall()

    if not pending:
        return 0

    count = 0
    for te_id, session_id, subject, human_id, created_at in pending:
        # Count distinct newer sessions for same (human_id, subject)
        newer_count_row = conn.execute(
            """
            SELECT COUNT(DISTINCT tes2.session_id)
            FROM transport_efficiency_sessions tes2
            WHERE tes2.human_id = ? AND tes2.subject = ?
              AND tes2.created_at > ?
            """,
            [human_id, subject, created_at],
        ).fetchone()

        newer_count = newer_count_row[0] if newer_count_row else 0
        if newer_count < 3:
            continue

        # Check if Level 0 flame_events exist for original session+subject
        level0_count_row = conn.execute(
            """
            SELECT COUNT(*)
            FROM flame_events
            WHERE session_id = ? AND subject = ? AND marker_level = 0
              AND axis_identified IS NOT NULL
            """,
            [session_id, subject],
        ).fetchone()

        level0_count = level0_count_row[0] if level0_count_row else 0
        if level0_count == 0:
            # No Level 0 events: keep trunk_quality at 0.5 but confirm status
            conn.execute(
                """
                UPDATE transport_efficiency_sessions
                SET trunk_quality_status = 'confirmed'
                WHERE te_id = ?
                """,
                [te_id],
            )
            count += 1
            continue

        # Get the next 3 session_ids (by created_at) for same human_id+subject
        next_3_sessions = conn.execute(
            """
            SELECT DISTINCT session_id
            FROM transport_efficiency_sessions
            WHERE human_id = ? AND subject = ? AND created_at > ?
            ORDER BY created_at
            LIMIT 3
            """,
            [human_id, subject, created_at],
        ).fetchall()

        next_3_ids = [r[0] for r in next_3_sessions]
        if not next_3_ids:
            continue

        # Compute trunk_quality: ratio of Level 0 axes that reappear at Level 5+
        # in the next 3 sessions
        placeholders = ", ".join(["?"] * len(next_3_ids))
        reappearance_row = conn.execute(
            f"""
            SELECT
                CAST(
                    COUNT(DISTINCT fe2.session_id) AS FLOAT
                ) / 3.0
            FROM flame_events fe_orig
            JOIN flame_events fe2
                ON fe2.axis_identified = fe_orig.axis_identified
                AND fe2.marker_level >= 5
                AND fe2.session_id != fe_orig.session_id
                AND fe2.subject = fe_orig.subject
            WHERE fe_orig.session_id = ?
                AND fe_orig.subject = ?
                AND fe_orig.marker_level = 0
                AND fe_orig.axis_identified IS NOT NULL
                AND fe2.session_id IN ({placeholders})
            """,
            [session_id, subject] + next_3_ids,
        ).fetchone()

        trunk_quality = reappearance_row[0] if reappearance_row and reappearance_row[0] is not None else 0.5

        # Cap at 1.0 (cannot exceed 100%)
        trunk_quality = min(trunk_quality, 1.0)

        # Recompute composite_te with confirmed trunk_quality
        te_row = conn.execute(
            """
            SELECT raven_depth, crow_efficiency, transport_speed
            FROM transport_efficiency_sessions
            WHERE te_id = ?
            """,
            [te_id],
        ).fetchone()

        if te_row:
            raven_d, crow_e, trans_s = te_row
            composite_te = (raven_d or 0.0) * (crow_e or 0.0) * (trans_s or 0.0) * trunk_quality
        else:
            composite_te = 0.0

        conn.execute(
            """
            UPDATE transport_efficiency_sessions
            SET trunk_quality = ?,
                trunk_quality_status = 'confirmed',
                composite_te = ?
            WHERE te_id = ?
            """,
            [trunk_quality, composite_te, te_id],
        )
        count += 1

    return count


def backfill_te_delta(conn: duckdb.DuckDBPyConnection) -> int:
    """Backfill te_delta for validated memory_candidates when sufficient data exists.

    Per Q6 locked decision: te_delta = post_te_avg - pre_te_avg, where:
    - pre_te_avg = AVG(composite_te) for AI subject, 5 sessions BEFORE created_at
    - post_te_avg = AVG(composite_te) for AI subject, 5 sessions AFTER reviewed_at

    Only computes when 5+ post-acceptance AI sessions exist.

    Args:
        conn: DuckDB connection.

    Returns:
        Count of candidates backfilled.
    """
    # Find validated candidates with NULL te_delta
    try:
        candidates = conn.execute(
            """
            SELECT id, created_at, reviewed_at
            FROM memory_candidates
            WHERE status = 'validated' AND te_delta IS NULL
            """
        ).fetchall()
    except Exception:
        return 0  # Table/columns may not exist yet

    if not candidates:
        return 0

    count = 0
    for cand_id, created_at, reviewed_at in candidates:
        if reviewed_at is None:
            continue

        # pre_te_avg: AVG(composite_te) for AI, 5 sessions BEFORE created_at
        pre_rows = conn.execute(
            """
            SELECT AVG(composite_te) AS pre_avg
            FROM (
                SELECT composite_te
                FROM transport_efficiency_sessions
                WHERE subject = 'ai' AND created_at < ?
                ORDER BY created_at DESC
                LIMIT 5
            )
            """,
            [created_at],
        ).fetchone()
        pre_te_avg = pre_rows[0] if pre_rows and pre_rows[0] is not None else None

        # Count post-acceptance AI sessions
        post_count_row = conn.execute(
            """
            SELECT COUNT(*)
            FROM transport_efficiency_sessions
            WHERE subject = 'ai' AND created_at > ?
            """,
            [reviewed_at],
        ).fetchone()

        post_count = post_count_row[0] if post_count_row else 0
        if post_count < 5:
            continue

        # post_te_avg: AVG(composite_te) for AI, 5 sessions AFTER reviewed_at
        post_rows = conn.execute(
            """
            SELECT AVG(composite_te) AS post_avg
            FROM (
                SELECT composite_te
                FROM transport_efficiency_sessions
                WHERE subject = 'ai' AND created_at > ?
                ORDER BY created_at ASC
                LIMIT 5
            )
            """,
            [reviewed_at],
        ).fetchone()
        post_te_avg = post_rows[0] if post_rows and post_rows[0] is not None else None

        if pre_te_avg is not None and post_te_avg is not None:
            te_delta = post_te_avg - pre_te_avg
        else:
            te_delta = None

        conn.execute(
            """
            UPDATE memory_candidates
            SET pre_te_avg = ?, post_te_avg = ?, te_delta = ?
            WHERE id = ?
            """,
            [pre_te_avg, post_te_avg, te_delta, cand_id],
        )
        count += 1

    return count
