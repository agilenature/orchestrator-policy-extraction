"""Docs CLI -- manage the doc_index table.

Provides the ``reindex`` command that walks docs/ and populates the
doc_index DuckDB table with CCD axis associations discovered via the
3-tier extraction cascade in :mod:`src.pipeline.doc_indexer`.
"""

from __future__ import annotations

import click


@click.group(name="docs")
def docs_group():
    """Documentation index management."""


@docs_group.command()
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option("--docs-dir", default="docs", help="Documentation directory")
@click.option(
    "--socket",
    default="/tmp/ope-governance-bus.sock",
    help="Bus socket path",
)
@click.option(
    "--memory-md",
    default=None,
    help="Path to MEMORY.md for axis vocabulary",
)
def reindex(db: str, docs_dir: str, socket: str, memory_md: str | None):
    """Rebuild the doc_index table from docs/ folder."""
    from src.pipeline.doc_indexer import reindex_docs

    click.echo(f"[OPE Docs] Reindexing {docs_dir} -> {db}")

    try:
        result = reindex_docs(
            db_path=db,
            docs_dir=docs_dir,
            socket_path=socket,
            memory_md_path=memory_md,
        )
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"[OPE Docs] Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(
        f"[OPE Docs] Indexed {result['total_files']} files, "
        f"{result['indexed_rows']} rows, "
        f"{result['unclassified_files']} unclassified"
    )
