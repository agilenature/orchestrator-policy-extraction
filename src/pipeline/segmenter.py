"""Trigger-based episode segmenter (EXTRACT-03).

Implements a state machine that walks the tagged event stream and detects
decision-point episode boundaries based on locked decisions:
- Q2: T_LINT is NOT an end trigger (observation only)
- Q3: Flat episodes with complexity metadata (interruption_count, context_switches)
- Q4: 30-second timeout (configurable via config.episode_timeout_seconds)

Start triggers: O_DIR, O_GATE, O_CORR, O_AXS
End triggers: T_TEST, T_RISKY, T_GIT_COMMIT, X_PROPOSE, timeout, superseded, stream_end
Note: X_ASK is NOT an end trigger — it is structurally mid-episode (a question within an
episode, never a boundary). Including X_ASK as an end trigger produces false-positive splits.

Exports:
    EpisodeSegmenter: Main segmenter class
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime

from src.pipeline.models.config import PipelineConfig
from src.pipeline.models.events import TaggedEvent
from src.pipeline.models.segments import EpisodeSegment

# Start triggers open new episodes
START_TRIGGERS = {"O_DIR", "O_GATE", "O_CORR", "O_AXS"}

# End triggers close open episodes (T_LINT explicitly excluded per Q2)
# X_ASK explicitly excluded: it is structurally mid-episode (a question within an episode,
# never a boundary). Including it produces false-positive episode splits where one episode
# should span the question and its resolution.
END_TRIGGERS = {"T_TEST", "T_RISKY", "T_GIT_COMMIT", "X_PROPOSE"}


class EpisodeSegmenter:
    """Trigger-based state machine for episode boundary detection.

    Walks the tagged event stream, opening episodes on start triggers
    and closing them on end triggers, timeouts, or superseding events.

    Args:
        config: Pipeline configuration (provides episode_timeout_seconds).
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config
        self._timeout_seconds = config.episode_timeout_seconds
        self._segments: list[EpisodeSegment] = []
        self._orphan_count: int = 0
        # Track the last event timestamp for timeout detection without
        # attaching dynamic attributes to the Pydantic EpisodeSegment model.
        self._last_event_ts: datetime | None = None

    def segment(self, tagged_events: list[TaggedEvent]) -> list[EpisodeSegment]:
        """Segment a stream of tagged events into episodes.

        State machine logic:
        1. Walk events in order
        2. If no episode open and event is a start trigger -> open new episode
        3. If episode open and timeout exceeded -> close with 'timeout'
        4. If episode open and event is a start trigger -> close with 'superseded', open new
        5. If episode open -> add event to current episode
        6. If episode open and event is an end trigger (not start) -> close episode
        7. At stream end, close any open episode with 'stream_end'

        Args:
            tagged_events: Ordered list of tagged events to segment.

        Returns:
            List of EpisodeSegment instances.
        """
        self._segments = []
        self._orphan_count = 0
        self._last_event_ts = None
        current: EpisodeSegment | None = None
        last_actor: str | None = None
        # Track whether we've seen the first body event after start trigger.
        # The start trigger -> first body event transition is not a context switch.
        body_started: bool = False

        for event in tagged_events:
            tag = self._get_primary_label(event)
            is_start = self._is_start_trigger(tag)
            is_end = self._is_end_trigger(tag)

            # Check timeout first (before processing current event)
            if current is not None and self._timed_out(current, event):
                # Close current episode due to timeout
                self._close_episode(current, event, trigger="timeout", outcome="timeout")
                current = None
                last_actor = None
                body_started = False

            # Handle start triggers
            if is_start:
                if current is not None:
                    # Supersede current episode
                    self._close_episode(current, event, trigger="superseded", outcome="superseded")
                # Open new episode
                current = self._open_episode(event, tag)
                last_actor = event.event.actor
                body_started = False
                continue

            # No episode open and not a start trigger -> orphan
            if current is None:
                self._orphan_count += 1
                continue

            # Add event to current episode
            current.add_event(event.event.event_id)

            # Track complexity metadata
            # Only count context switches after the body has started (first
            # non-start-trigger event). The start trigger -> first body event
            # transition is normal flow, not a context switch.
            effective_last_actor = last_actor if body_started else None
            self._update_complexity(current, event, effective_last_actor)
            last_actor = event.event.actor
            body_started = True

            # Check if this event is an end trigger
            if is_end:
                outcome = self._determine_outcome(event)
                self._close_episode(current, event, trigger=tag, outcome=outcome, include_event=False)
                current = None
                last_actor = None
                body_started = False

        # Stream end: close any open episode
        if current is not None:
            last_event = tagged_events[-1] if tagged_events else None
            if last_event is not None:
                current.close(
                    end_ts=last_event.event.ts_utc,
                    end_event_id=last_event.event.event_id,
                    end_trigger="stream_end",
                    outcome="stream_end",
                )
            self._segments.append(current)

        return self._segments

    def _get_primary_label(self, event: TaggedEvent) -> str | None:
        """Extract the primary classification label from a tagged event."""
        if event.primary is not None:
            return event.primary.label
        return None

    def _is_start_trigger(self, tag: str | None) -> bool:
        """Check if a tag is a start trigger."""
        return tag in START_TRIGGERS

    def _is_end_trigger(self, tag: str | None) -> bool:
        """Check if a tag is an end trigger (T_LINT excluded per Q2)."""
        return tag in END_TRIGGERS

    def _timed_out(self, current: EpisodeSegment, event: TaggedEvent) -> bool:
        """Check if the gap between the last event and this event exceeds timeout."""
        last_ts = self._last_event_ts if self._last_event_ts is not None else current.start_ts
        gap = (event.event.ts_utc - last_ts).total_seconds()
        return gap > self._timeout_seconds

    def _open_episode(self, event: TaggedEvent, tag: str | None) -> EpisodeSegment:
        """Open a new episode starting with this event."""
        segment_id = self._make_segment_id(event)
        episode = EpisodeSegment(
            segment_id=segment_id,
            session_id=event.event.session_id,
            start_event_id=event.event.event_id,
            start_ts=event.event.ts_utc,
            start_trigger=tag or "unknown",
        )
        episode.add_event(event.event.event_id)
        self._last_event_ts = event.event.ts_utc
        return episode

    def _close_episode(
        self,
        episode: EpisodeSegment,
        event: TaggedEvent,
        trigger: str,
        outcome: str,
        include_event: bool = False,
    ) -> None:
        """Close an episode and add it to the segments list.

        Args:
            episode: The episode to close.
            event: The event causing closure.
            trigger: The end trigger type.
            outcome: The episode outcome.
            include_event: Whether the closing event was already added.
        """
        if trigger == "timeout":
            # For timeout, end timestamp is the last event's timestamp,
            # not the new event that triggered timeout detection
            last_ts = self._last_event_ts if self._last_event_ts is not None else episode.start_ts
            episode.close(
                end_ts=last_ts,
                end_event_id=None,
                end_trigger="timeout",
                outcome="timeout",
            )
        elif trigger == "superseded":
            # For superseded, the superseding event is NOT part of this episode
            last_ts = self._last_event_ts if self._last_event_ts is not None else episode.start_ts
            episode.close(
                end_ts=last_ts,
                end_event_id=None,
                end_trigger="superseded",
                outcome="superseded",
            )
        else:
            episode.close(
                end_ts=event.event.ts_utc,
                end_event_id=event.event.event_id,
                end_trigger=trigger,
                outcome=outcome,
            )
        self._segments.append(episode)

    def _update_complexity(
        self,
        episode: EpisodeSegment,
        event: TaggedEvent,
        last_actor: str | None,
    ) -> None:
        """Update complexity metadata for the episode.

        Q3 locked decision: flat episodes with metadata.
        - If human_orchestrator message mid-episode (not start/end trigger) -> interruption
        - If actor changes executor->human->executor -> context switch
        - If interruption_count > 0 OR context_switches > 0 -> complexity='complex'
        """
        current_actor = event.event.actor
        tag = self._get_primary_label(event)

        # Check for interruption: human_orchestrator message that is NOT a trigger
        if (
            current_actor == "human_orchestrator"
            and not self._is_start_trigger(tag)
            and not self._is_end_trigger(tag)
        ):
            episode.interruption_count += 1

        # Check for context switch: actor changed from last event
        if last_actor is not None and current_actor != last_actor:
            episode.context_switches += 1

        # Update complexity
        if episode.interruption_count > 0 or episode.context_switches > 0:
            episode.complexity = "complex"

        # Track last event timestamp for timeout detection
        self._last_event_ts = event.event.ts_utc

    def _determine_outcome(self, event: TaggedEvent) -> str:
        """Determine the episode outcome based on the end trigger event.

        Outcome mapping:
        - T_TEST with test passing -> 'success'
        - T_TEST with test failing -> 'failure'
        - T_TEST with unknown result -> 'test_executed'
        - T_RISKY -> 'risky_action'
        - T_GIT_COMMIT -> 'committed'
        - X_PROPOSE -> 'executor_handoff'
        Note: X_ASK is not an end trigger and will never appear here.
        """
        tag = self._get_primary_label(event)

        if tag == "T_TEST":
            return self._determine_test_outcome(event)
        elif tag == "T_RISKY":
            return "risky_action"
        elif tag == "T_GIT_COMMIT":
            return "committed"
        elif tag == "X_PROPOSE":
            return "executor_handoff"
        else:
            return "unknown"

    def _determine_test_outcome(self, event: TaggedEvent) -> str:
        """Determine outcome for T_TEST events based on payload.

        Checks payload for test_result field:
        - 'pass' -> 'success'
        - 'fail' -> 'failure'
        - anything else / missing -> 'test_executed'
        """
        payload = event.event.payload
        test_result = payload.get("test_result", "")

        if test_result == "pass":
            return "success"
        elif test_result == "fail":
            return "failure"
        else:
            return "test_executed"

    def _make_segment_id(self, event: TaggedEvent) -> str:
        """Generate a deterministic segment ID from the starting event."""
        key = f"seg:{event.event.session_id}:{event.event.event_id}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def get_stats(self) -> dict:
        """Return segmentation statistics.

        Returns:
            Dict with total_episodes, by_outcome counts, and orphan_count.
        """
        by_outcome: dict[str, int] = defaultdict(int)
        for seg in self._segments:
            outcome = seg.outcome or "unknown"
            by_outcome[outcome] += 1

        return {
            "total_episodes": len(self._segments),
            "by_outcome": dict(by_outcome),
            "orphan_count": self._orphan_count,
        }
