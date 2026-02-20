"""CLI subcommands for managing project wisdom entities.

Provides subcommands under `wisdom`:
- ingest: Bulk-load wisdom entries from a JSON file
- check-scope: Check scope decisions applicable to a file path
- reindex: Rebuild the wisdom FTS search index
- list: List wisdom entities with optional type filter

Exports:
    wisdom_group: Click group for wisdom subcommands
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from loguru import logger


@click.group("wisdom")
def wisdom_group():
    """Manage project wisdom entities."""
    pass


@wisdom_group.command(name="ingest")
@click.argument("path", type=click.Path(exists=True))
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def ingest(path: str, db: str) -> None:
    """Ingest wisdom entries from a JSON file.

    PATH is the path to a JSON file containing wisdom entries. Accepts
    either a top-level JSON array or an object with an "entries" key.
    """
    _setup_logging()

    try:
        from src.pipeline.wisdom.ingestor import WisdomIngestor
        from src.pipeline.wisdom.store import WisdomStore

        store = WisdomStore(Path(db))
        ingestor = WisdomIngestor(store)
        result = ingestor.ingest_file(Path(path))

        click.echo(f"Added: {result.added}, Updated: {result.updated}, Skipped: {result.skipped}")
        if result.errors:
            for err in result.errors:
                click.echo(f"  Error: {err}", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wisdom_group.command(name="check-scope")
@click.argument("scope_path")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def check_scope(scope_path: str, db: str) -> None:
    """Check scope decisions for a given path.

    SCOPE_PATH is the file or directory path to check against stored
    scope decisions. Returns matching scope_decision entities.
    """
    _setup_logging()

    try:
        from src.pipeline.wisdom.store import WisdomStore

        store = WisdomStore(Path(db))
        entities = store.search_by_scope(scope_path)
        scope_decisions = [e for e in entities if e.entity_type == "scope_decision"]

        if not scope_decisions:
            click.echo(f"No scope decisions found for path: {scope_path}")
            return

        for decision in scope_decisions:
            click.echo(f"\n[scope_decision] {decision.title}")
            click.echo(f"  {decision.description}")
            if decision.scope_paths:
                click.echo(f"  Scope: {', '.join(decision.scope_paths)}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wisdom_group.command(name="reindex")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def reindex(db: str) -> None:
    """Rebuild the wisdom FTS search index.

    Recreates the full-text search index on the project_wisdom table.
    Required after bulk inserts for BM25 search to reflect new entries.
    """
    _setup_logging()

    try:
        from src.pipeline.wisdom.retriever import WisdomRetriever
        from src.pipeline.wisdom.store import WisdomStore

        store = WisdomStore(Path(db))
        retriever = WisdomRetriever(store)
        retriever.rebuild_index()

        click.echo("Wisdom FTS index rebuilt.")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wisdom_group.command(name="list")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--type", "entity_type", default=None, help="Filter by entity type.")
def list_wisdom(db: str, entity_type: str | None) -> None:
    """List wisdom entities with optional type filter.

    Shows each entity's type, title, and first 80 characters of description.
    Use --type to filter by entity type (breakthrough, dead_end,
    scope_decision, method_decision).
    """
    _setup_logging()

    try:
        from src.pipeline.wisdom.store import WisdomStore

        store = WisdomStore(Path(db))
        entities = store.list(entity_type=entity_type)

        if not entities:
            click.echo("No wisdom entities found.")
            return

        for entity in entities:
            desc_preview = entity.description[:80]
            if len(entity.description) > 80:
                desc_preview += "..."
            click.echo(f"[{entity.entity_type}] {entity.title}")
            click.echo(f"  {desc_preview}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING", format="{time:HH:mm:ss} | {level:<7} | {message}")
