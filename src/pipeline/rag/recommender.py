"""Action recommender with explainable provenance and danger detection.

Selects recommended orchestrator actions from retrieved similar episodes
using weighted majority vote. Checks recommendations against constraints
and protected paths for safety.

Exports:
    SourceEpisodeRef: Reference to a source episode used in recommendation
    Recommendation: RAG baseline recommendation with provenance
    Recommender: Action recommender using hybrid retrieval
    check_dangerous: Check if a recommendation would be dangerous
"""

from __future__ import annotations

from pydantic import BaseModel


class SourceEpisodeRef(BaseModel, frozen=True):
    """Reference to a source episode used in the recommendation."""

    episode_id: str
    similarity_score: float
    mode: str
    reaction_label: str | None = None
    relevance: str = ""


class Recommendation(BaseModel, frozen=True):
    """RAG baseline recommendation with explainable provenance."""

    recommended_mode: str
    recommended_risk: str
    recommended_scope_paths: list[str] = []
    recommended_gates: list[str] = []
    confidence: float
    source_episodes: list[SourceEpisodeRef]
    reasoning: str
    is_dangerous: bool = False
    danger_reasons: list[str] = []


class Recommender:
    """Action recommender using hybrid retrieval."""

    def __init__(self, conn, embedder, retriever, constraint_store=None, protected_paths=None):
        raise NotImplementedError

    def recommend(
        self,
        observation: dict,
        orchestrator_action: dict | None = None,
        exclude_episode_id: str | None = None,
    ) -> Recommendation:
        raise NotImplementedError


def check_dangerous(
    recommendation: dict,
    episode: dict,
    constraint_store=None,
    protected_paths: list[str] | None = None,
) -> tuple[bool, list[str]]:
    raise NotImplementedError
