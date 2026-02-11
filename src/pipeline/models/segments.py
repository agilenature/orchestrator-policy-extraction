"""Pydantic model for episode segments.

Implements the EpisodeSegment model from the research spec. Episodes are
mutable during construction (the segmenter builds them incrementally)
but carry all metadata needed for downstream analysis.

Flat episodes with metadata (Q3): interruption_count, context_switches,
complexity (simple | complex). No nested/hierarchical episodes in Phase 1.

Exports:
    EpisodeSegment: Mutable episode segment model
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EpisodeSegment(BaseModel):
    """A decision-point episode segment.

    NOT frozen -- needs mutation during construction by the segmenter.
    The segmenter calls add_event() as events arrive and close() when
    an end trigger or timeout is detected.

    Episodes represent orchestrator decision points (Q3: flat with metadata).
    """

    segment_id: str
    session_id: str
    start_event_id: str
    end_event_id: str | None = None
    start_ts: datetime
    end_ts: datetime | None = None
    start_trigger: str  # O_DIR | O_GATE
    end_trigger: str | None = None  # X_PROPOSE | X_ASK | T_TEST | T_RISKY | T_GIT_COMMIT | timeout | superseded | stream_end
    outcome: str | None = None  # success | failure | timeout | superseded | stream_end
    events: list[str] = Field(default_factory=list)  # list of event_ids
    event_count: int = 0
    complexity: str = "simple"  # simple | complex (Q3)
    interruption_count: int = 0  # Q3
    context_switches: int = 0  # Q3
    config_hash: str | None = None

    def add_event(self, event_id: str) -> None:
        """Add an event to this segment.

        Updates both the events list and the event_count.

        Args:
            event_id: The deterministic event ID to add.
        """
        self.events.append(event_id)
        self.event_count = len(self.events)

    def close(
        self,
        end_ts: datetime,
        end_event_id: str | None = None,
        end_trigger: str | None = None,
        outcome: str | None = None,
    ) -> None:
        """Close this episode segment.

        Sets the end timestamp, trigger, and outcome. Called by the
        segmenter when an end condition is detected.

        Args:
            end_ts: Timestamp when the episode ended.
            end_event_id: ID of the event that caused the episode to end.
            end_trigger: What triggered the end (e.g., "timeout", "X_PROPOSE").
            outcome: Episode outcome (success, failure, timeout, superseded, stream_end).
        """
        self.end_ts = end_ts
        self.end_event_id = end_event_id
        self.end_trigger = end_trigger
        self.outcome = outcome
