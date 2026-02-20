"""Project-level wisdom layer (Phase 11).

Stores and retrieves project wisdom: breakthroughs, dead ends, scope decisions,
and method decisions extracted from objectivism analysis documents. Enriches
RAG recommendations with historical project knowledge.

Exports:
    WisdomEntity: Frozen model for a wisdom entry (breakthrough, dead_end, etc.)
    WisdomRef: Lightweight reference to a wisdom entity with relevance score
    EnrichedRecommendation: Recommendation augmented with wisdom references
    WisdomStore: DuckDB-backed CRUD and search for wisdom entities
    WisdomRetriever: Hybrid BM25 + optional vector search for wisdom entities
    WisdomIngestor: Bulk JSON loader for wisdom entries
    IngestResult: Outcome model for ingestion operations
"""

from src.pipeline.wisdom.ingestor import IngestResult, WisdomIngestor
from src.pipeline.wisdom.models import (
    EnrichedRecommendation,
    WisdomEntity,
    WisdomRef,
)
from src.pipeline.wisdom.retriever import WisdomRetriever
from src.pipeline.wisdom.store import WisdomStore

__all__ = [
    "EnrichedRecommendation",
    "IngestResult",
    "WisdomEntity",
    "WisdomIngestor",
    "WisdomRef",
    "WisdomRetriever",
    "WisdomStore",
]
