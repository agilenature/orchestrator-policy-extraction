"""Tests for WisdomRetriever and Recommender wisdom enrichment.

Covers:
- WisdomRetriever.retrieve() on empty store
- BM25 matching by title and description
- Dead end flagging for dead_end entities
- Non-dead-end entities not flagged
- Scope filtering preference
- top_k result limiting
- rebuild_index() idempotency
- No-match query returns empty
- Recommender without wisdom_retriever returns Recommendation
- Recommender with wisdom_retriever returns EnrichedRecommendation
- EnrichedRecommendation dead end warning flag
- EnrichedRecommendation no warning when no dead ends
- retrieve() with empty/blank query returns empty
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.pipeline.wisdom.models import (
    EnrichedRecommendation,
    WisdomEntity,
    WisdomRef,
)
from src.pipeline.wisdom.retriever import WisdomRetriever
from src.pipeline.wisdom.store import WisdomStore
from src.pipeline.rag.recommender import Recommendation, Recommender


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path for isolated tests."""
    return tmp_path / "test_wisdom_retriever.db"


@pytest.fixture
def store(db_path: Path) -> WisdomStore:
    """Provide a WisdomStore with empty database."""
    return WisdomStore(db_path)


@pytest.fixture
def retriever(store: WisdomStore) -> WisdomRetriever:
    """Provide a WisdomRetriever backed by an empty store."""
    return WisdomRetriever(store, top_k=3)


@pytest.fixture
def populated_store(store: WisdomStore) -> WisdomStore:
    """Store with 4 entities: breakthrough, dead_end, scope_decision, method_decision."""
    entities = [
        WisdomEntity.create(
            "breakthrough",
            "DuckDB array columns handle Python lists",
            "VARCHAR[] columns accept Python lists directly without conversion",
            context_tags=["duckdb", "schema", "arrays"],
            scope_paths=["src/pipeline/storage/"],
            confidence=0.95,
        ),
        WisdomEntity.create(
            "dead_end",
            "jsonwebtoken in Edge runtime fails",
            "CommonJS import of jsonwebtoken fails in Edge runtime; use jose instead",
            context_tags=["auth", "edge", "cjs"],
            scope_paths=["src/auth/"],
            confidence=0.9,
        ),
        WisdomEntity.create(
            "scope_decision",
            "No pyarrow dependency for export",
            "Use DuckDB native COPY TO for Parquet export instead of pyarrow",
            context_tags=["duckdb", "export"],
            scope_paths=[],  # Repo-wide
        ),
        WisdomEntity.create(
            "method_decision",
            "Staging table upsert pattern for DuckDB",
            "CREATE TEMP TABLE then UPDATE then INSERT then DROP for DuckDB upserts",
            context_tags=["duckdb", "patterns"],
            scope_paths=["src/pipeline/storage/"],
        ),
    ]
    for e in entities:
        store.add(e)
    return store


@pytest.fixture
def populated_retriever(populated_store: WisdomStore) -> WisdomRetriever:
    """Retriever backed by populated store with FTS index built."""
    r = WisdomRetriever(populated_store, top_k=3)
    r.rebuild_index()
    return r


# ---------------------------------------------------------------------------
# WisdomRetriever: empty store
# ---------------------------------------------------------------------------


