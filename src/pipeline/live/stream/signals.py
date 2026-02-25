"""Classify GovernanceSignal types by boundary_dependency.

Event-level signals fire immediately on the triggering event and are
immune to episode boundary status. Episode-level signals must be
deferred until CONFIRMED_END to avoid five-property completeness
violations (the episode's outcome field is unknown at declaration time).

See: temporal-closure-dependency CCD axis in MEMORY.md.
"""

from __future__ import annotations

EVENT_LEVEL_SIGNAL_TYPES: frozenset[str] = frozenset({
    "escalation",
    "policy_violation",
    "premise_warning",
})

EPISODE_LEVEL_SIGNAL_TYPES: frozenset[str] = frozenset({
    "amnesia",
    "constraint_eval",
    "training_write",
})


def classify_boundary_dependency(signal_type: str) -> str:
    """Return 'event_level' or 'episode_level' for a signal type.

    Unknown signal types default to 'episode_level' (conservative:
    defer rather than emit prematurely).
    """
    if signal_type in EVENT_LEVEL_SIGNAL_TYPES:
        return "event_level"
    if signal_type in EPISODE_LEVEL_SIGNAL_TYPES:
        return "episode_level"
    return "episode_level"  # conservative default
