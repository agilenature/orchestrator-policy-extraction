"""Tests for the structural invariant checks.

Tests the four invariant functions that enforce structural correctness
against durable artifacts:
- check_at_most_once_verdict
- check_layer_coverage_monotonic
- check_specification_closure
- check_delta_retrieval (vacuous pass behavior)
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.review.invariants import (
    InvariantResult,
    check_at_most_once_verdict,
    check_layer_coverage_monotonic,
    check_specification_closure,
    check_delta_retrieval,
)
from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def conn():
    """In-memory DuckDB with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    yield c
    c.close()


def _insert_review(
    conn,
    review_id: str,
    instance_id: str,
    verdict: str = "accept",
    opinion: str | None = None,
    layer: str = "L1",
    point_id: str = "L1-1",
    component: str = "TestComponent",
) -> None:
    """Insert a review row directly for testing."""
    conn.execute(
        """
        INSERT INTO identification_reviews (
            review_id, identification_instance_id, layer, point_id,
            pipeline_component, trigger_text, observation_state,
            action_taken, downstream_impact, provenance_pointer,
            verdict, opinion
        ) VALUES (?, ?, ?, ?, ?, 'trigger', 'obs', 'action', 'impact', 'prov', ?, ?)
        """,
        [review_id, instance_id, layer, point_id, component, verdict, opinion],
    )


class TestAtMostOnceVerdict:
    """Tests for check_at_most_once_verdict."""

    def test_passes_when_all_unique(self, conn):
        """Passes when each instance has exactly one verdict."""
        _insert_review(conn, "rev-1", "inst-1")
        _insert_review(conn, "rev-2", "inst-2")

        result = check_at_most_once_verdict(conn)

        assert result.passed is True
        assert result.invariant_name == "at_most_once_verdict"
        assert len(result.violations) == 0

    def test_passes_on_empty_table(self, conn):
        """Passes vacuously when no reviews exist."""
        result = check_at_most_once_verdict(conn)

        assert result.passed is True
        assert len(result.violations) == 0

    def test_fails_when_duplicate_exists(self, conn):
        """Fails when same instance_id appears twice.

        The UNIQUE constraint normally prevents this, so we drop it
        and re-insert to simulate a constraint-relaxed scenario.
        """
        # Drop the existing table and recreate without UNIQUE constraint
        conn.execute("DROP TABLE identification_reviews")
        conn.execute(
            """
            CREATE TABLE identification_reviews (
                review_id                  VARCHAR PRIMARY KEY,
                identification_instance_id VARCHAR NOT NULL,
                layer                      VARCHAR NOT NULL,
                point_id                   VARCHAR NOT NULL,
                pipeline_component         VARCHAR NOT NULL,
                trigger_text               TEXT NOT NULL,
                observation_state          TEXT NOT NULL,
                action_taken               TEXT NOT NULL,
                downstream_impact          TEXT NOT NULL,
                provenance_pointer         TEXT NOT NULL,
                verdict                    VARCHAR NOT NULL,
                opinion                    TEXT,
                reviewed_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                session_id                 VARCHAR
            )
            """
        )

        _insert_review(conn, "rev-1", "inst-dup")
        _insert_review(conn, "rev-2", "inst-dup")

        result = check_at_most_once_verdict(conn)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0]["instance_id"] == "inst-dup"
        assert result.violations[0]["count"] == 2
        assert result.violations[0]["detail"] == "duplicate verdict"


