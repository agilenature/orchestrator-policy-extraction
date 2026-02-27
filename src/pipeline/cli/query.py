"""Unified query CLI -- single command dispatching to docs, sessions, code.

Provides the ``query`` command that searches across the three OPE backends
(doc_index axis retrieval, episode BM25/ILIKE search, code ripgrep/grep)
via a ``--source`` flag.

The ``--project`` flag resolves a project from ``data/projects.json``:
- For **doc queries**: uses DuckDB ``ATTACH`` (READ_ONLY) to query a remote
  project's ``doc_index`` table.  Direct axis matching only (no axis_edges
  expansion for cross-project queries).
- For **session queries**: filters ope.db episodes to sessions belonging to
  the specified project (using session IDs from the project's
  ``sessions_location`` directory).
- For **code queries**: reports "not available for remote projects" (code
  search is local-only).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import click
import duckdb

logger = logging.getLogger(__name__)


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

        python -m src.pipeline.cli query --project modernizing-tool --source docs "causal chain"
    """
    click.echo(f"[OPE Query] Searching {source}: {query_text!r}")

    results: list[dict[str, Any]] = []

    if project:
        # Cross-project query path
        project_config = _resolve_project(project)
        if project_config is None:
            click.echo(
                f"[OPE Query] Project {project!r} not found in registry"
            )
            return

        is_local = project_config.get("id") in (
            "orchestrator-policy-extraction", "ope",
        )

        if source in ("docs", "all"):
            if is_local:
                results.extend(_query_docs_source(query_text, db, top_n))
            else:
                db_path = project_config.get("db_path")
                if db_path:
                    remote_results = _query_docs_cross_project(
                        query_text, db_path, top_n
                    )
                    results.extend(remote_results)
                    if not remote_results:
                        click.echo(
                            f"[OPE Query] No doc results from project "
                            f"'{project}'."
                        )
                else:
                    click.echo(
                        f"[OPE Query] Project '{project}' has no "
                        f"doc_index database."
                    )

        if source in ("sessions", "all"):
            session_ids = _get_project_session_ids(project_config)
            results.extend(
                _query_sessions_source(
                    query_text, db, top_n, session_ids=session_ids,
                )
            )

        if source in ("code", "all"):
            if is_local:
                results.extend(_query_code_source(query_text, top_n))
            else:
                click.echo(
                    f"[OPE Query] Code search not available for "
                    f"remote projects."
                )
    else:
        # Local query path (existing behavior)
        if source in ("docs", "all"):
            results.extend(_query_docs_source(query_text, db, top_n))

        if source in ("sessions", "all"):
            results.extend(_query_sessions_source(query_text, db, top_n))

        if source in ("code", "all"):
            results.extend(_query_code_source(query_text, top_n))

    _print_results(results)


# ---------------------------------------------------------------------------
# Cross-project resolution helpers
# ---------------------------------------------------------------------------


def _resolve_project(
    project_id: str,
    registry_path: str = "data/projects.json",
) -> dict | None:
    """Look up project config from registry.

    Returns the project dict or ``None`` if not found.
    """
    reg = Path(registry_path)
    if not reg.exists():
        click.echo(
            f"[OPE Query] Warning: {registry_path} not found"
        )
        return None

    try:
        data = json.loads(reg.read_text())
        for p in data.get("projects", []):
            if p.get("id") == project_id:
                return p
    except Exception as exc:
        click.echo(f"[OPE Query] Warning: could not read {registry_path}: {exc}")
    return None


def _get_project_session_ids(project: dict) -> list[str] | None:
    """Get session IDs for a project from its sessions_location directory.

    Returns a list of session IDs (JSONL filenames without extension),
    or ``None`` if ``sessions_location`` is missing or the directory
    does not exist.
    """
    data_status = project.get("data_status", {})
    sessions_loc = data_status.get("sessions_location")
    if not sessions_loc:
        return None

    sessions_dir = Path(sessions_loc).expanduser()
    if not sessions_dir.is_dir():
        return None

    jsonl_files = list(sessions_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    return [f.stem for f in jsonl_files]


def _query_docs_cross_project(
    query: str,
    remote_db_path: str,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Query doc_index on a remote project's DuckDB via ATTACH (READ_ONLY).

    Uses direct axis matching only (no axis_edges expansion -- the remote
    DB may not have an ``axis_edges`` table).

    Returns results in the same format as ``query_docs()`` with
    ``source='docs'``.  Returns ``[]`` on any error (fail-open).
    """
    from src.pipeline.doc_query import _score_axis_match, _tokenize

    resolved_path = Path(remote_db_path).expanduser()
    if not resolved_path.exists():
        return []

    conn = None
    try:
        conn = duckdb.connect(":memory:")
        conn.execute(
            f"ATTACH '{resolved_path}' AS remote (READ_ONLY)"
        )

        # Check if remote has doc_index
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'remote.main' "
            "OR (table_catalog = 'remote' AND table_name = 'doc_index')"
        ).fetchall()

        # Also try a direct check
        has_doc_index = False
        try:
            conn.execute("SELECT 1 FROM remote.doc_index LIMIT 0")
            has_doc_index = True
        except Exception:
            pass

        if not has_doc_index:
            conn.execute("DETACH remote")
            conn.close()
            return []

        # Tokenize query
        query_tokens = _tokenize(query)
        if not query_tokens:
            conn.execute("DETACH remote")
            conn.close()
            return []

        # Load axes from remote doc_index
        axes_rows = conn.execute(
            "SELECT DISTINCT ccd_axis FROM remote.doc_index "
            "WHERE association_type != 'unclassified' "
            "AND ccd_axis != 'always-show'"
        ).fetchall()
        known_axes = [r[0] for r in axes_rows if r[0]]

        matched_axes = [
            axis for axis in known_axes
            if _score_axis_match(query_tokens, axis) >= 1
        ]

        if not matched_axes:
            conn.execute("DETACH remote")
            conn.close()
            return []

        # Query remote doc_index for matching docs (direct matches only)
        placeholders = ",".join(["?"] * len(matched_axes))
        rows = conn.execute(
            f"SELECT doc_path, ccd_axis, description_cache, "
            f"extracted_confidence "
            f"FROM remote.doc_index "
            f"WHERE ccd_axis IN ({placeholders}) "
            f"AND association_type != 'unclassified'",
            list(matched_axes),
        ).fetchall()

        # Sort by confidence DESC
        rows.sort(key=lambda r: -r[3])

        # Deduplicate by doc_path, return top_n
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for doc_path, ccd_axis, description_cache, _conf in rows:
            if doc_path in seen:
                continue
            seen.add(doc_path)
            result.append({
                "doc_path": doc_path,
                "ccd_axis": ccd_axis,
                "description_cache": description_cache or "",
                "match_reason": "direct",
                "source": "docs",
            })
            if len(result) >= top_n:
                break

        conn.execute("DETACH remote")
        conn.close()
        return result

    except Exception:
        logger.debug("_query_docs_cross_project failed", exc_info=True)
        if conn is not None:
            try:
                conn.execute("DETACH remote")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        return []


# ---------------------------------------------------------------------------
# Internal dispatch helpers
# ---------------------------------------------------------------------------


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
    query_text: str,
    db_path: str,
    top_n: int,
    session_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch to query_sessions (already includes source='sessions')."""
    from src.pipeline.session_query import query_sessions

    return query_sessions(
        query=query_text, db_path=db_path, top_n=top_n,
        session_ids=session_ids,
    )


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
