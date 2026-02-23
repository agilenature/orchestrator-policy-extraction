"""Tests for the VerdictRouter.

Verifies verdict routing:
- Rejected verdicts with opinions -> spec-correction candidates in memory_candidates
- Rejected verdicts without opinions -> warning, no DB write
- Accepted verdicts -> TrustAccumulator delegation, no memory_candidates write
- CCD format validation on written candidates
- Idempotent routing (same review twice -> no duplicate)
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.review.models import (
    IdentificationLayer,
    IdentificationReview,
    ReviewVerdict,
)
from src.pipeline.review.router import VerdictRouter, validate_ccd_format
from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    yield c
    c.close()


def _make_review(**overrides) -> IdentificationReview:
    """Create a test IdentificationReview with sensible defaults."""
    defaults = dict(
        review_id="rev-001",
        identification_instance_id="inst-001",
        layer=IdentificationLayer.L4_EPISODE_POPULATION,
        point_id="L4-4",
        pipeline_component="ReactionLabeler",
        trigger="Episode requires reaction label assignment",
        observation_state="episode=ep-42, events=[evt1,evt2,evt3]",
        action_taken="reaction_label=frustration (confidence=0.65)",
        downstream_impact="Reaction label affects constraint extraction",
        provenance_pointer="sess-abc:ep-42:episodes:row17",
        verdict=ReviewVerdict.REJECT,
        opinion="Should be curiosity, not frustration",
        reviewed_at="2026-02-23T18:00:00+00:00",
        session_id=None,
    )
    defaults.update(overrides)
    return IdentificationReview(**defaults)


class TestVerdictRouterRejectWithOpinion:
    """route(reject + non-empty opinion) -> writes to memory_candidates."""

    def test_writes_one_row(self, conn):
        """route() writes one row to memory_candidates on reject with opinion."""
        router = VerdictRouter(conn)
        review = _make_review()

        candidate_id = router.route(review)

        assert candidate_id is not None
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 1

    def test_returns_candidate_id(self, conn):
        """route() returns the candidate_id string."""
        router = VerdictRouter(conn)
        review = _make_review()

        candidate_id = router.route(review)

        assert isinstance(candidate_id, str)
        assert len(candidate_id) == 64  # SHA-256 hex length

    def test_ccd_axis_non_empty(self, conn):
        """Written candidate has non-empty ccd_axis."""
        router = VerdictRouter(conn)
        review = _make_review()
        candidate_id = router.route(review)

        row = conn.execute(
            "SELECT ccd_axis FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0].strip() != ""
        assert "L4-4" in row[0]

    def test_scope_rule_contains_component_and_action(self, conn):
        """scope_rule contains pipeline_component and action_taken."""
        router = VerdictRouter(conn)
        review = _make_review()
        candidate_id = router.route(review)

        row = conn.execute(
            "SELECT scope_rule FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        scope_rule = row[0]
        assert "ReactionLabeler" in scope_rule
        assert "reaction_label=frustration" in scope_rule
        assert "curiosity" in scope_rule

    def test_flood_example_is_provenance_pointer(self, conn):
        """flood_example matches the review's provenance_pointer."""
        router = VerdictRouter(conn)
        review = _make_review()
        candidate_id = router.route(review)

        row = conn.execute(
            "SELECT flood_example FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0] == "sess-abc:ep-42:episodes:row17"

    def test_source_instance_id_links_back(self, conn):
        """source_instance_id links to the review's identification_instance_id."""
        router = VerdictRouter(conn)
        review = _make_review()
        candidate_id = router.route(review)

        row = conn.execute(
            "SELECT source_instance_id FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0] == "inst-001"

    def test_status_is_pending(self, conn):
        """Written candidate has status='pending'."""
        router = VerdictRouter(conn)
        review = _make_review()
        candidate_id = router.route(review)

        row = conn.execute(
            "SELECT status FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0] == "pending"

    def test_pipeline_component_set(self, conn):
        """Written candidate has pipeline_component matching the review."""
        router = VerdictRouter(conn)
        review = _make_review()
        candidate_id = router.route(review)

        row = conn.execute(
            "SELECT pipeline_component FROM memory_candidates WHERE id = ?",
            [candidate_id],
        ).fetchone()
        assert row[0] == "ReactionLabeler"


class TestVerdictRouterRejectWithoutOpinion:
    """route(reject + empty opinion) -> no DB write, warning."""

    def test_returns_none(self, conn):
        """route() returns None when opinion is empty."""
        router = VerdictRouter(conn)
        review = _make_review(opinion=None)

        with pytest.warns(UserWarning):
            result = router.route(review)
        assert result is None

    def test_no_memory_candidates_written(self, conn):
        """No row written to memory_candidates."""
        router = VerdictRouter(conn)
        review = _make_review(opinion=None)

        with pytest.warns(UserWarning):
            router.route(review)

        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 0

    def test_emits_warning(self, conn):
        """Warning is emitted about missing opinion."""
        router = VerdictRouter(conn)
        review = _make_review(opinion=None)

        with pytest.warns(UserWarning, match="no opinion"):
            router.route(review)

    def test_still_records_reject_in_trust(self, conn):
        """Even without opinion, reject is recorded in trust accumulation."""
        router = VerdictRouter(conn)
        review = _make_review(opinion=None)

        with pytest.warns(UserWarning):
            router.route(review)

        from src.pipeline.review.trust import TrustAccumulator
        acc = TrustAccumulator(conn)
        trust = acc.get_trust("ReactionLabeler", "L4-4")
        assert trust["rejects"] == 1


class TestVerdictRouterAccept:
    """route(accept) -> trust accumulation, no memory_candidates write."""

    def test_returns_none(self, conn):
        """route() returns None for accepts."""
        router = VerdictRouter(conn)
        review = _make_review(verdict=ReviewVerdict.ACCEPT, opinion=None)

        result = router.route(review)
        assert result is None

    def test_no_memory_candidates_written(self, conn):
        """No row written to memory_candidates."""
        router = VerdictRouter(conn)
        review = _make_review(verdict=ReviewVerdict.ACCEPT, opinion=None)

        router.route(review)

        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 0

    def test_delegates_to_trust_accumulator(self, conn):
        """Accept is recorded in trust accumulation."""
        router = VerdictRouter(conn)
        review = _make_review(verdict=ReviewVerdict.ACCEPT, opinion=None)

        router.route(review)

        from src.pipeline.review.trust import TrustAccumulator
        acc = TrustAccumulator(conn)
        trust = acc.get_trust("ReactionLabeler", "L4-4")
        assert trust["accepts"] == 1


class TestVerdictRouterIdempotent:
    """Routing same review twice -> INSERT ON CONFLICT DO NOTHING."""

    def test_duplicate_routing_no_error(self, conn):
        """Routing same review twice does not error."""
        router = VerdictRouter(conn)
        review = _make_review()

        id1 = router.route(review)
        id2 = router.route(review)

        assert id1 == id2

    def test_duplicate_routing_one_row(self, conn):
        """Routing same review twice produces exactly one row."""
        router = VerdictRouter(conn)
        review = _make_review()

        router.route(review)
        router.route(review)

        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 1


class TestValidateCcdFormat:
    """Tests for validate_ccd_format()."""

    def test_valid_candidate_no_errors(self):
        candidate = {
            "ccd_axis": "L4-4: Reaction Label",
            "scope_rule": "Misclassified frustration as curiosity",
            "flood_example": "sess-abc:ep-42:episodes:row17",
        }
        assert validate_ccd_format(candidate) == []

    def test_empty_ccd_axis_error(self):
        candidate = {"ccd_axis": "", "scope_rule": "scope", "flood_example": "flood"}
        errors = validate_ccd_format(candidate)
        assert len(errors) == 1
        assert "ccd_axis" in errors[0]

    def test_whitespace_scope_rule_error(self):
        candidate = {"ccd_axis": "axis", "scope_rule": "  ", "flood_example": "flood"}
        errors = validate_ccd_format(candidate)
        assert len(errors) == 1
        assert "scope_rule" in errors[0]

    def test_missing_flood_example_error(self):
        candidate = {"ccd_axis": "axis", "scope_rule": "scope"}
        errors = validate_ccd_format(candidate)
        assert len(errors) == 1
        assert "flood_example" in errors[0]

    def test_all_empty_three_errors(self):
        candidate = {"ccd_axis": "", "scope_rule": "", "flood_example": ""}
        errors = validate_ccd_format(candidate)
        assert len(errors) == 3
