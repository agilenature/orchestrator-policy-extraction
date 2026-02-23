"""Verdict routing for identification reviews.

Routes rejected verdicts with opinions to spec-correction candidates in
the memory_candidates table. Routes accepted verdicts to the
TrustAccumulator for per-rule trust tracking.

The spec-correction candidate is written in CCD format:
- ccd_axis: names the identification point (e.g. "L4-4: Reaction Label")
- scope_rule: describes the misclassification and correct behavior
- flood_example: the provenance_pointer (ground-truth pointer to source)

Routing is idempotent: candidate_id = SHA-256(identification_instance_id),
so running `review route` twice produces no duplicates.

Exports:
    VerdictRouter
    validate_ccd_format
"""

from __future__ import annotations

import hashlib
import warnings
from typing import Optional

import duckdb

from src.pipeline.review.models import IdentificationReview, ReviewVerdict
from src.pipeline.review.trust import TrustAccumulator


def validate_ccd_format(candidate: dict) -> list[str]:
    """Validate that a candidate has non-empty CCD format fields.

    CCD format requires non-empty ccd_axis, scope_rule, and flood_example.
    This is the code-level validation complementing the SQL CHECK constraints
    on the memory_candidates table.

    Args:
        candidate: Dict with ccd_axis, scope_rule, flood_example keys.

    Returns:
        List of error strings. Empty list means valid.
    """
    errors = []
    for field in ("ccd_axis", "scope_rule", "flood_example"):
        if not candidate.get(field, "").strip():
            errors.append(f"memory_candidates.{field} must be non-empty")
    return errors


def _make_candidate_id(review: IdentificationReview) -> str:
    """Generate deterministic candidate_id from identification_instance_id.

    Uses SHA-256 to ensure routing is idempotent -- the same review
    always produces the same candidate_id.
    """
    return hashlib.sha256(
        review.identification_instance_id.encode()
    ).hexdigest()


class VerdictRouter:
    """Routes verdicts to spec-correction candidates or trust accumulation.

    When verdict=reject AND opinion is non-empty:
    - Writes a spec-correction candidate to memory_candidates
    - The candidate names: which pipeline_component, which heuristic failed,
      what the correct behavior should be
    - The candidate carries source_instance_id linking back to the review

    When verdict=accept:
    - Delegates to TrustAccumulator for per-rule trust tracking

    Rejected verdicts with empty opinion: no routing (a warning is logged).

    Args:
        conn: DuckDB connection with memory_candidates and
            identification_rule_trust tables.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn
        self._trust = TrustAccumulator(conn)

    def route(self, review: IdentificationReview) -> Optional[str]:
        """Route a review verdict to the appropriate destination.

        Args:
            review: The completed review to route.

        Returns:
            candidate_id if a spec-correction candidate was written,
            None otherwise (accepts and empty-opinion rejects).
        """
        if review.verdict == ReviewVerdict.ACCEPT:
            self._trust.record_accept(review)
            return None

        # Reject path
        self._trust.record_reject(review)

        if not review.opinion:
            warnings.warn(
                f"Rejected verdict for {review.point_id} has no opinion -- "
                "no spec-correction candidate generated. "
                "Consider re-reviewing with an opinion."
            )
            return None

        return self._write_spec_correction_candidate(review)

    def _write_spec_correction_candidate(
        self, review: IdentificationReview
    ) -> str:
        """Write one row to memory_candidates with CCD format.

        The candidate maps review fields to CCD structure:
        - ccd_axis = "{point_id}: {point_label or point_id}" (names the rule)
        - scope_rule = description of misclassification + correct behavior
        - flood_example = provenance_pointer (ground-truth pointer)
        - source_instance_id = links back to the identification instance
        - pipeline_component = the fix target (names exact class/module)
        - status = 'pending' (awaiting human review of the candidate itself)

        Uses INSERT ... ON CONFLICT DO NOTHING for idempotent routing.

        Args:
            review: The rejected review with a non-empty opinion.

        Returns:
            The candidate_id (SHA-256 of identification_instance_id).
        """
        candidate_id = _make_candidate_id(review)

        # Build CCD-format fields
        point_label = getattr(review, "point_label", None) or review.point_id
        ccd_axis = f"{review.point_id}: {point_label}"
        scope_rule = (
            f"The {review.pipeline_component} misclassified this instance. "
            f"Decision made: {review.action_taken}. "
            f"Correct behavior per reviewer: {review.opinion}"
        )
        flood_example = review.provenance_pointer

        # Validate before writing
        candidate = {
            "ccd_axis": ccd_axis,
            "scope_rule": scope_rule,
            "flood_example": flood_example,
        }
        errors = validate_ccd_format(candidate)
        if errors:
            raise ValueError(
                f"CCD format validation failed: {'; '.join(errors)}"
            )

        self._conn.execute(
            """
            INSERT INTO memory_candidates (
                id, source_instance_id, ccd_axis, scope_rule,
                flood_example, pipeline_component,
                heuristic_description, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            ON CONFLICT DO NOTHING
            """,
            [
                candidate_id,
                review.identification_instance_id,
                ccd_axis,
                scope_rule,
                flood_example,
                review.pipeline_component,
                f"Reactive spec-correction from rejected verdict on {review.point_id}",
            ],
        )

        return candidate_id
