"""Genus oracle -- searches axis_edges for matching genera.

Given a problem description, tokenizes it and scores against axis_a values
in axis_edges WHERE relationship_text = 'genus_of'. Returns the best match
by token-overlap confidence. Adapted from doc_query.py's tokenization pattern.

Requires the server's DuckDB connection (closure-passed, not opened here).
Fails open: any error returns null genus.
"""
from __future__ import annotations

import json
import re
from typing import Any

import duckdb

# Reuse stopwords from doc_query.py pattern -- same set ensures consistent
# tokenization across all axis-matching features.
GENUS_STOPWORDS = frozenset({
    "not", "vs", "as", "to", "the", "a", "an", "in", "of", "for", "is",
    "and", "or", "but", "if", "by", "on", "at", "up", "out", "be",
    "been", "being", "have", "has", "had", "are", "was", "were",
    "i", "you", "he", "she", "we", "they", "it",
    "how", "does", "do", "what", "where", "when", "why", "which", "who",
    "work", "works", "use", "uses", "get", "set", "can", "will", "would",
    "should", "could", "might", "make", "made", "show", "give", "tell",
    "explain", "describe", "help", "run", "runs", "find", "look",
    "my", "me", "this", "that", "these", "those",
    "from", "into", "about", "with", "then", "than", "more", "also",
})

_EMPTY_RESPONSE: dict[str, Any] = {
    "genus": None,
    "instances": [],
    "valid": False,
    "confidence": 0.0,
}


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase non-stopword tokens (>2 chars)."""
    raw = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in raw if t not in GENUS_STOPWORDS and len(t) > 2}


class GenusOracleHandler:
    """Searches axis_edges for genus_of entries matching a problem description.

    Uses the server's existing DuckDB connection (closure-passed). Never opens
    a new connection -- avoids single-writer conflicts.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            rows = self._conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = ?",
                [table_name],
            ).fetchall()
            return len(rows) > 0
        except Exception:
            return False

    def query_genus(
        self, problem: str, repo: str | None = None,
    ) -> dict[str, Any]:
        """Find best-matching genus for a problem description.

        Algorithm:
        1. Check axis_edges table exists (fail-open if not)
        2. Fetch all genus_of edges (optionally scoped to repo via
           bus_sessions JOIN)
        3. Tokenize problem, score each genus by token overlap
        4. Return top-1 by confidence

        Args:
            problem: Natural-language problem description to match against.
            repo: Optional repo name for scoping via bus_sessions JOIN.

        Returns:
            Dict with {genus, instances, valid, confidence}. Null genus
            when no match found or on any error.
        """
        try:
            if not problem or not problem.strip():
                return dict(_EMPTY_RESPONSE)

            if not self._table_exists("axis_edges"):
                return dict(_EMPTY_RESPONSE)

            # Fetch genus_of edges, optionally repo-scoped
            rows = self._fetch_genus_edges(repo)
            if not rows:
                return dict(_EMPTY_RESPONSE)

            query_tokens = _tokenize(problem)
            if not query_tokens:
                return dict(_EMPTY_RESPONSE)

            # Score each genus by token overlap
            best_genus: str | None = None
            best_score: float = 0.0
            best_evidence: dict[str, Any] = {}

            for axis_a, evidence_raw in rows:
                genus_tokens = _tokenize(axis_a)
                if not genus_tokens:
                    continue

                # Primary score: genus name token overlap
                matched = sum(1 for t in genus_tokens if t in query_tokens)
                score = matched / len(genus_tokens)

                # Secondary: check if problem mentions any known instance
                evidence = self._parse_evidence(evidence_raw)
                instances = evidence.get("instances", [])
                for inst in instances:
                    inst_tokens = _tokenize(str(inst))
                    if inst_tokens:
                        inst_matched = sum(
                            1 for t in inst_tokens if t in query_tokens
                        )
                        inst_score = inst_matched / len(inst_tokens)
                        # Boost: instance match adds 0.2 * inst_score
                        score += 0.2 * inst_score

                if score > best_score:
                    best_score = score
                    best_genus = axis_a
                    best_evidence = evidence

            if best_genus is None or best_score == 0.0:
                return dict(_EMPTY_RESPONSE)

            instances = best_evidence.get("instances", [])
            return {
                "genus": best_genus,
                "instances": instances[:2],
                "valid": len(instances) >= 2,
                "confidence": round(min(best_score, 1.0), 2),
            }
        except Exception:
            return dict(_EMPTY_RESPONSE)

    def _fetch_genus_edges(
        self, repo: str | None,
    ) -> list[tuple[str, str]]:
        """Fetch genus_of edges, optionally scoped to repo.

        When repo is provided and bus_sessions exists, JOINs through
        bus_sessions to filter by repo. Otherwise returns all genus_of edges.
        """
        try:
            if repo and self._table_exists("bus_sessions"):
                rows = self._conn.execute(
                    "SELECT DISTINCT ae.axis_a, ae.evidence "
                    "FROM axis_edges ae "
                    "JOIN bus_sessions bs ON ae.created_session_id = bs.session_id "
                    "WHERE ae.relationship_text = 'genus_of' "
                    "AND ae.status IN ('candidate', 'active') "
                    "AND bs.repo = ?",
                    [repo],
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT DISTINCT axis_a, evidence FROM axis_edges "
                    "WHERE relationship_text = 'genus_of' "
                    "AND status IN ('candidate', 'active')"
                ).fetchall()
            return rows
        except Exception:
            return []

    @staticmethod
    def _parse_evidence(evidence_raw: Any) -> dict[str, Any]:
        """Parse evidence field (JSON string or dict)."""
        if isinstance(evidence_raw, dict):
            return evidence_raw
        if isinstance(evidence_raw, str):
            try:
                return json.loads(evidence_raw)
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}
