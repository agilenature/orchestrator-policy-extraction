"""Tests for the TrustAccumulator.

Verifies per-classification-rule trust accumulation:
- record_accept() increments accept_count
- record_reject() increments reject_count
- trust_level computation: established / provisional / unverified
- trust_level recomputation on state changes (e.g. rejects after established)
- get_all() listing with optional component filter
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.review.models import (
    IdentificationLayer,
    IdentificationReview,
    ReviewVerdict,
)
from src.pipeline.review.schema import create_review_schema
from src.pipeline.review.trust import TrustAccumulator, compute_trust_level


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
        layer=IdentificationLayer.L2_TAGGING,
        point_id="L2-1",
        pipeline_component="EventTagger",
        trigger="Event tool_use requires classification",
        observation_state="actor=orchestrator, event_type=tool_use",
        action_taken="primary_tag=delegation (confidence=0.85)",
        downstream_impact="Primary tag drives episode population",
        provenance_pointer="sess:evt:events:line42",
        verdict=ReviewVerdict.ACCEPT,
        opinion=None,
        reviewed_at="2026-02-23T18:00:00+00:00",
        session_id=None,
    )
    defaults.update(overrides)
    return IdentificationReview(**defaults)


class TestComputeTrustLevel:
    """Tests for the compute_trust_level function."""

    def test_established_at_10_accepts_0_rejects(self):
        assert compute_trust_level(10, 0) == "established"

    def test_established_at_15_accepts_0_rejects(self):
        assert compute_trust_level(15, 0) == "established"

    def test_not_established_with_any_rejects(self):
        assert compute_trust_level(10, 1) != "established"

    def test_provisional_at_3_accepts_0_rejects(self):
        assert compute_trust_level(3, 0) == "provisional"

    def test_provisional_at_3_accepts_1_reject(self):
        assert compute_trust_level(3, 1) == "provisional"

    def test_not_provisional_at_3_accepts_2_rejects(self):
        result = compute_trust_level(3, 2)
        assert result == "unverified"

    def test_unverified_at_0_0(self):
        assert compute_trust_level(0, 0) == "unverified"

    def test_unverified_at_2_accepts(self):
        assert compute_trust_level(2, 0) == "unverified"


class TestTrustAccumulatorRecordAccept:
    """Tests for TrustAccumulator.record_accept()."""

    def test_record_accept_increments_accept_count(self, conn):
        acc = TrustAccumulator(conn)
        review = _make_review()
        acc.record_accept(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["accepts"] == 1
        assert trust["rejects"] == 0

    def test_multiple_accepts_accumulate(self, conn):
        acc = TrustAccumulator(conn)
        for i in range(5):
            review = _make_review(
                review_id=f"rev-{i}",
                identification_instance_id=f"inst-{i}",
            )
            acc.record_accept(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["accepts"] == 5


class TestTrustAccumulatorRecordReject:
    """Tests for TrustAccumulator.record_reject()."""

    def test_record_reject_increments_reject_count(self, conn):
        acc = TrustAccumulator(conn)
        review = _make_review(verdict=ReviewVerdict.REJECT, opinion="Wrong label")
        acc.record_reject(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["accepts"] == 0
        assert trust["rejects"] == 1


class TestTrustAccumulatorGetTrust:
    """Tests for TrustAccumulator.get_trust()."""

    def test_returns_unverified_for_unknown_rule(self, conn):
        acc = TrustAccumulator(conn)
        trust = acc.get_trust("NonExistent", "X-99")
        assert trust == {"accepts": 0, "rejects": 0, "trust_level": "unverified"}

    def test_returns_established_at_10_accepts(self, conn):
        acc = TrustAccumulator(conn)
        for i in range(10):
            review = _make_review(
                review_id=f"rev-{i}",
                identification_instance_id=f"inst-{i}",
            )
            acc.record_accept(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["trust_level"] == "established"
        assert trust["accepts"] == 10
        assert trust["rejects"] == 0

    def test_returns_provisional_at_3_accepts_1_reject(self, conn):
        acc = TrustAccumulator(conn)
        for i in range(3):
            review = _make_review(
                review_id=f"rev-acc-{i}",
                identification_instance_id=f"inst-acc-{i}",
            )
            acc.record_accept(review)

        review = _make_review(
            review_id="rev-rej-0",
            identification_instance_id="inst-rej-0",
            verdict=ReviewVerdict.REJECT,
            opinion="Wrong label",
        )
        acc.record_reject(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["trust_level"] == "provisional"
        assert trust["accepts"] == 3
        assert trust["rejects"] == 1

    def test_trust_level_degrades_when_rejects_occur(self, conn):
        """Trust downgrades from established when rejects occur."""
        acc = TrustAccumulator(conn)
        # Reach established
        for i in range(10):
            review = _make_review(
                review_id=f"rev-{i}",
                identification_instance_id=f"inst-{i}",
            )
            acc.record_accept(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["trust_level"] == "established"

        # Add a reject -- should degrade
        review = _make_review(
            review_id="rev-rej",
            identification_instance_id="inst-rej",
            verdict=ReviewVerdict.REJECT,
            opinion="Misclassified",
        )
        acc.record_reject(review)

        trust = acc.get_trust("EventTagger", "L2-1")
        assert trust["trust_level"] != "established"
        # 10 accepts, 1 reject -> provisional
        assert trust["trust_level"] == "provisional"


class TestTrustAccumulatorGetAll:
    """Tests for TrustAccumulator.get_all()."""

    def test_get_all_returns_all_rules(self, conn):
        acc = TrustAccumulator(conn)

        review_a = _make_review(
            pipeline_component="EventTagger", point_id="L2-1"
        )
        review_b = _make_review(
            review_id="rev-002",
            identification_instance_id="inst-002",
            pipeline_component="Segmenter",
            point_id="L3-1",
        )
        acc.record_accept(review_a)
        acc.record_accept(review_b)

        all_rules = acc.get_all()
        assert len(all_rules) == 2

    def test_get_all_filters_by_component(self, conn):
        acc = TrustAccumulator(conn)

        review_a = _make_review(
            pipeline_component="EventTagger", point_id="L2-1"
        )
        review_b = _make_review(
            review_id="rev-002",
            identification_instance_id="inst-002",
            pipeline_component="Segmenter",
            point_id="L3-1",
        )
        acc.record_accept(review_a)
        acc.record_accept(review_b)

        filtered = acc.get_all(pipeline_component="EventTagger")
        assert len(filtered) == 1
        assert filtered[0]["pipeline_component"] == "EventTagger"
