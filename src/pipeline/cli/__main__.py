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
    python -m src.pipeline.cli review harness [options]
    python -m src.pipeline.cli review stats [options]
    python -m src.pipeline.cli intelligence profile <human_id> [options]
    python -m src.pipeline.cli intelligence stagnant [options]
    python -m src.pipeline.cli intelligence memory-review [options]
    python -m src.pipeline.cli bus start [options]
    python -m src.pipeline.cli bus status [options]
    python -m src.pipeline.cli docs reindex [options]
    python -m src.pipeline.cli query [--source docs|sessions|code|all] <query_text> [options]
"""

import click

from src.pipeline.cli.audit import audit_group
from src.pipeline.cli.bus import bus_group
from src.pipeline.cli.docs import docs_group
from src.pipeline.cli.extract import main as extract_cmd
from src.pipeline.cli.query import query_cmd
from src.pipeline.cli.govern import govern_group
from src.pipeline.cli.intelligence import intelligence_group
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
cli.add_command(intelligence_group, name="intelligence")
cli.add_command(bus_group, name="bus")
cli.add_command(docs_group, name="docs")
cli.add_command(query_cmd, name="query")

if __name__ == "__main__":
    cli()
