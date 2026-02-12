"""Hybrid BM25 + embedding retriever with Reciprocal Rank Fusion.

Combines DuckDB FTS (BM25) and VSS (cosine similarity) search results
using Reciprocal Rank Fusion for robust episode retrieval.

Exports:
    HybridRetriever: Hybrid BM25 + embedding search with RRF fusion
"""

from __future__ import annotations

import duckdb


class HybridRetriever:
    """Retrieve similar episodes using BM25 + embedding hybrid search."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, top_k: int = 5) -> None:
        raise NotImplementedError

    def retrieve(
        self,
        query_text: str,
        query_embedding: list[float],
        exclude_episode_id: str | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    def _bm25_search(
        self, query: str, exclude_id: str | None
    ) -> list[tuple[str, float]]:
        raise NotImplementedError

    def _embedding_search(
        self, embedding: list[float], exclude_id: str | None
    ) -> list[tuple[str, float]]:
        raise NotImplementedError

    @staticmethod
    def _rrf_fuse(
        bm25_results: list[tuple[str, float]],
        emb_results: list[tuple[str, float]],
        k: int,
        rrf_k: int = 60,
    ) -> list[dict]:
        raise NotImplementedError
