"""BM25 fulltext search over episode_search_text with ILIKE fallback.

Provides ``query_sessions()`` -- the session/episode query backend for the
unified discriminated query interface.  Searches the ``episode_search_text``
table using DuckDB's FTS extension (BM25 scoring) when an FTS index is
present, falling back to ``ILIKE`` substring matching when it is not.

Matched episode IDs are enriched with metadata from the ``episodes`` table
(session_id, mode, content preview).

Fail-open: any error returns ``[]``.

Exports:
    query_sessions: BM25/ILIKE episode search with metadata enrichment
"""

from __future__ import annotations

import logging
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_sessions(
    query: str,
    db_path: str = "data/ope.db",
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Search episodes by text, returning enriched result dicts.

    Algorithm:
    1. Connect to DuckDB at *db_path* (read-write -- FTS extension needs it).
    2. If an FTS index exists on ``episode_search_text``, run BM25 search.
    3. Otherwise fall back to ``ILIKE`` substring matching.
    4. Enrich matched episode_ids with metadata from the ``episodes`` table.

    Args:
        query: Natural-language search string.
        db_path: Path to the DuckDB database file.
        top_n: Maximum number of results to return.

    Returns:
        List of dicts with keys ``source``, ``episode_id``, ``session_id``,
        ``content_preview``, ``match_reason``.  Returns ``[]`` on any error
        (fail-open).
    """
    if not query or not query.strip():
        return []

    conn = None
    try:
        conn = duckdb.connect(db_path)

        # Check if episode_search_text table exists
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'episode_search_text'"
        ).fetchall()
        if not tables:
            return []

        # Try BM25 first; fall back to ILIKE if no FTS index exists.
        # FTS internal tables are not visible via duckdb_tables(), so we
        # attempt the BM25 query and catch the CatalogException that fires
        # when the index is absent.
        matches = _try_bm25_then_ilike(conn, query, top_n)

        if not matches:
            # Check if table is empty -- suggest indexing if so
            row_count = conn.execute(
                "SELECT COUNT(*) FROM episode_search_text"
            ).fetchone()[0]
            if row_count == 0:
                logger.warning(
                    "episode_search_text has 0 rows. "
                    "Run: python -m src.pipeline.cli train embed"
                )
            return []

        # Enrich with metadata from episodes table
        return _enrich_matches(conn, matches)

    except Exception:
        logger.debug("query_sessions failed", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _try_bm25_then_ilike(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    limit: int,
) -> list[tuple[str, float, str]]:
    """Attempt BM25 search; fall back to ILIKE if FTS index is absent.

    DuckDB's FTS internal tables are not exposed via ``duckdb_tables()`` or
    ``information_schema``, so the only reliable detection is to attempt the
    BM25 query and catch the ``CatalogException`` raised when the index does
    not exist.
    """
    try:
        conn.execute("LOAD fts;")
        return _bm25_search(conn, query, limit)
    except duckdb.CatalogException:
        return _ilike_search(conn, query, limit)


def _bm25_search(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    limit: int,
) -> list[tuple[str, float, str]]:
    """Run BM25 search via DuckDB FTS extension.

    Returns list of ``(episode_id, score, match_reason)`` tuples.
    """
    rows = conn.execute(
        """
        SELECT sq.episode_id, sq.score
        FROM (
            SELECT *, fts_main_episode_search_text.match_bm25(
                episode_id, ?
            ) AS score
            FROM episode_search_text
        ) sq
        WHERE sq.score IS NOT NULL
        ORDER BY sq.score DESC
        LIMIT ?
        """,
        [query, limit],
    ).fetchall()
    return [
        (eid, score, f"bm25 (score={score:.2f})")
        for eid, score in rows
    ]


def _ilike_search(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    limit: int,
) -> list[tuple[str, float, str]]:
    """Run ILIKE fallback search when no FTS index is available.

    Returns list of ``(episode_id, score, match_reason)`` tuples.
    """
    rows = conn.execute(
        """
        SELECT episode_id, 1.0 AS score
        FROM episode_search_text
        WHERE search_text ILIKE ?
        LIMIT ?
        """,
        [f"%{query}%", limit],
    ).fetchall()
    return [(eid, score, "ilike") for eid, score in rows]


def _enrich_matches(
    conn: duckdb.DuckDBPyConnection,
    matches: list[tuple[str, float, str]],
) -> list[dict[str, Any]]:
    """Enrich episode matches with metadata from the episodes table.

    Returns list of result dicts with keys: ``source``, ``episode_id``,
    ``session_id``, ``content_preview``, ``match_reason``.
    """
    episode_ids = [m[0] for m in matches]
    reason_map = {m[0]: m[2] for m in matches}
    order_map = {m[0]: i for i, m in enumerate(matches)}

    placeholders = ",".join(["?"] * len(episode_ids))

    # Check if episodes table exists for enrichment
    ep_tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'episodes'"
    ).fetchall()

    if ep_tables:
        rows = conn.execute(
            f"""
            SELECT e.episode_id, e.session_id, e.mode,
                   LEFT(est.search_text, 200) AS preview
            FROM episodes e
            JOIN episode_search_text est ON e.episode_id = est.episode_id
            WHERE e.episode_id IN ({placeholders})
            """,
            episode_ids,
        ).fetchall()
    else:
        # Fallback: no episodes table, use search_text only
        rows = conn.execute(
            f"""
            SELECT est.episode_id, NULL AS session_id, NULL AS mode,
                   LEFT(est.search_text, 200) AS preview
            FROM episode_search_text est
            WHERE est.episode_id IN ({placeholders})
            """,
            episode_ids,
        ).fetchall()

    # Build result dicts preserving original match order
    result_map: dict[str, dict[str, Any]] = {}
    for episode_id, session_id, mode, preview in rows:
        result_map[episode_id] = {
            "source": "sessions",
            "episode_id": episode_id,
            "session_id": session_id or "",
            "content_preview": (preview or "").strip(),
            "match_reason": reason_map.get(episode_id, "unknown"),
        }

    # Return in original match order
    results = []
    for eid in sorted(result_map, key=lambda x: order_map.get(x, 999)):
        results.append(result_map[eid])

    return results
