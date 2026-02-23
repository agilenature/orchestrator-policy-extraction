"""Balanced layer sampler for identification review.

Ensures uniform coverage across pipeline layers by preferentially
sampling from the layer with the lowest current coverage ratio
(reviewed/available). When N >= 40 samples, no layer should exceed
20% of total output.

Excludes already-reviewed instances by checking the identification_reviews
table for existing verdicts.

Exports:
    BalancedLayerSampler
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Optional

import duckdb

from src.pipeline.review.models import IdentificationLayer, IdentificationPoint


class BalancedLayerSampler:
    """Samples uniformly across 8 layers with coverage-based priority.

    Excludes already-reviewed instances (those with a verdict in
    identification_reviews table). Selects from the layer with the
    lowest current coverage ratio to ensure balanced review progress.

    Empty layers are gracefully skipped -- only layers with available
    pool instances are considered.

    Args:
        pool: List of IdentificationPoint instances to sample from.
        conn: DuckDB connection for checking reviewed instances.
    """

    def __init__(
        self,
        pool: list[IdentificationPoint],
        conn: duckdb.DuckDBPyConnection,
    ):
        self.pool = pool
        self.conn = conn
        # Pre-index pool by layer for fast lookup
        self._by_layer: dict[IdentificationLayer, list[IdentificationPoint]] = (
            defaultdict(list)
        )
        for point in pool:
            self._by_layer[point.layer].append(point)

    def sample_one(self) -> Optional[IdentificationPoint]:
        """Return one unreviewed instance from the lowest-coverage layer.

        Returns:
            An IdentificationPoint that has not been reviewed, or None
            if all instances have been reviewed.
        """
        reviewed_ids = self._get_reviewed_ids()
        unreviewed = [p for p in self.pool if p.instance_id not in reviewed_ids]
        if not unreviewed:
            return None

        # Compute coverage per layer and select from lowest
        layer_coverage = self._compute_layer_coverage(reviewed_ids)
        if not layer_coverage:
            return random.choice(unreviewed)

        target_layer = min(layer_coverage, key=lambda l: layer_coverage[l])
        candidates = [
            p for p in unreviewed if p.layer == target_layer
        ]
        if not candidates:
            # Fallback: any unreviewed instance
            candidates = unreviewed

        return random.choice(candidates)

    def sample_batch(self, n: int) -> list[IdentificationPoint]:
        """Return up to n unreviewed instances with balanced layer distribution.

        Calls sample_one repeatedly, simulating the progressive coverage
        improvement. Uses a local tracking set to avoid duplicates within
        the batch without writing to the database.

        Args:
            n: Maximum number of instances to return.

        Returns:
            List of up to n IdentificationPoint instances.
        """
        reviewed_ids = self._get_reviewed_ids()
        unreviewed = [p for p in self.pool if p.instance_id not in reviewed_ids]
        if not unreviewed:
            return []

        batch: list[IdentificationPoint] = []
        selected_ids: set[str] = set()

        for _ in range(min(n, len(unreviewed))):
            # Build candidates excluding already-selected
            remaining = [
                p for p in unreviewed if p.instance_id not in selected_ids
            ]
            if not remaining:
                break

            # Compute coverage including batch selections as "reviewed"
            simulated_reviewed = reviewed_ids | selected_ids
            layer_coverage = self._compute_layer_coverage(simulated_reviewed)

            if layer_coverage:
                target_layer = min(
                    layer_coverage, key=lambda l: layer_coverage[l]
                )
                candidates = [
                    p for p in remaining if p.layer == target_layer
                ]
                if not candidates:
                    candidates = remaining
            else:
                candidates = remaining

            selected = random.choice(candidates)
            batch.append(selected)
            selected_ids.add(selected.instance_id)

        return batch

    def _get_reviewed_ids(self) -> set[str]:
        """Fetch IDs of already-reviewed instances from DuckDB.

        Returns:
            Set of identification_instance_id values that have verdicts.
        """
        try:
            rows = self.conn.execute(
                "SELECT identification_instance_id "
                "FROM identification_reviews"
            ).fetchall()
            return {row[0] for row in rows}
        except Exception:
            # Table may not exist yet
            return set()

    def _compute_layer_coverage(
        self, reviewed_ids: set[str]
    ) -> dict[IdentificationLayer, float]:
        """Compute coverage ratio for each layer in the pool.

        Coverage = reviewed_count / pool_count for that layer.
        Only includes layers with pool instances > 0.

        Args:
            reviewed_ids: Set of instance IDs already reviewed.

        Returns:
            Dict mapping layer to coverage ratio (0.0 to 1.0).
        """
        coverage: dict[IdentificationLayer, float] = {}

        for layer, points in self._by_layer.items():
            pool_count = len(points)
            if pool_count == 0:
                continue
            reviewed_count = sum(
                1 for p in points if p.instance_id in reviewed_ids
            )
            coverage[layer] = reviewed_count / pool_count

        return coverage
