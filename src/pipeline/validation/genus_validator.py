"""GenusValidator -- five-layer composed episode validator.

Composes multiple ValidationLayer implementations and returns
combined (bool, list[str]) results. Warnings (prefixed 'warning:')
do not cause overall validation failure.

Exports:
    GenusValidator
"""

from __future__ import annotations

from typing import Any

from src.pipeline.validation.layers import (
    ConstraintEnforcementLayer,
    EpisodeIntegrityLayer,
    EvidenceGroundingLayer,
    NonContradictionLayer,
    SchemaLayer,
)


class GenusValidator:
    """Five-layer genus-based validator per AUTHORITATIVE_DESIGN.md Part 5.

    Runs all validation layers, collects all messages, and separates
    warnings from hard errors. The overall result is:
        - (True, warnings) if no hard errors
        - (False, errors + warnings) if any hard errors

    Args:
        layers: List of objects conforming to the ValidationLayer protocol.
    """

    def __init__(self, layers: list[Any]) -> None:
        self._layers = layers

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Run all layers and return composite result.

        Warnings (prefixed 'warning:') do not cause failure.
        Only non-warning messages count as hard errors.

        Returns:
            Tuple of (is_valid, all_messages). is_valid is True only
            if no hard errors exist.
        """
        all_messages: list[str] = []

        for layer in self._layers:
            _, messages = layer.validate(episode)
            all_messages.extend(messages)

        # Separate warnings from hard errors
        hard_errors = [m for m in all_messages if not m.startswith("warning:")]
        has_errors = len(hard_errors) > 0

        return (not has_errors, all_messages)

    def validate_batch(
        self, episodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Validate a batch of episodes.

        Returns:
            Dict with keys: valid (count), invalid (count), errors
            (list of dicts with index and error messages).
        """
        valid_count = 0
        invalid_count = 0
        all_errors: list[dict[str, Any]] = []

        for i, episode in enumerate(episodes):
            is_valid, messages = self.validate(episode)
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
                all_errors.append({"index": i, "errors": messages})

        return {
            "valid": valid_count,
            "invalid": invalid_count,
            "errors": all_errors,
        }

    @classmethod
    def default(
        cls,
        episode_validator: Any = None,
        constraints: list[dict[str, Any]] | None = None,
    ) -> GenusValidator:
        """Create a GenusValidator with the default five layers.

        Args:
            episode_validator: An EpisodeValidator instance for Layer A.
                If None, creates one with default schema path.
            constraints: List of constraint dicts for Layer D.
                If None, uses empty list.

        Returns:
            GenusValidator with all five layers configured.
        """
        if episode_validator is None:
            from src.pipeline.episode_validator import EpisodeValidator
            episode_validator = EpisodeValidator()

        layers: list[Any] = [
            SchemaLayer(episode_validator),
            EvidenceGroundingLayer(),
            NonContradictionLayer(),
            ConstraintEnforcementLayer(constraints or []),
            EpisodeIntegrityLayer(),
        ]
        return cls(layers)
