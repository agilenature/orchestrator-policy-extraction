"""Validation layer implementations -- stubs for TDD RED phase.

Each layer conforms to the ValidationLayer Protocol:
    validate(episode: dict) -> tuple[bool, list[str]]
"""

from __future__ import annotations

from typing import Any, Protocol


class ValidationLayer(Protocol):
    """Protocol for pluggable validation layers."""

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Return (is_valid, error_messages)."""
        ...


class SchemaLayer:
    """Layer A: Wraps EpisodeValidator for JSON Schema checks."""

    def __init__(self, episode_validator: Any) -> None:
        self._validator = episode_validator

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        raise NotImplementedError("RED phase stub")


class EvidenceGroundingLayer:
    """Layer B: Mode-specific evidence checks (warnings only)."""

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        raise NotImplementedError("RED phase stub")


class NonContradictionLayer:
    """Layer C: Mode/gate consistency checks (warnings only)."""

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        raise NotImplementedError("RED phase stub")


class ConstraintEnforcementLayer:
    """Layer D: Constraint scope/severity checks."""

    def __init__(self, constraints: list[dict[str, Any]] | None = None) -> None:
        self._constraints = constraints or []

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        raise NotImplementedError("RED phase stub")


class EpisodeIntegrityLayer:
    """Layer E: Structural integrity checks."""

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        raise NotImplementedError("RED phase stub")
