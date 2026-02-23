"""Presenter for identification review instances.

Formats an IdentificationPoint for terminal display in five-field format,
showing all decision-boundary externalization properties:
1. IDENTIFICATION POINT (layer + label)
2. RAW DATA (observation_state)
3. DECISION MADE (action_taken)
4. DOWNSTREAM IMPACT (downstream_impact)
5. PROVENANCE (provenance_pointer)

Exports:
    present: Format an IdentificationPoint as a display string
"""

from __future__ import annotations

import textwrap

from src.pipeline.review.models import IdentificationPoint


def present(point: IdentificationPoint) -> str:
    """Return the five-field display string for terminal output.

    Args:
        point: The identification instance to display.

    Returns:
        Formatted multi-line string with all five externalization fields.
    """
    return (
        f"\nIDENTIFICATION POINT: [{point.layer.value}] {point.point_label}\n"
        f"RAW DATA:             {_wrap(point.observation_state)}\n"
        f"DECISION MADE:        {point.action_taken}\n"
        f"DOWNSTREAM IMPACT:    {_wrap(point.downstream_impact)}\n"
        f"PROVENANCE:           {point.provenance_pointer}\n"
        f"\n[Pipeline component: {point.pipeline_component}]\n"
    )


def _wrap(text: str, width: int = 80) -> str:
    """Wrap long text for terminal display.

    Args:
        text: Text to wrap.
        width: Maximum line width.

    Returns:
        Text wrapped at the given width, with continuation lines
        indented to align with the field value.
    """
    if len(text) <= width:
        return text
    # Indent continuation lines by 22 chars to align with field value start
    indent = " " * 22
    lines = textwrap.wrap(text, width=width)
    if not lines:
        return text
    return ("\n" + indent).join(lines)
