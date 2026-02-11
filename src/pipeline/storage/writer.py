"""DuckDB event and segment writer with idempotent upsert.

Writes canonical events and episode segments to DuckDB tables with
INSERT ... ON CONFLICT(event_id) DO UPDATE behavior for safe
re-ingestion. Re-ingesting the same data increments ingestion_count
and updates last_seen without creating duplicates.

Exports:
    write_events: Write events to DuckDB with idempotent upsert
    write_segments: Write episode segments to DuckDB
    read_events: Query events from DuckDB with optional filtering
    get_event_stats: Aggregate statistics about stored events
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import duckdb
from loguru import logger

from src.pipeline.models.events import CanonicalEvent, TaggedEvent
from src.pipeline.models.segments import EpisodeSegment


def write_events(
    conn: duckdb.DuckDBPyConnection,
    events: list[CanonicalEvent],
    tagged_events: list[TaggedEvent] | None = None,
) -> dict[str, int]:
    """Write canonical events to DuckDB with idempotent upsert.

    Uses INSERT ... ON CONFLICT(event_id) DO UPDATE to safely handle
    re-ingestion. On conflict, updates last_seen timestamp and
    increments ingestion_count.

    If tagged_events are provided, includes primary_tag and
    primary_tag_confidence columns. Otherwise, those columns are NULL.

    Args:
        conn: DuckDB connection with events table created.
        events: List of CanonicalEvent instances to write.
        tagged_events: Optional tagged versions of events (for tag data).

    Returns:
        Stats dict: {inserted: N, updated: N, total: N}
    """
    if not events:
        return {"inserted": 0, "updated": 0, "total": 0}

    # Build tag lookup if tagged events provided
    tag_lookup: dict[str, TaggedEvent] = {}
    if tagged_events:
        for te in tagged_events:
            tag_lookup[te.event.event_id] = te

    # Get initial count to calculate inserts vs updates
    initial_count = conn.execute("SELECT count(*) FROM events").fetchone()[0]

    # Build batch data for INSERT
    rows: list[tuple] = []
    for event in events:
        # Get tag data if available
        te = tag_lookup.get(event.event_id)
        primary_tag = None
        primary_tag_confidence = None
        secondary_tags_json = None

        if te and te.primary:
            primary_tag = te.primary.label
            primary_tag_confidence = te.primary.confidence
        if te and te.secondaries:
            secondary_tags_json = json.dumps(
                [{"label": c.label, "confidence": c.confidence} for c in te.secondaries]
            )

        rows.append(
            (
                event.event_id,
                event.ts_utc.isoformat(),
                event.session_id,
                event.actor,
                event.event_type,
                primary_tag,
                primary_tag_confidence,
                secondary_tags_json,
                json.dumps(event.payload),
                json.dumps(event.links),
                event.risk_score,
                json.dumps(event.risk_factors),
                event.source_system,
                event.source_ref,
            )
        )

    # Use batch INSERT with ON CONFLICT for idempotent upsert
    # DuckDB supports INSERT OR IGNORE and INSERT OR REPLACE, but for
    # updating specific columns on conflict, we use a staging table approach
    _batch_upsert(conn, rows)

    # Calculate stats
    final_count = conn.execute("SELECT count(*) FROM events").fetchone()[0]
    inserted = final_count - initial_count
    updated = len(events) - inserted

    if updated > 0:
        dup_rate = updated / len(events)
        if dup_rate > 0.05:
            logger.warning(
                "High duplicate rate in write: {}/{} ({:.1%}) were updates",
                updated,
                len(events),
                dup_rate,
            )
        else:
            logger.debug(
                "Write: {} inserts, {} updates (duplicates)",
                inserted,
                updated,
            )

    logger.info(
        "Wrote {} events ({} inserted, {} updated)",
        len(events),
        inserted,
        updated,
    )

    return {"inserted": inserted, "updated": updated, "total": len(events)}


def _batch_upsert(
    conn: duckdb.DuckDBPyConnection,
    rows: list[tuple],
) -> None:
    """Perform batch upsert using a staging table.

    DuckDB does not support INSERT ... ON CONFLICT ... DO UPDATE with
    positional parameters in all versions. We use a staging table pattern:
    1. Insert into a temp staging table
    2. Update existing rows in events from staging
    3. Insert new rows from staging
    """
    if not rows:
        return

    # Create staging table
    conn.execute("DROP TABLE IF EXISTS _staging_events")
    conn.execute("""
        CREATE TEMPORARY TABLE _staging_events (
            event_id VARCHAR,
            ts_utc VARCHAR,
            session_id VARCHAR,
            actor VARCHAR,
            event_type VARCHAR,
            primary_tag VARCHAR,
            primary_tag_confidence FLOAT,
            secondary_tags VARCHAR,
            payload VARCHAR,
            links VARCHAR,
            risk_score FLOAT,
            risk_factors VARCHAR,
            source_system VARCHAR,
            source_ref VARCHAR
        )
    """)

    # Batch insert into staging
    conn.executemany(
        """
        INSERT INTO _staging_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    # Update existing events: increment ingestion_count, update last_seen
    conn.execute("""
        UPDATE events
        SET last_seen = current_timestamp,
            ingestion_count = events.ingestion_count + 1
        WHERE event_id IN (SELECT event_id FROM _staging_events)
    """)

    # Insert new events (those not already in events table)
    conn.execute("""
        INSERT INTO events (
            event_id, ts_utc, session_id, actor, event_type,
            primary_tag, primary_tag_confidence, secondary_tags,
            payload, links, risk_score, risk_factors,
            source_system, source_ref
        )
        SELECT
            s.event_id,
            CAST(s.ts_utc AS TIMESTAMPTZ),
            s.session_id,
            s.actor,
            s.event_type,
            s.primary_tag,
            s.primary_tag_confidence,
            CAST(s.secondary_tags AS JSON),
            CAST(s.payload AS JSON),
            CAST(s.links AS JSON),
            s.risk_score,
            CAST(s.risk_factors AS JSON),
            s.source_system,
            s.source_ref
        FROM _staging_events s
        WHERE s.event_id NOT IN (SELECT event_id FROM events)
    """)

    # Clean up
    conn.execute("DROP TABLE IF EXISTS _staging_events")


