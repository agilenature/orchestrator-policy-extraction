"""Event normalizer -- merge, deduplicate, and temporally align events.

Merges JSONL events and git events into a single unified stream with:
- Temporal alignment (Q1): Explicit commit-hash links preferred (confidence=1.0),
  falls back to +/-2s windowing (confidence=0.8), or no link (confidence=0.0).
- Deduplication (Q14): Deterministic event_id eliminates duplicates.
- Temporal anomaly handling (Q18): Deterministic microsecond noise for
  duplicate timestamps.
- Ingestion metadata (Q13): first_seen, last_seen, ingestion_count tracking.

Exports:
    normalize_events: Merge, align, and deduplicate events from all sources
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from src.pipeline.models.config import PipelineConfig
from src.pipeline.models.events import CanonicalEvent


def normalize_events(
    jsonl_events: list[CanonicalEvent],
    git_events: list[CanonicalEvent],
    config: PipelineConfig,
) -> list[CanonicalEvent]:
    """Merge, temporally align, and deduplicate events from all sources.

    Pipeline:
    1. Temporal alignment: Link git events to JSONL events by commit hash
       or timestamp windowing.
    2. Merge: Combine all events into a single list.
    3. Sort: By ts_utc with deterministic microsecond noise for ties (Q18).
    4. Deduplicate: Remove events with duplicate event_ids (Q14).

    Args:
        jsonl_events: Events from Claude Code JSONL adapter.
        git_events: Events from git history adapter.
        config: Pipeline configuration with temporal alignment settings.

    Returns:
        Sorted, deduplicated list of CanonicalEvent instances.
    """
    causal_window = config.temporal.causal_window_seconds
    link_confidence = config.temporal.link_confidence

    # Step 1: Temporal alignment of git events
    aligned_git_events = _align_git_events(
        jsonl_events, git_events, causal_window, link_confidence
    )

    # Step 2: Merge all events
    all_events = list(jsonl_events) + aligned_git_events

    # Step 3: Handle temporal anomalies (Q18) -- add deterministic
    # microsecond noise for duplicate timestamps
    all_events = _handle_temporal_anomalies(all_events)

    # Step 4: Sort by timestamp (stable sort preserves line order)
    all_events.sort(key=lambda e: e.ts_utc)

    # Step 5: Deduplicate by event_id (Q14)
    deduped = _deduplicate(all_events)

    logger.info(
        "Normalized {} events (from {} JSONL + {} git, {} after dedup)",
        len(deduped),
        len(jsonl_events),
        len(git_events),
        len(deduped),
    )

    return deduped


def _align_git_events(
    jsonl_events: list[CanonicalEvent],
    git_events: list[CanonicalEvent],
    causal_window_seconds: int,
    link_confidence: dict[str, float],
) -> list[CanonicalEvent]:
    """Temporally align git events with JSONL events.

    Hybrid approach (Q1 locked decision):
    1. Explicit link: Find JSONL tool_result with matching commit_hash
       (confidence=1.0). Set git event timestamp to tool_result + 1ms.
    2. Windowing fallback: Find JSONL tool_use with 'git commit' in text
       within +/-causal_window_seconds (confidence=0.8). Set git event
       timestamp to matched event + 1ms.
    3. No match: Keep original timestamp (confidence=0.0).
    """
    if not git_events:
        return []

    # Build index of JSONL events by commit_hash for O(1) lookup
    commit_hash_index: dict[str, CanonicalEvent] = {}
    for event in jsonl_events:
        ch = event.links.get("commit_hash")
        if ch:
            commit_hash_index[ch] = event

    # Build list of JSONL tool_use events mentioning git commit
    git_tool_uses: list[CanonicalEvent] = []
    for event in jsonl_events:
        if event.event_type == "tool_use":
            text = event.payload.get("common", {}).get("text", "")
            tool_name = event.payload.get("common", {}).get("tool_name", "")
            if "git commit" in text.lower() or "git commit" in tool_name.lower():
                git_tool_uses.append(event)

    aligned: list[CanonicalEvent] = []
    explicit_count = 0
    windowing_count = 0
    no_link_count = 0

    for git_event in git_events:
        git_hash = git_event.links.get("commit_hash", "")

        # Strategy 1: Explicit link via commit hash
        matched_event = commit_hash_index.get(git_hash)
        if not matched_event and len(git_hash) >= 7:
            # Try prefix match (short hash -> full hash or vice versa)
            for ch, ev in commit_hash_index.items():
                if ch.startswith(git_hash) or git_hash.startswith(ch):
                    matched_event = ev
                    break

        if matched_event:
            new_ts = matched_event.ts_utc + timedelta(milliseconds=1)
            new_links = dict(git_event.links)
            new_links["alignment_confidence"] = link_confidence.get("explicit", 1.0)
            new_links["aligned_to_event"] = matched_event.event_id
            aligned.append(
                _replace_event(git_event, ts_utc=new_ts, links=new_links)
            )
            explicit_count += 1
            continue

        # Strategy 2: Windowing fallback
        window = timedelta(seconds=causal_window_seconds)
        best_match: CanonicalEvent | None = None
        best_delta = timedelta.max

        for tool_event in git_tool_uses:
            delta = abs(git_event.ts_utc - tool_event.ts_utc)
            if delta <= window and delta < best_delta:
                best_delta = delta
                best_match = tool_event

        if best_match:
            new_ts = best_match.ts_utc + timedelta(milliseconds=1)
            new_links = dict(git_event.links)
            new_links["alignment_confidence"] = link_confidence.get("windowing", 0.8)
            new_links["aligned_to_event"] = best_match.event_id
            aligned.append(
                _replace_event(git_event, ts_utc=new_ts, links=new_links)
            )
            windowing_count += 1
            continue

        # Strategy 3: No match -- keep original timestamp
        new_links = dict(git_event.links)
        new_links["alignment_confidence"] = link_confidence.get("none", 0.0)
        aligned.append(_replace_event(git_event, links=new_links))
        no_link_count += 1

    logger.info(
        "Temporal alignment: {} explicit, {} windowing, {} unlinked (of {} git events)",
        explicit_count,
        windowing_count,
        no_link_count,
        len(git_events),
    )

    return aligned


def _handle_temporal_anomalies(
    events: list[CanonicalEvent],
) -> list[CanonicalEvent]:
    """Add deterministic microsecond noise for duplicate timestamps (Q18).

    For events with identical timestamps, add hash(event_id) % 1000
    microseconds to create a deterministic but unique ordering.
    """
    # Group events by timestamp
    ts_groups: dict[datetime, list[int]] = {}
    for i, event in enumerate(events):
        ts_groups.setdefault(event.ts_utc, []).append(i)

    # Find groups with duplicates
    result = list(events)
    anomaly_count = 0

    for ts, indices in ts_groups.items():
        if len(indices) <= 1:
            continue

        anomaly_count += len(indices)
        for idx in indices:
            event = events[idx]
            # Deterministic noise: hash of event_id modulo 1000 microseconds
            noise_us = int(
                hashlib.sha256(event.event_id.encode()).hexdigest()[:8], 16
            ) % 1000
            new_ts = event.ts_utc + timedelta(microseconds=noise_us)
            new_links = dict(event.links)
            new_links["temporal_anomaly"] = "duplicate_timestamp"
            result[idx] = _replace_event(event, ts_utc=new_ts, links=new_links)

    if anomaly_count > 0:
        logger.debug(
            "Applied deterministic microsecond noise to {} events with duplicate timestamps",
            anomaly_count,
        )

    return result


def _deduplicate(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
    """Remove events with duplicate event_ids (Q14).

    Keeps the first occurrence. Logs duplicates at DEBUG level.
    Warns if duplicate rate >5% (Q15).
    """
    seen: set[str] = set()
    unique: list[CanonicalEvent] = []
    duplicate_count = 0

    for event in events:
        if event.event_id in seen:
            duplicate_count += 1
            logger.debug(
                "Duplicate event_id={} from source={} at ts={}",
                event.event_id,
                event.source_system,
                event.ts_utc.isoformat(),
            )
            continue
        seen.add(event.event_id)
        unique.append(event)

    total = len(events)
    if total > 0:
        dup_rate = duplicate_count / total
        if dup_rate > 0.05:
            logger.warning(
                "High duplicate rate: {}/{} ({:.1%}) events were duplicates",
                duplicate_count,
                total,
                dup_rate,
            )
        elif duplicate_count > 0:
            logger.debug(
                "Deduplicated {}/{} events ({:.1%})",
                duplicate_count,
                total,
                dup_rate,
            )

    return unique


def _replace_event(
    event: CanonicalEvent,
    ts_utc: datetime | None = None,
    links: dict[str, Any] | None = None,
) -> CanonicalEvent:
    """Create a new CanonicalEvent with replaced fields.

    Since CanonicalEvent is frozen (immutable), we must create a new
    instance with the desired changes.
    """
    data = event.model_dump()
    if ts_utc is not None:
        data["ts_utc"] = ts_utc
    if links is not None:
        data["links"] = links
    return CanonicalEvent(**data)
