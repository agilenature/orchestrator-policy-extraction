"""Wisdom entity data models.

Frozen Pydantic v2 models for the project wisdom system. WisdomEntity
represents a single piece of project wisdom (breakthrough, dead end,
scope decision, or method decision). WisdomRef is a lightweight reference
used when attaching wisdom to recommendations. EnrichedRecommendation
wraps a RAG Recommendation with wisdom references.

ID generation: SHA-256 of (entity_type + title) truncated to 16 hex chars,
prefixed with 'w-'. Example: w-a3f2b1c4d5e6f7a8.

Exports:
    WisdomEntity: Frozen model for a wisdom entry
    WisdomRef: Lightweight reference with relevance score
    EnrichedRecommendation: Recommendation augmented with wisdom refs
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _make_wisdom_id(entity_type: str, title: str) -> str:
    """Generate a deterministic wisdom ID from entity type and title.

    Uses SHA-256 hash of the concatenated entity_type and title,
    truncated to 16 hex characters, prefixed with 'w-'.

    Args:
        entity_type: One of breakthrough, dead_end, scope_decision, method_decision.
        title: Human-readable title of the wisdom entry.

    Returns:
        Deterministic wisdom ID string, e.g. 'w-a3f2b1c4d5e6f7a8'.
    """
    raw = (entity_type + title).encode()
    return "w-" + hashlib.sha256(raw).hexdigest()[:16]


class WisdomEntity(BaseModel):
    """A single piece of project wisdom.

    Represents a breakthrough discovery, a dead-end approach, a scope
    decision, or a method decision extracted from objectivism analysis
    documents. Frozen for immutability; use model_copy(update={...})
    to create modified versions.

    Attributes:
        wisdom_id: Deterministic ID (SHA-256 of entity_type + title).
        entity_type: Category of wisdom.
        title: Human-readable title.
        description: Detailed description of the wisdom entry.
        context_tags: Searchable tags for categorization.
        scope_paths: File/directory paths this wisdom applies to.
        confidence: Confidence score (0.0-1.0), default 1.0.
        source_document: Document this was extracted from.
        source_phase: Phase number where this was discovered.
        embedding: Optional embedding vector for similarity search.
    """

    model_config = ConfigDict(frozen=True)

    wisdom_id: str
    entity_type: Literal[
        "breakthrough", "dead_end", "scope_decision", "method_decision"
    ]
    title: str
    description: str
    context_tags: list[str] = Field(default_factory=list)
    scope_paths: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    source_document: str | None = None
    source_phase: int | None = None
    embedding: list[float] | None = None

    @classmethod
    def create(
        cls,
        entity_type: Literal[
            "breakthrough", "dead_end", "scope_decision", "method_decision"
        ],
        title: str,
        description: str,
        **kwargs: Any,
    ) -> WisdomEntity:
        """Factory method that auto-generates the wisdom_id.

        Computes the deterministic wisdom_id from entity_type and title,
        then constructs the frozen model.

        Args:
            entity_type: Category of wisdom.
            title: Human-readable title.
            description: Detailed description.
            **kwargs: Additional fields (context_tags, scope_paths, etc.).

        Returns:
            New WisdomEntity with generated wisdom_id.
        """
        wisdom_id = _make_wisdom_id(entity_type, title)
        return cls(
            wisdom_id=wisdom_id,
            entity_type=entity_type,
            title=title,
            description=description,
            **kwargs,
        )


class WisdomRef(BaseModel):
    """Lightweight reference to a wisdom entity.

    Used when attaching wisdom context to recommendations without
    carrying the full entity. Includes relevance score and dead-end
    warning flag for safety.

    Attributes:
        wisdom_id: Reference to the full WisdomEntity.
        entity_type: Category (breakthrough, dead_end, etc.).
        title: Human-readable title for display.
        relevance_score: How relevant this wisdom is (0.0-1.0).
        is_dead_end_warning: True if this warns about a known dead end.
        description: Optional description for context.
    """

    model_config = ConfigDict(frozen=True)

    wisdom_id: str
    entity_type: str
    title: str
    relevance_score: float
    is_dead_end_warning: bool = False
    description: str = ""


class EnrichedRecommendation(BaseModel):
    """A RAG recommendation enriched with project wisdom references.

    Wraps the existing Recommendation model from rag/recommender.py
    with additional wisdom context. Uses Any type for the recommendation
    field to avoid circular imports.

    Attributes:
        recommendation: The base RAG recommendation (Recommendation instance).
        wisdom_refs: List of relevant wisdom references attached.
        has_dead_end_warning: True if any wisdom ref is a dead-end warning.
    """

    model_config = ConfigDict(frozen=True)

    recommendation: Any  # Recommendation from rag/recommender.py
    wisdom_refs: list[WisdomRef] = Field(default_factory=list)
    has_dead_end_warning: bool = False
