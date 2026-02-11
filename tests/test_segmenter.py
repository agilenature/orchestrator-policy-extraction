"""TDD tests for the trigger-based episode segmenter (EXTRACT-03).

Tests the state machine that walks tagged event streams and detects
decision-point episode boundaries based on locked decisions:
- Q2: T_LINT is NOT an end trigger (observation only)
- Q3: Flat episodes with complexity metadata
- Q4: 30-second timeout (configurable via config)

Test classes:
- TestBasicSegmentation: Start/end trigger combinations
- TestFailFast: T_TEST ends episode regardless of pass/fail
- TestLintNotEndTrigger: T_LINT does not close episodes
- TestTimeout: 30-second timeout closes episodes
- TestSuperseding: Start trigger while episode open -> supersede
- TestOutcomeDetermination: Correct outcome for each end trigger type
- TestComplexityMetadata: interruption_count, context_switches, complexity
- TestOrphanEvents: Events outside episodes tracked but don't create episodes
- TestEmptyStream: Empty input returns empty output
- TestStreamEnd: Unclosed episode at end of stream closes with stream_end
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import make_event, make_tagged_event

from src.pipeline.models.config import PipelineConfig
from src.pipeline.segmenter import EpisodeSegmenter

BASE_TIME = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _te(
    event_id: str,
    ts_offset: float,
    primary_label: str | None = None,
    actor: str = "executor",
    event_type: str = "assistant_text",
    payload: dict | None = None,
):
    """Shorthand for creating a tagged event with a time offset from BASE_TIME."""
    ts = BASE_TIME + timedelta(seconds=ts_offset)
    event = make_event(
        actor=actor,
        event_type=event_type,
        payload=payload or {},
        ts_utc=ts,
        event_id=event_id,
    )
    return make_tagged_event(event, primary_label=primary_label)


class TestBasicSegmentation:
    """Start and end trigger combinations produce correct episodes."""

    def test_single_episode_o_dir_to_t_test(self, sample_config):
        """[O_DIR, tool_use, tool_result(test), T_TEST] -> 1 episode."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, event_type="tool_use"),
            _te("e3", 2, None, event_type="tool_result"),
            _te("e4", 3, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].start_trigger == "O_DIR"
        assert segments[0].end_trigger == "T_TEST"
        assert segments[0].event_count == 4

    def test_single_episode_o_gate_to_x_propose(self, sample_config):
        """[O_GATE, assistant_text, X_PROPOSE] -> 1 episode."""
        events = [
            _te("e1", 0, "O_GATE", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 2, "X_PROPOSE"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].start_trigger == "O_GATE"
        assert segments[0].end_trigger == "X_PROPOSE"

    def test_multiple_sequential_episodes(self, sample_config):
        """Two separate episodes back-to-back."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_TEST", event_type="tool_result"),
            _te("e3", 5, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 6, "X_ASK"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 2
        assert segments[0].end_trigger == "T_TEST"
        assert segments[1].start_trigger == "O_DIR"
        assert segments[1].end_trigger == "X_ASK"


class TestFailFast:
    """T_TEST ends episode regardless of pass/fail (Q2 fail-fast)."""

    def test_t_test_pass_ends_episode(self, sample_config):
        """T_TEST with passing result ends episode with success outcome."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te(
                "e3",
                2,
                "T_TEST",
                event_type="tool_result",
                payload={"test_result": "pass"},
            ),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].outcome == "success"

    def test_t_test_fail_ends_episode(self, sample_config):
        """T_TEST with failing result ends episode with failure outcome."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te(
                "e3",
                2,
                "T_TEST",
                event_type="tool_result",
                payload={"test_result": "fail"},
            ),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].outcome == "failure"

    def test_t_test_unknown_result(self, sample_config):
        """T_TEST without clear pass/fail gets test_executed outcome."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].outcome == "test_executed"


