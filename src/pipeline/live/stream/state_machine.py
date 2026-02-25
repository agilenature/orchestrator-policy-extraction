"""Session state machine for real-time stream processing.

Implements the temporal-closure-dependency CCD axis: episode boundaries
are defined by what follows them, not what precedes them. A TENTATIVE_END
becomes CONFIRMED_END only when a subsequent start-trigger arrives.

Phase 14 locked decision: X_ASK is mid-episode and never triggers
state transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class SessionState(str, Enum):
    ACTIVE = "active"
    TENTATIVE_END = "tentative_end"
    CONFIRMED_END = "confirmed_end"
    REOPENED = "reopened"


# End triggers (Phase 14 locked decision -- X_ASK excluded)
END_TRIGGER_TYPES = frozenset({"X_PROPOSE", "T_TEST", "T_RISKY", "T_GIT_COMMIT"})

# Start triggers
START_TRIGGER_TYPES = frozenset({"O_DIR", "O_GATE", "O_CORR", "O_AXS"})

# Mid-episode types that NEVER trigger state transitions (Phase 14 locked decision).
# X_ASK is structurally mid-episode: a question within an episode, never a boundary.
MID_EPISODE_TYPES = frozenset({"X_ASK"})

# TTL: 30 minutes
SESSION_TTL_MINUTES = 30


@dataclass
class SessionStateMachine:
    """Tracks session state for one active session.

    Transitions:
        ACTIVE + end_trigger -> TENTATIVE_END
        TENTATIVE_END + start_trigger -> CONFIRMED_END (flush episode signals)
        TENTATIVE_END + continuation -> ACTIVE (reopen)
        CONFIRMED_END + start_trigger -> ACTIVE (new episode)
    """

    state: SessionState = SessionState.ACTIVE
    tentative_end_at: datetime | None = None

    def transition(
        self, event_type: str, now: datetime | None = None
    ) -> tuple[SessionState, bool]:
        """Process one event.

        Returns:
            (new_state, episode_boundary_confirmed).
            episode_boundary_confirmed=True means CONFIRMED_END was just
            reached -- flush episode_level signals now.
        """
        now = now or datetime.now(timezone.utc)

        # Mid-episode types never trigger any state transition in any state
        if event_type in MID_EPISODE_TYPES:
            return self.state, False

        if self.state == SessionState.ACTIVE:
            if event_type in END_TRIGGER_TYPES:
                self.state = SessionState.TENTATIVE_END
                self.tentative_end_at = now
                return self.state, False
            return self.state, False

        if self.state in (SessionState.TENTATIVE_END, SessionState.REOPENED):
            if event_type in START_TRIGGER_TYPES:
                self.state = SessionState.CONFIRMED_END
                return self.state, True
            if event_type not in END_TRIGGER_TYPES:
                # Continuation event -- reopen
                self.state = SessionState.ACTIVE
                self.tentative_end_at = None
                return self.state, False
            return self.state, False

        if self.state == SessionState.CONFIRMED_END:
            # After confirmed end, a new start trigger opens a new episode
            if event_type in START_TRIGGER_TYPES:
                self.state = SessionState.ACTIVE
                self.tentative_end_at = None
            return self.state, False

        return self.state, False

    def is_ttl_expired(self, now: datetime | None = None) -> bool:
        """True when in TENTATIVE_END for more than SESSION_TTL_MINUTES."""
        if self.state != SessionState.TENTATIVE_END or self.tentative_end_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return (now - self.tentative_end_at) > timedelta(minutes=SESSION_TTL_MINUTES)
