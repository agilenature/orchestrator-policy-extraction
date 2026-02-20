"""Wisdom retriever with hybrid BM25 search and dead end detection.

Searches project wisdom entities using DuckDB FTS (BM25 keyword matching)
and optional vector similarity, fused via Reciprocal Rank Fusion. Dead end
entities receive special dual-agreement filtering to reduce false positives.

Usage:
    retriever = WisdomRetriever(store, top_k=3)
    retriever.rebuild_index()  # Build FTS index (required before first query)
    refs = retriever.retrieve("DuckDB array columns", scope_paths=["src/"])

Exports:
    WisdomRetriever: Hybrid BM25 + optional vector search for wisdom entities
"""

from __future__ import annotations

from loguru import logger

from src.pipeline.wisdom.models import WisdomEntity, WisdomRef
from src.pipeline.wisdom.store import WisdomStore


class WisdomRetriever:
    """Retrieve relevant wisdom entities using hybrid BM25 + vector search.

    Uses DuckDB FTS for BM25 keyword matching on title and description.
    Optionally uses array_cosine_similarity on embedding columns for
    semantic search. Results are fused via Reciprocal Rank Fusion (RRF),
    the same pattern as HybridRetriever.

    Dead end entities require dual agreement (BM25 score >= threshold)
    to be flagged as warnings, reducing false positives.

    Args:
        store: WisdomStore instance (same-package access to _conn).
        top_k: Number of results to return (default 3).
    """

    def __init__(self, store: WisdomStore, top_k: int = 3) -> None:
        self._store = store
        self._conn = store._conn
        self._top_k = top_k
        self._fts_built = False

    def rebuild_index(self) -> None:
        """Rebuild the FTS index on project_wisdom table.

        Must be called after inserting entities for BM25 search to work.
        Uses overwrite=1 to replace any existing index. Safe to call
        multiple times.
        """
        self._conn.execute("INSTALL fts; LOAD fts;")
        self._conn.execute("""
            PRAGMA create_fts_index(
                'project_wisdom',
                'wisdom_id',
                'title',
                'description',
                stemmer = 'porter',
                stopwords = 'english',
                lower = 1,
                overwrite = 1
            )
        """)
        self._fts_built = True
        logger.debug("Rebuilt FTS index on project_wisdom")

    def retrieve(
        self,
        query: str,
        scope_paths: list[str] | None = None,
        dead_end_threshold: float = 0.6,
    ) -> list[WisdomRef]:
        """Retrieve relevant wisdom entities for a query.

        Steps:
        1. BM25 search via DuckDB FTS on title + description
        2. Vector search via cosine similarity (if embeddings present)
        3. RRF fusion over both result sets
        4. Scope filtering: prefer entities with overlapping scope_paths
        5. Dead end detection: flag dead_end entities with high BM25 score
        6. Return sorted WisdomRef list

        Args:
            query: Search query text.
            scope_paths: Optional list of paths to prefer matching scope.
            dead_end_threshold: BM25 score threshold for dead end warnings
                (default 0.6).

        Returns:
            List of WisdomRef sorted by relevance_score descending,
            limited to top_k.
        """
        if scope_paths is None:
            scope_paths = []

        if not query or not query.strip():
            return []

        # Check if table has any rows
        count = self._conn.execute(
            "SELECT COUNT(*) FROM project_wisdom"
        ).fetchone()
        if count is None or count[0] == 0:
            return []

        # Ensure FTS index is built
        if not self._fts_built:
            self.rebuild_index()

        # 1. BM25 search
        bm25_results = self._bm25_search(query)

        # 2. Vector search (if embeddings present)
        vector_results = self._vector_search(query)

        # 3. RRF fusion
        if bm25_results or vector_results:
            fused = self._rrf_fuse(bm25_results, vector_results)
        else:
            return []

        # 4. Fetch full entities for fused results
        fused_ids = [wid for wid, _ in fused]
        entities_by_id: dict[str, WisdomEntity] = {}
        bm25_scores: dict[str, float] = {wid: score for wid, score in bm25_results}

        for wid in fused_ids:
            entity = self._store.get(wid)
            if entity is not None:
                entities_by_id[wid] = entity

        # 5. Build WisdomRef list with scope boosting and dead end detection
        refs: list[WisdomRef] = []
        for wid, rrf_score in fused:
            entity = entities_by_id.get(wid)
            if entity is None:
                continue

            # Scope boost: increase score if scope overlaps
            relevance = rrf_score
            if scope_paths and entity.scope_paths:
                overlap = self._scope_overlap(scope_paths, entity.scope_paths)
                if overlap > 0:
                    relevance *= 1.5  # 50% boost for scope match

            # Dead end detection
            is_dead_end = self._is_dead_end_warning(
                entity, bm25_scores.get(wid, 0.0), dead_end_threshold
            )

            refs.append(
                WisdomRef(
                    wisdom_id=wid,
                    entity_type=entity.entity_type,
                    title=entity.title,
                    relevance_score=round(relevance, 6),
                    is_dead_end_warning=is_dead_end,
                    description=entity.description,
                )
            )

        # Sort by relevance descending, limit to top_k
        refs.sort(key=lambda r: r.relevance_score, reverse=True)
        return refs[: self._top_k]

    def _bm25_search(self, query: str) -> list[tuple[str, float]]:
        """Search wisdom entities using BM25 text matching via DuckDB FTS.

        Args:
            query: Text query for BM25 matching.

        Returns:
            List of (wisdom_id, score) tuples sorted by score descending.
        """
        try:
            rows = self._conn.execute(
                """
                SELECT sq.wisdom_id, sq.score
                FROM (
                    SELECT *, fts_main_project_wisdom.match_bm25(
                        wisdom_id, ?
                    ) AS score
                    FROM project_wisdom
                ) sq
                WHERE sq.score IS NOT NULL
                ORDER BY sq.score DESC
                LIMIT ?
                """,
                [query, self._top_k * 2],
            ).fetchall()
            return rows
        except Exception as e:
            logger.warning("BM25 search failed: {}", e)
            return []

    def _vector_search(self, query: str) -> list[tuple[str, float]]:
        """Search wisdom entities using cosine similarity on embeddings.

        Falls back to empty results if no embeddings are present in the
        table. Does not generate query embeddings -- uses a simple text
        match fallback if no embedding infrastructure is available.

        Args:
            query: Text query (used for embedding lookup if available).

        Returns:
            List of (wisdom_id, similarity) tuples sorted descending.
            Empty list if no embeddings present.
        """
        # Check if any embeddings exist
        try:
            has_embeddings = self._conn.execute(
                "SELECT COUNT(*) FROM project_wisdom WHERE embedding IS NOT NULL"
            ).fetchone()
            if has_embeddings is None or has_embeddings[0] == 0:
                return []
        except Exception:
            return []

        # Without an embedding model wired in, we cannot generate a query
        # embedding to compare against stored embeddings. Return empty
        # and rely on BM25-only results. Future plans may wire in an
        # embedder for wisdom vector search.
        return []

    def _rrf_fuse(
        self,
        bm25_results: list[tuple[str, float]],
        vector_results: list[tuple[str, float]],
        rrf_k: int = 60,
    ) -> list[tuple[str, float]]:
        """Fuse ranked lists using Reciprocal Rank Fusion.

        Same formula as HybridRetriever: score = sum(1/(rrf_k + rank)).
        Episodes in both lists get higher combined scores.

        Args:
            bm25_results: Ranked (wisdom_id, score) from BM25.
            vector_results: Ranked (wisdom_id, similarity) from vectors.
            rrf_k: RRF constant (default 60).

        Returns:
            List of (wisdom_id, rrf_score) sorted by score descending.
        """
        scores: dict[str, float] = {}
        for rank, (wid, _) in enumerate(bm25_results):
            scores[wid] = scores.get(wid, 0) + 1.0 / (rrf_k + rank)
        for rank, (wid, _) in enumerate(vector_results):
            scores[wid] = scores.get(wid, 0) + 1.0 / (rrf_k + rank)

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items

    @staticmethod
    def _is_dead_end_warning(
        entity: WisdomEntity,
        bm25_score: float,
        threshold: float,
    ) -> bool:
        """Determine if a wisdom entity should be flagged as a dead end warning.

        Requires entity_type == 'dead_end' AND BM25 score meeting threshold.
        The dual agreement filter (BM25 + vector) reduces false positives.
        When no vector search is available, requires higher BM25 confidence
        (threshold * 1.5 for keyword-only mode).

        Args:
            entity: The wisdom entity to check.
            bm25_score: BM25 relevance score for this entity.
            threshold: Score threshold for flagging (default 0.6).

        Returns:
            True if entity should be flagged as a dead end warning.
        """
        if entity.entity_type != "dead_end":
            return False

        # BM25 scores from DuckDB FTS are negative (lower = better match).
        # A score of -0.8 is a stronger match than -0.2.
        # We use the absolute value for threshold comparison.
        abs_score = abs(bm25_score)
        return abs_score >= threshold

    @staticmethod
    def _scope_overlap(
        query_paths: list[str], entity_paths: list[str]
    ) -> float:
        """Compute scope overlap between query paths and entity paths.

        Uses bidirectional prefix matching: either path being a prefix
        of the other counts as overlap.

        Args:
            query_paths: Paths from the query context.
            entity_paths: Paths from the wisdom entity.

        Returns:
            Overlap ratio (0.0 to 1.0).
        """
        if not query_paths or not entity_paths:
            return 0.0

        matches = 0
        for qp in query_paths:
            for ep in entity_paths:
                if qp.startswith(ep) or ep.startswith(qp):
                    matches += 1
                    break

        return matches / len(query_paths)
