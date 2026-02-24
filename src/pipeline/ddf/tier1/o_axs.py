"""O_AXS (Axis Shift) detector for DDF Tier 1.

Detects the O_AXS signal: a human orchestrator shifting from detailed
operational language to compact, axis-naming language. Requires BOTH:

  Signal A: Granularity drop -- current message token count is below
            config.granularity_drop_ratio * average of prior messages.

  Signal B: Novel concept -- a capitalized noun phrase not previously
            seen appears at least config.novel_concept_min_occurrences
            times in the recent message window.

State is per-session and must be reset between sessions via reset().

Exports:
    OAxsDetector
"""

from __future__ import annotations

import re
from collections import deque

from src.pipeline.models.config import OAxsConfig


_NOUN_PHRASE_PAT: re.Pattern[str] = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
)


class OAxsDetector:
    """Detects O_AXS (axis shift) signals in human orchestrator messages.

    Stateful: tracks token counts and known concepts across messages
    within a single session. Call reset() between sessions.

    Args:
        config: OAxsConfig with detection thresholds.
    """

    def __init__(self, config: OAxsConfig) -> None:
        self.config = config
        self.token_counts: deque[int] = deque(maxlen=config.prior_prompts_window)
        self.known_concepts: set[str] = set()
        self.recent_messages: deque[str] = deque(
            maxlen=config.novel_concept_message_window
        )

    def reset(self) -> None:
        """Reset per-session state."""
        self.token_counts.clear()
        self.known_concepts.clear()
        self.recent_messages.clear()

    def detect(self, text: str, actor: str) -> tuple[bool, dict | None]:
        """Detect O_AXS signal in a message.

        Returns False immediately if actor is not human_orchestrator.

        Args:
            text: Message text.
            actor: Actor identifier (must be 'human_orchestrator' to proceed).

        Returns:
            (detected, evidence_dict) -- evidence contains token_count,
            avg_prior, drop_ratio, novel_concept when detected.
        """
        if actor != "human_orchestrator":
            return False, None

        # Signal A: Granularity drop
        token_count = len(text.split())
        drop_detected = False
        if len(self.token_counts) >= 2:  # Need some history
            avg_prior = sum(self.token_counts) / len(self.token_counts)
            if avg_prior > 0 and token_count < self.config.granularity_drop_ratio * avg_prior:
                drop_detected = True

        # Add current to tracking
        self.token_counts.append(token_count)
        self.recent_messages.append(text)

        if not drop_detected:
            return False, None

        # Signal B: Novel concept (capitalized noun phrase)
        all_recent = " ".join(self.recent_messages)
        novel_concept = None
        for m in _NOUN_PHRASE_PAT.finditer(text):
            phrase = m.group(1)
            if phrase not in self.known_concepts:
                # Check min_occurrences in recent messages
                count = all_recent.count(phrase)
                if count >= self.config.novel_concept_min_occurrences:
                    novel_concept = phrase
                    self.known_concepts.add(phrase)
                    break

        if novel_concept is None:
            return False, None

        # Both conditions met
        avg_prior_for_ev = sum(list(self.token_counts)[:-1]) / max(
            len(self.token_counts) - 1, 1
        )
        return True, {
            "token_count": token_count,
            "avg_prior": avg_prior_for_ev,
            "drop_ratio": token_count / avg_prior_for_ev if avg_prior_for_ev > 0 else 0,
            "novel_concept": novel_concept,
        }
