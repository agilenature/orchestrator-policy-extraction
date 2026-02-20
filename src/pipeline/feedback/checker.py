"""Policy violation checker -- pre-surfacing constraint check.

Given a recommendation text, determines whether it should be suppressed
based on active constraint detection_hints. Constraints with empty
detection_hints are skipped (scope overlap fallback is explicitly
deferred to a future gap closure plan).

Pre-compiles detection_hints as regex patterns at init time for efficiency.

Exports:
    PolicyViolationChecker
"""

from __future__ import annotations

import re

from loguru import logger


class PolicyViolationChecker:
    """Pre-surfacing check for recommendations against active constraints.

    Loads active constraints at init time, pre-compiles detection_hints
    as case-insensitive regex patterns. Constraints with empty or missing
    detection_hints are skipped entirely (never matched).

    Usage:
        checker = PolicyViolationChecker(constraint_store)
        text = PolicyViolationChecker.build_recommendation_text(recommendation)
        should_suppress, matched = checker.check(text)

    Args:
        constraint_store: ConstraintStore (or compatible) with get_active_constraints().
    """

    def __init__(self, constraint_store) -> None:
        active = constraint_store.get_active_constraints()
        # Pre-compile hints for constraints that have non-empty detection_hints
        self._compiled: list[tuple[dict, list[re.Pattern[str]]]] = []
        for constraint in active:
            hints = constraint.get("detection_hints", [])
            if not hints:
                continue
            patterns = []
            for hint in hints:
                try:
                    patterns.append(re.compile(re.escape(hint), re.IGNORECASE))
                except re.error:
                    continue
            if patterns:
                self._compiled.append((constraint, patterns))

    def check(self, recommendation_text: str) -> tuple[bool, dict | None]:
        """Check recommendation text against active constraint detection_hints.

        Iterates compiled patterns. On first match:
        - forbidden/requires_approval severity -> (True, constraint)
        - warning severity -> (False, constraint)

        If no match: (False, None).

        Args:
            recommendation_text: Concatenated recommendation text to check.

        Returns:
            Tuple of (should_suppress, matching_constraint_or_none).
        """
        for constraint, patterns in self._compiled:
            for pattern in patterns:
                if pattern.search(recommendation_text):
                    severity = constraint.get("severity", "")
                    if severity in ("forbidden", "requires_approval"):
                        return (True, constraint)
                    else:
                        # warning or other -> log only, do not suppress
                        logger.info(
                            "Warning constraint {} matched recommendation (not suppressed)",
                            constraint.get("constraint_id", "unknown"),
                        )
                        return (False, constraint)
        return (False, None)

    @staticmethod
    def build_recommendation_text(recommendation) -> str:
        """Concatenate Recommendation fields into searchable text.

        Combines reasoning, scope_paths, mode, and gates to maximize
        hint matching surface.

        Args:
            recommendation: Recommendation model instance.

        Returns:
            Single string with all recommendation fields concatenated.
        """
        parts = [recommendation.reasoning or ""]
        scope_paths = recommendation.recommended_scope_paths or []
        if scope_paths:
            parts.append(" ".join(scope_paths))
        parts.append(recommendation.recommended_mode or "")
        gates = recommendation.recommended_gates or []
        if gates:
            parts.append(" ".join(gates))
        return " ".join(parts)
