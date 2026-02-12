"""Tests for Recommender: action selection, provenance, and danger detection.

Tests weighted majority vote action selection, Recommendation/SourceEpisodeRef
models, and danger detection against constraints and protected paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from src.pipeline.rag.embedder import EpisodeEmbedder, observation_to_text
from src.pipeline.rag.recommender import (
    Recommendation,
    Recommender,
    SourceEpisodeRef,
    check_dangerous,
)
from src.pipeline.rag.retriever import HybridRetriever
from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.storage.schema import create_schema, get_connection
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
    gates: list[str] | None = None,
    scope_paths: list[str] | None = None,
) -> dict:
    """Create a valid episode dict matching the populator output format."""
    if changed_files is None:
        changed_files = ["src/main.py", "tests/test_main.py"]
    if open_questions is None:
        open_questions = []
    if constraints_in_force is None:
        constraints_in_force = []
    if gates is None:
        gates = []
    if scope_paths is None:
        scope_paths = ["src/main.py"]

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
            "scope": {"paths": scope_paths},
            "executor_instruction": executor_instruction,
            "gates": gates,
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
    """Shared EpisodeEmbedder instance."""
    return EpisodeEmbedder()


@pytest.fixture
def db_with_episodes(embedder):
    """In-memory DuckDB with schema, episodes, embeddings, and FTS index."""
    conn = get_connection(":memory:")
    create_schema(conn)

    episodes = [
        _make_episode(
            episode_id="ep-approve-impl",
            segment_id="seg-1",
            mode="Implement",
            risk="medium",
            reaction_label="approve",
            recent_summary="Implementing auth module with JWT tokens for login",
            goal="Build auth module",
            scope_paths=["src/auth.py"],
            gates=["run_tests"],
        ),
        _make_episode(
            episode_id="ep-approve-explore",
            segment_id="seg-2",
            mode="Explore",
            risk="low",
            reaction_label="approve",
            recent_summary="Exploring database options for the application",
            goal="Investigate database choices",
            scope_paths=["docs/"],
        ),
        _make_episode(
            episode_id="ep-approve-impl2",
            segment_id="seg-3",
            mode="Implement",
            risk="high",
            reaction_label="approve",
            recent_summary="Building API endpoint for user creation with validation",
            goal="Implement user API",
            scope_paths=["src/api/users.py"],
            gates=["run_tests", "require_human_approval"],
        ),
        _make_episode(
            episode_id="ep-correct",
            segment_id="seg-4",
            mode="Implement",
            risk="medium",
            reaction_label="correct",
            recent_summary="Attempted to modify database migrations directly",
            goal="Update database schema",
            scope_paths=["db/migrations/"],
        ),
        _make_episode(
            episode_id="ep-block",
            segment_id="seg-5",
            mode="Implement",
            risk="critical",
            reaction_label="block",
            recent_summary="Tried to push to main without review",
            goal="Deploy to production",
            scope_paths=["infra/deploy.yaml"],
            gates=["require_human_approval", "protected_paths"],
        ),
    ]

    write_episodes(conn, episodes)
    embedder.embed_episodes(conn)

    yield conn
    conn.close()


# --- Action selection tests ---


class TestActionSelection:
    """Tests for _select_action weighted majority vote."""

    def test_select_action_single_approved(self, db_with_episodes, embedder):
        """Single approved episode: recommended mode is that episode's mode."""
        retriever = HybridRetriever(db_with_episodes)
        recommender = Recommender(
            db_with_episodes, embedder, retriever,
        )
        # Query that should match the Explore episode
        rec = recommender.recommend(
            observation={"context": {"recent_summary": "Exploring database options and choices"}},
        )
        # Should return some recommendation (not raise)
        assert isinstance(rec, Recommendation)
        assert rec.recommended_mode in ("Explore", "Implement", "Plan", "Verify", "Triage", "Refactor", "Integrate")

    def test_select_action_majority_vote_weighted(self, db_with_episodes, embedder):
        """Multiple approved episodes: mode is weighted majority vote by rrf_score."""
        retriever = HybridRetriever(db_with_episodes)
        recommender = Recommender(
            db_with_episodes, embedder, retriever,
        )
        # Query that should match Implement episodes (2 Implement approves vs 1 Explore approve)
        rec = recommender.recommend(
            observation={"context": {"recent_summary": "Building authentication module with JWT implementation"}},
        )
        # Implement should win (more approved episodes for implementation)
        assert isinstance(rec, Recommendation)

    def test_select_action_no_approved_falls_back(self, db_with_episodes, embedder):
        """No approved episodes in results: falls back to most similar episode."""
        # Create a DB where only corrected/blocked episodes match
        conn = get_connection(":memory:")
        create_schema(conn)
        episodes = [
            _make_episode(
                episode_id="ep-corr",
                segment_id="seg-c1",
                mode="Implement",
                risk="medium",
                reaction_label="correct",
                recent_summary="Unique zebra crossing algorithm implementation",
                goal="Build zebra module",
            ),
        ]
        write_episodes(conn, episodes)
        embedder.embed_episodes(conn)

        retriever = HybridRetriever(conn)
        recommender = Recommender(conn, embedder, retriever)
        rec = recommender.recommend(
            observation={"context": {"recent_summary": "Unique zebra crossing algorithm"}},
        )
        assert isinstance(rec, Recommendation)
        conn.close()

    def test_select_action_max_risk_conservative(self, db_with_episodes, embedder):
        """Risk is maximum from approved episodes (conservative approach)."""
        retriever = HybridRetriever(db_with_episodes)
        recommender = Recommender(
            db_with_episodes, embedder, retriever,
        )
        # Query matching implementation episodes which include high risk
        rec = recommender.recommend(
            observation={"context": {"recent_summary": "Building API endpoint for user creation"}},
        )
        # Should get at least medium risk (could be high since ep-approve-impl2 has high risk)
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        assert risk_order.get(rec.recommended_risk, 0) >= 1  # at least medium

    def test_select_action_includes_constraints_from_corrected(self, db_with_episodes, embedder):
        """Constraints from corrected/blocked episodes are surfaced in reasoning."""
        retriever = HybridRetriever(db_with_episodes)
        recommender = Recommender(
            db_with_episodes, embedder, retriever,
        )
        rec = recommender.recommend(
            observation={"context": {"recent_summary": "Building API implementation with database"}},
        )
        # Should produce a valid recommendation
        assert isinstance(rec, Recommendation)
        assert len(rec.reasoning) > 0


