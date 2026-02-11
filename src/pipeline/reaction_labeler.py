"""Reaction labeler for classifying human messages after episode boundaries.

Implements EXTRACT-05: After each episode boundary, the next human message
reveals whether the human approved, corrected, redirected, blocked, or
questioned the executor's work. These labels are critical training signals
for the preference model (Phase 5).

Two-tier confidence scoring:
    - Strong pattern match: 0.85
    - Weak pattern match: 0.55
    - O_CORR tag override: 0.90
    - Implicit approval (O_DIR without correction): 0.50
    - Unknown (no match): 0.30

Priority ordering (first match wins):
    block > correct > redirect > question > approve

Exports:
    ReactionLabeler
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.pipeline.models.config import PipelineConfig

# Confidence constants
STRONG_CONFIDENCE = 0.85
WEAK_CONFIDENCE = 0.55
O_CORR_CONFIDENCE = 0.90
IMPLICIT_APPROVE_CONFIDENCE = 0.50
UNKNOWN_CONFIDENCE = 0.30

# Pattern definitions: (label, tier, regex_pattern)
# Ordered by priority: block > correct > redirect > question > approve
# Within each label: strong patterns listed before weak patterns.
REACTION_PATTERNS: list[tuple[str, str, str]] = [
    # --- block (highest priority) ---
    ("block", "strong", r"^NO[!.\s]*$"),
    ("block", "strong", r"\bstop\b"),
    ("block", "strong", r"\bnever\b"),
    ("block", "strong", r"\bdon't\s+do\s+that\b"),
    ("block", "weak", r"\bdon't\b"),
    ("block", "weak", r"\bavoid\b"),
    # --- correct ---
    ("correct", "strong", r"\b(?:no|nope),?\s+(?:do|use|try|change)"),
    ("correct", "strong", r"\bthat'?s?\s+(?:wrong|not|incorrect)\b"),
    ("correct", "strong", r"\bchange\s+it\s+to\b"),
    ("correct", "weak", r"\bfix\b"),
    ("correct", "weak", r"\binstead\b"),
    # --- redirect ---
    ("redirect", "strong", r"\binstead\s+focus\b"),
    ("redirect", "strong", r"\bdifferent\s+direction\b"),
    ("redirect", "strong", r"\bswitch\s+to\b"),
    ("redirect", "strong", r"\bfirst\s+(?:do|handle|fix)\b"),
    ("redirect", "weak", r"\bbefore\s+that\b"),
    ("redirect", "weak", r"\bpriority\b"),
    # --- question ---
    ("question", "strong", r"\bwhy\b.*\?"),
    ("question", "strong", r"\bwhat\s+about\b"),
    ("question", "strong", r"\bhow\s+does\b"),
    ("question", "strong", r"\bexplain\b"),
    ("question", "weak", r"\?$"),
    # --- approve (lowest priority) ---
    ("approve", "strong", r"\b(?:yes|yeah|looks?\s+good|go\s+ahead|LGTM|approved?)\b"),
    ("approve", "weak", r"\b(?:ok|sure|fine|proceed|that\s+works)\b"),
]

# Labels that indicate correction when found in O_DIR messages
_CORRECTION_LABELS = {"block", "correct"}

# Priority order for labels (lower index = higher priority)
_LABEL_PRIORITY = ["block", "correct", "redirect", "question", "approve"]


class ReactionLabeler:
    """Classifies human messages into reaction labels with confidence scores.

    Usage:
        labeler = ReactionLabeler(config)
        result = labeler.label(next_msg, episode_end_trigger, episode_outcome)
        # result: {"label": "approve", "message": "yes", "confidence": 0.85}
        # or None if no next message
    """

    def __init__(self, config: PipelineConfig) -> None:
        """Initialize with pre-compiled regex patterns.

        Args:
            config: Pipeline configuration (used for potential future
                    reaction_keywords expansion).
        """
        self._config = config
        # Pre-compile all regex patterns with IGNORECASE
        # Store as list of (label, tier, compiled_pattern) tuples
        self._compiled_patterns: list[tuple[str, str, re.Pattern[str]]] = [
            (label, tier, re.compile(pattern, re.IGNORECASE))
            for label, tier, pattern in REACTION_PATTERNS
        ]

    def label(
        self,
        next_human_message: dict[str, Any] | None,
        episode_end_trigger: str | None = None,
        episode_outcome: str | None = None,
    ) -> dict[str, Any] | None:
        """Classify the next human message as a reaction.

        Args:
            next_human_message: The next human_orchestrator event after episode
                end. None if end of session.
            episode_end_trigger: The tag that ended the episode (T_TEST, etc.).
            episode_outcome: The segment outcome (success, failure, etc.).

        Returns:
            Dict with {label, message, confidence} or None if no reaction
            determinable (no next message).
        """
        if next_human_message is None:
            return None

        # Check for tag-based overrides first
        tags = next_human_message.get("tags", [])
        text = self._extract_text(next_human_message)

        # O_CORR override: always "correct" at 0.9
        if "O_CORR" in tags:
            return {
                "label": "correct",
                "message": text,
                "confidence": O_CORR_CONFIDENCE,
            }

        # O_DIR/O_GATE implicit approval check
        has_directive_tag = "O_DIR" in tags or "O_GATE" in tags
        if has_directive_tag:
            # Check if text contains correction keywords
            classified_label, classified_conf = self._classify_text(text)
            if classified_label in _CORRECTION_LABELS:
                # Text overrides implicit approval
                return {
                    "label": classified_label,
                    "message": text,
                    "confidence": classified_conf,
                }
            # Implicit approval
            return {
                "label": "approve",
                "message": text,
                "confidence": IMPLICIT_APPROVE_CONFIDENCE,
            }

        # Standard text-based classification
        classified_label, classified_conf = self._classify_text(text)

        if classified_label is not None:
            return {
                "label": classified_label,
                "message": text,
                "confidence": classified_conf,
            }

        # No match -> unknown
        return {
            "label": "unknown",
            "message": text,
            "confidence": UNKNOWN_CONFIDENCE,
        }

    def _classify_text(self, text: str) -> tuple[str | None, float]:
        """Classify text using priority-ordered pattern matching.

        Algorithm:
        1. For each label in priority order (block, correct, redirect,
           question, approve):
           a. Check strong patterns first -- if any match, return immediately
              with (label, STRONG_CONFIDENCE)
           b. Check weak patterns -- if any match, record as candidate
        2. If candidates found, return highest-priority candidate with
           WEAK_CONFIDENCE
        3. If no matches, return (None, 0.0)

        Args:
            text: The message text to classify.

        Returns:
            Tuple of (label, confidence) or (None, 0.0) if no match.
        """
        if not text or not text.strip():
            return None, 0.0

        # Track best weak candidate by priority
        weak_candidate: str | None = None
        weak_priority: int = len(_LABEL_PRIORITY)  # worst possible

        for label, tier, pattern in self._compiled_patterns:
            if pattern.search(text):
                if tier == "strong":
                    # Strong match: return immediately (patterns are priority-ordered)
                    return label, STRONG_CONFIDENCE
                elif tier == "weak":
                    # Weak match: track if higher priority than current candidate
                    try:
                        priority = _LABEL_PRIORITY.index(label)
                    except ValueError:
                        priority = len(_LABEL_PRIORITY)
                    if priority < weak_priority:
                        weak_candidate = label
                        weak_priority = priority

        if weak_candidate is not None:
            return weak_candidate, WEAK_CONFIDENCE

        return None, 0.0

    def _extract_text(self, message: dict[str, Any]) -> str:
        """Extract text from a message event's payload.

        Handles two cases:
        - payload is a dict with "text" key
        - payload is a JSON string that needs parsing

        Args:
            message: The message event dict.

        Returns:
            The extracted text string, or empty string if not found.
        """
        payload = message.get("payload", {})
        return self._parse_payload(payload).get("text", "")

    @staticmethod
    def _parse_payload(payload: Any) -> dict[str, Any]:
        """Parse payload, handling JSON string or dict.

        Args:
            payload: Event payload (dict or JSON string).

        Returns:
            Parsed dict.
        """
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return {"text": payload}
        if isinstance(payload, dict):
            return payload
        return {}
