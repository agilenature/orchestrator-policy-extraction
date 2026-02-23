"""Integration tests for the review route and review trust CLI commands.

Tests the full flow:
- review route: finds unrouted rejections, routes to memory_candidates
- review route: idempotent (running twice produces no duplicates)
- review trust: displays trust levels per classification rule

Uses temporary DuckDB files and directly seeded review rows.
"""

from __future__ import annotations

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def runner():
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DuckDB with review schema only."""
    path = str(tmp_path / "test.db")
    conn = duckdb.connect(path)
    create_review_schema(conn)
    conn.close()
    return path


def _seed_rejected_review(
    db_path: str,
    review_id: str = "rev-rej-001",
    instance_id: str = "inst-rej-001",
    opinion: str = "Wrong label -- should be curiosity",
    point_id: str = "L4-4",
    component: str = "ReactionLabeler",
) -> None:
    """Seed one rejected review with opinion into the DB."""
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        INSERT INTO identification_reviews (
            review_id, identification_instance_id, layer, point_id,
            pipeline_component, trigger_text, observation_state,
            action_taken, downstream_impact, provenance_pointer,
            verdict, opinion
        ) VALUES (?, ?, 'L4', ?, ?, 'trigger', 'observation',
                  'action taken', 'impact', 'sess:ep:table:row',
                  'reject', ?)
        """,
        [review_id, instance_id, point_id, component, opinion],
    )
    conn.close()


def _seed_accepted_review(
    db_path: str,
    review_id: str = "rev-acc-001",
    instance_id: str = "inst-acc-001",
    point_id: str = "L2-1",
    component: str = "EventTagger",
) -> None:
    """Seed one accepted review into the DB."""
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        INSERT INTO identification_reviews (
            review_id, identification_instance_id, layer, point_id,
            pipeline_component, trigger_text, observation_state,
            action_taken, downstream_impact, provenance_pointer,
            verdict
        ) VALUES (?, ?, 'L2', ?, ?, 'trigger', 'observation',
                  'action', 'impact', 'prov', 'accept')
        """,
        [review_id, instance_id, point_id, component],
    )
    conn.close()


class TestReviewRouteWithUnrouted:
    """review route with unrouted rejected verdicts."""

    def test_routes_unrouted_rejections(self, runner, db_path):
        """review route finds and routes unrouted rejected verdicts."""
        _seed_rejected_review(db_path)

        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["route", "--db", db_path])

        assert result.exit_code == 0
        assert "Routed 1 rejected verdict(s)" in result.output

    def test_writes_to_memory_candidates(self, runner, db_path):
        """review route writes a row to memory_candidates."""
        _seed_rejected_review(db_path)

        from src.pipeline.cli.review import review_group

        runner.invoke(review_group, ["route", "--db", db_path])

        conn = duckdb.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 1

        row = conn.execute(
            "SELECT source_instance_id, pipeline_component, status "
            "FROM memory_candidates"
        ).fetchone()
        assert row[0] == "inst-rej-001"
        assert row[1] == "ReactionLabeler"
        assert row[2] == "pending"
        conn.close()

    def test_multiple_rejections_routed(self, runner, db_path):
        """review route handles multiple unrouted rejections."""
        _seed_rejected_review(
            db_path, review_id="rev-1", instance_id="inst-1", opinion="Wrong"
        )
        _seed_rejected_review(
            db_path,
            review_id="rev-2",
            instance_id="inst-2",
            opinion="Also wrong",
            point_id="L3-1",
            component="Segmenter",
        )

        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["route", "--db", db_path])

        assert result.exit_code == 0
        assert "Routed 2 rejected verdict(s)" in result.output


class TestReviewRouteIdempotent:
    """review route is idempotent -- running twice produces no duplicates."""

    def test_second_run_finds_nothing(self, runner, db_path):
        """Second run of review route finds no unrouted verdicts."""
        _seed_rejected_review(db_path)

        from src.pipeline.cli.review import review_group

        runner.invoke(review_group, ["route", "--db", db_path])
        result = runner.invoke(review_group, ["route", "--db", db_path])

        assert result.exit_code == 0
        assert "No unrouted rejected verdicts found" in result.output

    def test_no_duplicate_candidates(self, runner, db_path):
        """Running twice produces exactly one memory_candidates row."""
        _seed_rejected_review(db_path)

        from src.pipeline.cli.review import review_group

        runner.invoke(review_group, ["route", "--db", db_path])
        runner.invoke(review_group, ["route", "--db", db_path])

        conn = duckdb.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 1
        conn.close()


class TestReviewRouteEmpty:
    """review route with no rejected verdicts."""

    def test_no_rejections_prints_message(self, runner, db_path):
        """review route with no rejections prints informational message."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["route", "--db", db_path])

        assert result.exit_code == 0
        assert "No unrouted rejected verdicts found" in result.output

    def test_accepted_only_not_routed(self, runner, db_path):
        """Accepted verdicts are not routed to memory_candidates."""
        _seed_accepted_review(db_path)

        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["route", "--db", db_path])

        assert result.exit_code == 0
        assert "No unrouted rejected verdicts found" in result.output


