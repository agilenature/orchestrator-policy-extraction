"""CLI subcommands for identification transparency review.

Provides the ``review`` group with:
- next: Present one unreviewed identification instance and collect a verdict

This is the Agent B terminal command -- the mechanism through which
the human reviews pipeline classification acts.

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


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="WARNING",
        format="{time:HH:mm:ss} | {level:<7} | {message}",
    )
