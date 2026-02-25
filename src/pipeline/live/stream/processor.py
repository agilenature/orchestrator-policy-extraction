"""Real-time stream processor for live session events.

Routes governance signals by boundary_dependency:
- event_level signals fire immediately on the triggering event
- episode_level signals buffer until CONFIRMED_END

The stream processor does NOT write to DuckDB directly -- it emits
GovernanceSignal objects. The governing daemon (Plan 03) receives
these and manages DuckDB writes, preserving the single-writer
invariant from Phase 14 research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .signals import classify_boundary_dependency
from .state_machine import SessionState, SessionStateMachine

# Import GovernanceSignal from bus if available, else define stub.
# Plan 19-01 (bus package) and 19-02 (stream package) run in parallel,
# so bus/models.py may not exist yet.
try:
    from ..bus.models import GovernanceSignal
except ImportError:

    @dataclass
    class GovernanceSignal:  # type: ignore[no-redef]
        """Minimal stub until bus package provides the canonical model."""

        signal_id: str
        session_id: str
        run_id: str
        signal_type: str
        boundary_dependency: str
        payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamProcessor:
    """Processes a stream of tagged events for one session.

    Usage:
        processor = StreamProcessor(session_id="s1", run_id="r1")
        for event in event_stream:
            signals = processor.process_event(event)
            for sig in signals:
                bus.emit(sig)  # daemon handles DuckDB writes
    """

    session_id: str
    run_id: str
    _state_machine: SessionStateMachine = field(default_factory=SessionStateMachine)
    _episode_buffer: list[GovernanceSignal] = field(default_factory=list)

    @property
    def state(self) -> SessionState:
        """Current session state."""
        return self._state_machine.state

    def process_event(self, event: dict[str, Any]) -> list[GovernanceSignal]:
        """Process one tagged event. Returns immediately-emittable signals.

        Event-level signals are returned immediately.
        Episode-level signals are buffered until CONFIRMED_END.
        On CONFIRMED_END (or TTL expiry), buffered signals are flushed
        and included in the return list.
        """
        event_type = event.get("type", "")
        now = datetime.now(timezone.utc)

        _new_state, boundary_confirmed = self._state_machine.transition(
            event_type, now
        )

        immediate: list[GovernanceSignal] = []
        pending_signals = self._detect_signals(event)

        for sig in pending_signals:
            if sig.boundary_dependency == "event_level":
                immediate.append(sig)
            else:
                self._episode_buffer.append(sig)

        if boundary_confirmed:
            flushed = self.flush_episode_signals()
            immediate.extend(flushed)

        if self._state_machine.is_ttl_expired(now):
            flushed = self.flush_episode_signals()
            immediate.extend(flushed)

        return immediate

    def flush_episode_signals(self) -> list[GovernanceSignal]:
        """Flush buffered episode_level signals and clear the buffer."""
        flushed = list(self._episode_buffer)
        self._episode_buffer.clear()
        return flushed

    def _detect_signals(self, event: dict[str, Any]) -> list[GovernanceSignal]:
        """Detect governance signals from an event.

        Stub implementation -- the governing daemon (Plan 03) wires
        real detectors (EscalationDetector, AmnesiaDetector, etc.)
        via dependency injection or subclass override.
        """
        return []
