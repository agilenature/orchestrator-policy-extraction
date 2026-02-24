"""Tests for IntelligenceProfile aggregation (DDF-04, Phase 15-05).

Covers:
- Basic aggregation: flame_frequency, avg_marker_level, max_marker_level
- Flood rate: L6+ events / total events
- Session count: distinct session_ids
- Empty data: returns None, not exception
- AI profile: aggregates only subject='ai' events
- Spiral depth: longest ascending marker_level streak (transition count)
- Spiral depth across sessions: max across all sessions
- list_available_humans: distinct human_ids
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.intelligence_profile import (
    compute_ai_profile,
    compute_intelligence_profile,
    compute_spiral_depth_for_human,
    list_available_humans,
)
from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema (including DDF)."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


def _make_event(
    flame_id: str,
    session_id: str = "sess1",
    human_id: str = "alice",
    marker_level: int = 3,
    marker_type: str = "L3_assertive",
    subject: str = "human",
    prompt_number: int = 1,
) -> FlameEvent:
    """Create a FlameEvent for testing with sensible defaults."""
    return FlameEvent(
        flame_event_id=flame_id,
        session_id=session_id,
        human_id=human_id,
        prompt_number=prompt_number,
        marker_level=marker_level,
        marker_type=marker_type,
        evidence_excerpt="test evidence",
        subject=subject,
        detection_source="stub",
    )


# ═══════════════════════════════════════════════════════════════════
# Test 1: basic aggregation
# ═══════════════════════════════════════════════════════════════════


def test_profile_basic_aggregation(conn):
    """5 flame_events produce correct frequency, avg, max."""
    events = [
        _make_event("fe1", marker_level=1, prompt_number=1),
        _make_event("fe2", marker_level=2, prompt_number=2),
        _make_event("fe3", marker_level=3, prompt_number=3),
        _make_event("fe4", marker_level=4, prompt_number=4),
        _make_event("fe5", marker_level=5, prompt_number=5),
    ]
    write_flame_events(conn, events)

    profile = compute_intelligence_profile(conn, "alice")
    assert profile is not None
    assert profile.flame_frequency == 5
    assert profile.avg_marker_level == 3.0  # (1+2+3+4+5)/5
    assert profile.max_marker_level == 5
    assert profile.subject == "human"
    assert profile.human_id == "alice"


# ═══════════════════════════════════════════════════════════════════
# Test 2: flood rate with L6+ events
# ═══════════════════════════════════════════════════════════════════


def test_profile_flood_rate(conn):
    """2 of 5 events at L6+ -> flood_rate = 0.4."""
    events = [
        _make_event("fe1", marker_level=2, prompt_number=1),
        _make_event("fe2", marker_level=3, prompt_number=2),
        _make_event("fe3", marker_level=4, prompt_number=3),
        _make_event("fe4", marker_level=6, prompt_number=4),  # L6+
        _make_event("fe5", marker_level=7, prompt_number=5),  # L6+
    ]
    write_flame_events(conn, events)

    profile = compute_intelligence_profile(conn, "alice")
    assert profile is not None
    assert profile.flood_rate == 0.4


# ═══════════════════════════════════════════════════════════════════
# Test 3: zero flood rate
# ═══════════════════════════════════════════════════════════════════


def test_profile_zero_flood_rate(conn):
    """No L6+ events -> flood_rate = 0.0."""
    events = [
        _make_event("fe1", marker_level=0, prompt_number=1),
        _make_event("fe2", marker_level=3, prompt_number=2),
        _make_event("fe3", marker_level=5, prompt_number=3),
    ]
    write_flame_events(conn, events)

    profile = compute_intelligence_profile(conn, "alice")
    assert profile is not None
    assert profile.flood_rate == 0.0


# ═══════════════════════════════════════════════════════════════════
# Test 4: session count
# ═══════════════════════════════════════════════════════════════════


def test_profile_session_count(conn):
    """Events across 3 sessions -> session_count = 3."""
    events = [
        _make_event("fe1", session_id="s1", prompt_number=1),
        _make_event("fe2", session_id="s2", prompt_number=1),
        _make_event("fe3", session_id="s3", prompt_number=1),
        _make_event("fe4", session_id="s1", prompt_number=2),  # same session
        _make_event("fe5", session_id="s2", prompt_number=2),  # same session
    ]
    write_flame_events(conn, events)

    profile = compute_intelligence_profile(conn, "alice")
    assert profile is not None
    assert profile.session_count == 3


# ═══════════════════════════════════════════════════════════════════
# Test 5: no data returns None
# ═══════════════════════════════════════════════════════════════════


def test_profile_no_data_returns_none(conn):
    """No flame_events for human -> None."""
    profile = compute_intelligence_profile(conn, "nonexistent")
    assert profile is None


# ═══════════════════════════════════════════════════════════════════
# Test 6: AI profile
# ═══════════════════════════════════════════════════════════════════


def test_ai_profile(conn):
    """subject='ai' events aggregated separately."""
    # Human events -- should NOT appear in AI profile
    human_events = [
        _make_event("fe_h1", marker_level=5, subject="human", prompt_number=1),
    ]
    # AI events
    ai_events = [
        _make_event("fe_a1", marker_level=2, subject="ai", prompt_number=1),
        _make_event("fe_a2", marker_level=4, subject="ai", prompt_number=2),
        _make_event("fe_a3", marker_level=6, subject="ai", prompt_number=3),
    ]
    write_flame_events(conn, human_events + ai_events)

    profile = compute_ai_profile(conn)
    assert profile is not None
    assert profile.flame_frequency == 3
    assert profile.avg_marker_level == 4.0  # (2+4+6)/3
    assert profile.max_marker_level == 6
    assert profile.subject == "ai"
    assert profile.human_id == "ai"
    # 1 of 3 is L6+ -> flood_rate = 1/3
    assert abs(profile.flood_rate - 1 / 3) < 0.01


# ═══════════════════════════════════════════════════════════════════
# Test 7: AI profile no data
# ═══════════════════════════════════════════════════════════════════


def test_ai_profile_no_data_returns_none(conn):
    """No AI flame_events -> None."""
    profile = compute_ai_profile(conn)
    assert profile is None


# ═══════════════════════════════════════════════════════════════════
# Test 8: spiral depth ascending
# ═══════════════════════════════════════════════════════════════════


def test_spiral_depth_ascending(conn):
    """L1, L2, L3, L4 -> depth=3 (3 ascending transitions)."""
    events = [
        _make_event("fe1", marker_level=1, prompt_number=1),
        _make_event("fe2", marker_level=2, prompt_number=2),
        _make_event("fe3", marker_level=3, prompt_number=3),
        _make_event("fe4", marker_level=4, prompt_number=4),
    ]
    write_flame_events(conn, events)

    depth = compute_spiral_depth_for_human(conn, "alice")
    assert depth == 3


# ═══════════════════════════════════════════════════════════════════
# Test 9: spiral depth broken streak
# ═══════════════════════════════════════════════════════════════════


def test_spiral_depth_broken_streak(conn):
    """L1, L2, L0, L3, L4 -> depth=2 (longest ascending: L0->L3->L4 = 2 transitions)."""
    events = [
        _make_event("fe1", marker_level=1, prompt_number=1),
        _make_event("fe2", marker_level=2, prompt_number=2),
        _make_event("fe3", marker_level=0, prompt_number=3),
        _make_event("fe4", marker_level=3, prompt_number=4),
        _make_event("fe5", marker_level=4, prompt_number=5),
    ]
    write_flame_events(conn, events)

    depth = compute_spiral_depth_for_human(conn, "alice")
    assert depth == 2


# ═══════════════════════════════════════════════════════════════════
# Test 10: spiral depth no ascending
# ═══════════════════════════════════════════════════════════════════


def test_spiral_depth_no_ascending(conn):
    """L3, L2, L1 -> depth=0 (no ascending transitions)."""
    events = [
        _make_event("fe1", marker_level=3, prompt_number=1),
        _make_event("fe2", marker_level=2, prompt_number=2),
        _make_event("fe3", marker_level=1, prompt_number=3),
    ]
    write_flame_events(conn, events)

    depth = compute_spiral_depth_for_human(conn, "alice")
    assert depth == 0


# ═══════════════════════════════════════════════════════════════════
# Test 11: spiral depth multiple sessions
# ═══════════════════════════════════════════════════════════════════


def test_spiral_depth_multiple_sessions(conn):
    """Max ascending streak across sessions returned.

    Session s1: L1, L2 -> 1 transition
    Session s2: L0, L1, L2, L3 -> 3 transitions
    Max = 3
    """
    events = [
        # Session s1
        _make_event("fe1", session_id="s1", marker_level=1, prompt_number=1),
        _make_event("fe2", session_id="s1", marker_level=2, prompt_number=2),
        # Session s2
        _make_event("fe3", session_id="s2", marker_level=0, prompt_number=1),
        _make_event("fe4", session_id="s2", marker_level=1, prompt_number=2),
        _make_event("fe5", session_id="s2", marker_level=2, prompt_number=3),
        _make_event("fe6", session_id="s2", marker_level=3, prompt_number=4),
    ]
    write_flame_events(conn, events)

    depth = compute_spiral_depth_for_human(conn, "alice")
    assert depth == 3


# ═══════════════════════════════════════════════════════════════════
# Test 12: list available humans
# ═══════════════════════════════════════════════════════════════════


def test_list_available_humans(conn):
    """Returns distinct human_ids from flame_events."""
    events = [
        _make_event("fe1", human_id="alice", prompt_number=1),
        _make_event("fe2", human_id="bob", prompt_number=1),
        _make_event("fe3", human_id="alice", prompt_number=2),  # duplicate
        _make_event("fe4", human_id="carol", prompt_number=1),
        # AI event -- should NOT appear
        _make_event("fe5", human_id="ai", subject="ai", prompt_number=1),
    ]
    write_flame_events(conn, events)

    humans = list_available_humans(conn)
    assert humans == ["alice", "bob", "carol"]
