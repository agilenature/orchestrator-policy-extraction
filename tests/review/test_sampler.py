"""Tests for the BalancedLayerSampler.

Verifies:
- sample_one() returns None when pool is empty
- sample_one() excludes already-reviewed instances
- sample_one() preferentially samples from lowest-coverage layer
- After 40 samples, no layer exceeds 20% of total (distribution test)
"""

from __future__ import annotations

import uuid
from collections import Counter

import duckdb
import pytest

from src.pipeline.review.models import (
    IdentificationLayer,
    IdentificationPoint,
    ReviewVerdict,
)
from src.pipeline.review.sampler import BalancedLayerSampler
from src.pipeline.review.schema import create_review_schema


def _make_point(
    layer: IdentificationLayer,
    point_id: str = "L1-1",
    instance_id: str | None = None,
) -> IdentificationPoint:
    """Helper to create a test IdentificationPoint."""
    return IdentificationPoint(
        instance_id=instance_id or str(uuid.uuid4()),
        layer=layer,
        point_id=point_id,
        point_label="test",
        pipeline_component="TestComponent",
        trigger="test trigger",
        observation_state="test observation",
        action_taken="test action",
        downstream_impact="test impact",
        provenance_pointer="test:provenance",
    )


def _make_pool(per_layer: int = 10) -> list[IdentificationPoint]:
    """Create a pool with per_layer instances for each of the 8 layers."""
    pool: list[IdentificationPoint] = []
    for layer in IdentificationLayer:
        for i in range(per_layer):
            point_id = f"{layer.value}-{i+1}"
            pool.append(
                _make_point(
                    layer=layer,
                    point_id=point_id,
                    instance_id=f"{layer.value}:{i}",
                )
            )
    return pool


