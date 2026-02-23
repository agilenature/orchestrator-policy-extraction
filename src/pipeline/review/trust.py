"""Per-classification-rule trust accumulation.

Tracks accepted/rejected verdicts per (pipeline_component, point_id) pair,
computing a trust_level based on accumulated evidence:
- established: >= 10 accepts and 0 rejects (high confidence in the rule)
- provisional: >= 3 accepts and <= 1 reject (growing confidence)
- unverified: below provisional threshold (insufficient evidence)

Stored in the identification_rule_trust DuckDB table. The rule_id is a
SHA-256 hash of (pipeline_component + point_id) for deterministic
deduplication.

Exports:
    TrustAccumulator
    TRUST_LEVELS
    compute_trust_level
"""

from __future__ import annotations

import hashlib

import duckdb

from src.pipeline.review.models import IdentificationReview


TRUST_LEVELS = {
    "established": {"min_accepts": 10, "max_rejects": 0},
    "provisional": {"min_accepts": 3, "max_rejects": 1},
    "unverified": {"min_accepts": 0, "max_rejects": None},
}


def compute_trust_level(accepts: int, rejects: int) -> str:
    """Compute trust level from accept/reject counts.

    Args:
        accepts: Number of accepted verdicts for this rule.
        rejects: Number of rejected verdicts for this rule.

    Returns:
        One of 'established', 'provisional', or 'unverified'.
    """
    if accepts >= 10 and rejects == 0:
        return "established"
    elif accepts >= 3 and rejects <= 1:
        return "provisional"
    return "unverified"


def _make_rule_id(pipeline_component: str, point_id: str) -> str:
    """Generate deterministic rule_id from component and point."""
    return hashlib.sha256(
        f"{pipeline_component}:{point_id}".encode()
    ).hexdigest()


class TrustAccumulator:
    """Tracks accepted/rejected verdicts per classification rule.

    Computes trust_level based on accumulated evidence per
    (pipeline_component, point_id) pair. Each verdict updates
    the running counts and recomputes the trust level.

    Args:
        conn: DuckDB connection with the identification_rule_trust table.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn

    def record_accept(self, review: IdentificationReview) -> None:
        """Record an accepted verdict for a classification rule.

        Increments accept_count for the (pipeline_component, point_id)
        pair and recomputes trust_level.

        Args:
            review: The accepted review to record.
        """
        self._upsert(
            review.pipeline_component,
            review.point_id,
            accept_delta=1,
            reject_delta=0,
        )

    def record_reject(self, review: IdentificationReview) -> None:
        """Record a rejected verdict for a classification rule.

        Increments reject_count for the (pipeline_component, point_id)
        pair and recomputes trust_level.

        Args:
            review: The rejected review to record.
        """
        self._upsert(
            review.pipeline_component,
            review.point_id,
            accept_delta=0,
            reject_delta=1,
        )

    def get_trust(self, pipeline_component: str, point_id: str) -> dict:
        """Get trust state for a classification rule.

        Args:
            pipeline_component: The pipeline component name.
            point_id: The identification point ID.

        Returns:
            Dict with keys: accepts, rejects, trust_level.
            Returns unverified with zero counts if no data exists.
        """
        rule_id = _make_rule_id(pipeline_component, point_id)
        row = self._conn.execute(
            "SELECT accept_count, reject_count, trust_level "
            "FROM identification_rule_trust WHERE rule_id = ?",
            [rule_id],
        ).fetchone()

        if row is None:
            return {"accepts": 0, "rejects": 0, "trust_level": "unverified"}

        return {
            "accepts": row[0],
            "rejects": row[1],
            "trust_level": row[2],
        }

    def get_all(self, pipeline_component: str | None = None) -> list[dict]:
        """Get trust state for all classification rules.

        Args:
            pipeline_component: Optional filter by pipeline component.

        Returns:
            List of dicts with keys: pipeline_component, point_id,
            accepts, rejects, trust_level.
        """
        if pipeline_component:
            rows = self._conn.execute(
                "SELECT pipeline_component, point_id, accept_count, "
                "reject_count, trust_level FROM identification_rule_trust "
                "WHERE pipeline_component = ? ORDER BY point_id",
                [pipeline_component],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT pipeline_component, point_id, accept_count, "
                "reject_count, trust_level FROM identification_rule_trust "
                "ORDER BY pipeline_component, point_id"
            ).fetchall()

        return [
            {
                "pipeline_component": r[0],
                "point_id": r[1],
                "accepts": r[2],
                "rejects": r[3],
                "trust_level": r[4],
            }
            for r in rows
        ]

    def _upsert(
        self,
        pipeline_component: str,
        point_id: str,
        accept_delta: int,
        reject_delta: int,
    ) -> None:
        """Insert or update trust counts for a classification rule.

        Uses SELECT + INSERT/UPDATE pattern since DuckDB INSERT OR REPLACE
        resets defaults. Computes the new trust_level from updated counts.
        """
        rule_id = _make_rule_id(pipeline_component, point_id)

        existing = self._conn.execute(
            "SELECT accept_count, reject_count FROM identification_rule_trust "
            "WHERE rule_id = ?",
            [rule_id],
        ).fetchone()

        if existing is None:
            new_accepts = accept_delta
            new_rejects = reject_delta
            trust_level = compute_trust_level(new_accepts, new_rejects)
            self._conn.execute(
                "INSERT INTO identification_rule_trust "
                "(rule_id, pipeline_component, point_id, accept_count, "
                "reject_count, trust_level) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    rule_id,
                    pipeline_component,
                    point_id,
                    new_accepts,
                    new_rejects,
                    trust_level,
                ],
            )
        else:
            new_accepts = existing[0] + accept_delta
            new_rejects = existing[1] + reject_delta
            trust_level = compute_trust_level(new_accepts, new_rejects)
            self._conn.execute(
                "UPDATE identification_rule_trust "
                "SET accept_count = ?, reject_count = ?, trust_level = ?, "
                "last_updated = NOW() WHERE rule_id = ?",
                [new_accepts, new_rejects, trust_level, rule_id],
            )
