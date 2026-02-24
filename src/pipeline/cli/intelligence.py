"""CLI subcommands for DDF Intelligence Profile display.

Provides subcommands under `intelligence`:
- profile: Display IntelligenceProfile for a human or AI subject
- stagnant: List stagnant constraints (floating abstractions)

Exports:
    intelligence_group: Click group for intelligence subcommands
"""

from __future__ import annotations

import sys

import click
from loguru import logger


@click.group("intelligence")
def intelligence_group():
    """DDF Intelligence Profile commands."""
    pass


@intelligence_group.command(name="profile")
@click.argument("human_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--ai", "show_ai", is_flag=True, help="Display AI marker profile instead.")
def profile(human_id: str, db: str, show_ai: bool) -> None:
    """Display IntelligenceProfile for a human or AI subject.

    Usage:
        python -m src.pipeline.cli intelligence profile <human_id>
        python -m src.pipeline.cli intelligence profile ai --ai
    """
    _setup_logging()

    try:
        import duckdb

        from src.pipeline.ddf.intelligence_profile import (
            compute_ai_profile,
            compute_intelligence_profile,
            compute_spiral_depth_for_human,
        )
        from src.pipeline.ddf.schema import create_ddf_schema

        conn = duckdb.connect(db, read_only=True)

        # Ensure tables exist for queries (read_only=True prevents actual DDL
        # on disk, but for in-memory tables created fresh, this is safe)
        try:
            create_ddf_schema(conn)
        except Exception:
            pass  # Read-only mode may block DDL; tables should already exist

        if show_ai or human_id == "ai":
            ip = compute_ai_profile(conn)
        else:
            ip = compute_intelligence_profile(conn, human_id)

        conn.close()

        if ip is None:
            click.echo(f"No flame events found for human_id: {human_id}")
            sys.exit(0)

        # Format display
        subject_label = "AI" if ip.subject == "ai" else human_id
        click.echo(f"Intelligence Profile: {subject_label}")
        click.echo("=" * 40)
        click.echo(f"Sessions:         {ip.session_count}")
        click.echo(f"Flame Frequency:  {ip.flame_frequency}")
        click.echo(f"Avg Marker Level: {ip.avg_marker_level:.1f}")
        click.echo(f"Max Marker Level: {ip.max_marker_level}")
        click.echo(f"Spiral Depth:     {ip.spiral_depth}")
        flood_pct = f"{ip.flood_rate * 100:.0f}" if ip.flood_rate else "0"
        click.echo(f"Flood Rate:       {ip.flood_rate:.2f} ({flood_pct}%)")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@intelligence_group.command(name="stagnant")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def stagnant(db: str) -> None:
    """List stagnant constraints (floating abstractions).

    Stagnant constraints have radius=1 (single scope context) with
    high firing count -- potential floating abstractions that never
    generalized beyond their original context.

    Usage:
        python -m src.pipeline.cli intelligence stagnant
    """
    _setup_logging()

    try:
        import duckdb

        from src.pipeline.ddf.generalization import detect_stagnation
        from src.pipeline.ddf.schema import create_ddf_schema
        from src.pipeline.models.config import load_config

        conn = duckdb.connect(db, read_only=True)

        try:
            create_ddf_schema(conn)
        except Exception:
            pass  # Read-only mode may block DDL; tables should already exist

        try:
            config = load_config("data/config.yaml")
        except Exception:
            config = None

        stagnant_metrics = detect_stagnation(conn, config)
        conn.close()

        if not stagnant_metrics:
            click.echo("No stagnant constraints detected.")
            sys.exit(0)

        # Table header
        click.echo(
            f"{'constraint_id':<20} {'radius':<10} {'firing_count':<15} {'stagnant':<10}"
        )
        click.echo("-" * 55)

        for m in stagnant_metrics:
            cid = m.constraint_id[:18] if len(m.constraint_id) > 18 else m.constraint_id
            click.echo(
                f"{cid:<20} {m.radius:<10} {m.firing_count:<15} {str(m.is_stagnant):<10}"
            )

        click.echo(f"\nTotal stagnant: {len(stagnant_metrics)}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING", format="{time:HH:mm:ss} | {level:<7} | {message}")
