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
        sys.exit(2)


@wisdom_group.command(name="check-scope")
@click.argument("scope_path")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option(
    "--constraints",
    default="data/constraints.json",
    help="Path to constraints JSON file.",
)
def check_scope(scope_path: str, db: str, constraints: str) -> None:
    """Validate scope decisions against active constraints.

    SCOPE_PATH is the file or directory path to check. Finds matching
    scope_decision entities and cross-references them against active
    constraints from the constraint store. Exits with structured codes:

    \b
    Exit 0 = no violations found (or no matching scope decisions)
    Exit 1 = at least one violation found
    Exit 2 = runtime error
    """
    _setup_logging()

    try:
        from src.pipeline.constraint_store import ConstraintStore
        from src.pipeline.utils import scopes_overlap
        from src.pipeline.wisdom.store import WisdomStore

        store = WisdomStore(Path(db))
        entities = store.search_by_scope(scope_path)
        scope_decisions = [e for e in entities if e.entity_type == "scope_decision"]

        if not scope_decisions:
            click.echo(f"No scope decisions found for path: {scope_path}")
            sys.exit(0)

        constraint_store = ConstraintStore(path=Path(constraints))
        active_constraints = constraint_store.get_active_constraints()

        violations: list[tuple[str, dict]] = []

        for decision in scope_decisions:
            # Extract title words > 3 chars for text matching
            title_words = [
                w for w in decision.title.lower().split() if len(w) > 3
            ]

            for constraint in active_constraints:
                constraint_text = constraint.get("text", "").lower()

                # Check title word overlap: need 2+ matching words
                matching_words = [
                    w for w in title_words if w in constraint_text
                ]
                if len(matching_words) < 2:
                    continue

                # Check scope overlap if constraint has scope paths
                constraint_paths = constraint.get("scope", {}).get("paths", [])
                if constraint_paths and not scopes_overlap(
                    constraint_paths, [scope_path]
                ):
                    continue

                # Check severity for violation
                severity = constraint.get("severity", "")
                if severity in ("forbidden", "requires_approval"):
                    violations.append((decision.title, constraint))

        if violations:
            click.echo(
                f"Found {len(violations)} scope violation(s) for path: {scope_path}"
            )
            for title, constraint in violations:
                click.echo(
                    f"  [{constraint.get('severity')}] {title} -> "
                    f"{constraint.get('constraint_id', 'unknown')}: "
                    f"{constraint.get('text', '')[:80]}"
                )
            sys.exit(1)

        click.echo(f"No violations found for path: {scope_path}")
        sys.exit(0)

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


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
        sys.exit(2)


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
        sys.exit(2)


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING", format="{time:HH:mm:ss} | {level:<7} | {message}")
