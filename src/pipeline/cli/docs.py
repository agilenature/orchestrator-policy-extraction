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
@click.argument("query_text")
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option("--top", "top_n", default=3, help="Max docs to return")
def query(query_text: str, db: str, top_n: int):
    """Find docs relevant to QUERY_TEXT using the axis graph.

    Derives CCD axis from query tokens, expands via axis_edges (1-hop),
    returns matching docs from doc_index.  No running bus required.

    Example:
        python -m src.pipeline.cli docs query "raven cost function absent"
    """
    from src.pipeline.doc_query import query_docs

    results = query_docs(query=query_text, db_path=db, top_n=top_n)

    if not results:
        click.echo(f"[OPE Docs] No axis match for: {query_text!r}")
        return

    click.echo(f"[OPE Docs] Query: {query_text!r}")
    click.echo(f"[OPE Docs] {len(results)} relevant doc(s):")
    for doc in results:
        path = doc["doc_path"]
        axis = doc["ccd_axis"]
        reason = doc["match_reason"]
        desc = doc["description_cache"][:80] if doc["description_cache"] else ""
        click.echo(f"[OPE]   - {path} (axis: {axis}, {reason})")
        if desc:
            click.echo(f"[OPE]     {desc}")


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
