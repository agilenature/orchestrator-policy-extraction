"""Project-level wisdom layer (Phase 11).

Stores and retrieves project wisdom: breakthroughs, dead ends, scope decisions,
and method decisions extracted from objectivism analysis documents. Enriches
RAG recommendations with historical project knowledge.

Exports:
    WisdomEntity: Frozen model for a wisdom entry (breakthrough, dead_end, etc.)
    WisdomRef: Lightweight reference to a wisdom entity with relevance score
    EnrichedRecommendation: Recommendation augmented with wisdom references
    WisdomStore: DuckDB-backed CRUD and search for wisdom entities
"""

from src.pipeline.wisdom.models import (
    EnrichedRecommendation,
    WisdomEntity,
    WisdomRef,
)

__all__ = [
    "EnrichedRecommendation",
    "WisdomEntity",
    "WisdomRef",
]
