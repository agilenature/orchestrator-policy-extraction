"""Episode validation against the JSON Schema.

Wraps jsonschema validation with additional business rule checks
for orchestrator decision-point episodes.

Loads data/schemas/orchestrator-episode.schema.json and validates
episode dicts against it using Draft 2020-12.

Exports:
    EpisodeValidator: Validator for episode dicts
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import validators

# Default schema path relative to project root
_DEFAULT_SCHEMA_PATH = Path("data/schemas/orchestrator-episode.schema.json")


class EpisodeValidator:
    """Validates episode dicts against the orchestrator-episode JSON Schema.

    Uses jsonschema with Draft 2020-12 auto-detection and adds
    additional business rule checks beyond what the schema enforces.

    Args:
        schema_path: Path to the JSON Schema file. Defaults to
            data/schemas/orchestrator-episode.schema.json.
    """

    def __init__(self, schema_path: str | Path = _DEFAULT_SCHEMA_PATH) -> None:
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path) as f:
            self._schema = json.load(f)

        # Auto-detect the correct validator class for the schema draft
        validator_cls = validators.validator_for(self._schema)

        # Validate the schema itself
        validator_cls.check_schema(self._schema)

        # Create format checker for date-time etc.
        self._format_checker = jsonschema.FormatChecker()

        # Build the validator instance
        self._validator = validator_cls(
            self._schema,
            format_checker=self._format_checker,
        )

    def validate(self, episode_dict: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate an episode dict against the JSON Schema and business rules.

        Args:
            episode_dict: A dict representing an episode.

        Returns:
            Tuple of (is_valid, error_messages). If is_valid is True,
            error_messages will be empty.
        """
        errors: list[str] = []

        # JSON Schema validation
        for error in self._validator.iter_errors(episode_dict):
            # Build a readable path from the error
            path = ".".join(str(p) for p in error.absolute_path)
            if path:
                errors.append(f"{path}: {error.message}")
            else:
                errors.append(error.message)

        # Additional business rule checks (beyond schema)
        errors.extend(self._check_business_rules(episode_dict))

        return (len(errors) == 0, errors)

    def validate_batch(
        self, episodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Validate a batch of episode dicts.

        Args:
            episodes: List of episode dicts to validate.

        Returns:
            Dict with keys: valid (count), invalid (count), errors (list of
            dicts with index and error messages).
        """
        valid_count = 0
        invalid_count = 0
        all_errors: list[dict[str, Any]] = []

        for i, episode in enumerate(episodes):
            is_valid, error_messages = self.validate(episode)
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
                all_errors.append({"index": i, "errors": error_messages})

        return {
            "valid": valid_count,
            "invalid": invalid_count,
            "errors": all_errors,
        }

    def _check_business_rules(self, episode_dict: dict[str, Any]) -> list[str]:
        """Check business rules beyond what JSON Schema enforces.

        Args:
            episode_dict: A dict representing an episode.

        Returns:
            List of error messages for failed business rules.
        """
        errors: list[str] = []

        # Rule: provenance must have at least 1 source
        provenance = episode_dict.get("provenance", {})
        sources = provenance.get("sources", [])
        if isinstance(sources, list) and len(sources) == 0:
            errors.append("provenance.sources: must have at least 1 source")

        # Rule: reaction confidence must be in [0.0, 1.0]
        outcome = episode_dict.get("outcome", {})
        reaction = outcome.get("reaction")
        if reaction is not None and isinstance(reaction, dict):
            confidence = reaction.get("confidence")
            if confidence is not None and isinstance(confidence, (int, float)):
                if not 0.0 <= confidence <= 1.0:
                    errors.append(
                        f"outcome.reaction.confidence: must be between 0.0 and 1.0, got {confidence}"
                    )

        # Rule: mode must be a valid enum value
        action = episode_dict.get("orchestrator_action", {})
        if isinstance(action, dict):
            mode = action.get("mode")
            valid_modes = {
                "Explore", "Plan", "Implement", "Verify",
                "Integrate", "Triage", "Refactor",
            }
            if mode is not None and mode not in valid_modes:
                errors.append(
                    f"orchestrator_action.mode: must be one of {sorted(valid_modes)}, got '{mode}'"
                )

        # Rule: reaction label must be a valid enum value
        if reaction is not None and isinstance(reaction, dict):
            label = reaction.get("label")
            valid_labels = {
                "approve", "correct", "redirect", "block", "question", "unknown",
            }
            if label is not None and label not in valid_labels:
                errors.append(
                    f"outcome.reaction.label: must be one of {sorted(valid_labels)}, got '{label}'"
                )

        return errors
