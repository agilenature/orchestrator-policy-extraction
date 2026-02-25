"""Tests for Phase 18 structural integrity detectors, computer, Op-8, and pipeline step.

Covers:
- Gravity Check: 6 tests (grounded, floating, outside window, empty, COALESCE, subject tagging)
- Main Cable: 4 tests (in axis_edges, floating, empty, no axis)
- Dependency Sequencing: 4 tests (respected, violated, no prerequisite, empty)
- Spiral Reinforcement: 3 tests (wisdom match, no wisdom, metadata match)
- Computer: 4 tests (with events, neutral fallback, all pass, empty session)
- Op-8: 3 tests (deposit floating, dedup, skip human)
- Pipeline integration: 1 test (Step 21 exists in runner)
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.structural.computer import compute_structural_integrity
from src.pipeline.ddf.structural.detectors import (
    detect_dependency_sequencing,
    detect_gravity_checks,
    detect_main_cables,
    detect_spiral_reinforcement,
    detect_structural_signals,
)
from src.pipeline.ddf.structural.models import StructuralEvent
from src.pipeline.ddf.structural.op8 import deposit_op8_corrections
from src.pipeline.ddf.structural.schema import create_structural_schema
from src.pipeline.ddf.structural.writer import write_structural_events
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema (flame_events, axis_edges, etc)."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    create_ddf_schema(c)
    yield c
    c.close()


def _insert_flame_event(
    conn,
    flame_event_id,
    session_id,
    prompt_number,
    marker_level,
    subject="human",
    ccd_axis=None,
    axis_identified=None,
    flood_confirmed=False,
    marker_type="stub_marker",
):
    """Helper to insert a flame_event directly."""
    conn.execute(
        """
        INSERT OR REPLACE INTO flame_events
        (flame_event_id, session_id, prompt_number, marker_level, subject,
         ccd_axis, axis_identified, flood_confirmed, marker_type,
         detection_source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'stub', NOW())
        """,
        [
            flame_event_id,
            session_id,
            prompt_number,
            marker_level,
            subject,
            ccd_axis,
            axis_identified,
            flood_confirmed,
            marker_type,
        ],
    )


def _insert_axis_edge(conn, axis_a, axis_b, status="active"):
    """Helper to insert an axis_edge."""
    edge_id = f"{axis_a}:{axis_b}"
    conn.execute(
        """
        INSERT OR REPLACE INTO axis_edges
        (edge_id, axis_a, axis_b, relationship_text, activation_condition,
         evidence, abstraction_level, status, created_session_id, created_at)
        VALUES (?, ?, ?, 'test relation', '{"goal_type":["any"]}',
                '{"source":"test"}', 5, ?, 'test-session', NOW())
        """,
        [edge_id, axis_a, axis_b, status],
    )


def _insert_project_wisdom(conn, wisdom_id, session_id, title="Test wisdom"):
    """Helper to insert a project_wisdom entry with session in metadata."""
    import json

    metadata = json.dumps({"source_session_id": session_id, "promotion_source": "ddf_spiral_tracking"})
    conn.execute(
        """
        INSERT OR REPLACE INTO project_wisdom
        (wisdom_id, entity_type, title, description, created_at, last_updated, metadata)
        VALUES (?, 'breakthrough', ?, ?, NOW(), NOW(), ?)
        """,
        [wisdom_id, title, title, metadata],
    )


# ============================================================
# Gravity Check tests (6)
# ============================================================


def test_gravity_check_grounded(conn):
    """L5 event + L1 event with same axis within 3 prompts -> signal_passed=True."""
    sid = "sess-gc-1"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="test-axis")
    _insert_flame_event(conn, "fe-l1", sid, 11, 1, ccd_axis="test-axis")

    events = detect_gravity_checks(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is True
    assert events[0].signal_type == "gravity_check"
    assert events[0].structural_role == "grounding"


def test_gravity_check_floating(conn):
    """L5 event, no L0-L2 with same axis -> signal_passed=False."""
    sid = "sess-gc-2"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="test-axis")

    events = detect_gravity_checks(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is False


def test_gravity_check_outside_window(conn):
    """L5 event + L1 event but 5 prompts apart -> signal_passed=False."""
    sid = "sess-gc-3"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="test-axis")
    _insert_flame_event(conn, "fe-l1", sid, 15, 1, ccd_axis="test-axis")

    events = detect_gravity_checks(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is False


def test_gravity_check_empty_session(conn):
    """No L5+ events -> returns []."""
    sid = "sess-gc-4"
    _insert_flame_event(conn, "fe-l1", sid, 10, 2, ccd_axis="test-axis")

    events = detect_gravity_checks(conn, sid)
    assert events == []


def test_gravity_check_uses_coalesce(conn):
    """L5 with ccd_axis=None, axis_identified='test-axis'; L1 with ccd_axis='test-axis' -> matches."""
    sid = "sess-gc-5"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis=None, axis_identified="test-axis")
    _insert_flame_event(conn, "fe-l1", sid, 11, 1, ccd_axis="test-axis")

    events = detect_gravity_checks(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is True


def test_gravity_check_subject_tagging(conn):
    """L5 event with subject='ai' -> StructuralEvent has subject='ai'."""
    sid = "sess-gc-6"
    _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="ai-axis")

    events = detect_gravity_checks(conn, sid)
    assert len(events) == 1
    assert events[0].subject == "ai"


# ============================================================
# Main Cable tests (4)
# ============================================================


def test_main_cable_in_axis_edges(conn):
    """L5 event whose axis appears in axis_edges -> signal_passed=True."""
    sid = "sess-mc-1"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="axis-a")
    _insert_axis_edge(conn, "axis-a", "axis-b")

    events = detect_main_cables(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is True
    assert events[0].structural_role == "load_bearing"


def test_main_cable_floating_cable(conn):
    """L5 event, no edges, no flood -> signal_passed=False (floating cable)."""
    sid = "sess-mc-2"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="orphan-axis", flood_confirmed=False)

    events = detect_main_cables(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is False


def test_main_cable_empty(conn):
    """No L5+ events -> returns []."""
    sid = "sess-mc-3"
    _insert_flame_event(conn, "fe-l2", sid, 10, 2, ccd_axis="test-axis")

    events = detect_main_cables(conn, sid)
    assert events == []


def test_main_cable_no_axis(conn):
    """L5 event with no axis (ccd_axis=None, axis_identified=None) -> signal_passed=False."""
    sid = "sess-mc-4"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5)

    events = detect_main_cables(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is False


# ============================================================
# Dependency Sequencing tests (4)
# ============================================================


def test_dependency_respected(conn):
    """Axis 'B' has prerequisite 'A'; 'A' appears at L3+ before 'B' at L5+ -> True."""
    sid = "sess-ds-1"
    _insert_flame_event(conn, "fe-a3", sid, 5, 3, ccd_axis="axis-A")
    _insert_flame_event(conn, "fe-b5", sid, 10, 5, ccd_axis="axis-B")
    _insert_axis_edge(conn, "axis-B", "axis-A")

    events = detect_dependency_sequencing(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is True


def test_dependency_violated(conn):
    """Axis 'B' has prerequisite 'A'; 'A' has NOT appeared -> False."""
    sid = "sess-ds-2"
    _insert_flame_event(conn, "fe-b5", sid, 10, 5, ccd_axis="axis-B")
    _insert_axis_edge(conn, "axis-B", "axis-A")

    events = detect_dependency_sequencing(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is False
    assert "missing prerequisite" in events[0].evidence


def test_no_prerequisite(conn):
    """Axis 'X' has no axis_edges -> signal_passed=True (no known prerequisites)."""
    sid = "sess-ds-3"
    _insert_flame_event(conn, "fe-x5", sid, 10, 5, ccd_axis="isolated-axis")

    events = detect_dependency_sequencing(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is True


def test_dependency_empty(conn):
    """No L5+ events -> returns []."""
    sid = "sess-ds-4"
    _insert_flame_event(conn, "fe-l2", sid, 10, 2, ccd_axis="test-axis")

    events = detect_dependency_sequencing(conn, sid)
    assert events == []


# ============================================================
# Spiral Reinforcement tests (3)
# ============================================================


def test_spiral_with_wisdom_entry(conn):
    """project_wisdom entry with session_id in metadata -> signal_passed=True."""
    sid = "sess-sp-1"
    _insert_project_wisdom(conn, "w-001", sid, title="Spiral promotion test")

    events = detect_spiral_reinforcement(conn, sid)
    assert len(events) == 1
    assert events[0].signal_passed is True
    assert events[0].signal_type == "spiral_reinforcement"
    assert events[0].structural_role == "reinforcing"


def test_spiral_no_wisdom(conn):
    """No project_wisdom for session -> returns []."""
    sid = "sess-sp-2"

    events = detect_spiral_reinforcement(conn, sid)
    assert events == []


def test_spiral_metadata_match(conn):
    """project_wisdom entry with session_id in metadata JSON -> matches."""
    sid = "sess-sp-3"
    _insert_project_wisdom(conn, "w-002", sid, title="Another spiral")

    events = detect_spiral_reinforcement(conn, sid)
    assert len(events) == 1
    assert "Another spiral" in events[0].evidence


# ============================================================
# Computer tests (4)
# ============================================================


def _write_structural_event(conn, session_id, signal_type, signal_passed, subject="human", prompt_number=1):
    """Helper to write a structural_event directly."""
    create_structural_schema(conn)
    evt = StructuralEvent(
        event_id=StructuralEvent.make_id(session_id, prompt_number, f"{signal_type}_{signal_passed}_{prompt_number}"),
        session_id=session_id,
        prompt_number=prompt_number,
        subject=subject,
        signal_type=signal_type,
        signal_passed=signal_passed,
    )
    write_structural_events(conn, [evt])
    return evt


def test_compute_with_events(conn):
    """Write 3 structural events (2 gravity pass, 1 main_cable fail), compute score."""
    sid = "sess-comp-1"
    _write_structural_event(conn, sid, "gravity_check", True, prompt_number=1)
    _write_structural_event(conn, sid, "gravity_check", True, prompt_number=2)
    _write_structural_event(conn, sid, "main_cable", False, prompt_number=3)

    result = compute_structural_integrity(conn, sid, "human")

    assert result.session_id == sid
    assert result.subject == "human"
    assert result.gravity_ratio == 1.0  # 2/2
    assert result.main_cable_ratio == 0.0  # 0/1
    assert result.dependency_ratio == 0.5  # neutral fallback (no events)
    assert result.spiral_capped == 0.0  # no spiral events
    assert result.structural_event_count == 3

    # Expected: 0.30*1.0 + 0.40*0.0 + 0.20*0.5 + 0.10*0.0 = 0.30 + 0.00 + 0.10 + 0.00 = 0.40
    assert result.integrity_score == 0.4


def test_compute_neutral_fallback(conn):
    """No events for any signal type -> all ratios = neutral_fallback (0.5), spiral=0.0."""
    sid = "sess-comp-2"
    create_structural_schema(conn)

    result = compute_structural_integrity(conn, sid, "human")

    assert result.gravity_ratio == 0.5
    assert result.main_cable_ratio == 0.5
    assert result.dependency_ratio == 0.5
    assert result.spiral_capped == 0.0
    assert result.structural_event_count == 0

    # Expected: 0.30*0.5 + 0.40*0.5 + 0.20*0.5 + 0.10*0.0 = 0.15 + 0.20 + 0.10 + 0.00 = 0.45
    assert result.integrity_score == 0.45


def test_compute_all_pass(conn):
    """All signals pass + spirals present -> high score."""
    sid = "sess-comp-3"
    _write_structural_event(conn, sid, "gravity_check", True, prompt_number=1)
    _write_structural_event(conn, sid, "main_cable", True, prompt_number=2)
    _write_structural_event(conn, sid, "dependency_sequencing", True, prompt_number=3)
    _write_structural_event(conn, sid, "spiral_reinforcement", True, prompt_number=4)
    _write_structural_event(conn, sid, "spiral_reinforcement", True, prompt_number=5)
    _write_structural_event(conn, sid, "spiral_reinforcement", True, prompt_number=6)

    result = compute_structural_integrity(conn, sid, "human")

    assert result.gravity_ratio == 1.0
    assert result.main_cable_ratio == 1.0
    assert result.dependency_ratio == 1.0
    assert result.spiral_capped == 1.0  # min(3, 3) / 3 = 1.0

    # Expected: 0.30*1.0 + 0.40*1.0 + 0.20*1.0 + 0.10*1.0 = 1.0
    assert result.integrity_score == 1.0


def test_compute_empty_session(conn):
    """No structural events at all -> neutral fallback applied."""
    sid = "sess-comp-4"
    create_structural_schema(conn)

    result = compute_structural_integrity(conn, sid, "ai")

    assert result.subject == "ai"
    assert result.gravity_ratio == 0.5
    assert result.main_cable_ratio == 0.5
    assert result.dependency_ratio == 0.5
    assert result.spiral_capped == 0.0


# ============================================================
# Op-8 tests (3)
# ============================================================


def test_op8_deposits_floating_cable(conn):
    """AI main_cable signal_passed=False -> deposits to memory_candidates."""
    sid = "sess-op8-1"
    # Insert an AI L5+ flame event (needed for axis lookup)
    _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="floating-axis")

    # Write a structural event that represents a failed main_cable for AI
    create_structural_schema(conn)
    evt = StructuralEvent(
        event_id=StructuralEvent.make_id(sid, 10, "main_cable"),
        session_id=sid,
        prompt_number=10,
        subject="ai",
        signal_type="main_cable",
        signal_passed=False,
        contributing_flame_event_ids=["fe-ai5"],
    )
    write_structural_events(conn, [evt])

    count = deposit_op8_corrections(conn, sid)
    assert count == 1

    # Check memory_candidates
    row = conn.execute(
        "SELECT ccd_axis, source_type, fidelity, confidence, status "
        "FROM memory_candidates WHERE source_type = 'op8_correction'"
    ).fetchone()
    assert row is not None
    assert row[0] == "floating-axis"
    assert row[1] == "op8_correction"
    assert row[2] == 2  # fidelity
    assert row[3] == pytest.approx(0.60, abs=1e-4)  # confidence (FLOAT precision)
    assert row[4] == "pending"  # status


def test_op8_dedup(conn):
    """Same floating cable written twice -> only 1 candidate (INSERT OR REPLACE)."""
    sid = "sess-op8-2"
    _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="dedup-axis")

    create_structural_schema(conn)
    evt = StructuralEvent(
        event_id=StructuralEvent.make_id(sid, 10, "main_cable"),
        session_id=sid,
        prompt_number=10,
        subject="ai",
        signal_type="main_cable",
        signal_passed=False,
        contributing_flame_event_ids=["fe-ai5"],
    )
    write_structural_events(conn, [evt])

    # Deposit twice
    deposit_op8_corrections(conn, sid)
    deposit_op8_corrections(conn, sid)

    count = conn.execute(
        "SELECT COUNT(*) FROM memory_candidates WHERE source_type = 'op8_correction'"
    ).fetchone()[0]
    assert count == 1


def test_op8_skips_human_cables(conn):
    """Human main_cable signal_passed=False -> NOT deposited (Op-8 is AI-only)."""
    sid = "sess-op8-3"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, subject="human", ccd_axis="human-axis")

    create_structural_schema(conn)
    evt = StructuralEvent(
        event_id=StructuralEvent.make_id(sid, 10, "main_cable"),
        session_id=sid,
        prompt_number=10,
        subject="human",
        signal_type="main_cable",
        signal_passed=False,
        contributing_flame_event_ids=["fe-h5"],
    )
    write_structural_events(conn, [evt])

    count = deposit_op8_corrections(conn, sid)
    assert count == 0


# ============================================================
# Orchestrator test (1)
# ============================================================


def test_detect_structural_signals_combines_all(conn):
    """detect_structural_signals returns events from all four detectors."""
    sid = "sess-orch-1"
    _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="test-axis")
    _insert_flame_event(conn, "fe-l1", sid, 11, 1, ccd_axis="test-axis")
    _insert_axis_edge(conn, "test-axis", "other-axis")

    events = detect_structural_signals(conn, sid)
    signal_types = {e.signal_type for e in events}

    # Should have at least gravity_check and main_cable (dependency_sequencing if axis has edges)
    assert "gravity_check" in signal_types
    assert "main_cable" in signal_types


# ============================================================
# Pipeline integration test (1)
# ============================================================


def test_step21_in_runner():
    """Verify Step 21 code path exists in PipelineRunner."""
    import inspect

    from src.pipeline.runner import PipelineRunner

    source = inspect.getsource(PipelineRunner.run_session)
    assert "Step 21" in source
    assert "detect_structural_signals" in source
    assert "deposit_op8_corrections" in source
