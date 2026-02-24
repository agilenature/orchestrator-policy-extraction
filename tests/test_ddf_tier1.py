"""Tests for Tier 1 DDF marker detectors L0-L2 and OAxsDetector (Phase 15).

Covers:
- L0 trunk identification (positive/negative/excerpt)
- L1 causal language (positive/negative)
- L2 assertive causal (positive/negative)
- detect_markers human-only filtering, FlameEvent output, prompt numbering
- OAxsDetector both-conditions, single-condition, actor filter, reset, dedup
"""

from __future__ import annotations

import pytest

from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.tier1.markers import (
    detect_l0_trunk,
    detect_l1_causal,
    detect_l2_assertive,
    detect_markers,
)
from src.pipeline.ddf.tier1.o_axs import OAxsDetector
from src.pipeline.models.config import OAxsConfig


# ── Helper: build a minimal event dict ──


def _make_event(
    text: str,
    actor: str = "human_orchestrator",
    event_type: str = "user_msg",
) -> dict:
    return {
        "actor": actor,
        "event_type": event_type,
        "payload": {"common": {"text": text}},
    }


# ═══════════════════════════════════════════════════════════════════
# L0 Trunk Identification
# ═══════════════════════════════════════════════════════════════════


# ── Test 1: L0 positive ──


def test_l0_trunk_positive():
    """'The core issue is X' triggers L0 detection."""
    detected, _ = detect_l0_trunk("The core issue is that we lack a schema.")
    assert detected is True


# ── Test 2: L0 negative ──


def test_l0_trunk_negative():
    """Ordinary text without trunk markers is not detected."""
    detected, _ = detect_l0_trunk("I found the file in the directory listing.")
    assert detected is False


# ── Test 3: L0 evidence excerpt ──


def test_l0_trunk_evidence_excerpt():
    """Evidence excerpt is not None when L0 is detected."""
    detected, excerpt = detect_l0_trunk(
        "Looking at everything, the fundamental question is how we handle state."
    )
    assert detected is True
    assert excerpt is not None
    assert "fundamental question" in excerpt


# ═══════════════════════════════════════════════════════════════════
# L1 Causal Language
# ═══════════════════════════════════════════════════════════════════


# ── Test 4: L1 positive ──


def test_l1_causal_positive():
    """'because X leads to Y' triggers L1 detection."""
    detected, _ = detect_l1_causal("because X leads to Y, we need to fix it.")
    assert detected is True


# ── Test 5: L1 negative ──


def test_l1_causal_negative():
    """'today then tomorrow' does not trigger L1 (no causal structure)."""
    detected, _ = detect_l1_causal("today then tomorrow we ship the release.")
    assert detected is False


# ═══════════════════════════════════════════════════════════════════
# L2 Assertive Causal
# ═══════════════════════════════════════════════════════════════════


# ── Test 6: L2 positive ──


def test_l2_assertive_positive():
    """'the root cause is memory leak' triggers L2 detection."""
    detected, _ = detect_l2_assertive("the root cause is a memory leak in the pool.")
    assert detected is True


# ── Test 7: L2 negative ──


def test_l2_assertive_negative():
    """Tentative language does not trigger L2."""
    detected, _ = detect_l2_assertive("maybe it could be X, but I'm not sure yet.")
    assert detected is False


# ═══════════════════════════════════════════════════════════════════
# detect_markers integration
# ═══════════════════════════════════════════════════════════════════


# ── Test 8: human-only filtering ──


def test_detect_markers_human_only():
    """Non-human-orchestrator events are skipped entirely."""
    events = [
        _make_event("The core issue is X", actor="ai_agent"),
        _make_event("the root cause is Y", actor="system"),
    ]
    results = detect_markers(events, "sess-1")
    assert results == []


# ── Test 9: returns FlameEvent objects ──


def test_detect_markers_returns_flame_events():
    """detect_markers returns a list of FlameEvent objects."""
    events = [
        _make_event("The core issue is that the schema is wrong."),
    ]
    results = detect_markers(events, "sess-1")
    assert len(results) >= 1
    assert all(isinstance(r, FlameEvent) for r in results)
    assert results[0].session_id == "sess-1"
    assert results[0].detection_source == "stub"
    assert results[0].subject == "human"


# ── Test 10: prompt numbering ──


