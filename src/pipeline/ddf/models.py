"""Pydantic v2 models for DDF Detection Substrate (Phase 15).

Frozen (immutable) models for:
- FlameEvent: human or AI DDF marker at levels 0-7
- AxisHypothesis: candidate CCD axis identification
- ConstraintMetric: constraint radius/stagnation tracking
- IntelligenceProfile: aggregated DDF statistics per subject

All models use frozen=True to prevent pipeline stages from corrupting
detection results. IDs are deterministic SHA-256[:16] hashes.

Exports:
    FlameEvent
    AxisHypothesis
    ConstraintMetric
    IntelligenceProfile
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class FlameEvent(BaseModel, frozen=True):
    """A DDF flame marker event for human or AI subject.

    Represents a single detection of conceptual activity at a specific
    DDF level (0-7). Level 0 = trunk identification, Level 7 = full
    flood confirmation.

    Frozen to prevent mutation after creation.
    """

    flame_event_id: str
    session_id: str
    human_id: Optional[str] = None
    prompt_number: Optional[int] = None
    marker_level: int
    marker_type: str
    evidence_excerpt: Optional[str] = None
    quality_score: Optional[float] = None
    axis_identified: Optional[str] = None
    flood_confirmed: bool = False
    subject: Literal["human", "ai"] = "human"
    detection_source: Literal["stub", "opeml"] = "stub"
    deposited_to_candidates: bool = False
    source_episode_id: Optional[str] = None
    session_event_ref: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("marker_level")
    @classmethod
    def marker_level_in_range(cls, v: int) -> int:
        """Validate marker_level is 0-7 (DDF levels)."""
        if not 0 <= v <= 7:
            raise ValueError(
                f"marker_level must be between 0 and 7, got {v}"
            )
        return v

    @classmethod
    def make_id(
        cls,
        session_id: str,
        prompt_number: int | None,
        marker_type: str,
    ) -> str:
        """Generate a deterministic flame event ID.

        Uses SHA-256[:16] of the composite key for consistent,
        collision-resistant identification.

        Args:
            session_id: Session identifier.
            prompt_number: Prompt number within session (may be None).
            marker_type: Type of DDF marker.

        Returns:
            16-character lowercase hex string.
        """
        key = f"{session_id}:{prompt_number}:{marker_type}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class AxisHypothesis(BaseModel, frozen=True):
    """A candidate CCD axis identification.

    Represents a hypothesis that a particular CCD axis has been
    identified in a session or episode, with confidence score.

    Frozen to prevent mutation after creation.
    """

    hypothesis_id: str
    session_id: str
    episode_id: Optional[str] = None
    hypothesized_axis: str
    confidence: float
    marker_type: str = "false_integration"
    evidence: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def make_id(
        cls,
        session_id: str,
        episode_id: str | None,
        hypothesized_axis: str,
    ) -> str:
        """Generate a deterministic axis hypothesis ID.

        Args:
            session_id: Session identifier.
            episode_id: Episode identifier (may be None).
            hypothesized_axis: The hypothesized CCD axis name.

        Returns:
            16-character lowercase hex string.
        """
        key = f"{session_id}:{episode_id}:{hypothesized_axis}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class ConstraintMetric(BaseModel, frozen=True):
    """Constraint radius and stagnation tracking.

    Tracks how many sessions a constraint has fired in (radius),
    total firing count, and whether it is stagnant (high firing
    count but no new episodes affected).

    Frozen to prevent mutation after creation.
    """

    constraint_id: str
    radius: int = 0
    firing_count: int = 0
    is_stagnant: bool = False
    last_computed: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class IntelligenceProfile(BaseModel, frozen=True):
    """Aggregated DDF statistics for a human or AI subject.

    Provides a summary view of flame event patterns for a given
    subject, useful for tracking conceptual development over time.

    Frozen to prevent mutation after creation.
    """

    human_id: str
    subject: Literal["human", "ai"] = "human"
    flame_frequency: int = 0
    avg_marker_level: float = 0.0
    max_marker_level: int = 0
    spiral_depth: int = 0
    flood_rate: float = 0.0
    session_count: int = 0
