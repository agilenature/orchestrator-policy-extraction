"""Query-time axis retrieval using the OPE axis graph.

Translates a natural-language query into CCD axis matches, expands via
axis_edges (1-hop neighborhood), then retrieves relevant docs from doc_index.

This is the query-time complement to GovernorDaemon._query_relevant_docs()
(which delivers a globally-ranked session-start briefing).  This function
delivers axis-targeted retrieval at the moment of the question — the
raven-cost-function-absent fix at query time rather than session-start time.

The axis graph (axis_edges + memory_candidates) provides selection pressure
the AI lacks: given a query, derive its governing CCD axis, walk the graph
for related axes, surface the docs indexed under those axes.

No running bus required — callable standalone from any context.
"""

from __future__ import annotations

import re
from typing import Any

import duckdb

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUERY_STOPWORDS = frozenset(
    {
        # Standard English
        "not", "vs", "as", "to", "the", "a", "an", "in", "of", "for", "is",
        "and", "or", "but", "if", "by", "on", "at", "up", "out", "be",
        "been", "being", "have", "has", "had", "are", "was", "were",
        "i", "you", "he", "she", "we", "they", "it",
        # Question words
        "how", "does", "do", "what", "where", "when", "why", "which", "who",
        # Common verbs
        "work", "works", "use", "uses", "get", "set", "can", "will", "would",
        "should", "could", "might", "make", "made", "show", "give", "tell",
        "explain", "describe", "help", "run", "runs", "find", "look",
        # Pronouns / determiners
        "my", "me", "this", "that", "these", "those",
        # Prepositions
        "from", "into", "about", "with", "then", "than", "more", "also",
    }
)

# Minimum tokens an axis must contribute to be considered "meaningful"
_MIN_AXIS_TOKENS = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens, filtering QUERY_STOPWORDS.

    Splits on whitespace and non-alpha characters (hyphens become
    separators, matching how axis names split on ``-``).
    """
    raw = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in raw if t not in QUERY_STOPWORDS and len(t) > 2}


def _axis_non_stop_tokens(axis: str) -> list[str]:
    """Return non-stopword tokens of an axis name (split on '-')."""
    return [t for t in axis.split("-") if t.lower() not in QUERY_STOPWORDS and len(t) > 2]


def _score_axis_match(query_tokens: set[str], axis: str) -> int:
    """Count how many axis tokens appear in *query_tokens*.

    An axis with fewer than :data:`_MIN_AXIS_TOKENS` non-stopword parts
    is too ambiguous for reliable matching — returns 0.
    """
    tokens = _axis_non_stop_tokens(axis)
    if len(tokens) < _MIN_AXIS_TOKENS:
        return 0
    return sum(1 for t in tokens if t.lower() in query_tokens)


def _load_doc_axes(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Load distinct classified CCD axes from doc_index.

    Excludes ``'unclassified'`` and ``'always-show'`` (always-show is a
    session-start concern, not a query-time match target).
    Fails gracefully on missing table or any error.
    """
    try:
        rows = conn.execute(
            "SELECT DISTINCT ccd_axis FROM doc_index "
            "WHERE association_type != 'unclassified' "
            "AND ccd_axis != 'always-show'"
        ).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def _expand_via_axis_edges(
    matched_axes: list[str],
    conn: duckdb.DuckDBPyConnection,
) -> set[str]:
    """Walk axis_edges for 1-hop neighbors of *matched_axes*.

    Includes edges with status 'active' or 'candidate' (candidate edges are
    generated but unvalidated; included for breadth at query time).
    Fails gracefully on missing table or any error — returns empty set.
    """
    if not matched_axes:
        return set()
    try:
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'axis_edges'"
        ).fetchall()
        if not tables:
            return set()

        placeholders = ",".join(["?"] * len(matched_axes))
        rows = conn.execute(
            f"SELECT axis_a, axis_b FROM axis_edges "
            f"WHERE (axis_a IN ({placeholders}) OR axis_b IN ({placeholders})) "
            f"AND status IN ('active', 'candidate')",
            matched_axes + matched_axes,
        ).fetchall()

        neighbors: set[str] = set()
        for axis_a, axis_b in rows:
            neighbors.add(axis_a)
            neighbors.add(axis_b)
        return neighbors
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_docs(
    query: str,
    db_path: str = "data/ope.db",
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Find docs relevant to *query* using the OPE axis graph.

    Algorithm:
    1. Tokenize query; match tokens against known CCD axis names in doc_index.
    2. Expand matched axes via axis_edges (1-hop neighborhood).
    3. Query doc_index for docs associated with matched + neighbor axes.
    4. Return top *top_n* docs, deduplicated by doc_path, direct matches first.

    Args:
        query: Natural-language question or topic.
        db_path: DuckDB path containing doc_index and axis_edges.
        top_n: Maximum docs to return.

    Returns:
        List of ``{doc_path, ccd_axis, description_cache, match_reason}`` dicts.
        ``match_reason`` is ``'direct'`` (query tokens matched the axis) or
        ``'neighbor'`` (reached via axis_edges expansion).
        Returns ``[]`` on any error (fail-open).
    """
    if not query or not query.strip():
        return []

    try:
        conn = duckdb.connect(db_path)
        try:
            # Graceful pre-Phase-21 fallback
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'doc_index'"
            ).fetchall()
            if not tables:
                return []

            # Step 1: Match query tokens against known axes
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            known_axes = _load_doc_axes(conn)
            matched_axes = [
                axis
                for axis in known_axes
                if _score_axis_match(query_tokens, axis) >= 1
            ]

            if not matched_axes:
                return []

            # Step 2: Expand via axis_edges (1-hop)
            neighbor_axes = _expand_via_axis_edges(matched_axes, conn)
            all_axes = set(matched_axes) | neighbor_axes

            # Step 3: Query doc_index for all matching axes
            placeholders = ",".join(["?"] * len(all_axes))
            rows = conn.execute(
                f"SELECT doc_path, ccd_axis, description_cache, extracted_confidence "
                f"FROM doc_index "
                f"WHERE ccd_axis IN ({placeholders}) "
                f"AND association_type != 'unclassified'",
                list(all_axes),
            ).fetchall()

            # Sort: direct matches first, then by confidence DESC
            direct_set = set(matched_axes)
            rows.sort(key=lambda r: (0 if r[1] in direct_set else 1, -r[3]))

            # Step 4: Deduplicate by doc_path, return top_n
            seen: set[str] = set()
            result: list[dict[str, Any]] = []
            for doc_path, ccd_axis, description_cache, _conf in rows:
                if doc_path in seen:
                    continue
                seen.add(doc_path)
                result.append(
                    {
                        "doc_path": doc_path,
                        "ccd_axis": ccd_axis,
                        "description_cache": description_cache or "",
                        "match_reason": "direct" if ccd_axis in direct_set else "neighbor",
                    }
                )
                if len(result) >= top_n:
                    break

            return result
        finally:
            conn.close()
    except Exception:
        return []
