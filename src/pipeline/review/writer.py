"""Append-only writer for identification reviews.

Inserts one row per review into the identification_reviews DuckDB table.
Never issues UPDATE or DELETE -- the append-only contract is enforced
at the API level (no update/delete methods exist).

Raises ReviewWriterError on integrity violations (duplicate review_id
or identification_instance_id).

Exports:
    ReviewWriter
    ReviewWriterError
"""

from __future__ import annotations

import duckdb

from src.pipeline.review.models import IdentificationReview


class ReviewWriterError(Exception):
    """Raised when an append-only contract violation occurs."""

    pass


class ReviewWriter:
    """Append-only writer for identification reviews.

    Args:
        conn: DuckDB connection with the identification_reviews table.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn

    def write(self, review: IdentificationReview) -> None:
        """Insert one review row into identification_reviews.

        Raises ReviewWriterError if review_id or identification_instance_id
        already exists (UNIQUE constraint violation). Never issues UPDATE
        or DELETE -- append-only contract.

        Args:
            review: The completed review to persist.

        Raises:
            ReviewWriterError: On duplicate key or integrity violation.
        """
        try:
            self._conn.execute(
                """
                INSERT INTO identification_reviews (
                    review_id, identification_instance_id, layer, point_id,
                    pipeline_component, trigger_text, observation_state,
                    action_taken, downstream_impact, provenance_pointer,
                    verdict, opinion, reviewed_at, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    review.review_id,
                    review.identification_instance_id,
                    review.layer.value,
                    review.point_id,
                    review.pipeline_component,
                    review.trigger,
                    review.observation_state,
                    review.action_taken,
                    review.downstream_impact,
                    review.provenance_pointer,
                    review.verdict.value,
                    review.opinion,
                    review.reviewed_at,
                    review.session_id,
                ],
            )
        except duckdb.ConstraintException as e:
            raise ReviewWriterError(f"Append-only violation: {e}") from e