class TestLayerCoverageMonotonic:
    """Tests for check_layer_coverage_monotonic."""

    def test_passes_when_monotonic(self, conn):
        """Passes when coverage ratio increases across snapshots."""
        # First snapshot: L1 at 50%
        conn.execute(
            """
            INSERT INTO layer_coverage_snapshots
                (snapshot_id, run_at, layer, reviewed_count, pool_count, coverage_ratio)
            VALUES ('snap-1', '2026-02-01T00:00:00+00:00', 'L1', 5, 10, 0.5)
            """
        )
        # Second snapshot: L1 at 70%
        conn.execute(
            """
            INSERT INTO layer_coverage_snapshots
                (snapshot_id, run_at, layer, reviewed_count, pool_count, coverage_ratio)
            VALUES ('snap-2', '2026-02-02T00:00:00+00:00', 'L1', 7, 10, 0.7)
            """
        )

        result = check_layer_coverage_monotonic(conn)

        assert result.passed is True
        assert result.invariant_name == "layer_coverage_monotonic"
        assert len(result.violations) == 0

    def test_passes_on_empty_snapshots(self, conn):
        """Passes vacuously when no snapshots exist."""
        result = check_layer_coverage_monotonic(conn)

        assert result.passed is True
        assert len(result.violations) == 0

    def test_passes_with_single_snapshot(self, conn):
        """Passes with only one snapshot (no pair to compare)."""
        conn.execute(
            """
            INSERT INTO layer_coverage_snapshots
                (snapshot_id, run_at, layer, reviewed_count, pool_count, coverage_ratio)
            VALUES ('snap-1', '2026-02-01T00:00:00+00:00', 'L1', 5, 10, 0.5)
            """
        )

        result = check_layer_coverage_monotonic(conn)

        assert result.passed is True

    def test_fails_when_coverage_decreases(self, conn):
        """Fails when latest snapshot shows lower coverage than previous."""
        # First snapshot: L1 at 80%
        conn.execute(
            """
            INSERT INTO layer_coverage_snapshots
                (snapshot_id, run_at, layer, reviewed_count, pool_count, coverage_ratio)
            VALUES ('snap-1', '2026-02-01T00:00:00+00:00', 'L1', 8, 10, 0.8)
            """
        )
        # Second snapshot: L1 at 50% (regression!)
        conn.execute(
            """
            INSERT INTO layer_coverage_snapshots
                (snapshot_id, run_at, layer, reviewed_count, pool_count, coverage_ratio)
            VALUES ('snap-2', '2026-02-02T00:00:00+00:00', 'L1', 5, 10, 0.5)
            """
        )

        result = check_layer_coverage_monotonic(conn)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0]["layer"] == "L1"
        assert "coverage decreased" in result.violations[0]["detail"]


class TestSpecificationClosure:
    """Tests for check_specification_closure."""

    def test_passes_when_all_rejections_have_candidates(self, conn):
        """Passes when every reject+opinion has a memory_candidates counterpart."""
        _insert_review(
            conn, "rev-1", "inst-1", verdict="reject",
            opinion="Wrong label", component="ReactionLabeler",
        )
        # Create matching memory_candidates row
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, source_instance_id, ccd_axis, scope_rule, flood_example)
            VALUES ('mc-1', 'inst-1', 'test-axis', 'test-scope', 'test-flood')
            """
        )

        result = check_specification_closure(conn)

        assert result.passed is True
        assert result.invariant_name == "specification_closure"

    def test_passes_on_empty_table(self, conn):
        """Passes vacuously when no reviews exist."""
        result = check_specification_closure(conn)

        assert result.passed is True

    def test_passes_when_rejection_has_no_opinion(self, conn):
        """Rejection without opinion does not require a candidate."""
        _insert_review(
            conn, "rev-1", "inst-1", verdict="reject", opinion=None,
        )

        result = check_specification_closure(conn)

        assert result.passed is True

    def test_passes_when_rejection_has_empty_opinion(self, conn):
        """Rejection with empty-string opinion does not require a candidate."""
        _insert_review(
            conn, "rev-1", "inst-1", verdict="reject", opinion="",
        )

        result = check_specification_closure(conn)

        assert result.passed is True

    def test_fails_when_reject_opinion_lacks_candidate(self, conn):
        """Fails when a reject+opinion row has no memory_candidates counterpart."""
        _insert_review(
            conn, "rev-1", "inst-1", verdict="reject",
            opinion="Wrong label", component="ReactionLabeler",
        )
        # No memory_candidates row for inst-1

        result = check_specification_closure(conn)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0]["instance_id"] == "inst-1"
        assert result.violations[0]["pipeline_component"] == "ReactionLabeler"
        assert "spec-correction candidate" in result.violations[0]["detail"]

    def test_violation_names_pipeline_component(self, conn):
        """Violation includes the pipeline_component for debugging."""
        _insert_review(
            conn, "rev-1", "inst-1", verdict="reject",
            opinion="Bad segmentation", component="Segmenter",
        )

        result = check_specification_closure(conn)

        assert result.violations[0]["pipeline_component"] == "Segmenter"


class TestDeltaRetrieval:
    """Tests for check_delta_retrieval."""

    def test_passes_vacuously_with_no_accepted_candidates(self, conn):
        """Passes when no accepted (validated) memory_candidates exist."""
        result = check_delta_retrieval(conn)

        assert result.passed is True
        assert result.invariant_name == "delta_retrieval"
        assert len(result.violations) == 0

    def test_passes_when_axis_appears_in_action_taken(self, conn):
        """Passes when accepted axis appears in review action_taken fields."""
        conn.execute(
            """
            INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status)
            VALUES ('mc-1', 'test-axis', 'scope', 'flood', 'validated')
            """
        )
        _insert_review(conn, "rev-1", "inst-1")
        # Update action_taken to include the axis
        conn.execute(
            """
            UPDATE identification_reviews
            SET action_taken = 'Applied test-axis pattern'
            WHERE review_id = 'rev-1'
            """
        )

        result = check_delta_retrieval(conn)

        assert result.passed is True
