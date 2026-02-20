"""Session constraint evaluator with 3-state evaluation.

Evaluates each active constraint against a session's events to determine
HONORED or VIOLATED status. Constraints that don't overlap the session
scope are excluded entirely (UNKNOWN -- never stored).

O_ESC episodes auto-qualify as VIOLATED for the bypassed constraint.

Exports:
    SessionConstraintEvaluator
    ConstraintEvalResult
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Literal

from loguru import logger
from pydantic import BaseModel

from src.pipeline.models.config import PipelineConfig
from src.pipeline.utils import scopes_overlap


class ConstraintEvalResult(BaseModel, frozen=True):
    """Result of evaluating a single constraint against a session.

    Only HONORED and VIOLATED states are stored. UNKNOWN constraints
    (scope mismatch) are excluded entirely per locked decision 2.

    Attributes:
        session_id: Session that was evaluated.
        constraint_id: Constraint that was evaluated.
        eval_state: HONORED or VIOLATED.
        evidence: List of evidence dicts with event_id, matched_pattern, payload_excerpt.
        scope_matched: Always True for stored results (False excluded).
    """

    session_id: str
    constraint_id: str
    eval_state: Literal["HONORED", "VIOLATED"]
    evidence: list[dict] = []
    scope_matched: bool = True


class SessionConstraintEvaluator:
    """Evaluates constraints against session events.

    Implements the 3-state evaluation logic:
    - HONORED: constraint scope overlaps session, no detection hints matched
    - VIOLATED: constraint scope overlaps, detection hints matched or O_ESC bypass
    - UNKNOWN (excluded): constraint scope doesn't overlap session scope

    The evaluator does NOT write to DuckDB -- it returns ConstraintEvalResult
    objects. Writing is handled by the writer functions.

    Args:
        config: Pipeline configuration for evidence_excerpt_max_chars.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config
        self._max_excerpt = config.durability.evidence_excerpt_max_chars

    def evaluate(
        self,
        session_id: str,
        session_scope_paths: list[str],
        session_start_time: str,
        events: list[dict],
        constraints: list[dict],
        escalation_violations: dict[str, str] | None = None,
    ) -> list[ConstraintEvalResult]:
        """Evaluate all constraints against a session's events.

        For each constraint:
        1. Temporal check: skip if constraint wasn't active at session time
        2. Scope check: skip if scope doesn't overlap (UNKNOWN)
        3. O_ESC auto-violation: check escalation_violations dict
        4. Detection hints scan: case-insensitive substring match
        5. Default: HONORED if scope overlaps but nothing matched

        Args:
            session_id: Session being evaluated.
            session_scope_paths: File paths touched in this session.
            session_start_time: ISO 8601 timestamp of session start.
            events: List of event dicts for the session.
            constraints: List of constraint dicts to evaluate against.
            escalation_violations: Optional dict of {constraint_id: session_id}
                from O_ESC episodes that bypassed constraints.

        Returns:
            List of ConstraintEvalResult for constraints with definite outcomes.
        """
        if escalation_violations is None:
            escalation_violations = {}

        results: list[ConstraintEvalResult] = []

        # Parse session start time once
        try:
            session_dt = datetime.fromisoformat(session_start_time)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid session_start_time: {}, skipping evaluation",
                session_start_time,
            )
            return results

        for constraint in constraints:
            result = self._evaluate_single(
                session_id=session_id,
                session_scope_paths=session_scope_paths,
                session_dt=session_dt,
                events=events,
                constraint=constraint,
                escalation_violations=escalation_violations,
            )
            if result is not None:
                results.append(result)

        return results

    def _evaluate_single(
        self,
        session_id: str,
        session_scope_paths: list[str],
        session_dt: datetime,
        events: list[dict],
        constraint: dict,
        escalation_violations: dict[str, str],
    ) -> ConstraintEvalResult | None:
        """Evaluate a single constraint against the session.

        Returns None if constraint should be excluded (UNKNOWN).
        """
        constraint_id = constraint.get("constraint_id", "")

        # --- Temporal existence check ---
        created_at = constraint.get("created_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
                if session_dt < created_dt:
                    # Constraint didn't exist yet at session time
                    return None
            except (ValueError, TypeError):
                pass  # Ignore malformed created_at, continue evaluation

        # --- Temporal status check ---
        status_at_time = self._get_status_at_time(constraint, session_dt)
        if status_at_time != "active":
            return None

        # --- Scope check ---
        constraint_paths = constraint.get("scope", {}).get("paths", [])
        if not scopes_overlap(session_scope_paths, constraint_paths):
            return None  # UNKNOWN -- excluded

        # --- O_ESC auto-violation ---
        if constraint_id in escalation_violations:
            return ConstraintEvalResult(
                session_id=session_id,
                constraint_id=constraint_id,
                eval_state="VIOLATED",
                evidence=[
                    {
                        "event_id": "escalation",
                        "matched_pattern": "O_ESC bypass",
                        "payload_excerpt": "Escalation episode bypassed this constraint",
                    }
                ],
            )

        # --- Detection hints scan ---
        detection_hints = constraint.get("detection_hints", [])
        if detection_hints:
            evidence = self._scan_hints(events, detection_hints)
            if evidence:
                return ConstraintEvalResult(
                    session_id=session_id,
                    constraint_id=constraint_id,
                    eval_state="VIOLATED",
                    evidence=evidence,
                )

        # --- Default: HONORED ---
        return ConstraintEvalResult(
            session_id=session_id,
            constraint_id=constraint_id,
            eval_state="HONORED",
        )

    def _get_status_at_time(
        self, constraint: dict, session_dt: datetime
    ) -> str | None:
        """Get constraint status at a specific point in time.

        Mirrors ConstraintStore.get_status_at_time() logic but operates
        on a raw constraint dict (no store dependency).

        Args:
            constraint: Constraint dict with status_history.
            session_dt: Datetime to evaluate at.

        Returns:
            Status string at that time, None if constraint didn't exist yet.
        """
        status_history = constraint.get("status_history", [])

        if not status_history:
            # Fallback to current status field
            return constraint.get("status", "active")

        result_status = None
        for entry in status_history:
            try:
                entry_dt = datetime.fromisoformat(entry["changed_at"])
            except (ValueError, TypeError, KeyError):
                continue
            if entry_dt <= session_dt:
                result_status = entry["status"]
            else:
                break  # status_history is chronological

        return result_status

    def _scan_hints(
        self, events: list[dict], detection_hints: list[str]
    ) -> list[dict]:
        """Scan events for detection hint matches.

        Uses case-insensitive substring containment (same as Phase 9
        always-bypass matching). Pre-compiles patterns once per constraint
        (not per event).

        Args:
            events: Session events to scan.
            detection_hints: Hint strings to search for.

        Returns:
            List of evidence dicts for matched events.
        """
        # Pre-compile patterns (case-insensitive)
        compiled_hints = []
        for hint in detection_hints:
            try:
                compiled_hints.append(
                    (hint, re.compile(re.escape(hint), re.IGNORECASE))
                )
            except re.error:
                continue

        if not compiled_hints:
            return []

        evidence: list[dict] = []

        for event in events:
            payload = event.get("payload")
            # Serialize payload to string for search
            if isinstance(payload, dict):
                payload_str = json.dumps(payload)
            elif isinstance(payload, str):
                payload_str = payload
            else:
                continue

            for hint_text, hint_re in compiled_hints:
                if hint_re.search(payload_str):
                    excerpt = payload_str[: self._max_excerpt]
                    evidence.append(
                        {
                            "event_id": event.get("event_id", "unknown"),
                            "matched_pattern": hint_text,
                            "payload_excerpt": excerpt,
                        }
                    )
                    break  # One match per event is sufficient

        return evidence