def write_segments(
    conn: duckdb.DuckDBPyConnection,
    segments: list[EpisodeSegment],
) -> dict[str, int]:
    """Write episode segments to DuckDB with idempotent upsert.

    Similar to write_events, uses staging table for idempotent upsert
    on segment_id.

    Args:
        conn: DuckDB connection with episode_segments table created.
        segments: List of EpisodeSegment instances to write.

    Returns:
        Stats dict: {inserted: N, updated: N, total: N}
    """
    if not segments:
        return {"inserted": 0, "updated": 0, "total": 0}

    initial_count = conn.execute(
        "SELECT count(*) FROM episode_segments"
    ).fetchone()[0]

    # Create staging table
    conn.execute("DROP TABLE IF EXISTS _staging_segments")
    conn.execute("""
        CREATE TEMPORARY TABLE _staging_segments (
            segment_id VARCHAR,
            session_id VARCHAR,
            start_event_id VARCHAR,
            end_event_id VARCHAR,
            start_ts VARCHAR,
            end_ts VARCHAR,
            start_trigger VARCHAR,
            end_trigger VARCHAR,
            outcome VARCHAR,
            event_count INTEGER,
            event_ids VARCHAR,
            complexity VARCHAR,
            interruption_count INTEGER,
            context_switches INTEGER,
            config_hash VARCHAR
        )
    """)

    rows: list[tuple] = []
    for seg in segments:
        rows.append(
            (
                seg.segment_id,
                seg.session_id,
                seg.start_event_id,
                seg.end_event_id,
                seg.start_ts.isoformat() if seg.start_ts else None,
                seg.end_ts.isoformat() if seg.end_ts else None,
                seg.start_trigger,
                seg.end_trigger,
                seg.outcome,
                seg.event_count,
                json.dumps(seg.events),
                seg.complexity,
                seg.interruption_count,
                seg.context_switches,
                seg.config_hash,
            )
        )

    conn.executemany(
        "INSERT INTO _staging_segments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )

    # Insert new segments only (no update on re-insert for segments)
    conn.execute("""
        INSERT INTO episode_segments (
            segment_id, session_id, start_event_id, end_event_id,
            start_ts, end_ts, start_trigger, end_trigger,
            outcome, event_count, event_ids,
            complexity, interruption_count, context_switches, config_hash
        )
        SELECT
            s.segment_id, s.session_id, s.start_event_id, s.end_event_id,
            CAST(s.start_ts AS TIMESTAMPTZ), CAST(s.end_ts AS TIMESTAMPTZ),
            s.start_trigger, s.end_trigger,
            s.outcome, s.event_count, CAST(s.event_ids AS JSON),
            s.complexity, s.interruption_count, s.context_switches, s.config_hash
        FROM _staging_segments s
        WHERE s.segment_id NOT IN (SELECT segment_id FROM episode_segments)
    """)

    conn.execute("DROP TABLE IF EXISTS _staging_segments")

    final_count = conn.execute(
        "SELECT count(*) FROM episode_segments"
    ).fetchone()[0]
    inserted = final_count - initial_count

    logger.info("Wrote {} segments ({} new)", len(segments), inserted)

    return {
        "inserted": inserted,
        "updated": len(segments) - inserted,
        "total": len(segments),
    }


def read_events(
    conn: duckdb.DuckDBPyConnection,
    session_id: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Query events from DuckDB with optional filtering.

    Returns events as plain dicts with JSON columns parsed back to
    Python objects.

    Args:
        conn: DuckDB connection with events table.
        session_id: Optional filter by session_id.
        tag: Optional filter by primary_tag.

    Returns:
        List of event dicts.
    """
    where_parts: list[str] = []
    params: list[Any] = []

    if session_id:
        where_parts.append("session_id = ?")
        params.append(session_id)
    if tag:
        where_parts.append("primary_tag = ?")
        params.append(tag)

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    rows = conn.execute(
        f"""
        SELECT
            event_id, ts_utc, session_id, actor, event_type,
            primary_tag, primary_tag_confidence, secondary_tags,
            payload, links, risk_score, risk_factors,
            first_seen, last_seen, ingestion_count,
            source_system, source_ref
        FROM events
        {where_clause}
        ORDER BY ts_utc ASC
        """,
        params,
    ).fetchall()

    column_names = [
        "event_id",
        "ts_utc",
        "session_id",
        "actor",
        "event_type",
        "primary_tag",
        "primary_tag_confidence",
        "secondary_tags",
        "payload",
        "links",
        "risk_score",
        "risk_factors",
        "first_seen",
        "last_seen",
        "ingestion_count",
        "source_system",
        "source_ref",
    ]

    results = []
    for row in rows:
        d = dict(zip(column_names, row))
        # Parse JSON columns back to Python objects
        for json_col in ("secondary_tags", "payload", "links", "risk_factors"):
            val = d.get(json_col)
            if isinstance(val, str):
                try:
                    d[json_col] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        results.append(d)

    return results


def get_event_stats(
    conn: duckdb.DuckDBPyConnection,
) -> dict[str, Any]:
    """Return aggregate statistics about stored events.

    Provides counts by actor, event_type, primary_tag, and
    overall totals.

    Args:
        conn: DuckDB connection with events table.

    Returns:
        Stats dict with total, by_actor, by_type, by_tag, duplicate_count.
    """
    total = conn.execute("SELECT count(*) FROM events").fetchone()[0]

    by_actor = dict(
        conn.execute(
            "SELECT actor, count(*) FROM events GROUP BY actor ORDER BY count(*) DESC"
        ).fetchall()
    )

    by_type = dict(
        conn.execute(
            "SELECT event_type, count(*) FROM events GROUP BY event_type ORDER BY count(*) DESC"
        ).fetchall()
    )

    by_tag = dict(
        conn.execute(
            "SELECT COALESCE(primary_tag, 'untagged'), count(*) FROM events GROUP BY primary_tag ORDER BY count(*) DESC"
        ).fetchall()
    )

    # Count events that were re-ingested (ingestion_count > 1)
    duplicate_count = conn.execute(
        "SELECT count(*) FROM events WHERE ingestion_count > 1"
    ).fetchone()[0]

    return {
        "total": total,
        "by_actor": by_actor,
        "by_type": by_type,
        "by_tag": by_tag,
        "duplicate_count": duplicate_count,
    }