class TestReviewTrust:
    """review trust command."""

    def test_no_data_prints_message(self, runner, db_path):
        """review trust with no data prints informational message."""
        from src.pipeline.cli.review import review_group

        result = runner.invoke(review_group, ["trust", "--db", db_path])

        assert result.exit_code == 0
        assert "No trust data found" in result.output

    def test_shows_trust_after_routing(self, runner, db_path):
        """review trust shows trust data after route has been run."""
        _seed_rejected_review(db_path)

        from src.pipeline.cli.review import review_group

        # Route first to populate trust data
        runner.invoke(review_group, ["route", "--db", db_path])

        result = runner.invoke(review_group, ["trust", "--db", db_path])

        assert result.exit_code == 0
        assert "ReactionLabeler" in result.output
        assert "L4-4" in result.output
        assert "1 rule(s) tracked" in result.output

    def test_shows_established_rules(self, runner, db_path):
        """review trust shows established trust level at 10+ accepts."""
        # Seed 10 accepted reviews for same rule
        for i in range(10):
            _seed_accepted_review(
                db_path,
                review_id=f"rev-acc-{i:03d}",
                instance_id=f"inst-acc-{i:03d}",
                point_id="L2-1",
                component="EventTagger",
            )

        from src.pipeline.cli.review import review_group

        # Route to populate trust data via accepted verdicts
        # But route only processes rejects. We need to use TrustAccumulator directly.
        # Actually, the trust command reads from identification_rule_trust table,
        # which is populated by VerdictRouter.route() for both accepts and rejects.
        # Since `review route` only processes rejects, we need a different approach.
        # Let's directly populate via the router for accepted reviews.
        import duckdb as _duckdb

        from src.pipeline.review.models import (
            IdentificationLayer,
            IdentificationReview,
            ReviewVerdict,
        )
        from src.pipeline.review.router import VerdictRouter
        from src.pipeline.review.schema import create_review_schema

        conn = _duckdb.connect(db_path)
        create_review_schema(conn)
        router = VerdictRouter(conn)

        for i in range(10):
            review = IdentificationReview(
                review_id=f"rev-trust-{i}",
                identification_instance_id=f"inst-trust-{i}",
                layer=IdentificationLayer.L2_TAGGING,
                point_id="L2-1",
                pipeline_component="EventTagger",
                trigger="trigger",
                observation_state="obs",
                action_taken="action",
                downstream_impact="impact",
                provenance_pointer="prov",
                verdict=ReviewVerdict.ACCEPT,
                reviewed_at="2026-02-23T18:00:00+00:00",
            )
            router.route(review)
        conn.close()

        result = runner.invoke(review_group, ["trust", "--db", db_path])

        assert result.exit_code == 0
        assert "established" in result.output
        assert "EventTagger" in result.output

    def test_filter_by_component(self, runner, db_path):
        """review trust --component filters output."""
        import duckdb as _duckdb

        from src.pipeline.review.models import (
            IdentificationLayer,
            IdentificationReview,
            ReviewVerdict,
        )
        from src.pipeline.review.router import VerdictRouter
        from src.pipeline.review.schema import create_review_schema

        conn = _duckdb.connect(db_path)
        create_review_schema(conn)
        router = VerdictRouter(conn)

        # Two different components
        review_a = IdentificationReview(
            review_id="rev-a",
            identification_instance_id="inst-a",
            layer=IdentificationLayer.L2_TAGGING,
            point_id="L2-1",
            pipeline_component="EventTagger",
            trigger="t", observation_state="o",
            action_taken="a", downstream_impact="d",
            provenance_pointer="p",
            verdict=ReviewVerdict.ACCEPT,
            reviewed_at="2026-02-23T18:00:00+00:00",
        )
        review_b = IdentificationReview(
            review_id="rev-b",
            identification_instance_id="inst-b",
            layer=IdentificationLayer.L3_SEGMENTATION,
            point_id="L3-1",
            pipeline_component="Segmenter",
            trigger="t", observation_state="o",
            action_taken="a", downstream_impact="d",
            provenance_pointer="p",
            verdict=ReviewVerdict.ACCEPT,
            reviewed_at="2026-02-23T18:00:00+00:00",
        )
        router.route(review_a)
        router.route(review_b)
        conn.close()

        from src.pipeline.cli.review import review_group

        result = runner.invoke(
            review_group,
            ["trust", "--db", db_path, "--component", "EventTagger"],
        )

        assert result.exit_code == 0
        assert "EventTagger" in result.output
        assert "Segmenter" not in result.output
        assert "1 rule(s) tracked" in result.output