@pytest.fixture
def conn():
    """In-memory DuckDB with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    yield c
    c.close()


def _insert_review(
    conn: duckdb.DuckDBPyConnection,
    instance_id: str,
    verdict: str = "accept",
) -> None:
    """Insert a review row to mark an instance as reviewed."""
    conn.execute(
        """
        INSERT INTO identification_reviews (
            review_id, identification_instance_id, layer, point_id,
            pipeline_component, trigger_text, observation_state,
            action_taken, downstream_impact, provenance_pointer,
            verdict
        ) VALUES (?, ?, 'L1', 'L1-1', 'comp', 'trig', 'obs', 'act',
                  'imp', 'prov', ?)
        """,
        [str(uuid.uuid4()), instance_id, verdict],
    )


class TestSampleOneEmpty:
    """sample_one() returns None when pool is empty."""

    def test_empty_pool_returns_none(self, conn: duckdb.DuckDBPyConnection):
        sampler = BalancedLayerSampler(pool=[], conn=conn)
        assert sampler.sample_one() is None

    def test_all_reviewed_returns_none(self, conn: duckdb.DuckDBPyConnection):
        pool = [_make_point(IdentificationLayer.L1_EVENT_FILTER, instance_id="inst1")]
        _insert_review(conn, "inst1")
        sampler = BalancedLayerSampler(pool=pool, conn=conn)
        assert sampler.sample_one() is None


class TestSampleOneExcludesReviewed:
    """sample_one() excludes already-reviewed instances."""

    def test_excludes_reviewed(self, conn: duckdb.DuckDBPyConnection):
        pool = [
            _make_point(IdentificationLayer.L1_EVENT_FILTER, instance_id="reviewed1"),
            _make_point(IdentificationLayer.L1_EVENT_FILTER, instance_id="unreviewed1"),
        ]
        _insert_review(conn, "reviewed1")

        sampler = BalancedLayerSampler(pool=pool, conn=conn)
        result = sampler.sample_one()
        assert result is not None
        assert result.instance_id == "unreviewed1"

    def test_multiple_reviewed_excluded(self, conn: duckdb.DuckDBPyConnection):
        pool = [
            _make_point(IdentificationLayer.L2_TAGGING, instance_id="r1"),
            _make_point(IdentificationLayer.L2_TAGGING, instance_id="r2"),
            _make_point(IdentificationLayer.L2_TAGGING, instance_id="u1"),
        ]
        _insert_review(conn, "r1")
        _insert_review(conn, "r2")

        sampler = BalancedLayerSampler(pool=pool, conn=conn)
        result = sampler.sample_one()
        assert result is not None
        assert result.instance_id == "u1"


class TestSampleOneLayerPriority:
    """sample_one() preferentially samples from lowest-coverage layer."""

    def test_prefers_lowest_coverage(self, conn: duckdb.DuckDBPyConnection):
        # L1: 2 points, 1 reviewed (50% coverage)
        # L2: 2 points, 0 reviewed (0% coverage)
        pool = [
            _make_point(IdentificationLayer.L1_EVENT_FILTER, instance_id="l1-a"),
            _make_point(IdentificationLayer.L1_EVENT_FILTER, instance_id="l1-b"),
            _make_point(IdentificationLayer.L2_TAGGING, instance_id="l2-a"),
            _make_point(IdentificationLayer.L2_TAGGING, instance_id="l2-b"),
        ]
        _insert_review(conn, "l1-a")

        sampler = BalancedLayerSampler(pool=pool, conn=conn)
        result = sampler.sample_one()
        assert result is not None
        # Should pick from L2 (0% coverage) over L1 (50% coverage)
        assert result.layer == IdentificationLayer.L2_TAGGING

    def test_equal_coverage_still_returns(self, conn: duckdb.DuckDBPyConnection):
        """When all layers have equal coverage, still returns something."""
        pool = _make_pool(per_layer=2)
        sampler = BalancedLayerSampler(pool=pool, conn=conn)
        result = sampler.sample_one()
        assert result is not None


class TestSampleBatchDistribution:
    """After 40+ samples, no layer exceeds 20% of total."""

    def test_balanced_distribution(self, conn: duckdb.DuckDBPyConnection):
        """With 10 instances per layer (80 total), 40 samples should be balanced."""
        pool = _make_pool(per_layer=10)
        sampler = BalancedLayerSampler(pool=pool, conn=conn)

        batch = sampler.sample_batch(40)
        assert len(batch) == 40

        layer_counts = Counter(p.layer for p in batch)
        total = len(batch)
        for layer, count in layer_counts.items():
            ratio = count / total
            assert ratio <= 0.20, (
                f"Layer {layer.value} has {count}/{total} = {ratio:.2%}, "
                f"exceeding 20% threshold"
            )

    def test_batch_no_duplicates(self, conn: duckdb.DuckDBPyConnection):
        pool = _make_pool(per_layer=10)
        sampler = BalancedLayerSampler(pool=pool, conn=conn)

        batch = sampler.sample_batch(40)
        ids = [p.instance_id for p in batch]
        assert len(ids) == len(set(ids)), "Batch contains duplicate instances"

    def test_batch_respects_pool_size(self, conn: duckdb.DuckDBPyConnection):
        """Batch cannot exceed pool size."""
        pool = _make_pool(per_layer=2)  # 16 total
        sampler = BalancedLayerSampler(pool=pool, conn=conn)

        batch = sampler.sample_batch(40)
        assert len(batch) == 16  # Can't exceed pool size

    def test_batch_excludes_reviewed(self, conn: duckdb.DuckDBPyConnection):
        pool = _make_pool(per_layer=5)  # 40 total
        # Review half of L1
        for i in range(3):
            _insert_review(conn, f"L1:{i}")

        sampler = BalancedLayerSampler(pool=pool, conn=conn)
        batch = sampler.sample_batch(10)

        reviewed_in_batch = [p for p in batch if p.instance_id.startswith("L1:") and int(p.instance_id.split(":")[1]) < 3]
        assert len(reviewed_in_batch) == 0, "Batch includes reviewed instances"
