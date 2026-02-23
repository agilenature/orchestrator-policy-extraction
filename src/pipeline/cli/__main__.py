"""CLI entry point for the orchestrator policy extraction pipeline.

Usage:
    python -m src.pipeline.cli extract <path> [options]
    python -m src.pipeline.cli validate export [options]
    python -m src.pipeline.cli validate metrics [options]
    python -m src.pipeline.cli validate export-parquet [options]
    python -m src.pipeline.cli train embed [options]
    python -m src.pipeline.cli train recommend <episode_id> [options]
    python -m src.pipeline.cli train shadow-run [options]
    python -m src.pipeline.cli train shadow-report [options]
    python -m src.pipeline.cli audit session [options]
    python -m src.pipeline.cli audit durability [options]
    python -m src.pipeline.cli wisdom ingest <path> [options]
    python -m src.pipeline.cli wisdom check-scope <scope_path> [options]
    python -m src.pipeline.cli wisdom reindex [options]
    python -m src.pipeline.cli wisdom list [options]
    python -m src.pipeline.cli govern ingest <path> [options]
    python -m src.pipeline.cli govern check-stability [options]
    python -m src.pipeline.cli review next [options]
    python -m src.pipeline.cli review route [options]
    python -m src.pipeline.cli review trust [options]
"""

import click

from src.pipeline.cli.audit import audit_group
from src.pipeline.cli.extract import main as extract_cmd
from src.pipeline.cli.govern import govern_group
from src.pipeline.cli.train import train_group
from src.pipeline.cli.validate import validate_group
from src.pipeline.cli.review import review_group
from src.pipeline.cli.wisdom import wisdom_group


@click.group()
def cli():
    """Orchestrator Policy Extraction pipeline CLI."""
    pass


cli.add_command(extract_cmd, name="extract")
cli.add_command(validate_group, name="validate")
cli.add_command(train_group, name="train")
cli.add_command(audit_group, name="audit")
cli.add_command(wisdom_group, name="wisdom")
cli.add_command(govern_group, name="govern")
cli.add_command(review_group, name="review")

if __name__ == "__main__":
    cli()
