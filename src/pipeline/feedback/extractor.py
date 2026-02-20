"""Policy feedback extractor -- constraint generation from blocked recommendations.

Extracts policy_feedback constraints from shadow recommendations that were
surfaced but blocked/corrected by human. Follows the EscalationConstraintGenerator
pattern: stateless extractor, caller handles ConstraintStore.add() in pipeline.

Exports:
    PolicyFeedbackExtractor
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from loguru import logger

from src.pipeline.feedback.models import make_policy_error_event


# Reactions that produce constraints
_BLOCK_REACTION = "block"
_CORRECT_REACTION = "correct"

# Reactions that map to severity
_SEVERITY_MAP = {
    _BLOCK_REACTION: "forbidden",
    _CORRECT_REACTION: "requires_approval",
}


class PolicyFeedbackExtractor:
    """Extracts policy_feedback constraints from blocked/corrected recommendations.

    Stateless: does not hold ConstraintStore state. The caller (pipeline
    integration) handles calling ConstraintStore.add().

    Usage:
        extractor = PolicyFeedbackExtractor()
        constraint = extractor.extract(recommendation, episode_dict, constraint_store)
        if constraint:
            constraint_store.add(constraint)
    """

    def extract(
        self,
        recommendation,
        episode: dict,
        constraint_store,
    ) -> dict | None:
        """Extract a constraint from a blocked/corrected recommendation.

        Args:
            recommendation: Recommendation model instance.
            episode: Episode dict with reaction_label.
            constraint_store: ConstraintStore with find_by_hints() for dedup.

        Returns:
            Constraint dict compatible with ConstraintStore, or None if
            reaction is approve/None or dedup matches existing constraint.
        """
        reaction = episode.get("reaction_label")
        if reaction not in _SEVERITY_MAP:
            return None

        severity = _SEVERITY_MAP[reaction]

        # Build constraint fields
        text = recommendation.reasoning or ""
        scope_paths = list(recommendation.recommended_scope_paths or [])
        detection_hints = self._build_detection_hints(recommendation)

        # Dedup check: 2+ shared detection_hints with existing constraint
        existing = constraint_store.find_by_hints(detection_hints, min_overlap=2)
        if existing is not None:
            return None

        # Generate deterministic constraint ID
        constraint_id = self._make_constraint_id(text, scope_paths)

        created_at = datetime.now(timezone.utc).isoformat()

        return {
            "constraint_id": constraint_id,
            "text": text,
            "severity": severity,
            "scope": {"paths": scope_paths},
            "detection_hints": detection_hints,
            "source_episode_id": episode.get("episode_id", ""),
            "created_at": created_at,
            "status": "candidate",
            "source": "policy_feedback",
            "examples": [],
            "type": "behavioral_constraint",
            "status_history": [{"status": "candidate", "changed_at": created_at}],
        }

    def promote_confirmed(
        self,
        constraint_store,
        conn,
        min_sessions: int = 3,
    ) -> int:
        """Promote candidate constraints with sufficient session evidence.

        Queries policy_error_events for candidate constraints with
        min_sessions+ distinct session_ids having error_type='surfaced_and_blocked'.
        Promotes matching constraints from candidate to active.

        Args:
            constraint_store: ConstraintStore with add_status_history_entry().
            conn: DuckDB connection with policy_error_events table.
            min_sessions: Minimum distinct sessions required for promotion.

        Returns:
            Number of promoted constraints.
        """
        rows = conn.execute(
            "SELECT constraint_id, COUNT(DISTINCT session_id) AS sess_count "
            "FROM policy_error_events "
            "WHERE error_type = 'surfaced_and_blocked' "
            "GROUP BY constraint_id "
            "HAVING COUNT(DISTINCT session_id) >= ?",
            [min_sessions],
        ).fetchall()

        promoted = 0
        now_utc = datetime.now(timezone.utc).isoformat()

        for constraint_id, sess_count in rows:
            # Only promote if constraint exists as candidate
            updated = constraint_store.add_status_history_entry(
                constraint_id, "active", now_utc
            )
            if updated:
                promoted += 1
                logger.info(
                    "Promoted constraint {} to active ({} sessions)",
                    constraint_id,
                    sess_count,
                )

        return promoted

    @staticmethod
    def _make_constraint_id(text: str, scope_paths: list[str]) -> str:
        """Generate deterministic constraint ID using SHA-256.

        ID = SHA-256(text.lower().strip() + ":" + json.dumps(sorted(scope_paths)) + ":policy_feedback")[:16]

        Args:
            text: Constraint text.
            scope_paths: Scope paths list.

        Returns:
            16 hex character constraint ID.
        """
        key = (
            text.lower().strip()
            + ":"
            + json.dumps(sorted(scope_paths))
            + ":policy_feedback"
        )
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @staticmethod
    def _build_detection_hints(recommendation) -> list[str]:
        """Build detection_hints from recommendation fields.

        Includes mode, scope paths, and key terms from reasoning.

        Args:
            recommendation: Recommendation model instance.

        Returns:
            List of detection hint strings (deduplicated).
        """
        hints: list[str] = []
        seen: set[str] = set()

        def _add(hint: str) -> None:
            if hint and hint not in seen:
                seen.add(hint)
                hints.append(hint)

        # Include mode
        if recommendation.recommended_mode:
            _add(recommendation.recommended_mode)

        # Include scope paths
        for path in (recommendation.recommended_scope_paths or []):
            _add(path)

        # Extract key terms from reasoning (first significant words)
        reasoning = recommendation.reasoning or ""
        # Extract words that look like identifiers or operations
        words = re.findall(r"\b[a-zA-Z_/][a-zA-Z0-9_./]*\b", reasoning)
        for word in words:
            if len(word) >= 4 and word.lower() not in (
                "should", "would", "could", "that", "this", "with",
                "from", "have", "been", "they", "them", "will",
                "into", "some", "than", "also", "each", "which",
                "about", "there", "their", "what", "when",
            ):
                _add(word)
                if len(hints) >= 8:
                    break

        return hints
