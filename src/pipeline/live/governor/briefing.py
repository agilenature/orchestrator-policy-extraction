"""ConstraintBriefing model and briefing generation.

Produces severity-ordered constraint briefings for delivery to sessions
via the /api/check endpoint. Constraints are sorted by severity
(forbidden > requires_approval > warning).

DDF co-pilot interventions (LIVE-06) are stubbed as an empty list --
deferred until post-OpenClaw installation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

SEVERITY_ORDER = {"forbidden": 0, "requires_approval": 1, "warning": 2}


class ConstraintBriefing(BaseModel, frozen=True):
    """Grouped, severity-ordered constraint briefing for a session."""

    constraints: list[dict[str, Any]] = []  # flat list for wire format
    interventions: list[dict[str, Any]] = []  # DDF co-pilot stubs (LIVE-06 deferred)
    total_count: int = 0
    top_severity: str | None = None
    relevant_docs: list[dict[str, Any]] = []  # Phase 21: doc_index entries
    genus_count: int = 0  # Phase 25: count of genus_of edges in axis_edges


def generate_briefing(constraints: list[dict[str, Any]]) -> ConstraintBriefing:
    """Sort constraints by severity, return as ConstraintBriefing.

    Args:
        constraints: List of active constraint dicts from the store.

    Returns:
        ConstraintBriefing with constraints sorted by severity
        (forbidden first), total_count, and top_severity.
    """
    if not constraints:
        return ConstraintBriefing()

    sorted_constraints = sorted(
        constraints,
        key=lambda c: SEVERITY_ORDER.get(c.get("severity", "warning"), 99),
    )

    severities = [c.get("severity", "warning") for c in constraints]
    top = min(severities, key=lambda s: SEVERITY_ORDER.get(s, 99)) if severities else None

    return ConstraintBriefing(
        constraints=sorted_constraints,
        total_count=len(sorted_constraints),
        top_severity=top,
    )
