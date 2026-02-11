"""Pydantic models for canonical events and tagged events.

Implements the event data models from the research spec:
- CanonicalEvent: Normalized event from any source (frozen/immutable)
- Classification: A label assignment with confidence (frozen/immutable)
- TaggedEvent: An event with primary + secondary classifications (frozen/immutable)

Event IDs are deterministic hashes (Q14) using SHA-256 truncated to 16 hex chars.

Exports:
    CanonicalEvent: Normalized event model
    Classification: Label assignment model
    TaggedEvent: Classified event model
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Classification(BaseModel, frozen=True):
    """A classification label assignment with confidence score.

    Frozen (immutable) to prevent pipeline stages from corrupting
    classification results.
    """

    label: str
    confidence: float
    source: str  # "direct" | "inferred" | "risk_model"

    @field_validator("label")
    @classmethod
    def label_valid(cls, v: str) -> str:
        valid_labels = {
            "O_DIR",
            "O_GATE",
            "O_CORR",
            "X_PROPOSE",
            "X_ASK",
            "T_TEST",
            "T_LINT",
            "T_GIT_COMMIT",
            "T_RISKY",
        }
        if v not in valid_labels:
            raise ValueError(
                f"Invalid label '{v}'. Must be one of: {sorted(valid_labels)}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("source")
    @classmethod
    def source_valid(cls, v: str) -> str:
        valid_sources = {"direct", "inferred", "risk_model"}
        if v not in valid_sources:
            raise ValueError(
                f"Invalid source '{v}'. Must be one of: {sorted(valid_sources)}"
            )
        return v


class CanonicalEvent(BaseModel, frozen=True):
    """Normalized event from any source system.

    Frozen (immutable) to prevent pipeline stages from corrupting
    upstream data. All events pass through this model after normalization.

    The event_id is a deterministic hash (Q14) ensuring idempotent
    re-ingestion: processing the same source file twice produces
    identical event IDs.
    """

    event_id: str
    ts_utc: datetime
    session_id: str
    actor: str  # human_orchestrator | executor | tool | system
    event_type: str  # user_msg | assistant_text | assistant_thinking | tool_use | tool_result | git_commit | system_event
    payload: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict)
    source_system: str  # claude_jsonl | git
    source_ref: str  # file:line_number or commit_hash
    risk_score: float = 0.0
    risk_factors: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("ts_utc")
    @classmethod
    def ts_must_be_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware (UTC)."""
        if v.tzinfo is None:
            raise ValueError(
                "ts_utc must be timezone-aware. Use datetime with tzinfo=timezone.utc"
            )
        return v

    @field_validator("risk_score")
    @classmethod
    def risk_score_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"risk_score must be between 0.0 and 1.0, got {v}")
        return v

    @classmethod
    def make_event_id(
        cls,
        source_system: str,
        session_id: str,
        turn_id: str,
        ts_utc: str,
        actor: str,
        event_type: str,
    ) -> str:
        """Generate a deterministic event ID from source components.

        Implements locked decision Q14: hash(source_system, session_id,
        turn_id, ts_utc, actor, type) truncated to 16 hex chars.

        Same input always produces the same output, enabling idempotent
        re-ingestion.

        Args:
            source_system: "claude_jsonl" or "git"
            session_id: Session UUID or identifier
            turn_id: UUID from source record or sequence number
            ts_utc: ISO 8601 timestamp string
            actor: Event actor
            event_type: Event type

        Returns:
            16-character lowercase hex string
        """
        key = f"{source_system}:{session_id}:{turn_id}:{ts_utc}:{actor}:{event_type}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class TaggedEvent(BaseModel, frozen=True):
    """An event with classification labels applied.

    After the multi-pass tagger processes a CanonicalEvent, it produces
    a TaggedEvent with:
    - primary: The highest-confidence label (Q9), or None if below min_confidence
    - secondaries: Additional labels (additive)
    - all_classifications: All candidates for metadata/debugging

    Frozen (immutable) to prevent downstream stages from altering
    classification results.
    """

    event: CanonicalEvent
    primary: Classification | None = None
    secondaries: list[Classification] = Field(default_factory=list)
    all_classifications: list[Classification] = Field(default_factory=list)
