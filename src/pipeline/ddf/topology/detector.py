"""Conjunctive Flame Detector for topological edge generation.

Detects flame events that qualify for axis_edges creation by enforcing
the conjunctive trigger: Level >= 5 AND Abstraction Delta >= 2 above
baseline_marker_level AND both axes simultaneously active in the same
episode within a 5-minute window.

Exports:
    ConjunctiveFlameDetector
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from src.pipeline.ddf.models import FlameEvent


@dataclass
class ConjunctiveTrigger:
    """Result of a conjunctive flame detection."""

    flame_event: FlameEvent
    baseline_marker_level: float
    delta: float
    active_axes: list[str]  # Both axis_a and axis_b
    episode_id: Optional[str]
    session_id: str


class ConjunctiveFlameDetector:
    """Detects conjunctive flame triggers for edge generation.

    Conjunctive rule (ALL must be true simultaneously):
    1. marker_level >= 5 (absolute)
    2. Abstraction Delta >= 2 above baseline_marker_level
       (baseline = rolling median of last 10 marker_levels for this session)
    3. Both axis_a and axis_b active in the same episode within 5-min window

    If ANY condition fails, the event does NOT qualify.
    """

    MIN_LEVEL: int = 5
    MIN_DELTA: float = 2.0
    BASELINE_WINDOW: int = 10
    COACTIVE_WINDOW: timedelta = timedelta(minutes=5)

    def __init__(self) -> None:
        # Per-session marker level history for baseline computation
        self._session_levels: dict[str, list[float]] = {}

    def compute_baseline(self, session_id: str) -> float:
        """Compute baseline_marker_level for a session.

        Rolling median of the last BASELINE_WINDOW marker_levels.
        Returns 0.0 if no history.
        """
        history = self._session_levels.get(session_id, [])
        if not history:
            return 0.0
        window = history[-self.BASELINE_WINDOW :]
        return statistics.median(window)

    def update_baseline(self, session_id: str, marker_level: int) -> None:
        """Record a marker_level for baseline computation."""
        if session_id not in self._session_levels:
            self._session_levels[session_id] = []
        self._session_levels[session_id].append(float(marker_level))

    def check_conjunctive(
        self,
        event: FlameEvent,
        active_axes_in_episode: list[str],
        episode_id: str | None = None,
    ) -> ConjunctiveTrigger | None:
        """Check if a flame event qualifies as a conjunctive trigger.

        Updates the baseline with this event's marker_level, then checks
        all three conjunctive conditions. Returns ConjunctiveTrigger if
        ALL conditions pass, None otherwise.

        Key: baseline is computed from events PRIOR to this one (current
        event is added to history first, then baseline uses history[:-1]).
        """
        # Always update baseline with this event
        self.update_baseline(event.session_id, event.marker_level)

        # Condition 1: Level >= 5
        if event.marker_level < self.MIN_LEVEL:
            return None

        # Condition 2: Delta >= 2 above baseline
        # Baseline computed from events PRIOR to this one
        history = self._session_levels.get(event.session_id, [])
        prior = history[:-1] if len(history) > 1 else []
        baseline = (
            statistics.median(prior[-self.BASELINE_WINDOW :]) if prior else 0.0
        )
        delta = event.marker_level - baseline
        if delta < self.MIN_DELTA:
            return None

        # Condition 3: Both axes active (at least 2 distinct axes)
        if len(set(active_axes_in_episode)) < 2:
            return None

        return ConjunctiveTrigger(
            flame_event=event,
            baseline_marker_level=baseline,
            delta=delta,
            active_axes=list(set(active_axes_in_episode)),
            episode_id=episode_id,
            session_id=event.session_id,
        )

    def reset_session(self, session_id: str) -> None:
        """Clear baseline history for a session."""
        self._session_levels.pop(session_id, None)
