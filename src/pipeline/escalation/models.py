"""Escalation detection data models.

Pydantic v2 frozen models for escalation candidate representation.
EscalationCandidate captures a detected block-then-bypass event pair
within a configurable turn window.

Exports:
    EscalationCandidate: Frozen model for a detected escalation event pair
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EscalationCandidate(BaseModel, frozen=True):
    """A detected escalation: block event followed by bypass within window.

    Captures the pair of events (block + bypass) that constitute an
    obstacle escalation, along with metadata for constraint generation
    and confidence scoring.

    Fields:
        session_id: Session where the escalation occurred
        block_event_id: The O_GATE/O_CORR event ID that blocked the agent
        block_event_tag: Tag of the blocking event ("O_GATE" or "O_CORR")
        bypass_event_id: The bypass tool call event ID
        bypass_tool_name: Tool used to bypass (Bash, Edit, Write, etc.)
        bypass_command: Command text for constraint template generation
        bypass_resource: Resource path for scope inference
        window_turns_used: Non-exempt events between block and bypass
        confidence: Detection confidence (1.0 for event-based detection)
        detector_version: Version of the detector that found this
    """

    session_id: str
    block_event_id: str
    block_event_tag: str
    bypass_event_id: str
    bypass_tool_name: str
    bypass_command: str = ""
    bypass_resource: str = ""
    window_turns_used: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    detector_version: str

    @field_validator("block_event_tag")
    @classmethod
    def block_tag_valid(cls, v: str) -> str:
        valid_tags = {"O_GATE", "O_CORR"}
        if v not in valid_tags:
            raise ValueError(
                f"block_event_tag must be one of {sorted(valid_tags)}, got '{v}'"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v