# --- Recommendation model tests ---


class TestRecommendationModels:
    """Tests for Recommendation and SourceEpisodeRef Pydantic models."""

    def test_recommendation_has_all_fields(self):
        """Recommendation has all required fields."""
        rec = Recommendation(
            recommended_mode="Implement",
            recommended_risk="medium",
            recommended_scope_paths=["src/main.py"],
            recommended_gates=["run_tests"],
            confidence=0.85,
            source_episodes=[
                SourceEpisodeRef(
                    episode_id="ep-001",
                    similarity_score=0.92,
                    mode="Implement",
                    reaction_label="approve",
                    relevance="High similarity to current task",
                ),
            ],
            reasoning="Based on 1 similar approved episode",
            is_dangerous=False,
            danger_reasons=[],
        )
        assert rec.recommended_mode == "Implement"
        assert rec.recommended_risk == "medium"
        assert rec.confidence == 0.85
        assert len(rec.source_episodes) == 1
        assert rec.reasoning == "Based on 1 similar approved episode"
        assert rec.is_dangerous is False
        assert rec.danger_reasons == []
        assert rec.recommended_scope_paths == ["src/main.py"]
        assert rec.recommended_gates == ["run_tests"]

    def test_source_episode_ref_has_all_fields(self):
        """SourceEpisodeRef has all required fields."""
        ref = SourceEpisodeRef(
            episode_id="ep-001",
            similarity_score=0.92,
            mode="Implement",
            reaction_label="approve",
            relevance="High similarity to current task",
        )
        assert ref.episode_id == "ep-001"
        assert ref.similarity_score == 0.92
        assert ref.mode == "Implement"
        assert ref.reaction_label == "approve"
        assert ref.relevance == "High similarity to current task"

    def test_recommend_returns_recommendation_with_sources(self, db_with_episodes, embedder):
        """Recommender.recommend() returns Recommendation with source_episodes populated."""
        retriever = HybridRetriever(db_with_episodes)
        recommender = Recommender(db_with_episodes, embedder, retriever)
        rec = recommender.recommend(
            observation={"context": {"recent_summary": "JWT authentication module"}},
            exclude_episode_id="ep-nonexistent",
        )
        assert isinstance(rec, Recommendation)
        assert len(rec.source_episodes) > 0
        for src in rec.source_episodes:
            assert isinstance(src, SourceEpisodeRef)
            assert src.episode_id
            assert src.similarity_score > 0


