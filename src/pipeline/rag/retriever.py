"""Hybrid BM25 + embedding retriever with Reciprocal Rank Fusion.

Combines DuckDB FTS (BM25) and VSS (cosine similarity) search results
using Reciprocal Rank Fusion for robust episode retrieval.

BM25 catches exact term matches (file paths, mode names, commands).
Embedding similarity captures semantic meaning. RRF fuses both ranked
lists with a parameter-free formula: score = sum(1/(rrf_k + rank)).

Exports:
    HybridRetriever: Hybrid BM25 + embedding search with RRF fusion
"""

from __future__ import annotations

import duckdb
from loguru import logger


class HybridRetriever:
    """Retrieve similar episodes using BM25 + embedding hybrid search.

    Combines DuckDB FTS (BM25 text matching) with DuckDB VSS (cosine
    similarity on 384-dim embeddings) via Reciprocal Rank Fusion.

    Args:
        conn: DuckDB connection with episode_search_text and
              episode_embeddings tables populated.
        top_k: Number of final results to return (default 5).
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection, top_k: int = 5) -> None:
        self._conn = conn
        self._top_k = top_k

    def retrieve(
        self,
        query_text: str,
        query_embedding: list[float],
        exclude_episode_id: str | None = None,
    ) -> list[dict]:
        """Retrieve top-k similar episodes using hybrid BM25 + cosine fusion.

        Runs BM25 and embedding searches in parallel (over-fetching top_k*2
        from each), then fuses via RRF to produce final ranked list.

        Args:
            query_text: Text query for BM25 search.
            query_embedding: 384-dim embedding for cosine similarity search.
            exclude_episode_id: Episode ID to exclude (for leave-one-out).

        Returns:
            List of dicts with 'episode_id' and 'rrf_score' keys,
            sorted by score descending, limited to top_k.
        """
        bm25_results = self._bm25_search(query_text, exclude_episode_id)
        embedding_results = self._embedding_search(query_embedding, exclude_episode_id)

        logger.debug(
            "Retrieval: {} BM25 results, {} embedding results",
            len(bm25_results),
            len(embedding_results),
        )

        return self._rrf_fuse(bm25_results, embedding_results, k=self._top_k)

    def _bm25_search(
        self, query: str, exclude_id: str | None
    ) -> list[tuple[str, float]]:
        """Search episodes using BM25 text matching via DuckDB FTS.

        Uses parameterized queries for safety. The exclude_id filter uses
        a WHERE clause with IS NULL OR != pattern to avoid SQL injection.

        Args:
            query: Text query for BM25 matching.
            exclude_id: Episode ID to exclude from results.

        Returns:
            List of (episode_id, score) tuples sorted by score descending.
        """
        rows = self._conn.execute(
            """
            SELECT sq.episode_id, sq.score
            FROM (
                SELECT *, fts_main_episode_search_text.match_bm25(
                    episode_id, ?
                ) AS score
                FROM episode_search_text
            ) sq
            WHERE sq.score IS NOT NULL
              AND (? IS NULL OR sq.episode_id != ?)
            ORDER BY sq.score DESC
            LIMIT ?
            """,
            [query, exclude_id, exclude_id, self._top_k * 2],
        ).fetchall()
        return rows

    def _embedding_search(
        self, embedding: list[float], exclude_id: str | None
    ) -> list[tuple[str, float]]:
        """Search episodes using cosine similarity via DuckDB VSS.

        Args:
            embedding: 384-dim query embedding.
            exclude_id: Episode ID to exclude from results.

        Returns:
            List of (episode_id, similarity) tuples sorted by similarity
            descending.
        """
        rows = self._conn.execute(
            """
            SELECT episode_id,
                   array_cosine_similarity(embedding, ?::FLOAT[384]) AS sim
            FROM episode_embeddings
            WHERE embedding IS NOT NULL
              AND (? IS NULL OR episode_id != ?)
            ORDER BY sim DESC
            LIMIT ?
            """,
            [embedding, exclude_id, exclude_id, self._top_k * 2],
        ).fetchall()
        return rows

    @staticmethod
    def _rrf_fuse(
        bm25_results: list[tuple[str, float]],
        emb_results: list[tuple[str, float]],
        k: int,
        rrf_k: int = 60,
    ) -> list[dict]:
        """Fuse two ranked lists using Reciprocal Rank Fusion.

        RRF score = sum(1/(rrf_k + rank)) for each list an episode appears
        in. Episodes appearing in both lists get higher combined scores.
        rrf_k=60 is the standard constant from the original RRF paper.

        Args:
            bm25_results: Ranked (episode_id, score) from BM25 search.
            emb_results: Ranked (episode_id, similarity) from embedding search.
            k: Maximum number of results to return.
            rrf_k: RRF constant (default 60).

        Returns:
            List of dicts with 'episode_id' and 'rrf_score' keys,
            sorted by score descending, limited to k.
        """
        scores: dict[str, float] = {}
        for rank, (eid, _) in enumerate(bm25_results):
            scores[eid] = scores.get(eid, 0) + 1.0 / (rrf_k + rank)
        for rank, (eid, _) in enumerate(emb_results):
            scores[eid] = scores.get(eid, 0) + 1.0 / (rrf_k + rank)

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:k]
        return [{"episode_id": eid, "rrf_score": scores[eid]} for eid in sorted_ids]
