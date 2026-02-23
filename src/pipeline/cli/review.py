"""CLI subcommands for identification transparency review.

Provides the ``review`` group with:
- next: Present one unreviewed identification instance and collect a verdict
- route: Route unrouted rejected verdicts to spec-correction candidates
- trust: Show per-classification-rule trust levels

This is the Agent B terminal command -- the mechanism through which
the human reviews pipeline classification acts. The ``route`` and
``trust`` subcommands close the loop from identification opacity to
closed-loop-to-specification.

Exports:
    review_group: Click group for review subcommands
"""

from __future__ import annotations

import sys

import click
from loguru import logger


@click.group("review")
def review_group():
    """Identification transparency review commands."""
    pass


@review_group.command(name="next")
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option(
    "--constraints",
    default="data/constraints.json",
    help="Constraints JSON file path.",
)
def review_next(db: str, constraints: str):
    """Present one unreviewed identification instance and collect a verdict."""
    _setup_logging()
    try:
        import duckdb
        from datetime import datetime, timezone
        from pathlib import Path

        from src.pipeline.review.collector import VerdictCollector
        from src.pipeline.review.models import IdentificationReview, ReviewVerdict
        from src.pipeline.review.pool_builder import PoolBuilder
        from src.pipeline.review.presenter import present
        from src.pipeline.review.sampler import BalancedLayerSampler
        from src.pipeline.review.schema import create_review_schema
        from src.pipeline.review.writer import ReviewWriter

        conn = duckdb.connect(db)
        create_review_schema(conn)

        builder = PoolBuilder(conn, constraints_path=Path(constraints))
        pool = builder.build()

        sampler = BalancedLayerSampler(pool, conn)
        instance = sampler.sample_one()

        if instance is None:
            click.echo("All identification instances have been reviewed.")
            return

        click.echo(present(instance))

        collector = VerdictCollector()
        verdict, opinion = collector.collect()

        review_obj = IdentificationReview(
            identification_instance_id=instance.instance_id,
            layer=instance.layer,
            point_id=instance.point_id,
            pipeline_component=instance.pipeline_component,
            trigger=instance.trigger,
            observation_state=instance.observation_state,
            action_taken=instance.action_taken,
            downstream_impact=instance.downstream_impact,
            provenance_pointer=instance.provenance_pointer,
            verdict=verdict,
            opinion=opinion,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )

        writer = ReviewWriter(conn)
        writer.write(review_obj)

        status = "Accepted" if verdict == ReviewVerdict.ACCEPT else "Rejected"
        click.echo(f"\n{status} -- review written.")
        if verdict == ReviewVerdict.REJECT and opinion:
            click.echo(
                "Opinion recorded. Spec-correction candidate will be "
                "generated (run: review route)."
            )
        elif verdict == ReviewVerdict.REJECT and not opinion:
            click.echo(
                "Tip: rejected verdicts with opinions generate named "
                "spec-correction targets."
            )

        conn.close()

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@review_group.command(name="route")
@click.option("--db", default="data/ope.db", help="DuckDB path")
def review_route(db: str):
    """Route all unrouted rejected verdicts to spec-correction candidates.

    Queries identification_reviews for rejected verdicts with non-empty
    opinions that have not yet been routed to memory_candidates. For each
    unrouted rejection, writes a CCD-format spec-correction candidate.

    Idempotent: running twice produces no duplicates.
    """
    _setup_logging()
    try:
        import duckdb

        from src.pipeline.review.models import (
            IdentificationLayer,
            IdentificationReview,
            ReviewVerdict,
        )
        from src.pipeline.review.router import VerdictRouter
        from src.pipeline.review.schema import create_review_schema

        conn = duckdb.connect(db)
        create_review_schema(conn)

        # Find unrouted rejected verdicts with opinions
        rows = conn.execute(
            """
            SELECT
                review_id, identification_instance_id, layer, point_id,
                pipeline_component, trigger_text, observation_state,
                action_taken, downstream_impact, provenance_pointer,
                verdict, opinion, reviewed_at, session_id
            FROM identification_reviews
            WHERE verdict = 'reject'
              AND opinion IS NOT NULL
              AND LENGTH(TRIM(opinion)) > 0
              AND identification_instance_id NOT IN (
                  SELECT source_instance_id
                  FROM memory_candidates
                  WHERE source_instance_id IS NOT NULL
              )
            """
        ).fetchall()

        if not rows:
            click.echo("No unrouted rejected verdicts found.")
            conn.close()
            return

        router = VerdictRouter(conn)
        routed_count = 0

        for row in rows:
            (
                review_id, inst_id, layer, point_id, component,
                trigger_text, obs_state, action, impact, provenance,
                verdict, opinion, reviewed_at, session_id,
            ) = row

            review = IdentificationReview(
                review_id=review_id,
                identification_instance_id=inst_id,
                layer=IdentificationLayer(layer),
                point_id=point_id,
                pipeline_component=component,
                trigger=trigger_text,
                observation_state=obs_state,
                action_taken=action,
                downstream_impact=impact,
                provenance_pointer=provenance,
                verdict=ReviewVerdict(verdict),
                opinion=opinion,
                reviewed_at=(
                    reviewed_at.isoformat()
                    if hasattr(reviewed_at, "isoformat")
                    else str(reviewed_at)
                ),
                session_id=session_id,
            )

            candidate_id = router.route(review)
            if candidate_id:
                routed_count += 1

        click.echo(
            f"Routed {routed_count} rejected verdict(s) to spec-correction candidates."
        )
        conn.close()

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@review_group.command(name="trust")
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option(
    "--component",
    default=None,
    help="Filter by pipeline component.",
)
def review_trust(db: str, component: str):
    """Show trust levels per classification rule.

    Displays a table of pipeline_component, point_id, accepts,
    rejects, and trust_level for all tracked classification rules.
    Optionally filter by --component.
    """
    _setup_logging()
    try:
        import duckdb

        from src.pipeline.review.schema import create_review_schema
        from src.pipeline.review.trust import TrustAccumulator

        conn = duckdb.connect(db)
        create_review_schema(conn)

        acc = TrustAccumulator(conn)
        rules = acc.get_all(pipeline_component=component)

        if not rules:
            click.echo("No trust data found.")
            conn.close()
            return

        # Header
        click.echo(
            f"{'Component':<30} {'Point':<10} {'Accepts':>8} "
            f"{'Rejects':>8} {'Trust Level':<15}"
        )
        click.echo("-" * 75)

        for rule in rules:
            click.echo(
                f"{rule['pipeline_component']:<30} "
                f"{rule['point_id']:<10} "
                f"{rule['accepts']:>8} "
                f"{rule['rejects']:>8} "
                f"{rule['trust_level']:<15}"
            )

        click.echo(f"\n{len(rules)} rule(s) tracked.")
        conn.close()

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="WARNING",
        format="{time:HH:mm:ss} | {level:<7} | {message}",
    )
