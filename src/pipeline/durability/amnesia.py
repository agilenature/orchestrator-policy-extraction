"""Amnesia detection from violated constraint evaluations.

Creates deterministic amnesia events from VIOLATED ConstraintEvalResult
objects. Amnesia events flag instances where a session violated an active
constraint -- indicating the agent "forgot" the constraint was in force.

Amnesia IDs are SHA-256(session_id + constraint_id)[:16] for idempotency.

Exports:
    AmnesiaDetector
    AmnesiaEvent
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel

from src.pipeline.durability.evaluator import ConstraintEvalResult


class AmnesiaEvent(BaseModel, frozen=True):
    """A detected amnesia event where a session violated an active constraint.

    Attributes:
        amnesia_id: Deterministic ID (SHA-256(session_id + constraint_id)[:16]).
        session_id: Session that violated the constraint.
        constraint_id: Constraint that was violated.
        constraint_type: Type of constraint (behavioral_constraint, architectural_decision).
        severity: Constraint severity (forbidden, requires_approval, warning).
        evidence: Evidence from the evaluation result.
        detected_at: ISO 8601 timestamp of detection.
    """

    amnesia_id: str
    session_id: str
    constraint_id: str
    constraint_type: str | None = None
    severity: str | None = None
    evidence: list[dict] = []
    detected_at: str = ""


class AmnesiaDetector:
    """Detects amnesia events from constraint evaluation results.

    For each VIOLATED ConstraintEvalResult, creates an AmnesiaEvent with
    deterministic ID and constraint metadata lookup.
    """

    def detect(
        self,
        eval_results: list[ConstraintEvalResult],
        constraints: list[dict],
    ) -> list[AmnesiaEvent]:
        """Create amnesia events from VIOLATED evaluation results.

        Args:
            eval_results: List of ConstraintEvalResult from the evaluator.
            constraints: List of constraint dicts for metadata lookup.

        Returns:
            List of AmnesiaEvent for each VIOLATED result.
        """
        # Build constraint lookup for metadata
        constraint_lookup: dict[str, dict] = {
            c.get("constraint_id", ""): c for c in constraints
        }

        now = datetime.now(timezone.utc).isoformat()
        events: list[AmnesiaEvent] = []

        for result in eval_results:
            if result.eval_state != "VIOLATED":
                continue

            # Deterministic ID for idempotency
            amnesia_id = hashlib.sha256(
                (result.session_id + result.constraint_id).encode()
            ).hexdigest()[:16]

            # Look up constraint metadata
            constraint = constraint_lookup.get(result.constraint_id, {})

            events.append(
                AmnesiaEvent(
                    amnesia_id=amnesia_id,
                    session_id=result.session_id,
                    constraint_id=result.constraint_id,
                    constraint_type=constraint.get("type"),
                    severity=constraint.get("severity"),
                    evidence=result.evidence,
                    detected_at=now,
                )
            )

        return events
