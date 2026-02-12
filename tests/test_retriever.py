"""Tests for HybridRetriever: BM25 + embedding hybrid search with RRF fusion.

Tests BM25 text search, embedding cosine similarity search, Reciprocal
Rank Fusion, exclude_episode_id filtering, and end-to-end retrieve().
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.rag.embedder import EpisodeEmbedder, observation_to_text
from src.pipeline.rag.retriever import HybridRetriever
from src.pipeline.storage.schema import create_schema, drop_schema, get_connection
from src.pipeline.storage.writer import write_episodes


# --- Fixture helpers ---


def _make_episode(
    episode_id: str = "ep-001",
    session_id: str = "sess-abc",
    segment_id: str = "seg-001",
    mode: str = "Implement",
    risk: str = "medium",
    reaction_label: str | None = "approve",
    reaction_confidence: float | None = 0.85,
    outcome_type: str = "success",
    tests_status: str = "pass",
    lint_status: str = "pass",
    changed_files: list[str] | None = None,
    config_hash: str = "abc12345",
    recent_summary: str = "Working on feature X",
    open_questions: list[str] | None = None,
    constraints_in_force: list[str] | None = None,
    goal: str = "Implement feature X",
    executor_instruction: str = "Implement the feature",
) -> dict:
    """Create a valid episode dict matching the populator output format."""
    if changed_files is None:
        changed_files = ["src/main.py", "tests/test_main.py"]
    if open_questions is None:
        open_questions = []
    if constraints_in_force is None:
        constraints_in_force = []

    reaction = None
    if reaction_label is not None:
        reaction = {
            "label": reaction_label,
            "message": "looks good",
            "confidence": reaction_confidence,
        }

    outcome: dict = {
        "executor_effects": {
            "tool_calls_count": 3,
            "files_touched": ["src/main.py"],
            "commands_ran": ["pytest tests/"],
            "git_events": [],
        },
        "quality": {
            "tests_status": tests_status,
            "lint_status": lint_status,
            "diff_stat": {"files": 2, "insertions": 10, "deletions": 3},
        },
        "reward_signals": {
            "objective": {"tests": 1.0, "lint": 1.0, "diff_risk": 0.2},
        },
    }
    if reaction is not None:
        outcome["reaction"] = reaction

    return {
        "episode_id": episode_id,
        "session_id": session_id,
        "segment_id": segment_id,
        "timestamp": "2026-02-11T12:00:00+00:00",
        "outcome_type": outcome_type,
        "observation": {
            "repo_state": {
                "changed_files": changed_files,
                "diff_stat": {"files": len(changed_files), "insertions": 5, "deletions": 2},
            },
            "quality_state": {
                "tests": {"status": tests_status},
                "lint": {"status": lint_status},
            },
            "context": {
                "recent_summary": recent_summary,
                "open_questions": open_questions,
                "constraints_in_force": constraints_in_force,
            },
        },
        "orchestrator_action": {
            "mode": mode,
            "goal": goal,
            "scope": {"paths": ["src/main.py"]},
            "executor_instruction": executor_instruction,
            "gates": [],
            "risk": risk,
        },
        "outcome": outcome,
        "provenance": {
            "sources": [
                {"type": "claude_jsonl", "ref": "session.jsonl:line-42"},
            ],
        },
        "config_hash": config_hash,
        "project": {"repo_path": "test-project"},
    }


@pytest.fixture
def embedder():
    """Shared EpisodeEmbedder instance (model loaded once)."""
    return EpisodeEmbedder()


@pytest.fixture
def db_with_episodes(embedder):
    """In-memory DuckDB with schema, 5 episodes, embeddings, and FTS index.

    Episodes have semantically distinct observation text:
    - ep-auth: Authentication and JWT tokens
    - ep-db: Database schema migration and SQL
    - ep-ui: React frontend user interface components
    - ep-test: Testing framework configuration and pytest
    - ep-deploy: Docker deployment and CI/CD pipeline
    """
    conn = get_connection(":memory:")
    create_schema(conn)

    episodes = [
        _make_episode(
            episode_id="ep-auth",
            segment_id="seg-auth",
            recent_summary="Implementing JWT authentication tokens for user login and session management",
            goal="Build auth module with JWT",
            executor_instruction="Create login endpoint with JWT token generation",
            changed_files=["src/auth.py", "src/tokens.py"],
        ),
        _make_episode(
            episode_id="ep-db",
            segment_id="seg-db",
            recent_summary="Database schema migration adding users table with PostgreSQL and SQLAlchemy ORM",
            goal="Create database migration",
            executor_instruction="Write alembic migration for users table",
            changed_files=["db/migrations/001.py", "models/user.py"],
        ),
        _make_episode(
            episode_id="ep-ui",
            segment_id="seg-ui",
            recent_summary="Building React frontend components for user dashboard with Material UI widgets",
            goal="Create user dashboard UI",
            executor_instruction="Build React components with Material UI",
            changed_files=["src/components/Dashboard.tsx", "src/components/Widget.tsx"],
        ),
        _make_episode(
            episode_id="ep-test",
            segment_id="seg-test",
            recent_summary="Configuring pytest testing framework with coverage reports and fixture setup",
            goal="Set up testing infrastructure",
            executor_instruction="Configure pytest with conftest and coverage",
            changed_files=["tests/conftest.py", "pytest.ini"],
        ),
        _make_episode(
            episode_id="ep-deploy",
            segment_id="seg-deploy",
            recent_summary="Docker containerization and CI/CD pipeline setup with GitHub Actions workflow",
            goal="Set up deployment pipeline",
            executor_instruction="Create Dockerfile and GitHub Actions workflow",
            changed_files=["Dockerfile", ".github/workflows/ci.yml"],
        ),
    ]

    write_episodes(conn, episodes)
    embedder.embed_episodes(conn)

    yield conn
    conn.close()


# --- BM25 search tests ---


class TestBM25Search:
    """Tests for _bm25_search BM25 text retrieval."""

    def test_bm25_search_returns_relevant_episodes(self, db_with_episodes, embedder):
        """BM25 search for 'JWT authentication' returns auth-related episodes."""
        retriever = HybridRetriever(db_with_episodes)
        results = retriever._bm25_search("JWT authentication tokens login", None)
        assert len(results) > 0
        episode_ids = [r[0] for r in results]
        assert "ep-auth" in episode_ids

    def test_bm25_search_exclude_episode_id(self, db_with_episodes, embedder):
        """BM25 search with exclude_episode_id omits that episode."""
        retriever = HybridRetriever(db_with_episodes)
        results = retriever._bm25_search("JWT authentication tokens login", "ep-auth")
        episode_ids = [r[0] for r in results]
        assert "ep-auth" not in episode_ids

    def test_bm25_search_no_matches(self, db_with_episodes, embedder):
        """BM25 search with no matching terms returns empty list."""
        retriever = HybridRetriever(db_with_episodes)
        results = retriever._bm25_search("xyzzyplughfoo", None)
        assert results == []


# --- Embedding search tests ---


class TestEmbeddingSearch:
    """Tests for _embedding_search cosine similarity retrieval."""

    def test_embedding_search_returns_similar_episodes(self, db_with_episodes, embedder):
        """Embedding search for auth-related text returns auth episode with high similarity."""
        retriever = HybridRetriever(db_with_episodes)
        query_embedding = embedder.embed_text("JWT authentication user login session tokens")
        results = retriever._embedding_search(query_embedding, None)
        assert len(results) > 0
        episode_ids = [r[0] for r in results]
        assert "ep-auth" in episode_ids

    def test_embedding_search_exclude_episode_id(self, db_with_episodes, embedder):
        """Embedding search with exclude_episode_id omits that episode."""
        retriever = HybridRetriever(db_with_episodes)
        query_embedding = embedder.embed_text("JWT authentication user login session tokens")
        results = retriever._embedding_search(query_embedding, "ep-auth")
        episode_ids = [r[0] for r in results]
        assert "ep-auth" not in episode_ids


# --- RRF fusion tests ---


class TestRRFFuse:
    """Tests for _rrf_fuse Reciprocal Rank Fusion."""

    def test_rrf_fuse_episode_in_both_lists_scores_higher(self):
        """Episode appearing in both BM25 and embedding results gets higher RRF score."""
        bm25_results = [("ep-1", 10.0), ("ep-2", 8.0), ("ep-3", 5.0)]
        emb_results = [("ep-1", 0.95), ("ep-4", 0.80), ("ep-3", 0.70)]

        fused = HybridRetriever._rrf_fuse(bm25_results, emb_results, k=5)

        # ep-1 appears in both lists, should have highest score
        scores = {r["episode_id"]: r["rrf_score"] for r in fused}
        assert scores["ep-1"] > scores["ep-2"]
        assert scores["ep-1"] > scores["ep-4"]

    def test_rrf_fuse_disjoint_sets(self):
        """RRF handles completely disjoint BM25 and embedding results."""
        bm25_results = [("ep-1", 10.0), ("ep-2", 8.0)]
        emb_results = [("ep-3", 0.95), ("ep-4", 0.80)]

        fused = HybridRetriever._rrf_fuse(bm25_results, emb_results, k=5)

        episode_ids = {r["episode_id"] for r in fused}
        assert episode_ids == {"ep-1", "ep-2", "ep-3", "ep-4"}
        # All scores should be positive
        for r in fused:
            assert r["rrf_score"] > 0

    def test_rrf_fuse_respects_k_limit(self):
        """RRF fusion limits output to k results."""
        bm25_results = [("ep-1", 10.0), ("ep-2", 8.0), ("ep-3", 5.0)]
        emb_results = [("ep-4", 0.95), ("ep-5", 0.80), ("ep-6", 0.70)]

        fused = HybridRetriever._rrf_fuse(bm25_results, emb_results, k=3)
        assert len(fused) == 3


# --- End-to-end retrieve tests ---


class TestRetrieve:
    """Tests for HybridRetriever.retrieve() end-to-end."""

    def test_retrieve_returns_ranked_results(self, db_with_episodes, embedder):
        """retrieve() returns list of dicts with episode_id and rrf_score keys."""
        retriever = HybridRetriever(db_with_episodes)
        query_text = "JWT authentication tokens"
        query_embedding = embedder.embed_text(query_text)

        results = retriever.retrieve(query_text, query_embedding)

        assert len(results) > 0
        for r in results:
            assert "episode_id" in r
            assert "rrf_score" in r
            assert r["rrf_score"] > 0

    def test_retrieve_with_exclude_episode_id(self, db_with_episodes, embedder):
        """retrieve() with exclude_episode_id prevents self-retrieval."""
        retriever = HybridRetriever(db_with_episodes)
        query_text = "JWT authentication tokens"
        query_embedding = embedder.embed_text(query_text)

        results = retriever.retrieve(query_text, query_embedding, exclude_episode_id="ep-auth")

        episode_ids = [r["episode_id"] for r in results]
        assert "ep-auth" not in episode_ids

    def test_retrieve_empty_database(self, embedder):
        """retrieve() returns empty list when database has no episodes."""
        conn = get_connection(":memory:")
        create_schema(conn)
        # Build FTS index on empty table so the FTS function exists
        EpisodeEmbedder.rebuild_fts_index(conn)

        retriever = HybridRetriever(conn)
        query_embedding = embedder.embed_text("test query")

        results = retriever.retrieve("test query", query_embedding)
        assert results == []

        conn.close()
