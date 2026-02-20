"""Policy error event models for the feedback loop (Phase 13).

Frozen Pydantic models for policy errors detected during episode processing.
A PolicyErrorEvent represents a single instance where the orchestrator's
recommendation conflicted with a known constraint.

Exports:
    PolicyErrorEvent: Frozen Pydantic model for storage in DuckDB
    make_policy_error_event: Factory function with deterministic ID + timestamp
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel


class PolicyErrorEvent(BaseModel, frozen=True):
    """A single policy error event detected during episode processing.

    Represents either:
    - 'suppressed': The orchestrator's recommendation was silently overridden
      by the policy layer (human correction that wasn't surfaced).
    - 'surfaced_and_blocked': The policy layer correctly blocked the
      recommendation and informed the user.

    Fields:
        error_id: Deterministic SHA-256 hash (16 hex chars) of
            session_id:episode_id:constraint_id:error_type.
        session_id: Session where the error occurred.
        episode_id: Episode where the error occurred.
        error_type: One of 'suppressed' or 'surfaced_and_blocked'.
        constraint_id: ID of the matched constraint.
        recommendation_mode: The recommended mode that was checked.
        recommendation_risk: The recommended risk level.
        detected_at: ISO 8601 UTC timestamp of detection.
    """

    error_id: str
    session_id: str
    episode_id: str
    error_type: str
    constraint_id: str
    recommendation_mode: str
    recommendation_risk: str
    detected_at: str


def make_policy_error_event(
    session_id: str,
    episode_id: str,
    constraint_id: str,
    error_type: str,
    recommendation_mode: str,
    recommendation_risk: str,
) -> PolicyErrorEvent:
    """Create a PolicyErrorEvent with deterministic error_id and auto-timestamp.

    The error_id is a truncated SHA-256 hash of the composite key
    (session_id:episode_id:constraint_id:error_type), ensuring the same
    error detected twice produces the same ID (idempotent).

    Args:
        session_id: Session where the error occurred.
        episode_id: Episode where the error occurred.
        constraint_id: ID of the matched constraint.
        error_type: One of 'suppressed' or 'surfaced_and_blocked'.
        recommendation_mode: The recommended mode.
        recommendation_risk: The recommended risk level.

    Returns:
        Frozen PolicyErrorEvent instance.
    """
    key = f"{session_id}:{episode_id}:{constraint_id}:{error_type}"
    error_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    detected_at = datetime.now(timezone.utc).isoformat()

    return PolicyErrorEvent(
        error_id=error_id,
        session_id=session_id,
        episode_id=episode_id,
        error_type=error_type,
        constraint_id=constraint_id,
        recommendation_mode=recommendation_mode,
        recommendation_risk=recommendation_risk,
        detected_at=detected_at,
    )
