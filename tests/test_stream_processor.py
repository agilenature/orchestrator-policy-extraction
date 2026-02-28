"""Tests for the real-time stream processor (Phase 19, Plan 02).

Covers:
- SessionStateMachine state transitions and TTL
- Signal boundary_dependency classification
- StreamProcessor event routing and buffer management
- X_ASK mid-episode invariant (Phase 14 locked decision)
- create_stream_processor_operator behavioral parity (Phase 27)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
import reactivex as rx

from src.pipeline.live.stream.processor import (
    StreamProcessor,
    create_stream_processor_operator,
)
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


# ---------------------------------------------------------------------------
# Operator Tests (Phase 27 -- create_stream_processor_operator)
# ---------------------------------------------------------------------------


# Helper: GovernanceSignal stub for operator tests (matches bus.models shape)
try:
    from src.pipeline.live.bus.models import GovernanceSignal as _GovSig
except ImportError:

    @dataclass
    class _GovSig:
        signal_id: str
        session_id: str
        run_id: str
        signal_type: str
        boundary_dependency: str
        payload: dict[str, Any] = field(default_factory=dict)


def _make_signal(session_id, run_id, signal_type, boundary_dependency):
    """Create a GovernanceSignal-compatible object for testing."""
    return _GovSig(
        signal_id=f"test-{signal_type}",
        session_id=session_id,
        run_id=run_id,
        signal_type=signal_type,
        boundary_dependency=boundary_dependency,
        payload={},
    )


class _SignalEmittingProcessor(StreamProcessor):
    """Subclass that emits signals on specific event types for testing.

    Overrides _detect_signals to produce GovernanceSignal objects
    for events with type 'escalation' (event_level) and 'amnesia'
    (episode_level), matching the signal classification in signals.py.
    """

    def _detect_signals(self, event):
        etype = event.get("type", "")
        signals = []
        if etype == "escalation_event":
            signals.append(
                _make_signal(self.session_id, self.run_id, "escalation", "event_level")
            )
        if etype == "amnesia_event":
            signals.append(
                _make_signal(self.session_id, self.run_id, "amnesia", "episode_level")
            )
        return signals


class TestStreamProcessorOperator:
    """Tests for create_stream_processor_operator (Phase 27 RxPY adoption)."""

    def test_operator_behavioral_parity(self):
        """Operator produces identical signal sequence as direct process_event() calls.

        Uses _SignalEmittingProcessor to generate real GovernanceSignal objects,
        then patches StreamProcessor so create_stream_processor_operator uses
        the signal-emitting subclass.
        """
        events = [
            {"type": "O_DIR"},          # start trigger, ACTIVE, no signals
            {"type": "escalation_event"},  # event_level signal emitted immediately
            {"type": "X_PROPOSE"},       # end trigger -> TENTATIVE_END
            {"type": "amnesia_event"},   # episode_level signal -> buffered
            {"type": "O_GATE"},          # start trigger -> CONFIRMED_END, flushes buffer
        ]

        # Direct process_event() calls
        direct_signals = []
        direct_proc = _SignalEmittingProcessor(session_id="s1", run_id="r1")
        for ev in events:
            direct_signals.extend(direct_proc.process_event(ev))

        # Operator-based pipeline (patch StreamProcessor to use subclass)
        operator_signals = []
        with patch(
            "src.pipeline.live.stream.processor.StreamProcessor",
            _SignalEmittingProcessor,
        ):
            rx.from_iterable(events).pipe(
                create_stream_processor_operator("s1", "r1")
            ).subscribe(on_next=operator_signals.append)

        # Behavioral parity: same signal types in same order
        assert len(operator_signals) == len(direct_signals), (
            f"Signal count mismatch: operator={len(operator_signals)}, "
            f"direct={len(direct_signals)}"
        )
        for op_sig, dir_sig in zip(operator_signals, direct_signals):
            assert op_sig.signal_type == dir_sig.signal_type
            assert op_sig.boundary_dependency == dir_sig.boundary_dependency

    def test_operator_cold_semantics(self):
        """Two subscriptions produce independent results (cold observable).

        Each subscription creates a fresh StreamProcessor with independent
        state machines, so both produce identical signal sequences.
        """
        events = [
            {"type": "O_DIR"},
            {"type": "X_PROPOSE"},
            {"type": "O_GATE"},
        ]

        with patch(
            "src.pipeline.live.stream.processor.StreamProcessor",
            _SignalEmittingProcessor,
        ):
            operator = create_stream_processor_operator("s1", "r1")
            source = rx.from_iterable(events).pipe(operator)

            signals_a = []
            signals_b = []
            source.subscribe(on_next=signals_a.append)
            source.subscribe(on_next=signals_b.append)

        # Both subscriptions see the same result (independent state machines)
        assert len(signals_a) == len(signals_b)

    def test_operator_error_propagation(self):
        """Errors from process_event are propagated to on_error."""
        errors = []

        def _boom_processor(session_id, run_id):
            proc = StreamProcessor(session_id=session_id, run_id=run_id)
            original = proc.process_event

            def exploding_process_event(event):
                if event.get("type") == "boom":
                    raise RuntimeError("test explosion")
                return original(event)

            proc.process_event = exploding_process_event
            return proc

        with patch(
            "src.pipeline.live.stream.processor.StreamProcessor",
            side_effect=lambda session_id, run_id: _boom_processor(
                session_id, run_id
            ),
        ):
            rx.from_iterable(
                [{"type": "O_DIR"}, {"type": "boom"}]
            ).pipe(
                create_stream_processor_operator("s1", "r1")
            ).subscribe(on_error=errors.append)

        assert len(errors) == 1
        assert "test explosion" in str(errors[0])
