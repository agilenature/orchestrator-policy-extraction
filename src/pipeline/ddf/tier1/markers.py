"""Tier 1 DDF marker detectors: L0 (Trunk ID), L1 (Causal), L2 (Assertive).

HIGH RECALL detectors using pre-compiled regex patterns. False positives
are expected and acceptable at this tier -- downstream Tier 2 filters
refine precision.

All patterns are pre-compiled at module level for performance.

Exports:
    detect_l0_trunk
    detect_l1_causal
    detect_l2_assertive
    detect_markers
"""

from __future__ import annotations

import re

from src.pipeline.ddf.models import FlameEvent


# ── L0: Trunk Identification ──
# Human names the core concept/axis.

_L0_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\bthe (?:core|real|actual|fundamental|key|essential|root) "
        r"(?:issue|problem|question|concept|axis|principle)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bthis is (?:really|fundamentally|essentially|actually) about\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bthe trunk (?:is|here is)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat (?:I|we) (?:actually|really) (?:need|want|mean)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bthe (?:CCD|common denominator|governing axis)\b",
        re.IGNORECASE,
    ),
]


# ── L1: Causal Language ──

_L1_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:because|since|therefore|caused by|leads to|results in|the reason)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bif .{1,50}? then\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhen .{1,50}? happens\b",
        re.IGNORECASE,
    ),
]


# ── L2: Assertive Causal (stronger than L1) ──

_L2_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bthe cause is\b", re.IGNORECASE),
    re.compile(r"\bthis causes\b", re.IGNORECASE),
    re.compile(r"\bdirectly leads to\b", re.IGNORECASE),
    re.compile(r"\bthe root cause\b", re.IGNORECASE),
    re.compile(r"\bI(?:'m| am) certain\b", re.IGNORECASE),
    re.compile(r"\bI(?:'ve| have) identified\b", re.IGNORECASE),
    re.compile(r"\bthe answer is\b", re.IGNORECASE),
    re.compile(r"\bthe principle here\b", re.IGNORECASE),
    re.compile(r"\bthe rule is\b", re.IGNORECASE),
    re.compile(r"\bthe invariant\b", re.IGNORECASE),
]


def _extract_excerpt(text: str, match: re.Match[str], window: int = 200) -> str:
    """Extract a window of text around a regex match.

    Returns up to `window` characters centered on the match.
    """
    start = max(0, match.start() - window // 2)
    end = min(len(text), match.end() + window // 2)
    return text[start:end]


def detect_l0_trunk(text: str) -> tuple[bool, str | None]:
    """Detect Level 0 trunk identification markers.

    Level 0: Human names the core concept/axis.

    Args:
        text: Text to scan for L0 markers.

    Returns:
        (detected, evidence_excerpt) -- excerpt is 200-char window
        around first match, or None if not detected.
    """
    for pat in _L0_PATTERNS:
        m = pat.search(text)
        if m:
            return True, _extract_excerpt(text, m)
    return False, None


def detect_l1_causal(text: str) -> tuple[bool, str | None]:
    """Detect Level 1 causal language markers.

    Level 1: Causal language (because, since, therefore, etc.).

    Args:
        text: Text to scan for L1 markers.

    Returns:
        (detected, evidence_excerpt) -- excerpt is 200-char window
        around first match, or None if not detected.
    """
    for pat in _L1_PATTERNS:
        m = pat.search(text)
        if m:
            return True, _extract_excerpt(text, m)
    return False, None


def detect_l2_assertive(text: str) -> tuple[bool, str | None]:
    """Detect Level 2 assertive causal markers.

    Level 2: Assertive causal (stronger than L1). Phrases like
    "the root cause", "I'm certain", "the invariant".

    Args:
        text: Text to scan for L2 markers.

    Returns:
        (detected, evidence_excerpt) -- excerpt is 200-char window
        around first match, or None if not detected.
    """
    for pat in _L2_PATTERNS:
        m = pat.search(text)
        if m:
            return True, _extract_excerpt(text, m)
    return False, None


# ── Marker type strings for FlameEvent ──

_LEVEL_DETECTORS = [
    (0, "L0_trunk", detect_l0_trunk),
    (1, "L1_causal", detect_l1_causal),
    (2, "L2_assertive", detect_l2_assertive),
]


def detect_markers(
    events: list[dict],
    session_id: str,
) -> list[FlameEvent]:
    """Apply L0, L1, L2 detectors to human_orchestrator events.

    Iterates over events, applies all three level detectors to
    human_orchestrator user_msg events only. Returns one FlameEvent
    per detected marker (an event matching multiple levels produces
    multiple FlameEvents).

    Args:
        events: List of event dicts (canonical event format).
        session_id: Session identifier for FlameEvent records.

    Returns:
        List of FlameEvent objects, one per detection.
    """
    results: list[FlameEvent] = []
    prompt_number = 0

    for event in events:
        actor = event.get("actor", "")
        event_type = event.get("event_type", "")

        # Only process human_orchestrator messages
        if actor != "human_orchestrator":
            continue
        if event_type not in ("user_msg", "human_msg", "message"):
            continue

        prompt_number += 1

        # Extract text from payload.common.text
        text = (
            event.get("payload", {})
            .get("common", {})
            .get("text", "")
        )
        if not text:
            continue

        # Apply each level detector
        for level, marker_type, detector in _LEVEL_DETECTORS:
            detected, excerpt = detector(text)
            if detected:
                flame_id = FlameEvent.make_id(
                    session_id, prompt_number, marker_type
                )
                results.append(
                    FlameEvent(
                        flame_event_id=flame_id,
                        session_id=session_id,
                        human_id="default_human",
                        prompt_number=prompt_number,
                        marker_level=level,
                        marker_type=marker_type,
                        evidence_excerpt=excerpt,
                        subject="human",
                        detection_source="stub",
                        session_event_ref=event.get("event_id"),
                    )
                )

    return results
