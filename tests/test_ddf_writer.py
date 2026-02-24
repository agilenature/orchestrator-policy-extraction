"""Tests for DDF writer and deposit functions (Phase 15).

Covers:
- write_flame_events insert, idempotency, empty list, column population
- deposit_to_memory_candidates new entry, dedup, case/whitespace normalization
- deposit different scope creates new entry
- deposit fidelity column
- mark_deposited flag update
- deposit empty ccd_axis constraint violation
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.deposit import deposit_to_memory_candidates, mark_deposited
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


def _make_flame_event(
    flame_id: str = "fe1",
    session_id: str = "sess1",
    marker_level: int = 0,
    marker_type: str = "L0_trunk",
    subject: str = "human",
) -> FlameEvent:
    """Create a minimal FlameEvent for testing."""
    return FlameEvent(
        flame_event_id=flame_id,
        session_id=session_id,
        human_id="default_human",
        prompt_number=1,
        marker_level=marker_level,
        marker_type=marker_type,
        evidence_excerpt="test evidence",
        subject=subject,
        detection_source="stub",
    )


# ═══════════════════════════════════════════════════════════════════
# write_flame_events
# ═══════════════════════════════════════════════════════════════════


# ── Test 1: basic insert ──


def test_write_flame_events_inserts(conn):
    """Write 3 events, verify count = 3."""
    events = [
        _make_flame_event(flame_id="fe1", marker_type="L0_trunk"),
        _make_flame_event(flame_id="fe2", marker_type="L1_causal"),
        _make_flame_event(flame_id="fe3", marker_type="L2_assertive"),
    ]
    result = write_flame_events(conn, events)
    assert result == {"written": 3}

    count = conn.execute("SELECT COUNT(*) FROM flame_events").fetchone()[0]
    assert count == 3


# ── Test 2: idempotent insert ──


def test_write_flame_events_idempotent(conn):
    """Write same event twice, count = 1 (INSERT OR REPLACE)."""
    event = _make_flame_event(flame_id="fe1")
    write_flame_events(conn, [event])
    write_flame_events(conn, [event])

    count = conn.execute("SELECT COUNT(*) FROM flame_events").fetchone()[0]
    assert count == 1


# ── Test 3: empty list ──


def test_write_flame_events_empty(conn):
    """Empty list returns {'written': 0}."""
    result = write_flame_events(conn, [])
    assert result == {"written": 0}


# ── Test 4: all columns populated ──


def test_write_flame_events_all_columns(conn):
    """Verify key columns (marker_level, subject, detection_source) populated."""
    event = _make_flame_event(
        flame_id="fe1",
        marker_level=2,
        subject="ai",
    )
    write_flame_events(conn, [event])

    row = conn.execute(
        "SELECT marker_level, subject, detection_source, human_id "
        "FROM flame_events WHERE flame_event_id = 'fe1'"
    ).fetchone()

    assert row[0] == 2  # marker_level
    assert row[1] == "ai"  # subject
    assert row[2] == "stub"  # detection_source
    assert row[3] == "default_human"  # human_id


# ═══════════════════════════════════════════════════════════════════
# deposit_to_memory_candidates
# ═══════════════════════════════════════════════════════════════════


# ── Test 5: new candidate ──


def test_deposit_new_candidate(conn):
    """First deposit returns non-None candidate_id."""
    cid = deposit_to_memory_candidates(
        conn,
        ccd_axis="ground-truth-pointer",
        scope_rule="Every abstraction must carry a perception pointer.",
        flood_example="MEMORY.md entries missing source_session_id.",
        source_flame_event_id="fe1",
    )
    assert cid is not None
    assert len(cid) == 16

    row = conn.execute(
        "SELECT ccd_axis, status, detection_count FROM memory_candidates WHERE id = ?",
        [cid],
    ).fetchone()
    assert row[0] == "ground-truth-pointer"
    assert row[1] == "pending"
    assert row[2] == 1


# ── Test 6: dedup increments count ──


def test_deposit_dedup_increments_count(conn):
    """Second deposit of same (axis, scope_rule) returns None, detection_count=2."""
    cid = deposit_to_memory_candidates(
        conn,
        ccd_axis="ground-truth-pointer",
        scope_rule="Every abstraction must carry a pointer.",
        flood_example="Example A.",
    )
    assert cid is not None

    cid2 = deposit_to_memory_candidates(
        conn,
        ccd_axis="ground-truth-pointer",
        scope_rule="Every abstraction must carry a pointer.",
        flood_example="Example B.",
    )
    assert cid2 is None

    count = conn.execute(
        "SELECT detection_count FROM memory_candidates WHERE id = ?", [cid]
    ).fetchone()[0]
    assert count == 2


# ── Test 7: case-insensitive dedup ──


def test_deposit_dedup_case_insensitive(conn):
    """'Ground Truth' and 'ground truth' treated as same axis."""
    cid = deposit_to_memory_candidates(
        conn,
        ccd_axis="Ground Truth",
        scope_rule="Pointer required.",
        flood_example="Example.",
    )
    assert cid is not None

    cid2 = deposit_to_memory_candidates(
        conn,
        ccd_axis="ground truth",
        scope_rule="pointer required.",
        flood_example="Example 2.",
    )
    assert cid2 is None

    count = conn.execute(
        "SELECT detection_count FROM memory_candidates WHERE id = ?", [cid]
    ).fetchone()[0]
    assert count == 2


# ── Test 8: whitespace-insensitive dedup ──


def test_deposit_dedup_whitespace_insensitive(conn):
    """'axis ' and 'axis' treated as same."""
    cid = deposit_to_memory_candidates(
        conn,
        ccd_axis="axis ",
        scope_rule="scope rule ",
        flood_example="Example.",
    )
    assert cid is not None

    cid2 = deposit_to_memory_candidates(
        conn,
        ccd_axis="axis",
        scope_rule="scope rule",
        flood_example="Example 2.",
    )
    assert cid2 is None

    count = conn.execute(
        "SELECT detection_count FROM memory_candidates WHERE id = ?", [cid]
    ).fetchone()[0]
    assert count == 2


# ── Test 9: different scope creates new ──


def test_deposit_different_scope_creates_new(conn):
    """Same axis, different scope_rule creates a new candidate."""
    cid1 = deposit_to_memory_candidates(
        conn,
        ccd_axis="ground-truth-pointer",
        scope_rule="Scope A: perception pointer required.",
        flood_example="Example A.",
    )
    cid2 = deposit_to_memory_candidates(
        conn,
        ccd_axis="ground-truth-pointer",
        scope_rule="Scope B: different scope entirely.",
        flood_example="Example B.",
    )
    assert cid1 is not None
    assert cid2 is not None
    assert cid1 != cid2

    total = conn.execute("SELECT COUNT(*) FROM memory_candidates").fetchone()[0]
    assert total == 2


# ── Test 10: fidelity column ──


def test_deposit_sets_fidelity(conn):
    """Verify fidelity column = 2 by default."""
    cid = deposit_to_memory_candidates(
        conn,
        ccd_axis="test-axis",
        scope_rule="test scope.",
        flood_example="test flood.",
    )
    fidelity = conn.execute(
        "SELECT fidelity FROM memory_candidates WHERE id = ?", [cid]
    ).fetchone()[0]
    assert fidelity == 2


# ═══════════════════════════════════════════════════════════════════
# mark_deposited
# ═══════════════════════════════════════════════════════════════════


# ── Test 11: mark_deposited flag ──


def test_mark_deposited(conn):
    """After mark_deposited, deposited_to_candidates is True in flame_events."""
    event = _make_flame_event(flame_id="fe_mark")
    write_flame_events(conn, [event])

    # Before: deposited_to_candidates is False
    before = conn.execute(
        "SELECT deposited_to_candidates FROM flame_events WHERE flame_event_id = 'fe_mark'"
    ).fetchone()[0]
    assert before is False

    mark_deposited(conn, "fe_mark")

    # After: deposited_to_candidates is True
    after = conn.execute(
        "SELECT deposited_to_candidates FROM flame_events WHERE flame_event_id = 'fe_mark'"
    ).fetchone()[0]
    assert after is True


# ═══════════════════════════════════════════════════════════════════
# Constraint enforcement
# ═══════════════════════════════════════════════════════════════════


# ── Test 12: empty ccd_axis fails ──


def test_deposit_empty_ccd_axis_fails(conn):
    """Empty ccd_axis raises error (CHECK constraint violation)."""
    with pytest.raises(duckdb.ConstraintException):
        deposit_to_memory_candidates(
            conn,
            ccd_axis="",
            scope_rule="valid scope.",
            flood_example="valid flood.",
        )
