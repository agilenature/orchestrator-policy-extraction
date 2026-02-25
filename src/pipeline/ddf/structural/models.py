"""Pydantic v2 models for structural integrity detection (Phase 18).

Frozen (immutable) models for:
- StructuralEvent: a single structural integrity signal (gravity check,
  main cable, dependency sequencing, spiral reinforcement)
- StructuralIntegrityResult: aggregated structural integrity scores
  for a session/subject

IDs are deterministic SHA-256[:16] hashes following the FlameEvent pattern.

Exports:
    StructuralEvent
    StructuralIntegrityResult
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class StructuralEvent(BaseModel, frozen=True):
    """A structural integrity signal for a session prompt.

    Represents detection of one of four structural signal types:
    gravity_check, main_cable, dependency_sequencing, spiral_reinforcement.

    Frozen to prevent mutation after creation.
    """

    event_id: str
    session_id: str
    assessment_session_id: Optional[str] = None
    prompt_number: int
    subject: Literal["human", "ai"]
    signal_type: Literal[
        "gravity_check",
        "main_cable",
        "dependency_sequencing",
        "spiral_reinforcement",
    ]
    structural_role: Optional[str] = None
    evidence: Optional[str] = None
    signal_passed: bool
    score_contribution: Optional[float] = None
    contributing_flame_event_ids: list[str] = Field(default_factory=list)
    op8_status: Optional[Literal["pass", "fail", "na"]] = None
    op8_correction_candidate_id: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def make_id(
        cls,
        session_id: str,
        prompt_number: int,
        signal_type: str,
    ) -> str:
        """Generate a deterministic structural event ID.

        Uses SHA-256[:16] of the composite key for consistent,
        collision-resistant identification.

        Args:
            session_id: Session identifier.
            prompt_number: Prompt number within session.
            signal_type: Type of structural signal.

        Returns:
            16-character lowercase hex string.
        """
        key = f"{session_id}:{prompt_number}:{signal_type}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class StructuralIntegrityResult(BaseModel, frozen=True):
    """Aggregated structural integrity scores for a session/subject.

    Summarises the four signal-type ratios and the composite
    integrity_score for a given session and subject.

    Frozen to prevent mutation after creation.
    """

    session_id: str
    subject: str
    integrity_score: Optional[float] = None
    gravity_ratio: float
    main_cable_ratio: float
    dependency_ratio: float
    spiral_capped: float
    structural_event_count: int = 0
