"""Escalation detector: sliding window sequence detection.

Detects obstacle escalation patterns in tagged event streams. Walks a list
of TaggedEvent objects and identifies block-then-bypass sequences within a
configurable turn window.

Algorithm:
1. Walk events in timestamp order
2. On O_GATE or O_CORR: open escalation window
3. Within window, count only NON-EXEMPT events toward the window_turns limit
4. Exempt tools (Read, Glob, Grep, WebFetch, WebSearch, Task): skip entirely
5. X_ASK or X_PROPOSE: close/reset ALL pending windows (approval sought)
6. Bypass-eligible tool within window: emit EscalationCandidate, consume oldest
7. Window expiry (window_turns non-exempt events passed): discard window

Exports:
    EscalationDetector: Sequence detector class with detect() method
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.escalation.models import EscalationCandidate
from src.pipeline.models.config import PipelineConfig
from src.pipeline.models.events import TaggedEvent


@dataclass
class _PendingWindow:
    """Internal tracking for an open escalation window."""

    block_event: TaggedEvent
    non_exempt_turns: int = 0


class EscalationDetector:
    """Detects O_ESC patterns in a tagged event stream.

    The detector walks a list of TaggedEvent objects and identifies sequences
    where an agent was blocked (O_GATE/O_CORR) then performed a bypass action
    (state-changing tool call) without seeking authorization (X_ASK/X_PROPOSE).

    Uses a two-layer bypass eligibility check:
    - Layer 1 (tag-based): T_RISKY, T_GIT_COMMIT, T_TEST tags
    - Layer 2 (tool-name-based): Write, Edit, Bash tool names
    - Additionally: always_bypass_patterns in Bash command text

    Args:
        config: PipelineConfig with escalation settings.
    """

    # Tags that indicate a blocking event (opens a window)
    _BLOCK_TAGS = frozenset({"O_GATE", "O_CORR"})

    # Tags that reset all pending windows (approval sought)
    _RESET_TAGS = frozenset({"X_ASK", "X_PROPOSE"})

    # Tags that trigger bypass via tag-based layer
    _BYPASS_TAGS = frozenset({"T_RISKY", "T_GIT_COMMIT", "T_TEST"})

    def __init__(self, config: PipelineConfig) -> None:
        esc = config.escalation
        self._window_turns = esc.window_turns
        self._exempt_tools = frozenset(esc.exempt_tools)
        self._bypass_eligible_tools = frozenset(esc.bypass_eligible_tools)
        self._always_bypass_patterns = esc.always_bypass_patterns
        self._detector_version = esc.detector_version

    def detect(self, tagged_events: list[TaggedEvent]) -> list[EscalationCandidate]:
        """Detect escalation candidates in a tagged event stream.

        Args:
            tagged_events: List of TaggedEvent objects in timestamp order.

        Returns:
            List of EscalationCandidate objects for each detected escalation.
        """
        candidates: list[EscalationCandidate] = []
        pending: list[_PendingWindow] = []

        for event in tagged_events:
            tag = event.primary.label if event.primary else None

            # Step 2: Open window on block event
            if tag in self._BLOCK_TAGS:
                pending.append(_PendingWindow(block_event=event))
                continue

            # Step 5: X_ASK/X_PROPOSE resets ALL pending windows
            if tag in self._RESET_TAGS:
                pending.clear()
                continue

            # Step 3: Check if this is an exempt tool (transparent to window)
            tool_name = self._extract_tool_name(event)
            if tool_name in self._exempt_tools:
                continue

            # For non-exempt events, process all pending windows
            command_text = self._extract_command_text(event)
            is_bypass = self._is_bypass_eligible(event, tag, tool_name, command_text)

            surviving: list[_PendingWindow] = []
            bypass_consumed = False

            for window in pending:
                window.non_exempt_turns += 1

                # Step 7: Check if window has expired
                if window.non_exempt_turns > self._window_turns:
                    # Window expired, discard
                    continue

                # Step 6: Bypass-eligible tool within window
                if is_bypass and not bypass_consumed:
                    candidate = self._build_candidate(
                        window=window,
                        bypass_event=event,
                        tool_name=tool_name,
                        command_text=command_text,
                    )
                    candidates.append(candidate)
                    bypass_consumed = True  # Pitfall 2: only consume oldest window
                    continue  # Window consumed, don't keep it

                surviving.append(window)

            pending = surviving

        return candidates

    def _is_bypass_eligible(
        self,
        event: TaggedEvent,
        tag: str | None,
        tool_name: str,
        command_text: str,
    ) -> bool:
        """Check if an event constitutes a bypass (two-layer check + always-bypass).

        Layer 1: Tag-based (T_RISKY, T_GIT_COMMIT, T_TEST)
        Layer 2: Tool-name-based (Write, Edit, Bash)
        Always-bypass: Patterns in Bash command text (rm, chmod, sudo, etc.)

        Returns:
            True if the event is bypass-eligible.
        """
        # Layer 1: Tag-based bypass
        if tag in self._BYPASS_TAGS:
            return True

        # Layer 2: Tool-name-based bypass
        if tool_name in self._bypass_eligible_tools:
            return True

        # Always-bypass patterns in command text
        if command_text and self._matches_always_bypass(command_text):
            return True

        return False

    def _matches_always_bypass(self, command_text: str) -> bool:
        """Check if command text contains any always-bypass pattern."""
        text_lower = command_text.lower()
        for pattern in self._always_bypass_patterns:
            if pattern.lower() in text_lower:
                return True
        return False

    def _extract_tool_name(self, event: TaggedEvent) -> str:
        """Extract tool name from event payload."""
        common = event.event.payload.get("common", {})
        return common.get("tool_name", "")

    def _extract_command_text(self, event: TaggedEvent) -> str:
        """Extract command text from event payload."""
        common = event.event.payload.get("common", {})
        return common.get("text", "")

    def _extract_resource_path(self, event: TaggedEvent) -> str:
        """Extract resource path from event payload details."""
        details = event.event.payload.get("details", {})
        return details.get("file_path", "")

    def _build_candidate(
        self,
        window: _PendingWindow,
        bypass_event: TaggedEvent,
        tool_name: str,
        command_text: str,
    ) -> EscalationCandidate:
        """Build an EscalationCandidate from a matched window and bypass event."""
        block_event = window.block_event
        block_tag = block_event.primary.label if block_event.primary else "UNKNOWN"

        return EscalationCandidate(
            session_id=block_event.event.session_id,
            block_event_id=block_event.event.event_id,
            block_event_tag=block_tag,
            bypass_event_id=bypass_event.event.event_id,
            bypass_tool_name=tool_name,
            bypass_command=command_text,
            bypass_resource=self._extract_resource_path(bypass_event),
            window_turns_used=window.non_exempt_turns,
            confidence=1.0,
            detector_version=self._detector_version,
        )
