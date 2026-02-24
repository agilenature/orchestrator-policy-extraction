"""Pydantic v2 models for topological edge-generation (Phase 16.1).

Frozen (immutable) models for:
- ActivationCondition: when an edge fires (structurally non-optional)
- EdgeRecord: a CCD axis relationship with evidence grounding

All models use frozen=True to prevent pipeline stages from corrupting
topology state. Edge IDs are deterministic SHA-256[:16] hashes of the
axis_a|axis_b|relationship_text composite key.

Exports:
    ActivationCondition
    EdgeRecord
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ActivationCondition(BaseModel, frozen=True):
    """When an edge fires during topology traversal.

    Defines the conditions under which the relationship between two
    CCD axes is relevant. The minimum valid condition uses defaults:
    goal_type=["any"], scope_prefix="", min_axes_simultaneously_active=2.

    Null/{} is rejected at the writer level, but default-constructed
    instances are valid.

    Frozen to prevent mutation after creation.
    """

    goal_type: list[str] = Field(default_factory=lambda: ["any"])
    scope_prefix: str = ""
    min_axes_simultaneously_active: int = 2


class EdgeRecord(BaseModel, frozen=True):
    """A CCD axis relationship with evidence grounding.

    Represents a first-class knowledge artifact: the relationship
    between two CCD axes (axis_a, axis_b) with mandatory activation
    condition and evidence pointers.

    Edge IDs are deterministic SHA-256[:16] hashes ensuring the same
    axis pair + relationship always produces the same ID.

    Frozen to prevent mutation after creation.
    """

    edge_id: str
    axis_a: str
    axis_b: str
    relationship_text: str
    activation_condition: ActivationCondition
    evidence: dict
    abstraction_level: int
    status: Literal["candidate", "active", "superseded"] = "candidate"
    trunk_quality: float = 1.0
    created_session_id: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("abstraction_level")
    @classmethod
    def abstraction_level_in_range(cls, v: int) -> int:
        """Validate abstraction_level is 0-7."""
        if not 0 <= v <= 7:
            raise ValueError(
                f"abstraction_level must be between 0 and 7, got {v}"
            )
        return v

    @field_validator("trunk_quality")
    @classmethod
    def trunk_quality_in_range(cls, v: float) -> float:
        """Validate trunk_quality is 0.0-1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"trunk_quality must be between 0.0 and 1.0, got {v}"
            )
        return v

    @classmethod
    def make_id(
        cls,
        axis_a: str,
        axis_b: str,
        relationship_text: str,
    ) -> str:
        """Generate a deterministic edge ID.

        Uses SHA-256[:16] of the composite key for consistent,
        collision-resistant identification.

        Args:
            axis_a: First CCD axis name.
            axis_b: Second CCD axis name.
            relationship_text: Description of the relationship.

        Returns:
            16-character lowercase hex string.
        """
        key = f"{axis_a}|{axis_b}|{relationship_text}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