class TestLintNotEndTrigger:
    """T_LINT does NOT close episodes (Q2 locked decision)."""

    def test_lint_mid_episode_does_not_end(self, sample_config):
        """[O_DIR, tool_use, T_LINT, tool_use, T_TEST] -> 1 episode."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, event_type="tool_use"),
            _te("e3", 2, "T_LINT", event_type="tool_result"),
            _te("e4", 3, None, event_type="tool_use"),
            _te("e5", 4, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].end_trigger == "T_TEST"
        assert segments[0].event_count == 5

    def test_lint_only_after_start_no_episode_end(self, sample_config):
        """[O_DIR, T_LINT] then stream ends -> episode closes with stream_end, not T_LINT."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_LINT", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].end_trigger == "stream_end"
        assert segments[0].outcome == "stream_end"


class TestTimeout:
    """30-second timeout closes episodes (Q4 locked decision)."""

    def test_timeout_closes_episode(self, sample_config):
        """Events with >30s gap -> episode closes with timeout outcome."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 35, None),  # 35s after last event, >30s timeout
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        # The episode should be closed due to timeout before e3 is processed
        assert len(segments) >= 1
        assert segments[0].outcome == "timeout"
        assert segments[0].end_trigger == "timeout"

    def test_timeout_uses_config_value(self):
        """Timeout uses config.episode_timeout_seconds, not hardcoded 30."""
        config = PipelineConfig(episode_timeout_seconds=10)
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 15, None),  # 15s > 10s custom timeout
        ]
        segmenter = EpisodeSegmenter(config)
        segments = segmenter.segment(events)
        assert len(segments) >= 1
        assert segments[0].outcome == "timeout"

    def test_no_timeout_within_window(self, sample_config):
        """Events within 30s window do NOT trigger timeout."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 10, None),
            _te("e3", 20, None),
            _te("e4", 25, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].outcome != "timeout"

    def test_timeout_then_start_trigger_opens_new(self, sample_config):
        """After timeout, if next event is start trigger, open new episode."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 35, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 36, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 2
        assert segments[0].outcome == "timeout"
        assert segments[1].start_trigger == "O_DIR"
        assert segments[1].outcome == "test_executed"


class TestSuperseding:
    """Start trigger while episode open -> supersede current episode."""

    def test_o_gate_supersedes_o_dir(self, sample_config):
        """[O_DIR, assistant_text, O_GATE, assistant_text] -> 2 episodes."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 2, "O_GATE", actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, None),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 2
        assert segments[0].outcome == "superseded"
        assert segments[0].end_trigger in ("O_GATE", "superseded")
        assert segments[1].start_trigger == "O_GATE"

    def test_o_corr_supersedes_episode(self, sample_config):
        """O_CORR while episode open -> supersede current, start new."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 2, "O_CORR", actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 2
        assert segments[0].outcome == "superseded"
        assert segments[1].start_trigger == "O_CORR"

    def test_superseded_episode_has_correct_events(self, sample_config):
        """Superseded episode should contain events up to the superseding event."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
            _te("e3", 2, "O_GATE", actor="human_orchestrator", event_type="user_msg"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].event_count == 2  # e1, e2 only


class TestOutcomeDetermination:
    """Correct outcome for each end trigger type."""

    def test_t_test_pass_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_TEST", event_type="tool_result", payload={"test_result": "pass"}),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "success"

    def test_t_test_fail_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_TEST", event_type="tool_result", payload={"test_result": "fail"}),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "failure"

    def test_t_risky_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_RISKY", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "risky_action"

    def test_t_git_commit_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_GIT_COMMIT", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "committed"

    def test_x_propose_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "X_PROPOSE"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "executor_handoff"

    def test_x_ask_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "X_ASK"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "executor_handoff"

    def test_superseded_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "O_GATE", actor="human_orchestrator", event_type="user_msg"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "superseded"

    def test_timeout_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 35, None),  # >30s gap
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "timeout"

    def test_stream_end_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].outcome == "stream_end"


