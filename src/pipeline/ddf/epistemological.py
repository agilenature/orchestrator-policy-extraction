"""Epistemological origin classification for constraints (DDF-07).

Classifies HOW a constraint was derived: reactively (from a correction),
principled (proactively stated), or inductively (pattern across instances).

Each classification carries a confidence float reflecting the certainty
of the categorization. Default is 'principled' with confidence 1.0 per
locked decision in DDFConfig.

Exports:
    classify_epistemological_origin
"""

from __future__ import annotations


def classify_epistemological_origin(episode: dict) -> tuple[str, float]:
    """Classify the epistemological origin of a constraint from its source episode.

    Classification logic (checked in order, first match wins):
    1. **reactive**: Episode has reaction_label in ('block', 'correct')
       AND episode mode != 'ESCALATE'. Confidence: 0.9 for block, 0.8 for correct.
    2. **principled**: Episode has constraints_in_force with 1+ entries
       OR episode mode is 'SUPERVISED'. Confidence: 0.7.
    3. **inductive**: Episode has 3+ examples in examples array, OR
       detection_hints matching 3+ distinct entries. Confidence: 0.6.
    4. **Default**: 'principled' with confidence 1.0.

    Args:
        episode: Episode dict with outcome.reaction, observation.context,
            mode, and optionally examples/detection_hints fields.

    Returns:
        Tuple of (origin, confidence) where origin is one of
        'reactive', 'principled', 'inductive'.
    """
    # Check reactive: reaction label is block/correct and not ESCALATE mode
    reaction = episode.get("outcome", {}).get("reaction") or {}
    label = reaction.get("label", "")
    mode = episode.get("mode", "")

    if label in ("block", "correct") and mode != "ESCALATE":
        confidence = 0.9 if label == "block" else 0.8
        return ("reactive", confidence)

    # Check principled: constraints_in_force present OR SUPERVISED mode
    observation = episode.get("observation", {})
    context = observation.get("context", {}) if isinstance(observation, dict) else {}
    constraints_in_force = context.get("constraints_in_force", [])

    if (constraints_in_force and len(constraints_in_force) >= 1) or mode == "SUPERVISED":
        return ("principled", 0.7)

    # Check inductive: 3+ examples or 3+ detection hints
    examples = episode.get("examples", [])
    detection_hints = episode.get("detection_hints", [])

    if (isinstance(examples, list) and len(examples) >= 3) or (
        isinstance(detection_hints, list) and len(detection_hints) >= 3
    ):
        return ("inductive", 0.6)

    # Default: principled with confidence 1.0
    return ("principled", 1.0)