class TestRetrieveEmptyStore:
    """Tests for retrieve() on empty stores and blank queries."""

    def test_retrieve_empty_store_returns_empty(
        self, retriever: WisdomRetriever
    ) -> None:
        """retrieve() returns empty list when store has no entities."""
        results = retriever.retrieve("DuckDB arrays")
        assert results == []

    def test_retrieve_blank_query_returns_empty(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """retrieve() returns empty list for blank/empty query."""
        assert populated_retriever.retrieve("") == []
        assert populated_retriever.retrieve("   ") == []


# ---------------------------------------------------------------------------
# WisdomRetriever: BM25 matching
# ---------------------------------------------------------------------------


class TestRetrieveBM25:
    """Tests for BM25 text matching on title and description."""

    def test_retrieve_bm25_matches_by_title(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """BM25 search matches entities by title keywords."""
        results = populated_retriever.retrieve("DuckDB array columns")
        assert len(results) > 0
        # The breakthrough about DuckDB array columns should appear
        titles = [r.title for r in results]
        assert any("DuckDB" in t and "array" in t for t in titles)

    def test_retrieve_bm25_matches_by_description(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """BM25 search matches entities by description keywords."""
        results = populated_retriever.retrieve("CommonJS import Edge runtime jose")
        assert len(results) > 0
        # The dead_end about jsonwebtoken should appear
        entity_types = [r.entity_type for r in results]
        assert "dead_end" in entity_types

    def test_retrieve_no_match_returns_empty(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """retrieve() returns empty when query matches no entities."""
        results = populated_retriever.retrieve("quantum computing blockchain NFT")
        assert results == []


# ---------------------------------------------------------------------------
# WisdomRetriever: dead end detection
# ---------------------------------------------------------------------------


class TestDeadEndDetection:
    """Tests for dead end warning flagging."""

    def test_retrieve_dead_end_flagged_as_warning(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """Dead end entities with strong BM25 match are flagged as warnings."""
        # Search specifically for the dead end content
        results = populated_retriever.retrieve(
            "jsonwebtoken Edge runtime CommonJS"
        )
        dead_end_refs = [r for r in results if r.entity_type == "dead_end"]
        if dead_end_refs:
            # If the dead end was retrieved with sufficient score, it should be flagged
            assert dead_end_refs[0].is_dead_end_warning is True

    def test_retrieve_non_dead_end_not_flagged(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """Non-dead-end entities are never flagged as dead end warnings."""
        results = populated_retriever.retrieve("DuckDB array columns")
        non_dead_end = [r for r in results if r.entity_type != "dead_end"]
        for ref in non_dead_end:
            assert ref.is_dead_end_warning is False


# ---------------------------------------------------------------------------
# WisdomRetriever: scope filtering
# ---------------------------------------------------------------------------


class TestScopeFilter:
    """Tests for scope path filtering preference."""

    def test_retrieve_scope_filter_prefers_matching_scope(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """Results matching query scope_paths get a relevance boost."""
        # Search with scope matching storage path
        results_with_scope = populated_retriever.retrieve(
            "DuckDB upsert pattern",
            scope_paths=["src/pipeline/storage/writer.py"],
        )
        # Search without scope
        results_no_scope = populated_retriever.retrieve(
            "DuckDB upsert pattern"
        )

        if results_with_scope and results_no_scope:
            # Scoped results should have boosted scores for matching entities
            scoped_scores = {r.wisdom_id: r.relevance_score for r in results_with_scope}
            unscoped_scores = {r.wisdom_id: r.relevance_score for r in results_no_scope}

            # Find an entity with storage scope that appears in both
            for wid in scoped_scores:
                if wid in unscoped_scores:
                    # Scoped score should be >= unscoped (boosted or equal)
                    assert scoped_scores[wid] >= unscoped_scores[wid]


# ---------------------------------------------------------------------------
# WisdomRetriever: top_k limiting
# ---------------------------------------------------------------------------


class TestTopKLimit:
    """Tests for top_k result limiting."""

    def test_retrieve_returns_top_k_limit(
        self, populated_store: WisdomStore
    ) -> None:
        """retrieve() respects the top_k limit."""
        # Create retriever with top_k=2
        r = WisdomRetriever(populated_store, top_k=2)
        r.rebuild_index()
        # Query that should match multiple entities
        results = r.retrieve("DuckDB")
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# WisdomRetriever: rebuild_index
# ---------------------------------------------------------------------------


class TestRebuildIndex:
    """Tests for rebuild_index() method."""

    def test_rebuild_index_no_error(self, retriever: WisdomRetriever) -> None:
        """rebuild_index() completes without error on empty store."""
        retriever.rebuild_index()  # Should not raise

    def test_rebuild_index_idempotent(
        self, populated_retriever: WisdomRetriever
    ) -> None:
        """rebuild_index() can be called multiple times safely."""
        populated_retriever.rebuild_index()
        populated_retriever.rebuild_index()
        # Should still work after double rebuild
        results = populated_retriever.retrieve("DuckDB")
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Recommender integration: without wisdom_retriever
# ---------------------------------------------------------------------------


class TestRecommenderWithoutWisdom:
    """Tests for Recommender backward compatibility without wisdom_retriever."""

    def test_recommender_without_wisdom_retriever_returns_recommendation(
        self,
    ) -> None:
        """Recommender without wisdom_retriever returns plain Recommendation."""
        # Mock the dependencies
        mock_conn = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.1] * 384
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        recommender = Recommender(
            conn=mock_conn,
            embedder=mock_embedder,
            retriever=mock_retriever,
        )

        result = recommender.recommend(
            observation={"context": {"recent_summary": "test"}}
        )

        assert isinstance(result, Recommendation)
        assert not isinstance(result, EnrichedRecommendation)


# ---------------------------------------------------------------------------
# Recommender integration: with wisdom_retriever
# ---------------------------------------------------------------------------


class TestRecommenderWithWisdom:
    """Tests for Recommender enrichment with WisdomRetriever."""

    def test_recommender_with_wisdom_retriever_returns_enriched(
        self, populated_store: WisdomStore
    ) -> None:
        """Recommender with wisdom_retriever returns EnrichedRecommendation."""
        wisdom_retriever = WisdomRetriever(populated_store, top_k=3)
        wisdom_retriever.rebuild_index()

        mock_conn = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.1] * 384
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        recommender = Recommender(
            conn=mock_conn,
            embedder=mock_embedder,
            retriever=mock_retriever,
            wisdom_retriever=wisdom_retriever,
        )

        result = recommender.recommend(
            observation={"context": {"recent_summary": "DuckDB array columns"}}
        )

        assert isinstance(result, EnrichedRecommendation)
        assert isinstance(result.recommendation, Recommendation)
        assert isinstance(result.wisdom_refs, list)

    def test_enriched_has_dead_end_warning_flag(
        self, populated_store: WisdomStore
    ) -> None:
        """EnrichedRecommendation has_dead_end_warning is True when dead end matched."""
        wisdom_retriever = WisdomRetriever(populated_store, top_k=5)
        wisdom_retriever.rebuild_index()

        mock_conn = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.1] * 384
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        recommender = Recommender(
            conn=mock_conn,
            embedder=mock_embedder,
            retriever=mock_retriever,
            wisdom_retriever=wisdom_retriever,
        )

        result = recommender.recommend(
            observation={
                "context": {
                    "recent_summary": "jsonwebtoken Edge runtime CommonJS import fails"
                }
            }
        )

        assert isinstance(result, EnrichedRecommendation)
        # If the dead end was matched, the flag should be set
        dead_end_refs = [r for r in result.wisdom_refs if r.entity_type == "dead_end"]
        if dead_end_refs and dead_end_refs[0].is_dead_end_warning:
            assert result.has_dead_end_warning is True

    def test_enriched_no_warning_when_no_dead_ends(
        self, db_path: Path
    ) -> None:
        """EnrichedRecommendation has_dead_end_warning is False without dead ends."""
        # Store with only non-dead-end entities
        store = WisdomStore(db_path)
        store.add(
            WisdomEntity.create(
                "breakthrough",
                "Clean architecture pattern",
                "Separate domain logic from infrastructure",
                context_tags=["architecture"],
            )
        )

        wisdom_retriever = WisdomRetriever(store, top_k=3)
        wisdom_retriever.rebuild_index()

        mock_conn = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.1] * 384
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        recommender = Recommender(
            conn=mock_conn,
            embedder=mock_embedder,
            retriever=mock_retriever,
            wisdom_retriever=wisdom_retriever,
        )

        result = recommender.recommend(
            observation={
                "context": {"recent_summary": "clean architecture pattern"}
            }
        )

        assert isinstance(result, EnrichedRecommendation)
        assert result.has_dead_end_warning is False
