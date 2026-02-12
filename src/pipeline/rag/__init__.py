"""RAG retrieval module for episode similarity search and recommendation.

Exports:
    EpisodeEmbedder: Episode embedding generator
    observation_to_text: Convert observation dict to searchable text
    HybridRetriever: Hybrid BM25 + embedding search with RRF fusion
    Recommender: Action recommender using hybrid retrieval
    Recommendation: RAG baseline recommendation with provenance
    SourceEpisodeRef: Reference to a source episode in recommendation
    check_dangerous: Check if a recommendation would be dangerous
"""

from __future__ import annotations

from src.pipeline.rag.embedder import EpisodeEmbedder, observation_to_text
from src.pipeline.rag.recommender import (
    Recommendation,
    Recommender,
    SourceEpisodeRef,
    check_dangerous,
)
from src.pipeline.rag.retriever import HybridRetriever

__all__ = [
    "EpisodeEmbedder",
    "observation_to_text",
    "HybridRetriever",
    "Recommender",
    "Recommendation",
    "SourceEpisodeRef",
    "check_dangerous",
]
