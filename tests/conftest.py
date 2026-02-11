"""Shared test fixtures for the orchestrator-policy-extraction test suite.

Provides factory helpers for creating CanonicalEvent instances and TaggedEvent
instances with sensible defaults, plus a sample PipelineConfig fixture loaded
from data/config.yaml.

Exports:
    sample_config: PipelineConfig fixture loaded from data/config.yaml
    make_event: Factory helper for CanonicalEvent with sensible defaults
    make_tagged_event: Factory helper for TaggedEvent wrapping a CanonicalEvent
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.pipeline.models.config import PipelineConfig, load_config
from src.pipeline.models.events import (
    CanonicalEvent,
    Classification,
    TaggedEvent,
)


@pytest.fixture
def sample_config() -> PipelineConfig:
    """Load PipelineConfig from data/config.yaml."""
    return load_config("data/config.yaml")


def make_event(
    actor: str = "executor",
    event_type: str = "assistant_text",
    payload: dict[str, Any] | None = None,
    links: dict[str, Any] | None = None,
    session_id: str = "test-session-001",
    source_system: str = "claude_jsonl",
    ts_utc: datetime | None = None,
    event_id: str | None = None,
) -> CanonicalEvent:
    """Create a CanonicalEvent with sensible defaults.

    Args:
        actor: Event actor (human_orchestrator, executor, tool, system).
        event_type: Event type (user_msg, assistant_text, tool_use, tool_result, etc.).
        payload: Event payload dict. Defaults to empty dict.
        links: Event links dict. Defaults to empty dict.
        session_id: Session ID. Defaults to "test-session-001".
        source_system: Source system. Defaults to "claude_jsonl".
        ts_utc: Timestamp. Defaults to a fixed UTC datetime.
        event_id: Event ID. If None, generated deterministically.

    Returns:
        CanonicalEvent instance.
    """
    if ts_utc is None:
        ts_utc = datetime(2026, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
    if payload is None:
        payload = {}
    if links is None:
        links = {}
    if event_id is None:
        event_id = CanonicalEvent.make_event_id(
            source_system=source_system,
            session_id=session_id,
            turn_id="test-turn",
            ts_utc=ts_utc.isoformat(),
            actor=actor,
            event_type=event_type,
        )
    return CanonicalEvent(
        event_id=event_id,
        ts_utc=ts_utc,
        session_id=session_id,
        actor=actor,
        event_type=event_type,
        payload=payload,
        links=links,
        source_system=source_system,
        source_ref="test:1",
    )


def make_tagged_event(
    event: CanonicalEvent,
    primary_label: str | None = None,
    confidence: float = 0.9,
) -> TaggedEvent:
    """Create a TaggedEvent wrapping a CanonicalEvent.

    Args:
        event: The canonical event to wrap.
        primary_label: Primary classification label. If None, no primary.
        confidence: Confidence for primary label.

    Returns:
        TaggedEvent instance.
    """
    primary = None
    if primary_label is not None:
        primary = Classification(
            label=primary_label,
            confidence=confidence,
            source="direct",
        )
    return TaggedEvent(
        event=event,
        primary=primary,
        secondaries=[],
        all_classifications=[primary] if primary else [],
    )
