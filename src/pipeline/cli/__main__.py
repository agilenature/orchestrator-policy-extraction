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
"""

import click

from src.pipeline.cli.extract import main as extract_cmd
from src.pipeline.cli.train import train_group
from src.pipeline.cli.validate import validate_group


@click.group()
def cli():
    """Orchestrator Policy Extraction pipeline CLI."""
    pass


cli.add_command(extract_cmd, name="extract")
cli.add_command(validate_group, name="validate")
cli.add_command(train_group, name="train")

if __name__ == "__main__":
    cli()
