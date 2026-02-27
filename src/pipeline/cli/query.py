"""Unified query CLI -- single command dispatching to docs, sessions, code.

Provides the ``query`` command that searches across the three OPE backends
(doc_index axis retrieval, episode BM25/ILIKE search, code ripgrep/grep)
via a ``--source`` flag.

The ``--project`` flag resolves a project's ``db_path`` from
``data/projects.json`` for cross-project doc queries.  Full cross-project
ATTACH logic is deferred to Plan 03.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


@click.command(name="query")
@click.argument("query_text")
@click.option(
    "--source",
    type=click.Choice(["docs", "sessions", "code", "all"]),
    default="all",
    help="Source to search: docs, sessions, code, or all",
)
@click.option(
    "--project",
    default=None,
    help="Project ID from projects.json (cross-project query)",
)
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option(
    "--top", "top_n", default=5, type=int, help="Max results per source"
)
def query_cmd(
    query_text: str,
    source: str,
    project: str | None,
    db: str,
    top_n: int,
):
    """Search OPE data across docs, sessions, and code.

    Dispatches to the three query backends based on --source.  Use --project
    to search a different project's database (requires db_path in projects.json).

    Examples:

        python -m src.pipeline.cli query "raven cost function"

        python -m src.pipeline.cli query --source docs "raven cost function"

        python -m src.pipeline.cli query --source sessions "segmenter fix"

        python -m src.pipeline.cli query --source code "episode populator"
    """
    click.echo(f"[OPE Query] Searching {source}: {query_text!r}")

    # Resolve db_path from project registry if --project is provided
    resolved_db = _resolve_project_db(project, db)

    results: list[dict[str, Any]] = []

    if source in ("docs", "all"):
        results.extend(_query_docs_source(query_text, resolved_db, top_n))

    if source in ("sessions", "all"):
        results.extend(_query_sessions_source(query_text, resolved_db, top_n))

    if source in ("code", "all"):
        results.extend(_query_code_source(query_text, top_n))

    _print_results(results)


# ---------------------------------------------------------------------------
# Internal dispatch helpers
# ---------------------------------------------------------------------------


def _resolve_project_db(project: str | None, default_db: str) -> str:
    """Resolve db_path from projects.json for --project flag.

    Returns *default_db* if no project specified or project not found.
    """
    if not project:
        return default_db

    # Local project aliases -- no lookup needed
    if project in ("orchestrator-policy-extraction", "ope"):
        return default_db

    projects_path = Path("data/projects.json")
    if not projects_path.exists():
        click.echo(
            f"[OPE Query] Warning: data/projects.json not found, "
            f"using default DB for --project {project!r}"
        )
        return default_db

    try:
        data = json.loads(projects_path.read_text())
        for p in data.get("projects", []):
            if p.get("id") == project:
                db_path = p.get("db_path")
                if db_path:
                    click.echo(
                        f"[OPE Query] Using project {project!r} DB: {db_path}"
                    )
                    return db_path
                click.echo(
                    f"[OPE Query] Project {project!r} has no db_path, "
                    f"using default DB"
                )
                return default_db
        click.echo(f"[OPE Query] Project {project!r} not found in registry")
    except Exception as exc:
        click.echo(f"[OPE Query] Warning: could not read projects.json: {exc}")

    return default_db


def _query_docs_source(
    query_text: str, db_path: str, top_n: int
) -> list[dict[str, Any]]:
    """Dispatch to query_docs and tag results with source='docs'."""
    from src.pipeline.doc_query import query_docs

    raw = query_docs(query=query_text, db_path=db_path, top_n=top_n)
    # query_docs returns dicts without a 'source' key -- add it
    for r in raw:
        r["source"] = "docs"
    return raw


def _query_sessions_source(
    query_text: str, db_path: str, top_n: int
) -> list[dict[str, Any]]:
    """Dispatch to query_sessions (already includes source='sessions')."""
    from src.pipeline.session_query import query_sessions

    return query_sessions(query=query_text, db_path=db_path, top_n=top_n)


def _query_code_source(
    query_text: str, top_n: int
) -> list[dict[str, Any]]:
    """Dispatch to query_code (already includes source='code')."""
    from src.pipeline.code_query import query_code

    return query_code(query=query_text, top_n=top_n)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _print_results(results: list[dict[str, Any]]) -> None:
    """Format and print query results, labeled by source type."""
    if not results:
        click.echo("[OPE Query] No results found.")
        return

    click.echo(f"[OPE Query] {len(results)} result(s):")

    for r in results:
        source = r.get("source", "unknown")

        if source == "docs":
            doc_path = r.get("doc_path", "")
            axis = r.get("ccd_axis", "")
            reason = r.get("match_reason", "")
            desc = (r.get("description_cache", "") or "")[:80]
            click.echo(f"[OPE]   [docs] {doc_path} (axis: {axis}, {reason})")
            if desc:
                click.echo(f"[OPE]     {desc}")

        elif source == "sessions":
            eid = r.get("episode_id", "")
            sid = r.get("session_id", "")
            reason = r.get("match_reason", "")
            preview = (r.get("content_preview", "") or "")[:120]
            click.echo(
                f"[OPE]   [sessions] episode={eid} session={sid} ({reason})"
            )
            if preview:
                click.echo(f"[OPE]     {preview}")

        elif source == "code":
            fpath = r.get("file_path", "")
            lineno = r.get("line_number", "")
            reason = r.get("match_reason", "")
            preview = (r.get("content_preview", "") or "")[:120]
            click.echo(f"[OPE]   [code] {fpath}:{lineno} ({reason})")
            if preview:
                click.echo(f"[OPE]     {preview}")

        else:
            click.echo(f"[OPE]   [{source}] {r}")