class TestComplexityMetadata:
    """Q3: interruption_count, context_switches, complexity field."""

    def test_simple_episode_no_interruptions(self, sample_config):
        """Executor-only episode is simple."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, actor="executor"),
            _te("e3", 2, None, actor="executor"),
            _te("e4", 3, "T_TEST", actor="executor", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].complexity == "simple"
        assert segments[0].interruption_count == 0
        assert segments[0].context_switches == 0

    def test_complex_episode_with_interruption(self, sample_config):
        """User message mid-episode (not start/end trigger) = interruption."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, actor="executor"),
            # User interrupts mid-episode with a non-trigger message
            _te("e3", 2, None, actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, None, actor="executor"),
            _te("e5", 4, "T_TEST", actor="executor", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].complexity == "complex"
        assert segments[0].interruption_count == 1

    def test_context_switches_counted(self, sample_config):
        """Actor changes from executor->human->executor = context switch."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, actor="executor"),
            _te("e3", 2, None, actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, None, actor="executor"),
            _te("e5", 4, "T_TEST", actor="executor", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].context_switches >= 1

    def test_multiple_interruptions(self, sample_config):
        """Multiple user messages mid-episode count separately."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, actor="executor"),
            _te("e3", 2, None, actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, None, actor="executor"),
            _te("e5", 4, None, actor="human_orchestrator", event_type="user_msg"),
            _te("e6", 5, None, actor="executor"),
            _te("e7", 6, "T_TEST", actor="executor", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert segments[0].interruption_count == 2
        assert segments[0].complexity == "complex"


class TestOrphanEvents:
    """Events outside episodes tracked but don't create episodes."""

    def test_orphan_events_before_first_episode(self, sample_config):
        """Events before first start trigger are orphaned."""
        events = [
            _te("e1", 0, None, actor="executor"),
            _te("e2", 1, None, actor="executor"),
            _te("e3", 2, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].start_trigger == "O_DIR"
        stats = segmenter.get_stats()
        assert stats["orphan_count"] == 2

    def test_orphan_events_between_episodes(self, sample_config):
        """Events after episode closes and before next start trigger are orphaned."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_TEST", event_type="tool_result"),
            _te("e3", 2, None, actor="executor"),  # orphan
            _te("e4", 3, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e5", 4, "T_TEST", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 2
        stats = segmenter.get_stats()
        assert stats["orphan_count"] == 1


class TestEmptyStream:
    """Empty input returns empty output."""

    def test_empty_list_returns_empty(self, sample_config):
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment([])
        assert segments == []

    def test_empty_stream_stats(self, sample_config):
        segmenter = EpisodeSegmenter(sample_config)
        segmenter.segment([])
        stats = segmenter.get_stats()
        assert stats["total_episodes"] == 0
        assert stats["orphan_count"] == 0


class TestStreamEnd:
    """Unclosed episode at end of stream closes with stream_end."""

    def test_open_episode_at_stream_end(self, sample_config):
        """Episode open when events run out -> close with stream_end."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, None, actor="executor"),
            _te("e3", 2, None, actor="executor"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].outcome == "stream_end"
        assert segments[0].end_trigger == "stream_end"
        assert segments[0].event_count == 3

    def test_stream_end_sets_end_ts(self, sample_config):
        """Stream end should set end_ts to last event's timestamp."""
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 5, None, actor="executor"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segments = segmenter.segment(events)
        expected_end_ts = BASE_TIME + timedelta(seconds=5)
        assert segments[0].end_ts == expected_end_ts


class TestGetStats:
    """Segmentation statistics are correctly computed."""

    def test_stats_counts_by_outcome(self, sample_config):
        events = [
            _te("e1", 0, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e2", 1, "T_TEST", event_type="tool_result"),
            _te("e3", 2, "O_DIR", actor="human_orchestrator", event_type="user_msg"),
            _te("e4", 3, "T_GIT_COMMIT", event_type="tool_result"),
        ]
        segmenter = EpisodeSegmenter(sample_config)
        segmenter.segment(events)
        stats = segmenter.get_stats()
        assert stats["total_episodes"] == 2
        assert stats["by_outcome"]["test_executed"] == 1
        assert stats["by_outcome"]["committed"] == 1