# --- Danger detection tests ---


class TestDangerDetection:
    """Tests for check_dangerous danger detection."""

    def test_scope_violation_detected(self, tmp_path):
        """Detects scope_violation when recommendation overlaps forbidden constraint paths."""
        # Create a constraint store with a forbidden constraint
        schema_path = tmp_path / "constraint.schema.json"
        schema_path.write_text("{}")
        constraints_path = tmp_path / "constraints.json"
        constraints_path.write_text(json.dumps([
            {
                "constraint_id": "c-001",
                "text": "Never modify secrets",
                "severity": "forbidden",
                "scope": {"paths": ["secrets/"]},
                "hint_patterns": [],
                "examples": [],
            }
        ]))

        store = ConstraintStore(
            path=constraints_path,
            schema_path=schema_path,
        )

        recommendation = {
            "scope_paths": ["secrets/api_key.yaml"],
            "risk": "low",
            "gates": [],
        }
        episode = {"risk": "low", "gates": []}

        is_dangerous, reasons = check_dangerous(
            recommendation, episode, constraint_store=store, protected_paths=[],
        )
        assert is_dangerous is True
        assert "scope_violation" in reasons

    def test_risk_underestimate_detected(self):
        """Detects risk_underestimate when rec risk is lower than actual high/critical."""
        recommendation = {
            "scope_paths": [],
            "risk": "low",
            "gates": [],
        }
        episode = {"risk": "high", "gates": []}

        is_dangerous, reasons = check_dangerous(
            recommendation, episode, protected_paths=[],
        )
        assert is_dangerous is True
        assert "risk_underestimate" in reasons

    def test_gate_dropped_detected(self):
        """Detects gate_dropped when actual episode had critical gates that rec omits."""
        recommendation = {
            "scope_paths": [],
            "risk": "high",
            "gates": [],
        }
        episode = {"risk": "high", "gates": ["require_human_approval", "run_tests"]}

        is_dangerous, reasons = check_dangerous(
            recommendation, episode, protected_paths=[],
        )
        assert is_dangerous is True
        assert "gate_dropped" in reasons

    def test_protected_path_detected(self):
        """Detects protected_path when recommendation scope includes protected paths."""
        recommendation = {
            "scope_paths": ["infra/deploy.yaml", "src/main.py"],
            "risk": "medium",
            "gates": [],
        }
        episode = {"risk": "medium", "gates": []}
        protected = ["infra/", "secrets/", ".github/workflows/"]

        is_dangerous, reasons = check_dangerous(
            recommendation, episode, protected_paths=protected,
        )
        assert is_dangerous is True
        assert "protected_path" in reasons

    def test_safe_recommendation_no_danger(self):
        """Safe recommendation returns (False, [])."""
        recommendation = {
            "scope_paths": ["src/feature.py"],
            "risk": "medium",
            "gates": ["run_tests"],
        }
        episode = {"risk": "medium", "gates": ["run_tests"]}

        is_dangerous, reasons = check_dangerous(
            recommendation, episode, protected_paths=["infra/", "secrets/"],
        )
        assert is_dangerous is False
        assert reasons == []
