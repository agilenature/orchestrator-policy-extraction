"""Tests for the real-time stream processor (Phase 19, Plan 02).

Covers:
- SessionStateMachine state transitions and TTL
- Signal boundary_dependency classification
- StreamProcessor event routing and buffer management
- X_ASK mid-episode invariant (Phase 14 locked decision)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.pipeline.live.stream.processor import StreamProcessor
from src.pipeline.live.stream.signals import classify_boundary_dependency
from src.pipeline.live.stream.state_machine import (
    SESSION_TTL_MINUTES,
    SessionState,
    SessionStateMachine,
)


# ---------------------------------------------------------------------------
# State Machine Tests
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_initial_state_active(self):
        sm = SessionStateMachine()
        assert sm.state == SessionState.ACTIVE

    def test_end_trigger_produces_tentative_end(self):
        sm = SessionStateMachine()
        state, confirmed = sm.transition("X_PROPOSE")
        assert state == SessionState.TENTATIVE_END
        assert confirmed is False

    def test_start_trigger_after_tentative_confirms(self):
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")
        state, confirmed = sm.transition("O_DIR")
        assert state == SessionState.CONFIRMED_END
        assert confirmed is True

    def test_continuation_after_tentative_reopens(self):
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")
        state, confirmed = sm.transition("tool_result")
        assert state == SessionState.ACTIVE
        assert confirmed is False

    def test_x_ask_never_triggers_state_change_from_active(self):
        """Phase 14 locked decision: X_ASK is mid-episode."""
        sm = SessionStateMachine()
        state, confirmed = sm.transition("X_ASK")
        assert state == SessionState.ACTIVE
        assert confirmed is False

    def test_x_ask_during_tentative_does_not_confirm(self):
        """Phase 14 locked decision: X_ASK does not reopen or confirm."""
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")
        state, confirmed = sm.transition("X_ASK")
        assert state == SessionState.TENTATIVE_END
        assert confirmed is False

    def test_ttl_not_expired_when_active(self):
        sm = SessionStateMachine()
        assert sm.is_ttl_expired() is False

    def test_ttl_expired_after_timeout(self):
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")
        past = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES + 1)
        sm.tentative_end_at = past
        assert sm.is_ttl_expired() is True

    def test_ttl_not_expired_before_timeout(self):
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")
        assert sm.is_ttl_expired() is False

    def test_confirmed_end_start_trigger_reactivates(self):
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")
        sm.transition("O_DIR")  # CONFIRMED_END
        state, confirmed = sm.transition("O_DIR")  # New start trigger
        assert state == SessionState.ACTIVE

    def test_all_end_triggers_produce_tentative(self):
        """All four end triggers should move ACTIVE -> TENTATIVE_END."""
        for trigger in ("X_PROPOSE", "T_TEST", "T_RISKY", "T_GIT_COMMIT"):
            sm = SessionStateMachine()
            state, _ = sm.transition(trigger)
            assert state == SessionState.TENTATIVE_END, f"{trigger} failed"

    def test_all_start_triggers_confirm_tentative(self):
        """All four start triggers should move TENTATIVE_END -> CONFIRMED_END."""
        for trigger in ("O_DIR", "O_GATE", "O_CORR", "O_AXS"):
            sm = SessionStateMachine()
            sm.transition("X_PROPOSE")  # -> TENTATIVE_END
            state, confirmed = sm.transition(trigger)
            assert state == SessionState.CONFIRMED_END, f"{trigger} failed"
            assert confirmed is True

    def test_duplicate_end_trigger_stays_tentative(self):
        """Second end trigger in TENTATIVE_END should not change state."""
        sm = SessionStateMachine()
        sm.transition("X_PROPOSE")  # -> TENTATIVE_END
        state, confirmed = sm.transition("T_TEST")
        assert state == SessionState.TENTATIVE_END
        assert confirmed is False


# ---------------------------------------------------------------------------
# Signal Classification Tests
# ---------------------------------------------------------------------------


class TestSignalClassification:
    def test_escalation_is_event_level(self):
        assert classify_boundary_dependency("escalation") == "event_level"

    def test_policy_violation_is_event_level(self):
        assert classify_boundary_dependency("policy_violation") == "event_level"

    def test_premise_warning_is_event_level(self):
        assert classify_boundary_dependency("premise_warning") == "event_level"

    def test_amnesia_is_episode_level(self):
        assert classify_boundary_dependency("amnesia") == "episode_level"

    def test_constraint_eval_is_episode_level(self):
        assert classify_boundary_dependency("constraint_eval") == "episode_level"

    def test_training_write_is_episode_level(self):
        assert classify_boundary_dependency("training_write") == "episode_level"

    def test_unknown_defaults_to_episode_level(self):
        assert classify_boundary_dependency("unknown_signal") == "episode_level"


# ---------------------------------------------------------------------------
# StreamProcessor Tests
# ---------------------------------------------------------------------------


class TestStreamProcessor:
    def test_initial_state(self):
        p = StreamProcessor(session_id="s1", run_id="r1")
        assert p.state == SessionState.ACTIVE

    def test_process_end_trigger_moves_to_tentative(self):
        p = StreamProcessor(session_id="s1", run_id="r1")
        sigs = p.process_event({"type": "X_PROPOSE"})
        assert sigs == []
        assert p.state == SessionState.TENTATIVE_END

    def test_flush_empty_buffer_returns_empty(self):
        p = StreamProcessor(session_id="s1", run_id="r1")
        assert p.flush_episode_signals() == []

    def test_flush_clears_buffer(self):
        p = StreamProcessor(session_id="s1", run_id="r1")
        sentinel = object()
        p._episode_buffer.append(sentinel)
        result = p.flush_episode_signals()
        assert result == [sentinel]
        assert p._episode_buffer == []

    def test_x_ask_does_not_change_state(self):
        """Phase 14 locked decision: X_ASK is mid-episode."""
        p = StreamProcessor(session_id="s1", run_id="r1")
        p.process_event({"type": "X_ASK"})
        assert p.state == SessionState.ACTIVE

    def test_x_ask_during_tentative_preserves_state(self):
        """X_ASK during TENTATIVE_END should not reopen or confirm."""
        p = StreamProcessor(session_id="s1", run_id="r1")
        p.process_event({"type": "X_PROPOSE"})
        assert p.state == SessionState.TENTATIVE_END
        p.process_event({"type": "X_ASK"})
        assert p.state == SessionState.TENTATIVE_END

    def test_session_id_and_run_id_stored(self):
        p = StreamProcessor(session_id="my-session", run_id="my-run")
        assert p.session_id == "my-session"
        assert p.run_id == "my-run"
