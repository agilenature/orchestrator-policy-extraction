"""Episode embedding generator for RAG retrieval.

Generates 384-dim embeddings from episode observation text using
sentence-transformers all-MiniLM-L6-v2. Stores embeddings in DuckDB
with HNSW cosine index for similarity search.

Exports:
    observation_to_text: Convert structured observation to searchable text
    EpisodeEmbedder: Episode embedding generator with DuckDB storage
"""

from __future__ import annotations

import duckdb


def observation_to_text(
    observation: dict, orchestrator_action: dict | None = None
) -> str:
    """Convert structured observation to searchable text.

    Extracts and joins text from observation fields (context, repo_state,
    quality_state) and optional orchestrator_action (goal, executor_instruction).

    Args:
        observation: Episode observation dict with nested fields.
        orchestrator_action: Optional orchestrator action dict.

    Returns:
        Searchable text string with parts joined by ' | '.
    """
    raise NotImplementedError("observation_to_text not yet implemented")


class EpisodeEmbedder:
    """Generate and store embeddings for episodes.

    Uses sentence-transformers all-MiniLM-L6-v2 for 384-dim embeddings.
    Stores results in DuckDB episode_embeddings and episode_search_text tables.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        raise NotImplementedError("EpisodeEmbedder.__init__ not yet implemented")

    def embed_text(self, text: str) -> list[float]:
        """Generate a 384-dim embedding for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of 384 floats.
        """
        raise NotImplementedError("embed_text not yet implemented")

    def embed_episodes(self, conn: duckdb.DuckDBPyConnection) -> dict:
        """Embed all un-embedded episodes in the database.

        Reads episodes from the episodes table, extracts observation text,
        generates embeddings, and writes to episode_embeddings and
        episode_search_text tables. Skips already-embedded episodes.

        Args:
            conn: DuckDB connection with schema already created.

        Returns:
            Stats dict with 'embedded' and 'skipped' counts.
        """
        raise NotImplementedError("embed_episodes not yet implemented")

    @staticmethod
    def rebuild_fts_index(conn: duckdb.DuckDBPyConnection) -> None:
        """Rebuild the FTS index on episode_search_text.

        Must be called after batch insertion for BM25 search to work.

        Args:
            conn: DuckDB connection.
        """
        raise NotImplementedError("rebuild_fts_index not yet implemented")
