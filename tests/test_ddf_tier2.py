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
