"""Tests for src/pipeline/ddf/linker.py — Tier 1 stub → episode linking.

Coverage:
  - Basic exact-containment match
  - Multiple stubs across multiple segments → each linked to correct episode
  - Direct session_event_ref lookup (stubs created after the markers.py fix)
  - Stub outside any segment but within 60s near-miss window → linked
  - Stub outside near-miss window → not linked
  - Session with no human_orchestrator messages → 0 linked
  - Session with no episode_segments → 0 linked
  - Integration: linked stubs produce L3-L5 events in enrich_tier1
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import duckdb
import pytest

from src.pipeline.ddf.linker import link_stubs_to_episodes
from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.storage.schema import create_schema


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ts(offset_seconds: float = 0.0) -> datetime:
    """Return a UTC datetime relative to a fixed epoch, offset by seconds."""
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_seconds)


def _make_db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    create_ddf_schema(conn)
    return conn


def _insert_event(conn, session_id: str, event_id: str, ts: datetime, actor: str = "human_orchestrator", event_type: str = "user_msg") -> None:
    conn.execute(
        """
        INSERT INTO events (
            event_id, ts_utc, session_id, actor, event_type,
            primary_tag, primary_tag_confidence, secondary_tags,
            payload, links, risk_score, risk_factors,
            first_seen, last_seen, ingestion_count,
            source_system, source_ref
        ) VALUES (?, ?, ?, ?, ?, NULL, 0.0, '[]', '{}', '{}', 0.0, '[]',
                  ?, ?, 1, 'test', 'test:1')
        ON CONFLICT DO NOTHING
        """,
        [event_id, ts, session_id, actor, event_type, ts, ts],
    )


def _insert_segment(conn, session_id: str, segment_id: str, start_ts: datetime, end_ts: datetime) -> None:
    conn.execute(
        """
        INSERT INTO episode_segments (
            segment_id, session_id, start_event_id, end_event_id,
            start_ts, end_ts, start_trigger, end_trigger, outcome,
            event_count, event_ids, complexity, interruption_count,
            context_switches, config_hash
        ) VALUES (?, ?, 'ev_start', 'ev_end', ?, ?, 'O_DIR', 'X_PROPOSE',
                  'committed', 1, '[]', 'simple', 0, 0, 'hash1')
        ON CONFLICT DO NOTHING
        """,
        [segment_id, session_id, start_ts, end_ts],
    )


def _insert_episode(conn, session_id: str, episode_id: str, segment_id: str, reaction_label: str = "correct", outcome_type: str = "committed") -> None:
    conn.execute(
        """
        INSERT INTO episodes (
            episode_id, session_id, segment_id, timestamp, mode,
            reaction_label, reaction_confidence, outcome_type,
            observation, orchestrator_action, outcome, provenance,
            labels, source_files, config_hash, schema_version
        ) VALUES (?, ?, ?, NOW(), 'Execute', ?, 0.9, ?,
                  '{}', '{}', '{}', '{}', '[]', '[]', 'hash1', '1.0')
        ON CONFLICT DO NOTHING
        """,
        [episode_id, session_id, segment_id, reaction_label, outcome_type],
    )


def _insert_stub(conn, session_id: str, flame_event_id: str, prompt_number: int, session_event_ref: str | None = None) -> None:
    fe = FlameEvent(
        flame_event_id=flame_event_id,
        session_id=session_id,
        human_id="human1",
        prompt_number=prompt_number,
        marker_level=2,
        marker_type="L2_assertive",
        evidence_excerpt="the root cause is X",
        subject="human",
        detection_source="stub",
        session_event_ref=session_event_ref,
    )
    write_flame_events(conn, [fe])


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_basic_exact_containment():
    """Stub at prompt_number 1 links to the single episode segment."""
    conn = _make_db()
    sid = "sess-link-01"

    # One human message at t=10s
    _insert_event(conn, sid, "ev1", _ts(10))
    # One segment from t=5s to t=30s
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(30))
    _insert_episode(conn, sid, "ep1", "seg1")
    # One stub at prompt_number=1
    _insert_stub(conn, sid, "stub1", prompt_number=1)

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 1
    row = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub1'"
    ).fetchone()
    assert row[0] == "ep1"


def test_multiple_stubs_multiple_segments():
    """Two stubs at different timestamps each link to the correct episode."""
    conn = _make_db()
    sid = "sess-link-02"

    # Two human messages at t=10s and t=60s
    _insert_event(conn, sid, "ev1", _ts(10))
    _insert_event(conn, sid, "ev2", _ts(60))

    # Two segments: seg1 covers t=5-30, seg2 covers t=50-80
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(30))
    _insert_episode(conn, sid, "ep1", "seg1")
    _insert_segment(conn, sid, "seg2", _ts(50), _ts(80))
    _insert_episode(conn, sid, "ep2", "seg2")

    _insert_stub(conn, sid, "stub1", prompt_number=1)
    _insert_stub(conn, sid, "stub2", prompt_number=2)

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 2
    r1 = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub1'"
    ).fetchone()
    r2 = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub2'"
    ).fetchone()
    assert r1[0] == "ep1"
    assert r2[0] == "ep2"


def test_direct_session_event_ref_lookup():
    """session_event_ref set → direct event_id lookup, bypasses prompt_number."""
    conn = _make_db()
    sid = "sess-link-03"

    # Human message at t=10s with a specific event_id
    _insert_event(conn, sid, "direct-ev-abc", _ts(10))
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(30))
    _insert_episode(conn, sid, "ep1", "seg1")

    # Stub with prompt_number=99 (impossible by count) but correct session_event_ref
    _insert_stub(conn, sid, "stub1", prompt_number=99, session_event_ref="direct-ev-abc")

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 1
    row = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub1'"
    ).fetchone()
    assert row[0] == "ep1"


def test_near_miss_within_60s():
    """Stub 30s after segment end links to that segment (near-miss window)."""
    conn = _make_db()
    sid = "sess-link-04"

    # Human message at t=50s (30s after segment ends at t=20s)
    _insert_event(conn, sid, "ev1", _ts(50))
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(20))
    _insert_episode(conn, sid, "ep1", "seg1")

    _insert_stub(conn, sid, "stub1", prompt_number=1)

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 1
    row = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub1'"
    ).fetchone()
    assert row[0] == "ep1"


def test_outside_near_miss_window_not_linked():
    """Stub >60s after segment end is not linked."""
    conn = _make_db()
    sid = "sess-link-05"

    # Human message at t=120s (100s after segment ends at t=20s)
    _insert_event(conn, sid, "ev1", _ts(120))
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(20))
    _insert_episode(conn, sid, "ep1", "seg1")

    _insert_stub(conn, sid, "stub1", prompt_number=1)

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 0
    row = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub1'"
    ).fetchone()
    assert row[0] is None


def test_no_human_messages_returns_zero():
    """Session with no human_orchestrator messages → 0 linked."""
    conn = _make_db()
    sid = "sess-link-06"

    # Segment and episode exist but no human events
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(30))
    _insert_episode(conn, sid, "ep1", "seg1")
    _insert_stub(conn, sid, "stub1", prompt_number=1)

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 0


def test_no_episode_segments_returns_zero():
    """Session with no episode_segments → 0 linked."""
    conn = _make_db()
    sid = "sess-link-07"

    _insert_event(conn, sid, "ev1", _ts(10))
    _insert_stub(conn, sid, "stub1", prompt_number=1)
    # No segments, no episodes

    linked = link_stubs_to_episodes(conn, sid)

    assert linked == 0


def test_already_linked_stubs_skipped():
    """Stubs that already have source_episode_id are not updated."""
    conn = _make_db()
    sid = "sess-link-08"

    _insert_event(conn, sid, "ev1", _ts(10))
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(30))
    _insert_episode(conn, sid, "ep1", "seg1")

    # Insert stub and pre-link it to a different episode
    _insert_stub(conn, sid, "stub1", prompt_number=1)
    conn.execute(
        "UPDATE flame_events SET source_episode_id = 'pre-linked-ep' WHERE flame_event_id = 'stub1'"
    )

    linked = link_stubs_to_episodes(conn, sid)

    # Should not overwrite the pre-existing link
    assert linked == 0
    row = conn.execute(
        "SELECT source_episode_id FROM flame_events WHERE flame_event_id = 'stub1'"
    ).fetchone()
    assert row[0] == "pre-linked-ep"


def test_integration_linked_stubs_produce_l5_events():
    """After linking, enrich_tier1 upgrades L2 stubs to L5 for correct-reaction episodes."""
    from src.pipeline.ddf.tier2.flame_extractor import FlameEventExtractor
    from src.pipeline.models.config import PipelineConfig, load_config

    conn = _make_db()
    sid = "sess-link-09"

    # Human message at t=10s
    _insert_event(conn, sid, "ev1", _ts(10))
    _insert_segment(conn, sid, "seg1", _ts(5), _ts(30))
    _insert_episode(conn, sid, "ep1", "seg1", reaction_label="correct", outcome_type="committed")

    # L2 stub at prompt_number=1 (no source_episode_id yet)
    _insert_stub(conn, sid, "stub1", prompt_number=1)

    # Link the stub
    linked = link_stubs_to_episodes(conn, sid)
    assert linked == 1

    # Build the episodes list as enrich_tier1 expects
    # (mirrors what the runner passes from valid_episodes)
    episodes = [
        {
            "episode_id": "ep1",
            "session_id": sid,
            "reaction_label": "correct",
            "outcome_type": "committed",
            "orchestrator_action": {"scope": ["path/a", "path/b"]},
            "outcome": {},
        }
    ]

    config = load_config("data/config.yaml")
    extractor = FlameEventExtractor(config, conn)
    enriched = extractor.enrich_tier1(sid, episodes)

    # L2 + reaction='correct' → should produce L5
    assert len(enriched) >= 1
    levels = [e.marker_level for e in enriched]
    assert 5 in levels, f"Expected L5 upgrade, got levels: {levels}"
