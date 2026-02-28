"""Pydantic models for the OPE Governance Bus.

Frozen models for bus sessions and governance signals, plus request/response
models for the /api/check endpoint.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel


class BusSession(BaseModel, frozen=True):
    """Represents a registered session on the governance bus."""

    session_id: str
    run_id: str
    status: str = "active"


class GovernanceSignal(BaseModel, frozen=True):
    """A governance signal emitted by the stream processor.

    boundary_dependency determines when the signal is actionable:
    - "event_level": fires immediately on the triggering event
    - "episode_level": deferred until CONFIRMED_END
    """

    signal_id: str
    session_id: str
    run_id: str
    signal_type: str
    boundary_dependency: str  # "event_level" | "episode_level"
    payload: dict[str, Any] = {}

    @staticmethod
    def make_id(session_id: str, signal_type: str, ts_iso: str) -> str:
        """Generate a deterministic 16-char hex signal ID."""
        raw = f"signal:{session_id}:{signal_type}:{ts_iso}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CheckRequest(BaseModel):
    """Request body for POST /api/check."""

    session_id: str
    run_id: str
    premise_data: dict[str, Any] = {}


class PushLink(BaseModel, frozen=True):
    """A causal push link between two decision artifacts across repo boundaries."""

    link_id: str
    parent_decision_id: str
    child_decision_id: str
    transition_trigger: str
    repo_boundary: str | None = None
    migration_run_id: str
    captured_at: str = ""  # ISO timestamp, set by server


class CheckResponse(BaseModel):
    """Response body for POST /api/check.

    Empty lists are the fail-open default: no constraints, no interventions.
    epistemological_signals is the stub for Gap 6 -- field exists in the
    response schema, enabling post-OpenClaw activation without schema change.
    relevant_docs: Phase 21 -- relevant documentation entries from doc_index.
    """

    constraints: list[dict[str, Any]] = []
    interventions: list[dict[str, Any]] = []
    epistemological_signals: list[dict[str, Any]] = []
    relevant_docs: list[dict[str, Any]] = []
    genus_count: int = 0


class GenusConsultRequest(BaseModel):
    """Request body for POST /api/genus-consult."""

    problem: str
    session_id: str = ""
    repo: str | None = None


class GenusConsultResponse(BaseModel):
    """Response body for POST /api/genus-consult.

    Null genus with confidence 0.0 is the fail-open default.
    """

    genus: str | None = None
    instances: list[str] = []
    valid: bool = False
    confidence: float = 0.0
