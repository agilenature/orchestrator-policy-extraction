"""Tests for Tier 2 DDF enrichment, AI marker detection, and deposit (Phase 15).

Covers FlameEventExtractor:
- enrich_tier1 upgrades L0->L3 with multi-scope, preserves without context
- enrich_tier1 L6 sets flood_confirmed=True
- detect_ai_markers assertive L2, flood L6, ignores human
- deposit_level6 writes candidates, skips low levels, marks deposited, dedup
- enriched events have detection_source='opeml'

Covers CausalIsolationRecorder:
- Success, failed, missing isolation markers
- No premises -> empty list
- Non-causal claims skipped
- All events subject='ai'
- Reads from premise_registry

Covers FalseIntegrationDetector:
- High/low confidence threshold behavior
- Writes hypotheses to axis_hypotheses table
- No episodes / single scope -> no detection
- Subject='ai' on all flame events
- Hypothesis make_id determinism
- Dual output (flame event + hypothesis)
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.ddf.models import AxisHypothesis, FlameEvent
from src.pipeline.ddf.tier2.causal_isolation import CausalIsolationRecorder
from src.pipeline.ddf.tier2.false_integration import FalseIntegrationDetector
from src.pipeline.ddf.tier2.flame_extractor import FlameEventExtractor
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.models.config import PipelineConfig
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema (including DDF)."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


@pytest.fixture
def config():
    """Default PipelineConfig for testing."""
    return PipelineConfig()


def _insert_stub(
    conn: duckdb.DuckDBPyConnection,
    flame_event_id: str = "stub_1",
    session_id: str = "sess1",
    marker_level: int = 0,
    marker_type: str = "L0_trunk",
    evidence_excerpt: str = "some evidence text that is long enough for testing purposes",
    axis_identified: str | None = None,
    prompt_number: int = 1,
    human_id: str = "default_human",
    source_episode_id: str | None = None,
    session_event_ref: str | None = None,
    quality_score: float | None = None,
) -> None:
    """Insert a stub flame_event directly into the database."""
    conn.execute(
        """
        INSERT INTO flame_events (
            flame_event_id, session_id, human_id, prompt_number,
            marker_level, marker_type, evidence_excerpt, quality_score,
            axis_identified, flood_confirmed, subject, detection_source,
            deposited_to_candidates, source_episode_id, session_event_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE, 'human', 'stub', FALSE, ?, ?)
        """,
        [
            flame_event_id,
            session_id,
            human_id,
            prompt_number,
            marker_level,
            marker_type,
            evidence_excerpt,
            quality_score,
            axis_identified,
            source_episode_id,
            session_event_ref,
        ],
    )


# ═══════════════════════════════════════════════════════════════════
# FlameEventExtractor.enrich_tier1
# ═══════════════════════════════════════════════════════════════════


# ── Test 1: L0 -> L3 upgrade with multi-scope ──


def test_enrich_tier1_upgrades_l0_to_l3(conn, config):
    """L0 stub + episode with 2 scope paths -> new_level=3."""
    _insert_stub(conn, "stub_l0", "sess1", marker_level=0, source_episode_id="ep1")
    episodes = [
        {
            "episode_id": "ep1",
            "orchestrator_action": {"scope": ["auth/login", "auth/session"]},
            "reaction_label": "neutral",
        }
    ]
    ext = FlameEventExtractor(config, conn)
    enriched = ext.enrich_tier1("sess1", episodes)
    assert len(enriched) == 1
    assert enriched[0].marker_level == 3


# ── Test 2: preserves stub without matching episode ──


def test_enrich_tier1_preserves_stub_without_context(conn, config):
    """L0 without matching episode stays L0."""
    _insert_stub(conn, "stub_l0_no_ep", "sess1", marker_level=0)
    ext = FlameEventExtractor(config, conn)
    enriched = ext.enrich_tier1("sess1", [])
    assert len(enriched) == 1
    assert enriched[0].marker_level == 0


# ── Test 3: L6 sets flood_confirmed=True ──


def test_enrich_tier1_l6_sets_flood_confirmed(conn, config):
    """Upgrade to L6 sets flood_confirmed=True."""
    _insert_stub(
        conn,
        "stub_l2_approve",
        "sess1",
        marker_level=2,
        source_episode_id="ep2",
        axis_identified="deposit-not-detect",
        evidence_excerpt="x" * 60,  # >50 chars
    )
    episodes = [
        {
            "episode_id": "ep2",
            "orchestrator_action": {"scope": ["a"]},
            "reaction_label": "approve",
        }
    ]
    ext = FlameEventExtractor(config, conn)
    enriched = ext.enrich_tier1("sess1", episodes)
    assert len(enriched) == 1
    assert enriched[0].marker_level == 6
    assert enriched[0].flood_confirmed is True


# ═══════════════════════════════════════════════════════════════════
# FlameEventExtractor.detect_ai_markers
# ═══════════════════════════════════════════════════════════════════


# ── Test 4: AI assertive L2 ──


def test_detect_ai_markers_assertive_l2(conn, config):
    """AI text with 'the root cause is' -> subject='ai', marker_level=2."""
    events = [
        {
            "actor": "executor",
            "payload": {
                "common": {"text": "After analysis, the root cause is a missing index."}
            },
        }
    ]
    ext = FlameEventExtractor(config, conn)
    markers = ext.detect_ai_markers("sess1", [], events)
    assert len(markers) >= 1
    assert markers[0].subject == "ai"
    assert markers[0].marker_level == 2


# ── Test 5: AI flood L6 ──


def test_detect_ai_markers_flood_l6(conn, config):
    """AI text with 3+ 'for example/instance/such as' -> L6, flood_confirmed."""
    text = (
        "This is common. For example, auth flows fail. For instance, "
        "token refresh breaks. Such as when the JWT expires. Specifically, "
        "the rotate endpoint returns 401."
    )
    events = [
        {"actor": "assistant", "payload": {"common": {"text": text}}}
    ]
    ext = FlameEventExtractor(config, conn)
    markers = ext.detect_ai_markers("sess1", [], events)
    l6 = [m for m in markers if m.marker_level == 6]
    assert len(l6) == 1
    assert l6[0].flood_confirmed is True
    assert l6[0].subject == "ai"


# ── Test 6: ignores human actor ──


def test_detect_ai_markers_ignores_human(conn, config):
    """Human actor events not included in AI markers."""
    events = [
        {
            "actor": "human_orchestrator",
            "payload": {
                "common": {"text": "The root cause is obvious."}
            },
        }
    ]
    ext = FlameEventExtractor(config, conn)
    markers = ext.detect_ai_markers("sess1", [], events)
    assert len(markers) == 0


# ═══════════════════════════════════════════════════════════════════
# FlameEventExtractor.deposit_level6
# ═══════════════════════════════════════════════════════════════════


# ── Test 7: deposit L6 writes candidates ──


def test_deposit_level6_writes_candidates(conn, config):
    """L6 + flood_confirmed -> memory_candidates row created."""
    fe = FlameEvent(
        flame_event_id="fe_l6_deposit",
        session_id="sess1",
        marker_level=6,
        marker_type="ai_concretization_flood",
        evidence_excerpt="Flood evidence text here",
        flood_confirmed=True,
        subject="ai",
        detection_source="opeml",
    )
    # Write event so mark_deposited can find it
    write_flame_events(conn, [fe])

    ext = FlameEventExtractor(config, conn)
    count = ext.deposit_level6(conn, [fe])
    assert count == 1

    row = conn.execute("SELECT COUNT(*) FROM memory_candidates").fetchone()[0]
    assert row == 1


# ── Test 8: deposit skips low levels ──


def test_deposit_level6_skips_low_levels(conn, config):
    """L3 event not deposited (returns 0)."""
    fe = FlameEvent(
        flame_event_id="fe_l3_skip",
        session_id="sess1",
        marker_level=3,
        marker_type="L0_trunk_enriched",
        flood_confirmed=False,
        subject="human",
        detection_source="opeml",
    )
    ext = FlameEventExtractor(config, conn)
    count = ext.deposit_level6(conn, [fe])
    assert count == 0


# ── Test 9: deposit marks deposited flag ──


def test_deposit_level6_marks_deposited(conn, config):
    """deposited_to_candidates = True after deposit."""
    fe = FlameEvent(
        flame_event_id="fe_l6_mark",
        session_id="sess1",
        marker_level=6,
        marker_type="ai_concretization_flood",
        flood_confirmed=True,
        subject="ai",
        detection_source="opeml",
    )
    write_flame_events(conn, [fe])

    ext = FlameEventExtractor(config, conn)
    ext.deposit_level6(conn, [fe])

    row = conn.execute(
        "SELECT deposited_to_candidates FROM flame_events WHERE flame_event_id = 'fe_l6_mark'"
    ).fetchone()
    assert row[0] is True


# ── Test 10: deposit dedup ──


def test_deposit_level6_dedup(conn, config):
    """Same axis deposited twice -> count still 1 (dedup)."""
    fe1 = FlameEvent(
        flame_event_id="fe_l6_d1",
        session_id="sess1",
        marker_level=6,
        marker_type="ai_concretization_flood",
        flood_confirmed=True,
        subject="ai",
        detection_source="opeml",
    )
    fe2 = FlameEvent(
        flame_event_id="fe_l6_d2",
        session_id="sess1",
        marker_level=6,
        marker_type="ai_concretization_flood",
        flood_confirmed=True,
        subject="ai",
        detection_source="opeml",
    )
    write_flame_events(conn, [fe1, fe2])

    ext = FlameEventExtractor(config, conn)
    count = ext.deposit_level6(conn, [fe1, fe2])
    # First deposits, second is dedup (same axis+scope), count=1
    assert count == 1

    total = conn.execute("SELECT COUNT(*) FROM memory_candidates").fetchone()[0]
    assert total == 1


# ── Test 11: enriched events have detection_source='opeml' ──


def test_enrich_tier1_returns_opeml_source(conn, config):
    """Enriched events have detection_source='opeml'."""
    _insert_stub(conn, "stub_check", "sess1", marker_level=0)
    ext = FlameEventExtractor(config, conn)
    enriched = ext.enrich_tier1("sess1", [])
    assert len(enriched) == 1
    assert enriched[0].detection_source == "opeml"


# ═══════════════════════════════════════════════════════════════════
# CausalIsolationRecorder
# ═══════════════════════════════════════════════════════════════════


def _insert_premise(
    conn: duckdb.DuckDBPyConnection,
    premise_id: str,
    claim: str,
    session_id: str = "sess1",
    foil_path_outcomes: str | None = None,
    foil: str | None = None,
) -> None:
    """Insert a premise_registry row for testing."""
    conn.execute(
        """
        INSERT INTO premise_registry (premise_id, claim, session_id, foil_path_outcomes, foil)
        VALUES (?, ?, ?, ?, ?)
        """,
        [premise_id, claim, session_id, foil_path_outcomes, foil],
    )


# ── Test 12: causal isolation success ──


def test_causal_isolation_success(conn):
    """Premise with divergence_node -> marker_level=3, subject='ai'."""
    _insert_premise(
        conn,
        "p1",
        "the schema causes the error",
        foil_path_outcomes=json.dumps({"divergence_node": "step_3"}),
    )
    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess1")
    assert len(markers) == 1
    assert markers[0].marker_level == 3
    assert markers[0].marker_type == "causal_isolation_success"
    assert markers[0].subject == "ai"


# ── Test 13: causal isolation failed ──


def test_causal_isolation_failed(conn):
    """Premise with foil outcomes but no divergence_node -> marker_level=2, subject='ai'."""
    _insert_premise(
        conn,
        "p2",
        "X leads to Y",
        foil_path_outcomes=json.dumps({"checked": True}),
    )
    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess1")
    assert len(markers) == 1
    assert markers[0].marker_level == 2
    assert markers[0].marker_type == "causal_isolation_failed"
    assert markers[0].subject == "ai"


# ── Test 14: missing isolation (causal without foil) ──


def test_causal_isolation_missing(conn):
    """Causal claim without foil -> marker_type='missing_isolation', subject='ai'."""
    _insert_premise(
        conn,
        "p3",
        "because X causes Y, we need Z",
        foil_path_outcomes=None,
    )
    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess1")
    assert len(markers) == 1
    assert markers[0].marker_type == "missing_isolation"
    assert markers[0].marker_level == 1
    assert markers[0].subject == "ai"


# ── Test 15: no premises -> empty list ──


def test_causal_isolation_no_premises(conn):
    """Session with no premises -> empty list."""
    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess_empty")
    assert len(markers) == 0


# ── Test 16: non-causal claim skipped ──


def test_causal_isolation_non_causal_skipped(conn):
    """Non-causal claim without foil -> not flagged."""
    _insert_premise(
        conn,
        "p4",
        "file exists at path /tmp/data.json",
        foil_path_outcomes=None,
    )
    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess1")
    assert len(markers) == 0


# ═══════════════════════════════════════════════════════════════════
# FalseIntegrationDetector
# ═══════════════════════════════════════════════════════════════════


def _make_episode(
    episode_id: str,
    scope: list[str],
    constraints: list[str] | None = None,
) -> dict:
    """Build a minimal episode dict for false integration testing."""
    return {
        "episode_id": episode_id,
        "orchestrator_action": {
            "scope": scope,
            "constraints": constraints or [],
        },
    }


# ── Test 17: high confidence emits flame event ──


def test_false_integration_high_confidence(conn, config):
    """confidence >= 0.6 -> flame event emitted."""
    episodes = [_make_episode("ep1", ["auth/login", "db/migrate"])]
    det = FalseIntegrationDetector(config, conn)
    flames, hyps = det.detect("sess1", episodes)
    assert len(flames) == 1
    assert flames[0].marker_level == 5
    assert flames[0].marker_type == "false_integration"


# ── Test 18: low confidence no flame event, hypothesis still recorded ──


def test_false_integration_low_confidence(conn, config):
    """confidence < 0.6 -> no flame event, hypothesis still recorded."""
    # Need exactly 2 prefixes -> confidence = 0.6. But we need <0.6.
    # Use a custom config with higher threshold.
    from src.pipeline.models.config import DDFConfig

    high_config = PipelineConfig(ddf=DDFConfig(false_integration_confidence_threshold=0.8))
    # 2 prefixes -> confidence = 0.6, threshold = 0.8 -> no flame
    episodes = [_make_episode("ep1", ["auth/login", "db/migrate"])]
    det = FalseIntegrationDetector(high_config, conn)
    flames, hyps = det.detect("sess1", episodes)
    assert len(flames) == 0
    assert len(hyps) == 1  # hypothesis still recorded


# ── Test 19: writes hypotheses to axis_hypotheses table ──


def test_false_integration_writes_hypotheses(conn, config):
    """axis_hypotheses table populated after detect()."""
    episodes = [_make_episode("ep1", ["auth/login", "db/migrate"])]
    det = FalseIntegrationDetector(config, conn)
    det.detect("sess1", episodes)
    count = conn.execute("SELECT COUNT(*) FROM axis_hypotheses").fetchone()[0]
    assert count == 1


# ── Test 20: no episodes -> empty results ──


def test_false_integration_no_episodes(conn, config):
    """Empty episodes -> empty results."""
    det = FalseIntegrationDetector(config, conn)
    flames, hyps = det.detect("sess1", [])
    assert len(flames) == 0
    assert len(hyps) == 0


# ── Test 21: single scope -> no detection ──


def test_false_integration_single_scope(conn, config):
    """Single scope path -> no false integration detected."""
    episodes = [_make_episode("ep1", ["auth/login"])]
    det = FalseIntegrationDetector(config, conn)
    flames, hyps = det.detect("sess1", episodes)
    assert len(flames) == 0
    assert len(hyps) == 0


# ── Test 22: all causal isolation events subject='ai' ──


def test_causal_isolation_all_events_subject_ai(conn):
    """ALL causal isolation events have subject='ai'."""
    _insert_premise(
        conn,
        "pa",
        "because X",
        foil_path_outcomes=json.dumps({"divergence_node": "s1"}),
    )
    _insert_premise(
        conn,
        "pb",
        "since Y fails",
        foil_path_outcomes=json.dumps({"checked": True}),
    )
    _insert_premise(
        conn,
        "pc",
        "therefore Z must hold",
        foil_path_outcomes=None,
    )
    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess1")
    assert len(markers) == 3
    for m in markers:
        assert m.subject == "ai", f"Expected subject='ai', got '{m.subject}' for {m.marker_type}"


# ── Test 23: false integration all flame events subject='ai' ──


def test_false_integration_subject_ai(conn, config):
    """All false integration flame events have subject='ai'."""
    episodes = [
        _make_episode("ep1", ["auth/login", "db/migrate", "api/endpoints"]),
    ]
    det = FalseIntegrationDetector(config, conn)
    flames, _ = det.detect("sess1", episodes)
    assert len(flames) >= 1
    for f in flames:
        assert f.subject == "ai"


# ── Test 24: causal isolation reads from premise_registry ──


def test_causal_isolation_reads_premise_registry(conn):
    """Verifies records come from premise_registry table."""
    _insert_premise(
        conn,
        "pread",
        "leads to failure",
        foil_path_outcomes=json.dumps({"divergence_node": "step_x"}),
    )
    # Verify the premise is in the table
    pcount = conn.execute(
        "SELECT COUNT(*) FROM premise_registry WHERE session_id = 'sess1'"
    ).fetchone()[0]
    assert pcount == 1

    rec = CausalIsolationRecorder(conn)
    markers = rec.record("sess1")
    assert len(markers) == 1
    assert markers[0].source_episode_id == "pread"


# ── Test 25: hypothesis make_id is deterministic ──


def test_false_integration_hypothesis_make_id(conn, config):
    """Hypothesis IDs are deterministic for same inputs."""
    id1 = AxisHypothesis.make_id("sess1", "ep1", "axis_a")
    id2 = AxisHypothesis.make_id("sess1", "ep1", "axis_a")
    id3 = AxisHypothesis.make_id("sess1", "ep1", "axis_b")
    assert id1 == id2  # Same inputs -> same ID
    assert id1 != id3  # Different axis -> different ID


# ── Test 26: dual output for high confidence detection ──


def test_false_integration_dual_output(conn, config):
    """High-confidence detection produces BOTH axis_hypotheses row AND flame event."""
    episodes = [_make_episode("ep_dual", ["auth/login", "db/migrate"])]
    det = FalseIntegrationDetector(config, conn)
    flames, hyps = det.detect("sess1", episodes)
    assert len(flames) == 1, "Expected 1 flame event for high-confidence detection"
    assert len(hyps) == 1, "Expected 1 hypothesis"

    # Verify both are in their respective stores
    ah_count = conn.execute("SELECT COUNT(*) FROM axis_hypotheses").fetchone()[0]
    assert ah_count == 1

    # Flame event has matching episode_id
    assert flames[0].source_episode_id == "ep_dual"
    assert hyps[0].episode_id == "ep_dual"
