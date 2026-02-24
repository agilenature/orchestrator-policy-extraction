"""Pydantic v2 models for Candidate Assessment System (Phase 17).

Frozen (immutable) models for:
- ScenarioSpec: assessment scenario definition derived from project wisdom
- AssessmentSession: tracks a single assessment session lifecycle
- AssessmentReport: aggregated results from a completed assessment

All models use frozen=True to prevent pipeline stages from corrupting
assessment results. IDs are deterministic SHA-256[:16] hashes.

Exports:
    ScenarioSpec
    AssessmentSession
    AssessmentReport
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ScenarioSpec(BaseModel, frozen=True):
    """Assessment scenario definition derived from project wisdom.

    Each scenario targets a specific DDF level by presenting a broken
    implementation that requires conceptual identification at that level
    to diagnose and fix correctly.

    Frozen to prevent mutation after creation.
    """

    scenario_id: str  # SHA-256[:16] of wisdom_id + ddf_target_level
    wisdom_id: str
    ddf_target_level: int  # 1-7
    entity_type: str
    title: str
    scenario_context: str
    broken_impl_filename: str
    broken_impl_content: str
    handicap_claude_md: Optional[str] = None
    scenario_seed: Optional[str] = None

    @field_validator("ddf_target_level")
    @classmethod
    def ddf_level_valid(cls, v: int) -> int:
        """Validate ddf_target_level is 1-7."""
        if not 1 <= v <= 7:
            raise ValueError(f"ddf_target_level must be 1-7, got {v}")
        return v

    @classmethod
    def make_id(cls, wisdom_id: str, ddf_target_level: int) -> str:
        """Generate a deterministic scenario ID.

        Uses SHA-256[:16] of the composite key for consistent,
        collision-resistant identification.

        Args:
            wisdom_id: Source wisdom entry identifier.
            ddf_target_level: Target DDF level (1-7).

        Returns:
            16-character lowercase hex string.
        """
        key = f"{wisdom_id}:{ddf_target_level}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class AssessmentSession(BaseModel, frozen=True):
    """Tracks a single assessment session lifecycle.

    Manages the lifecycle of a Claude Code session launched in a
    controlled /tmp assessment directory. The derive_jsonl_path method
    encodes the assessment directory path to locate the resulting
    JSONL session artifact.

    Frozen to prevent mutation after creation.
    """

    session_id: str
    scenario_id: str
    candidate_id: str
    assessment_dir: str
    jsonl_path: Optional[str] = None
    status: Literal["setup", "running", "completed", "failed"] = "setup"
    handicap_level: Optional[int] = None
    session_artifact_path: Optional[str] = None
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: Optional[datetime] = None

    @classmethod
    def derive_jsonl_path(cls, assessment_dir: str, session_id: str) -> str:
        """Derive the expected JSONL path for a session in an assessment dir.

        Claude Code stores session JSONL files under
        ~/.claude/projects/{encoded_dir}/{session_id}.jsonl where
        encoded_dir replaces all slashes (including leading) with dashes.

        Args:
            assessment_dir: The assessment working directory (e.g. /tmp/ope_assess_abc123/).
            session_id: The session identifier.

        Returns:
            Absolute path to the expected JSONL file.
        """
        clean_dir = assessment_dir.rstrip("/")
        encoded = clean_dir.replace("/", "-")
        return os.path.expanduser(
            f"~/.claude/projects/{encoded}/{session_id}.jsonl"
        )


class AssessmentReport(BaseModel, frozen=True):
    """Aggregated results from a completed assessment session.

    Captures the full assessment outcome including TE metrics,
    DDF flame event analysis, axis quality scores, and behavioral
    indicators (rejections, stubbornness). The source_type field
    validates that assessment data is properly tagged.

    Frozen to prevent mutation after creation.
    """

    report_id: str
    session_id: str
    scenario_id: str
    candidate_id: str
    flame_event_count: int = 0
    level_distribution: dict[str, int] = Field(default_factory=dict)
    candidate_te: Optional[float] = None
    raven_depth: Optional[float] = None
    crow_efficiency: Optional[float] = None
    trunk_quality: Optional[float] = None
    candidate_ratio: Optional[float] = None
    percentile_rank: Optional[float] = None
    axis_quality_scores: dict[str, float] = Field(default_factory=dict)
    flood_rate: Optional[float] = None
    spiral_evidence: list[str] = Field(default_factory=list)
    fringe_drift_rate: Optional[float] = None
    ai_avg_marker_level: Optional[float] = None
    ai_flame_event_count: int = 0
    rejections_detected: int = 0
    rejections_level5: int = 0
    stubbornness_indicators: int = 0
    source_type: Literal["simulation_review"] = "simulation_review"
    fidelity: int = 3
    confidence: float = 0.85
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def make_id(cls, session_id: str) -> str:
        """Generate a deterministic report ID from session_id.

        Args:
            session_id: The assessment session identifier.

        Returns:
            16-character lowercase hex string.
        """
        return hashlib.sha256(session_id.encode()).hexdigest()[:16]

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        """Validate source_type is one of the allowed values."""
        allowed = ("production", "assessment", "simulation_review")
        if v not in allowed:
            raise ValueError(f"source_type must be one of {allowed}, got {v}")
        return v
