"""RAG retrieval module for episode similarity search.

Exports:
    EpisodeEmbedder: Episode embedding generator
    observation_to_text: Convert observation dict to searchable text
"""

from __future__ import annotations

from src.pipeline.rag.embedder import EpisodeEmbedder, observation_to_text

__all__ = ["EpisodeEmbedder", "observation_to_text"]
