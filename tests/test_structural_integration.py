"""Integration tests for Phase 18 structural integrity: BRIDGE-01, BRIDGE-02, BRIDGE-03.

Verifies the full chain:
  flame_events -> detect_structural_signals -> write_structural_events
  -> compute_structural_integrity -> deposit_op8_corrections

These are INTEGRATION tests -- they exercise multiple components together
against realistic data patterns. Unit tests live in test_structural_detectors.py.

Test groups:
- BRIDGE-01: structural_events records all four signal types (6 tests)
- BRIDGE-02: StructuralIntegrityScore computed per session for both subjects (5 tests)
- BRIDGE-03: Op-8 fires on AI floating cables and deposits to memory_candidates (4 tests)
- Assessment isolation (1 test)
- End-to-end chain (2 tests)

Total: 18 tests.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.structural.computer import compute_structural_integrity
from src.pipeline.ddf.structural.detectors import detect_structural_signals
from src.pipeline.ddf.structural.op8 import deposit_op8_corrections
from src.pipeline.ddf.structural.writer import write_structural_events
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB with full schema (storage + DDF + structural)."""
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
    assessment_session_id=None,
):
    """Helper to insert a flame_event with all required columns."""
    conn.execute(
        """
        INSERT OR REPLACE INTO flame_events
        (flame_event_id, session_id, prompt_number, marker_level, subject,
         ccd_axis, axis_identified, flood_confirmed, marker_type,
         detection_source, assessment_session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'stub_marker', 'stub', ?, NOW())
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
            assessment_session_id,
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
    """Helper to insert project_wisdom with session_id in metadata JSON."""
    metadata = json.dumps({
        "source_session_id": session_id,
        "promotion_source": "ddf_spiral_tracking",
    })
    conn.execute(
        """
        INSERT OR REPLACE INTO project_wisdom
        (wisdom_id, entity_type, title, description, created_at, last_updated, metadata)
        VALUES (?, 'breakthrough', ?, ?, NOW(), NOW(), ?)
        """,
        [wisdom_id, title, title, metadata],
    )


def _run_detect_and_write(conn, session_id, assessment_session_id=None):
    """Detect structural signals and write them. Returns event list."""
    events = detect_structural_signals(conn, session_id, assessment_session_id)
    write_structural_events(conn, events)
    return events


# ============================================================
# BRIDGE-01: structural_events records all four signal types (6 tests)
# ============================================================


class TestBridge01SignalRecording:
    """BRIDGE-01: structural_events records all four signal types per session."""

    def test_gravity_check_recorded(self, conn):
        """Insert L5+ flame_event + L1 grounding, detect+write, verify gravity_check row."""
        sid = "integ-b01-gc"
        _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="deposit-not-detect")
        _insert_flame_event(conn, "fe-l1", sid, 11, 1, ccd_axis="deposit-not-detect")

        _run_detect_and_write(conn, sid)

        rows = conn.execute(
            "SELECT signal_type, signal_passed, subject, evidence "
            "FROM structural_events WHERE session_id = ? AND signal_type = 'gravity_check'",
            [sid],
        ).fetchall()

        assert len(rows) >= 1
        gc_row = rows[0]
        assert gc_row[0] == "gravity_check"
        assert gc_row[1] is True  # grounded
        assert gc_row[2] == "human"
        assert gc_row[3] is not None and len(gc_row[3]) > 0  # evidence populated

    def test_main_cable_recorded(self, conn):
        """Insert L5+ event with axis in axis_edges, verify main_cable row."""
        sid = "integ-b01-mc"
        _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="terminal-vs-instrumental")
        _insert_axis_edge(conn, "terminal-vs-instrumental", "deposit-not-detect")

        _run_detect_and_write(conn, sid)

        rows = conn.execute(
            "SELECT signal_type, signal_passed, evidence "
            "FROM structural_events WHERE session_id = ? AND signal_type = 'main_cable'",
            [sid],
        ).fetchall()

        assert len(rows) >= 1
        mc_row = rows[0]
        assert mc_row[0] == "main_cable"
        assert mc_row[1] is True  # axis found in axis_edges
        assert "edges=yes" in mc_row[2]

    def test_dependency_sequencing_recorded(self, conn):
        """Insert axis_edge (A->B), insert L5+ for B without A appearing first -> False."""
        sid = "integ-b01-ds"
        _insert_axis_edge(conn, "axis-B", "axis-A")
        _insert_flame_event(conn, "fe-b5", sid, 10, 5, ccd_axis="axis-B")

        _run_detect_and_write(conn, sid)

        rows = conn.execute(
            "SELECT signal_type, signal_passed, evidence "
            "FROM structural_events WHERE session_id = ? AND signal_type = 'dependency_sequencing'",
            [sid],
        ).fetchall()

        assert len(rows) >= 1
        ds_row = rows[0]
        assert ds_row[0] == "dependency_sequencing"
        assert ds_row[1] is False  # prerequisite missing
        assert "missing prerequisite" in ds_row[2]

    def test_spiral_reinforcement_recorded(self, conn):
        """Insert project_wisdom entry with source_session_id, verify spiral row."""
        sid = "integ-b01-sp"
        _insert_project_wisdom(conn, "w-integ-01", sid, title="Spiral test entry")

        _run_detect_and_write(conn, sid)

        rows = conn.execute(
            "SELECT signal_type, signal_passed, evidence "
            "FROM structural_events WHERE session_id = ? AND signal_type = 'spiral_reinforcement'",
            [sid],
        ).fetchall()

        assert len(rows) == 1
        sp_row = rows[0]
        assert sp_row[0] == "spiral_reinforcement"
        assert sp_row[1] is True
        assert "Spiral test entry" in sp_row[2]

    def test_both_subjects(self, conn):
        """Insert human L5+ AND ai L5+ events, verify both subjects in structural_events."""
        sid = "integ-b01-both"
        _insert_flame_event(conn, "fe-human5", sid, 10, 5, subject="human", ccd_axis="test-axis")
        _insert_flame_event(conn, "fe-ai5", sid, 12, 5, subject="ai", ccd_axis="ai-axis")

        _run_detect_and_write(conn, sid)

        subjects = conn.execute(
            "SELECT DISTINCT subject FROM structural_events WHERE session_id = ?",
            [sid],
        ).fetchall()
        subject_set = {row[0] for row in subjects}

        assert "human" in subject_set
        assert "ai" in subject_set

    def test_evidence_populated(self, conn):
        """Insert L5+ event with ccd_axis='deposit-not-detect', verify evidence contains axis."""
        sid = "integ-b01-ev"
        _insert_flame_event(conn, "fe-h5", sid, 10, 5, ccd_axis="deposit-not-detect")

        _run_detect_and_write(conn, sid)

        rows = conn.execute(
            "SELECT evidence FROM structural_events WHERE session_id = ?",
            [sid],
        ).fetchall()

        assert len(rows) > 0
        # At least one evidence field should contain the axis name
        evidence_texts = [row[0] for row in rows if row[0]]
        axis_mentions = [e for e in evidence_texts if "deposit-not-detect" in e]
        assert len(axis_mentions) > 0


# ============================================================
# BRIDGE-02: StructuralIntegrityScore computed per session (5 tests)
# ============================================================


class TestBridge02ScoreComputation:
    """BRIDGE-02: StructuralIntegrityScore computed per session for both human and AI."""

    def test_score_for_human(self, conn):
        """Insert human flame_events, detect+write+compute, verify StructuralIntegrityResult."""
        sid = "integ-b02-human"
        _insert_flame_event(conn, "fe-h5", sid, 10, 5, subject="human", ccd_axis="test-axis")
        _insert_flame_event(conn, "fe-l1", sid, 11, 1, subject="human", ccd_axis="test-axis")

        _run_detect_and_write(conn, sid)
        result = compute_structural_integrity(conn, sid, "human")

        assert result.session_id == sid
        assert result.subject == "human"
        assert 0.0 <= result.integrity_score <= 1.0

    def test_score_for_ai(self, conn):
        """Insert AI flame_events, detect+write+compute, verify StructuralIntegrityResult for AI."""
        sid = "integ-b02-ai"
        _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="ai-axis")

        _run_detect_and_write(conn, sid)
        result = compute_structural_integrity(conn, sid, "ai")

        assert result.session_id == sid
        assert result.subject == "ai"
        assert 0.0 <= result.integrity_score <= 1.0

    def test_neutral_fallback(self, conn):
        """No flame_events at all, compute for 'human' -> neutral fallback ratios (0.5), not 0.0."""
        sid = "integ-b02-neutral"
        # No flame events inserted -- empty session

        # Still need to run detect+write (produces nothing)
        _run_detect_and_write(conn, sid)
        result = compute_structural_integrity(conn, sid, "human")

        assert result.gravity_ratio == 0.5
        assert result.main_cable_ratio == 0.5
        assert result.dependency_ratio == 0.5
        # Spiral: 0 events -> 0.0 (no bonus, no penalty)
        assert result.spiral_capped == 0.0

    def test_high_integrity_score(self, conn):
        """All signals pass (grounded, connected, sequenced, spiral) -> score >= 0.7."""
        sid = "integ-b02-high"

        # Gravity: L5 + L1 with same axis -> grounded
        _insert_flame_event(conn, "fe-h5", sid, 10, 5, subject="human", ccd_axis="core-axis")
        _insert_flame_event(conn, "fe-l1", sid, 11, 1, subject="human", ccd_axis="core-axis")

        # Main cable: axis in axis_edges -> connected
        _insert_axis_edge(conn, "core-axis", "related-axis")

        # Dependency: prerequisite appears before dependent at L3+
        _insert_flame_event(conn, "fe-prereq", sid, 5, 3, subject="human", ccd_axis="related-axis")

        # Spiral: wisdom entry for this session
        _insert_project_wisdom(conn, "w-high-01", sid, title="High integrity wisdom")

        _run_detect_and_write(conn, sid)
        result = compute_structural_integrity(conn, sid, "human")

        # With all signals passing plus spiral, score should be high
        assert result.integrity_score >= 0.7

    def test_score_formula_components(self, conn):
        """Insert 2 gravity pass + 0 main_cable + 0 dep + 0 spiral -> verify gravity_ratio."""
        sid = "integ-b02-formula"

        # Two grounded L5+ events
        _insert_flame_event(conn, "fe-h5a", sid, 10, 5, subject="human", ccd_axis="axis-1")
        _insert_flame_event(conn, "fe-l1a", sid, 11, 1, subject="human", ccd_axis="axis-1")
        _insert_flame_event(conn, "fe-h5b", sid, 20, 5, subject="human", ccd_axis="axis-2")
        _insert_flame_event(conn, "fe-l1b", sid, 21, 1, subject="human", ccd_axis="axis-2")

        _run_detect_and_write(conn, sid)
        result = compute_structural_integrity(conn, sid, "human")

        # 2 gravity checks, both passed -> gravity_ratio = 1.0
        assert result.gravity_ratio == 1.0
        # 2 main_cable events (both floating, no axis_edges) -> main_cable_ratio = 0.0
        assert result.main_cable_ratio == 0.0
        # Dependency sequencing: 2 new axis introductions, no axis_edges -> True (no prerequisites)
        assert result.dependency_ratio == 1.0
        # No spiral events
        assert result.spiral_capped == 0.0


# ============================================================
# BRIDGE-03: Op-8 fires on AI floating cables (4 tests)
# ============================================================


class TestBridge03Op8Deposit:
    """BRIDGE-03: Op-8 fires on AI floating cables and deposits corrections."""

    def test_op8_deposits_floating_cable(self, conn):
        """Full chain: AI L5+ without grounding -> detect+write+deposit -> memory_candidates has op8_correction."""
        sid = "integ-b03-deposit"
        _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="floating-axis")

        _run_detect_and_write(conn, sid)
        count = deposit_op8_corrections(conn, sid)

        assert count >= 1

        # Verify memory_candidates row
        row = conn.execute(
            "SELECT ccd_axis, source_type, status "
            "FROM memory_candidates WHERE source_type = 'op8_correction'",
        ).fetchone()
        assert row is not None
        assert row[0] == "floating-axis"
        assert row[1] == "op8_correction"
        assert row[2] == "pending"

    def test_op8_confidence_fidelity(self, conn):
        """After deposit, verify fidelity=2 and confidence=0.60 in memory_candidates."""
        sid = "integ-b03-fidelity"
        _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="fidelity-axis")

        _run_detect_and_write(conn, sid)
        deposit_op8_corrections(conn, sid)

        row = conn.execute(
            "SELECT fidelity, confidence "
            "FROM memory_candidates WHERE source_type = 'op8_correction'",
        ).fetchone()
        assert row is not None
        assert row[0] == 2  # fidelity
        assert row[1] == pytest.approx(0.60, abs=1e-4)  # confidence

    def test_op8_dedup_across_sessions(self, conn):
        """Run deposit_op8_corrections twice for same session -> only 1 candidate."""
        sid = "integ-b03-dedup"
        _insert_flame_event(conn, "fe-ai5", sid, 10, 5, subject="ai", ccd_axis="dedup-axis")

        _run_detect_and_write(conn, sid)

        deposit_op8_corrections(conn, sid)
        deposit_op8_corrections(conn, sid)

        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates WHERE source_type = 'op8_correction'",
        ).fetchone()[0]
        assert count == 1

    def test_op8_skips_human(self, conn):
        """Human floating main_cable -> Op-8 deposits 0 rows (AI-only)."""
        sid = "integ-b03-human"
        _insert_flame_event(conn, "fe-h5", sid, 10, 5, subject="human", ccd_axis="human-floating")

        _run_detect_and_write(conn, sid)
        count = deposit_op8_corrections(conn, sid)

        assert count == 0

        mc_count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates WHERE source_type = 'op8_correction'",
        ).fetchone()[0]
        assert mc_count == 0


# ============================================================
# Assessment session isolation (1 test)
# ============================================================


class TestAssessmentIsolation:
    """Assessment session isolation: assessment_session_id IS NULL filtering works."""

    def test_assessment_session_isolation(self, conn):
        """Assessment events excluded from production structural analysis."""
        sid = "integ-assess-iso"

        # Insert production event (assessment_session_id=NULL)
        _insert_flame_event(
            conn, "fe-prod5", sid, 10, 5,
            subject="human", ccd_axis="prod-axis",
            assessment_session_id=None,
        )

        # Insert assessment event (assessment_session_id set)
        _insert_flame_event(
            conn, "fe-assess5", sid, 20, 5,
            subject="human", ccd_axis="assess-axis",
            assessment_session_id="assessment-1",
        )

        # Run detect in production mode (assessment_session_id=None)
        events = detect_structural_signals(conn, sid, assessment_session_id=None)

        # Only production event should be detected
        axes_in_evidence = [e.evidence for e in events if e.evidence]
        # Assessment axis should NOT appear
        assess_mentions = [e for e in axes_in_evidence if "assess-axis" in e]
        assert len(assess_mentions) == 0

        # Production axis SHOULD appear
        prod_mentions = [e for e in axes_in_evidence if "prod-axis" in e]
        assert len(prod_mentions) > 0


# ============================================================
# End-to-end chain tests (2 tests)
# ============================================================


class TestEndToEndChain:
    """End-to-end: flame_events -> structural_events -> memory_candidates deposit chain."""

    def test_full_chain(self, conn):
        """Mixed realistic session: grounded + floating AI events -> detect -> write -> compute -> deposit."""
        sid = "integ-e2e-full"

        # Grounded human L5 event (gravity passes)
        _insert_flame_event(conn, "fe-h5-grounded", sid, 10, 5, subject="human", ccd_axis="grounded-axis")
        _insert_flame_event(conn, "fe-l1-ground", sid, 11, 1, subject="human", ccd_axis="grounded-axis")

        # Floating AI L5 event (no grounding, no axis_edges)
        _insert_flame_event(conn, "fe-ai5-float", sid, 20, 5, subject="ai", ccd_axis="floating-ai-axis")

        # Connected AI L5 event (axis in axis_edges)
        _insert_flame_event(conn, "fe-ai5-conn", sid, 30, 5, subject="ai", ccd_axis="connected-axis")
        _insert_axis_edge(conn, "connected-axis", "grounded-axis")

        # Spiral wisdom for session
        _insert_project_wisdom(conn, "w-e2e-01", sid, title="E2E wisdom")

        # Step 1: Detect + write
        events = _run_detect_and_write(conn, sid)
        assert len(events) > 0

        # Step 2: Verify structural_events populated
        se_count = conn.execute(
            "SELECT COUNT(*) FROM structural_events WHERE session_id = ?",
            [sid],
        ).fetchone()[0]
        assert se_count > 0

        # Verify all four signal types present
        signal_types = conn.execute(
            "SELECT DISTINCT signal_type FROM structural_events WHERE session_id = ?",
            [sid],
        ).fetchall()
        signal_type_set = {row[0] for row in signal_types}
        assert "gravity_check" in signal_type_set
        assert "main_cable" in signal_type_set
        # dependency_sequencing should be present (new axis introductions exist)
        assert "dependency_sequencing" in signal_type_set
        assert "spiral_reinforcement" in signal_type_set

        # Step 3: Compute scores
        human_result = compute_structural_integrity(conn, sid, "human")
        ai_result = compute_structural_integrity(conn, sid, "ai")

        assert human_result.session_id == sid
        assert human_result.subject == "human"
        assert 0.0 <= human_result.integrity_score <= 1.0

        assert ai_result.session_id == sid
        assert ai_result.subject == "ai"
        assert 0.0 <= ai_result.integrity_score <= 1.0

        # Step 4: Deposit Op-8 corrections for floating AI cables
        deposit_count = deposit_op8_corrections(conn, sid)

        # floating-ai-axis has no axis_edges -> should produce an op8_correction
        assert deposit_count >= 1

        # Verify memory_candidates
        mc_rows = conn.execute(
            "SELECT ccd_axis, source_type, status "
            "FROM memory_candidates WHERE source_type = 'op8_correction'",
        ).fetchall()
        assert len(mc_rows) >= 1
        floating_axes = {row[0] for row in mc_rows}
        assert "floating-ai-axis" in floating_axes

    def test_empty_session(self, conn):
        """No flame_events. Full chain. No crashes. Neutral scores. 0 corrections."""
        sid = "integ-e2e-empty"

        # Step 1: Detect + write (empty)
        events = _run_detect_and_write(conn, sid)
        assert events == []

        # Step 2: No structural_events
        se_count = conn.execute(
            "SELECT COUNT(*) FROM structural_events WHERE session_id = ?",
            [sid],
        ).fetchone()[0]
        assert se_count == 0

        # Step 3: Compute returns neutral scores
        result = compute_structural_integrity(conn, sid, "human")
        assert result.gravity_ratio == 0.5
        assert result.main_cable_ratio == 0.5
        assert result.dependency_ratio == 0.5
        assert result.spiral_capped == 0.0

        # Step 4: Deposit returns 0
        count = deposit_op8_corrections(conn, sid)
        assert count == 0