def test_detect_markers_prompt_numbering():
    """Prompt numbers are assigned sequentially to human messages."""
    events = [
        _make_event("The core issue is X"),
        _make_event("something neutral from AI", actor="ai_agent"),
        _make_event("because Y leads to Z"),
    ]
    results = detect_markers(events, "sess-2")
    # First human message -> prompt_number=1 (L0)
    # Second human message -> prompt_number=2 (L1)
    prompt_numbers = [r.prompt_number for r in results]
    assert 1 in prompt_numbers
    assert 2 in prompt_numbers


# ═══════════════════════════════════════════════════════════════════
# OAxsDetector
# ═══════════════════════════════════════════════════════════════════


def _small_config() -> OAxsConfig:
    """Config with small window for easy threshold testing."""
    return OAxsConfig(
        granularity_drop_ratio=0.5,
        prior_prompts_window=2,
        novel_concept_min_occurrences=2,
        novel_concept_message_window=3,
    )


# ── Test 11: both conditions met ──


def test_o_axs_both_conditions_met():
    """With big token drop + novel concept 2+ times -> True."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    # Build up history with long messages (establish high average)
    det.detect("word " * 50, actor)
    det.detect("word " * 50, actor)

    # Short message with novel concept repeated (Trunk Concept appears twice)
    detected, evidence = det.detect(
        "Trunk Concept is the Trunk Concept here", actor
    )
    assert detected is True
    assert evidence is not None
    assert evidence["novel_concept"] == "Trunk Concept"
    assert evidence["token_count"] < evidence["avg_prior"]


# ── Test 12: granularity only (no novel concept) ──


def test_o_axs_granularity_only():
    """Big drop without novel concept -> False."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    det.detect("word " * 50, actor)
    det.detect("word " * 50, actor)

    # Short message, but no capitalized novel concept
    detected, evidence = det.detect("just a few lowercase words", actor)
    assert detected is False
    assert evidence is None


# ── Test 13: novel concept only (no drop) ──


def test_o_axs_novel_concept_only():
    """Novel concept without big drop -> False."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    # Short history, then roughly same-length message with concept
    det.detect("some words here", actor)
    det.detect("more words here", actor)

    detected, evidence = det.detect(
        "Trunk Concept is the Trunk Concept here yes", actor
    )
    assert detected is False
    assert evidence is None


# ── Test 14: actor filter ──


def test_o_axs_actor_filter():
    """Non-human actor always returns False."""
    cfg = _small_config()
    det = OAxsDetector(cfg)

    detected, evidence = det.detect("The core issue is X", "ai_agent")
    assert detected is False
    assert evidence is None


# ── Test 15: reset clears state ──


def test_o_axs_reset_clears_state():
    """After reset(), known_concepts is empty set."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    det.detect("word " * 50, actor)
    det.detect("word " * 50, actor)
    det.detect("Trunk Concept is the Trunk Concept here", actor)

    assert len(det.known_concepts) > 0

    det.reset()
    assert det.known_concepts == set()
    assert len(det.token_counts) == 0
    assert len(det.recent_messages) == 0


# ── Test 16: known concepts suppresses repeat detection ──


def test_o_axs_known_concepts_suppresses():
    """Concept seen once added to known_concepts, won't fire again on same concept."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    # First detection
    det.detect("word " * 50, actor)
    det.detect("word " * 50, actor)
    detected1, _ = det.detect(
        "Trunk Concept is the Trunk Concept here", actor
    )
    assert detected1 is True

    # Reset token history but NOT concepts (manual manipulation for test)
    det.token_counts.clear()
    det.recent_messages.clear()

    # Build up history again
    det.detect("word " * 50, actor)
    det.detect("word " * 50, actor)

    # Same concept should be suppressed
    detected2, evidence2 = det.detect(
        "Trunk Concept is the Trunk Concept here", actor
    )
    assert detected2 is False
    assert evidence2 is None


# ── Test 17: min_occurrences enforcement ──


def test_o_axs_min_occurrences():
    """Concept appearing only once in window -> no detection."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    det.detect("word " * 50, actor)
    det.detect("word " * 50, actor)

    # Novel concept appears only ONCE -- below min_occurrences=2
    detected, evidence = det.detect("Singleton Idea is short", actor)
    assert detected is False
    assert evidence is None


# ── Test 18: deque window limit ──


def test_o_axs_deque_window():
    """token_counts limited to prior_prompts_window size."""
    cfg = _small_config()
    det = OAxsDetector(cfg)
    actor = "human_orchestrator"

    # Fill beyond window (maxlen=2)
    det.detect("word " * 10, actor)
    det.detect("word " * 20, actor)
    det.detect("word " * 30, actor)

    assert len(det.token_counts) == 2  # prior_prompts_window=2
