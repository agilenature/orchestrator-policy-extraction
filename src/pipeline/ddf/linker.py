"""Tier 1→Tier 2 episode linker: assigns source_episode_id to flame event stubs.

Tier 1 detect_markers() creates flame event stubs without source_episode_id
because it runs as a pure text scanner without episode context. This module
provides link_stubs_to_episodes() which runs after episodes are written to
DuckDB and assigns source_episode_id to each stub by matching the stub's
triggering event (by timestamp) to the episode_segment that contains it.

Matching strategy:
  1. Exact containment: stub event ts falls within [segment.start_ts, segment.end_ts].
  2. Near-miss fallback: stub event ts falls within 60s after segment.end_ts
     (handles reaction messages that arrive just after episode closure).

If neither strategy finds a match the stub is left unlinked (source_episode_id
remains NULL). Unlinked stubs still produce valid Tier 2 events at their
original L0-L2 level; the episode-dependent upgrade rules simply don't fire.

Exports:
    link_stubs_to_episodes
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import duckdb
from loguru import logger

# Maximum seconds after a segment ends to still consider a message as belonging
# to that episode (covers reaction messages that arrive just after the segment
# closes).
_NEAR_MISS_WINDOW_SECONDS = 60


def link_stubs_to_episodes(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> int:
    """Assign source_episode_id to Tier 1 stubs by timestamp matching.

    Reads Tier 1 stubs (detection_source='stub', source_episode_id IS NULL)
    for the session, finds the triggering event by prompt_number or
    session_event_ref, looks up the episode_segment that contains that
    event's timestamp, and UPDATEs source_episode_id on the stub.

    Args:
        conn: DuckDB connection with flame_events, events,
              episode_segments, episodes tables.
        session_id: Session to link stubs for.

    Returns:
        Number of stubs that were successfully linked to episodes.
    """
    # Get stubs needing linking
    stubs = conn.execute(
        """
        SELECT flame_event_id, prompt_number, session_event_ref
        FROM flame_events
        WHERE session_id = ?
          AND detection_source = 'stub'
          AND source_episode_id IS NULL
        ORDER BY prompt_number ASC
        """,
        [session_id],
    ).fetchall()

    if not stubs:
        return 0

    # Get human_orchestrator messages ordered by ts_utc
    # (must match the ordering in detect_markers → prompt_number assignment)
    hm_rows = conn.execute(
        """
        SELECT event_id, ts_utc
        FROM events
        WHERE session_id = ?
          AND actor = 'human_orchestrator'
          AND event_type IN ('user_msg', 'human_msg', 'message')
        ORDER BY ts_utc ASC
        """,
        [session_id],
    ).fetchall()

    if not hm_rows:
        logger.debug("No human_orchestrator messages for session {}", session_id)
        return 0

    # prompt_number → (event_id, ts_utc), 1-indexed matching detect_markers
    pn_map: dict[int, tuple[str, Any]] = {
        i + 1: (row[0], row[1]) for i, row in enumerate(hm_rows)
    }

    # Build event_id → ts_utc index for direct session_event_ref lookups
    eid_to_ts: dict[str, Any] = {row[0]: row[1] for row in hm_rows}

    # Get episode_segments with their episode metadata for this session
    segments = conn.execute(
        """
        SELECT es.segment_id, es.start_ts, es.end_ts, ep.episode_id
        FROM episode_segments es
        JOIN episodes ep
          ON ep.session_id = es.session_id
         AND ep.segment_id = es.segment_id
        WHERE es.session_id = ?
        ORDER BY es.start_ts ASC
        """,
        [session_id],
    ).fetchall()

    if not segments:
        logger.debug("No episode_segments for session {}", session_id)
        return 0

    linked = 0
    for flame_event_id, prompt_number, session_event_ref in stubs:
        # Resolve the triggering event's timestamp
        ts = _resolve_timestamp(session_event_ref, prompt_number, pn_map, eid_to_ts)
        if ts is None:
            continue

        episode_id = _find_containing_episode(ts, segments)
        if episode_id is None:
            continue

        conn.execute(
            "UPDATE flame_events SET source_episode_id = ? WHERE flame_event_id = ?",
            [episode_id, flame_event_id],
        )
        linked += 1

    logger.debug(
        "Linked {}/{} stubs to episodes for session {}",
        linked,
        len(stubs),
        session_id,
    )
    return linked


def _resolve_timestamp(
    session_event_ref: str | None,
    prompt_number: int,
    pn_map: dict[int, tuple[str, Any]],
    eid_to_ts: dict[str, Any],
) -> Any | None:
    """Return the timestamp of the event that triggered this stub.

    Tries session_event_ref (direct event_id lookup) first; falls back to
    prompt_number index lookup.
    """
    if session_event_ref and session_event_ref in eid_to_ts:
        return eid_to_ts[session_event_ref]
    pair = pn_map.get(prompt_number)
    return pair[1] if pair else None


def _find_containing_episode(
    ts: Any,
    segments: list[tuple],
) -> str | None:
    """Return the episode_id of the segment that contains or is nearest to ts.

    Args:
        ts: Timestamp of the triggering event (timezone-aware datetime).
        segments: List of (segment_id, start_ts, end_ts, episode_id) tuples
                  ordered by start_ts ASC.

    Returns:
        episode_id of the best-matching segment, or None if no match found
        within the near-miss window.
    """
    # Pass 1: exact containment
    for _seg_id, start_ts, end_ts, episode_id in segments:
        if start_ts <= ts <= end_ts:
            return episode_id

    # Pass 2: near-miss — most recent segment that ended ≤60s before ts
    best_episode_id = None
    best_delta: float | None = None
    window = timedelta(seconds=_NEAR_MISS_WINDOW_SECONDS)

    for _seg_id, _start_ts, end_ts, episode_id in segments:
        if end_ts <= ts:
            delta = (ts - end_ts).total_seconds()
            if delta <= _NEAR_MISS_WINDOW_SECONDS:
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_episode_id = episode_id

    return best_episode_id
