"""Real-time stream processing for live session governance.

Provides the SessionStateMachine for episode boundary detection,
signal classification by boundary_dependency, and the StreamProcessor
that routes signals correctly: event_level fires immediately,
episode_level buffers until CONFIRMED_END.
"""

from .processor import StreamProcessor
from .signals import (
    EPISODE_LEVEL_SIGNAL_TYPES,
    EVENT_LEVEL_SIGNAL_TYPES,
    classify_boundary_dependency,
)
from .state_machine import (
    END_TRIGGER_TYPES,
    START_TRIGGER_TYPES,
    SessionState,
    SessionStateMachine,
)

__all__ = [
    "SessionStateMachine",
    "SessionState",
    "END_TRIGGER_TYPES",
    "START_TRIGGER_TYPES",
    "classify_boundary_dependency",
    "EVENT_LEVEL_SIGNAL_TYPES",
    "EPISODE_LEVEL_SIGNAL_TYPES",
    "StreamProcessor",
]
