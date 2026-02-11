"""CLI subcommands for the validation workflow.

Provides three subcommands under `validate`:
- export: Export episodes for human review
- metrics: Compute quality metrics from gold-standard labels
- export-parquet: Export validated episodes to Parquet format

Exports:
    validate_group: Click group for validation subcommands
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import duckdb
from loguru import logger

from src.pipeline.storage.schema import create_schema, get_connection
from src.pipeline.validation.exporter import export_parquet, export_parquet_partitioned
from src.pipeline.validation.gold_standard import export_for_review, import_labels
from src.pipeline.validation.metrics import compute_metrics, format_report


@click.group("validate")
def validate_group():
    """Validation workflow: export, metrics, and Parquet export."""
    pass


@validate_group.command("export")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--output-dir", default="data/gold-standard", help="Output directory.")
@click.option("--sample-size", default=100, type=int, help="Max episodes to export.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def export_cmd(db: str, output_dir: str, sample_size: int, verbose: bool) -> None:
    """Export episodes for human review with template label files."""
    _setup_logging(verbose)

    conn = get_connection(db)
    create_schema(conn)

    output_path = Path(output_dir)
    count = export_for_review(conn, output_path, sample_size=sample_size)

    conn.close()

    click.echo(f"Exported {count} episodes for review")
    click.echo(f"  Episodes: {output_path / 'episodes'}")
    click.echo(f"  Labels:   {output_path / 'labels'}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review each episode in episodes/")
    click.echo("  2. Fill in verified labels in labels/")
    click.echo(f"  3. Run: python -m src.pipeline.cli validate metrics --labels-dir {output_dir}/labels")


@validate_group.command("metrics")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--labels-dir", default="data/gold-standard/labels", help="Directory with label files.")
@click.option("--constraints", default="data/constraints.json", help="Constraints JSON file.")
@click.option("--output", default="data/gold-standard/metrics", help="Output directory for report.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def metrics_cmd(
    db: str, labels_dir: str, constraints: str, output: str, verbose: bool
) -> None:
    """Compute quality metrics from gold-standard labels."""
    _setup_logging(verbose)

    # Load labels
    schema_path = Path("data/schemas/gold-standard-label.schema.json")
    valid_labels, errors = import_labels(Path(labels_dir), schema_path)

    if errors:
        click.echo("Import errors:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)

    if not valid_labels:
        click.echo("No valid labels found. Cannot compute metrics.", err=True)
        sys.exit(1)

    # Load constraints
    constraints_list = None
    constraints_path = Path(constraints)
    if constraints_path.exists():
        try:
            with open(constraints_path) as f:
                constraints_list = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            click.echo(f"Warning: Could not load constraints: {e}", err=True)

    # Connect and compute
    conn = get_connection(db)
    create_schema(conn)

    report = compute_metrics(valid_labels, conn, constraints=constraints_list)
    conn.close()

    # Display report
    text = format_report(report)
    click.echo(text)

    # Save JSON report
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    report_dict = {
        "mode_accuracy": report.mode_accuracy,
        "reaction_accuracy": report.reaction_accuracy,
        "reaction_avg_confidence": report.reaction_avg_confidence,
        "constraint_extraction_rate": report.constraint_extraction_rate,
        "per_mode_accuracy": report.per_mode_accuracy,
        "per_reaction_accuracy": report.per_reaction_accuracy,
        "sample_size": report.sample_size,
        "thresholds_met": report.thresholds_met,
    }
    with open(report_path, "w") as f:
        json.dump(report_dict, f, indent=2)
        f.write("\n")

    click.echo(f"\nReport saved to {report_path}")


@validate_group.command("export-parquet")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--output", default="data/export/episodes.parquet", help="Output Parquet file.")
@click.option("--partition-by", default=None, help="Column to partition by (creates directory).")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def export_parquet_cmd(
    db: str, output: str, partition_by: str | None, verbose: bool
) -> None:
    """Export validated episodes to Parquet format."""
    _setup_logging(verbose)

    conn = get_connection(db)
    create_schema(conn)

    if partition_by:
        count = export_parquet_partitioned(conn, output, partition_by=partition_by)
        click.echo(f"Exported {count} episodes partitioned by '{partition_by}' to {output}/")
    else:
        count = export_parquet(conn, output)
        click.echo(f"Exported {count} episodes to {output}")

    conn.close()


def _setup_logging(verbose: bool) -> None:
    """Configure logging level."""
    logger.remove()
    log_level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=log_level, format="{time:HH:mm:ss} | {level:<7} | {message}")
