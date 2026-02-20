"""CLI subcommands for governance protocol management.

Provides subcommands under ``govern``:
- ingest: Ingest a governance Markdown document into constraints and wisdom
- check-stability: Run stability checks and flag missing validations

Exports:
    govern_group: Click group for governance subcommands
"""

from __future__ import annotations

import sys

import click
from loguru import logger


@click.group("govern")
def govern_group():
    """Governance protocol management."""
    pass


@govern_group.command(name="ingest")
@click.argument("path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview extraction without writing.")
@click.option("--source-id", default=None, help="Override source document ID.")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option(
    "--constraints",
    default="data/constraints.json",
    help="Constraints JSON file path.",
)
@click.option("--config", default="data/config.yaml", help="Pipeline config path.")
def ingest(path, dry_run, source_id, db, constraints, config):
    """Ingest a governance document (pre-mortem or DECISIONS.md)."""
    _setup_logging()
    try:
        from pathlib import Path as P

        from src.pipeline.constraint_store import ConstraintStore
        from src.pipeline.governance.ingestor import GovDocIngestor
        from src.pipeline.models.config import load_config
        from src.pipeline.wisdom.store import WisdomStore

        cfg = load_config(config)
        constraint_store = ConstraintStore(
            path=P(constraints),
            schema_path=P("data/schemas/constraint.schema.json"),
        )
        wisdom_store = WisdomStore(P(db))
        ingestor = GovDocIngestor(
            constraint_store=constraint_store,
            wisdom_store=wisdom_store,
            bulk_threshold=cfg.governance.bulk_ingest_threshold,
        )

        result = ingestor.ingest_file(P(path), source_id=source_id, dry_run=dry_run)

        # Output results
        mode_label = "[DRY RUN] " if dry_run else ""
        click.echo(
            f"{mode_label}Constraints: {result.constraints_added} added, "
            f"{result.constraints_skipped} skipped"
        )
        click.echo(
            f"{mode_label}Wisdom: {result.wisdom_added} added, "
            f"{result.wisdom_updated} updated, "
            f"{result.wisdom_skipped} skipped"
        )

        if result.errors:
            for err in result.errors:
                click.echo(f"  Warning: {err}", err=True)

        total = result.constraints_added + result.wisdom_added + result.wisdom_updated
        if total == 0 and not dry_run:
            click.echo("No entities extracted. Check document format.", err=True)
            sys.exit(2)

        # Flag bulk ingest if threshold exceeded
        if not dry_run and result.is_bulk:
            click.echo(
                f"BULK INGEST: {result.total_entities} entities "
                f"(threshold: {cfg.governance.bulk_ingest_threshold})"
            )
            click.echo("Marking episodes as requiring stability check...")
            # Reuse wisdom_store._conn to avoid two simultaneous write connections
            # (DuckDB raises IOException if two write connections open the same file)
            from src.pipeline.storage.schema import create_schema

            create_schema(wisdom_store._conn)  # Idempotent; ensures episodes table exists
            # Count matching rows before update
            flagged = wisdom_store._conn.execute(
                """
                SELECT COUNT(*) FROM episodes
                WHERE stability_check_status IS NULL
                  AND requires_stability_check = FALSE
                """
            ).fetchone()[0]
            wisdom_store._conn.execute(
                """
                UPDATE episodes
                SET requires_stability_check = TRUE
                WHERE stability_check_status IS NULL
                  AND requires_stability_check = FALSE
                """
            )
            click.echo(f"  {flagged} episode(s) flagged for stability check.")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@govern_group.command(name="check-stability")
@click.option(
    "--output",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format.",
)
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--config", default="data/config.yaml", help="Pipeline config path.")
def check_stability(output_format, db, config):
    """Run stability checks and flag missing validations."""
    _setup_logging()
    try:
        import dataclasses
        import json as json_mod
        import os

        from src.pipeline.governance.stability import StabilityRunner
        from src.pipeline.models.config import load_config
        from src.pipeline.storage.schema import create_schema, get_connection

        cfg = load_config(config)

        if not cfg.governance.stability_checks:
            click.echo("No stability checks configured.")
            sys.exit(0)

        conn = get_connection(db)
        create_schema(conn)

        runner = StabilityRunner(conn=conn, config=cfg.governance)
        repo_root = os.getcwd()
        outcomes = runner.run_checks(repo_root=repo_root)

        # Flag missing validations
        missing_count = runner.flag_missing_validation(conn)

        # Mark validated if all checks passed
        all_passed = all(o.status == "pass" for o in outcomes)
        validated_count = 0
        if all_passed:
            validated_count = runner.mark_validated(conn)

        # Output results
        if output_format == "json":
            result = {
                "outcomes": [dataclasses.asdict(o) for o in outcomes],
                "all_passed": all_passed,
                "missing_validation_flagged": missing_count,
                "episodes_validated": validated_count,
            }
            click.echo(json_mod.dumps(result, indent=2))
        else:
            for o in outcomes:
                if o.status == "pass":
                    status_icon = "PASS"
                elif o.status == "fail":
                    status_icon = "FAIL"
                else:
                    status_icon = "ERROR"
                click.echo(f"  [{status_icon}] {o.check_id} (exit {o.exit_code})")
            click.echo(f"Missing validation flagged: {missing_count}")
            if all_passed:
                click.echo(f"Episodes validated: {validated_count}")

        conn.close()

        # Exit codes: 0=all-passed, 1=error, 2=any-check-failed
        if not all_passed:
            sys.exit(2)

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
