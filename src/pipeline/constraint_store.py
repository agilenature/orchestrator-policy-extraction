"""Constraint store -- manages data/constraints.json with dedup and validation.

Implements CONST-02: Version-controlled JSON storage for durable constraints
extracted from user corrections and blocks.

The store reads/writes a top-level JSON array of constraint objects matching
data/schemas/constraint.schema.json. Deduplication uses deterministic
constraint IDs (SHA-256 hash of text + scope). On duplicate detection,
the existing constraint's examples array is enriched with the new episode
reference.

Exports:
    ConstraintStore
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import jsonschema
from jsonschema import validators
from loguru import logger


class ConstraintStore:
    """Manages data/constraints.json with dedup and JSON Schema validation.

    Usage:
        store = ConstraintStore(
            path=Path("data/constraints.json"),
            schema_path=Path("data/schemas/constraint.schema.json"),
        )
        added = store.add(constraint_dict)
        store.save()

    Args:
        path: Path to the constraints JSON file.
        schema_path: Path to the constraint JSON Schema file.
    """

    def __init__(
        self,
        path: Path = Path("data/constraints.json"),
        schema_path: Path = Path("data/schemas/constraint.schema.json"),
    ) -> None:
        self._path = path
        self._validator = self._load_validator(schema_path)
        self._constraints: list[dict] = self._load()
        self._added_count = 0

        # Build index for fast duplicate lookup
        self._id_index: dict[str, int] = {
            c["constraint_id"]: i for i, c in enumerate(self._constraints)
        }

    def add(self, constraint: dict) -> bool:
        """Add a constraint if not already present (by constraint_id).

        If duplicate: enriches the existing constraint's examples array
        with the new episode reference (if not already present).
        If new: validates against schema, appends to list.
        If validation fails: logs warning, returns False.

        Args:
            constraint: Constraint dict matching constraint.schema.json.

        Returns:
            True if added (new), False if duplicate or validation failed.
        """
        cid = constraint.get("constraint_id", "")

        # Check for duplicate
        if cid in self._id_index:
            # Enrich existing constraint's examples array
            existing = self._constraints[self._id_index[cid]]
            self._enrich_examples(existing, constraint)
            return False

        # Validate against schema
        if self._validator is not None:
            errors = list(self._validator.iter_errors(constraint))
            if errors:
                logger.warning(
                    "Constraint {} failed validation: {}",
                    cid,
                    errors[0].message,
                )
                return False

        self._constraints.append(constraint)
        self._id_index[cid] = len(self._constraints) - 1
        self._added_count += 1
        return True

    def save(self) -> int:
        """Persist constraints to JSON file.

        Creates parent directory if needed. Writes with indent=2 for
        human readability and clean git diffs.

        Returns:
            Total constraint count written.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._constraints, f, indent=2)
            f.write("\n")  # Trailing newline for git-friendliness
        return len(self._constraints)

    @property
    def count(self) -> int:
        """Total number of constraints in the store."""
        return len(self._constraints)

    @property
    def added_count(self) -> int:
        """Number of new constraints added since initialization."""
        return self._added_count

    @property
    def constraints(self) -> list[dict]:
        """Read-only copy of current constraints."""
        return list(self._constraints)

    # --- Temporal status methods (Phase 10) ---

    def get_status_at_time(self, constraint_id: str, session_time: str) -> str | None:
        """Get the constraint's status at a specific point in time.

        Looks up status_history and returns the status from the last entry
        where changed_at <= session_time. Uses datetime comparison for
        timezone safety (not string comparison).

        Args:
            constraint_id: ID of the constraint to look up.
            session_time: ISO 8601 timestamp to evaluate at.

        Returns:
            Status string at that time, None if constraint didn't exist yet
            or constraint_id not found.
        """
        if constraint_id not in self._id_index:
            return None

        constraint = self._constraints[self._id_index[constraint_id]]
        status_history = constraint.get("status_history", [])

        if not status_history:
            # Fallback to current status field
            return constraint.get("status")

        # Parse the session_time
        try:
            target_dt = datetime.fromisoformat(session_time)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid session_time format: {}", session_time
            )
            return None

        # Find the last entry where changed_at <= session_time
        result_status = None
        for entry in status_history:
            try:
                entry_dt = datetime.fromisoformat(entry["changed_at"])
            except (ValueError, TypeError, KeyError):
                continue
            if entry_dt <= target_dt:
                result_status = entry["status"]
            else:
                # status_history is chronological, so we can stop
                break

        return result_status

    def add_status_history_entry(
        self, constraint_id: str, status: str, changed_at: str
    ) -> bool:
        """Append a new entry to a constraint's status_history.

        Args:
            constraint_id: ID of the constraint to update.
            status: New status value (active, candidate, retired).
            changed_at: ISO 8601 timestamp of the status change.

        Returns:
            True if found and updated, False if constraint_id not found.
        """
        if constraint_id not in self._id_index:
            return False

        constraint = self._constraints[self._id_index[constraint_id]]
        history = constraint.setdefault("status_history", [])
        history.append({"status": status, "changed_at": changed_at})
        return True

    def get_by_type(self, constraint_type: str) -> list[dict]:
        """Return constraints filtered by type field.

        Args:
            constraint_type: Type to filter by (e.g., "behavioral_constraint").

        Returns:
            List of constraint dicts matching the type.
        """
        return [
            c for c in self._constraints
            if c.get("type") == constraint_type
        ]

    def get_active_constraints(self) -> list[dict]:
        """Return all constraints with status == 'active'.

        Convenience method for the durability evaluator.

        Returns:
            List of active constraint dicts.
        """
        return [
            c for c in self._constraints
            if c.get("status", "active") == "active"
        ]

    # --- Private helpers ---

    def _load(self) -> list[dict]:
        """Load existing constraints from JSON file.

        Returns empty list if file doesn't exist or contains invalid data.
        """
        if not self._path.exists():
            return []
        try:
            with open(self._path) as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.warning(
                    "Constraints file {} does not contain a JSON array, starting fresh",
                    self._path,
                )
                return []
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Failed to load constraints from {}: {}, starting fresh",
                self._path,
                e,
            )
            return []

    @staticmethod
    def _load_validator(schema_path: Path):
        """Load JSON Schema validator for constraints.

        Returns None if schema file is missing (validation will be skipped).
        """
        if not schema_path.exists():
            logger.warning(
                "Constraint schema not found at {}, validation disabled",
                schema_path,
            )
            return None
        try:
            with open(schema_path) as f:
                schema = json.load(f)
            validator_cls = validators.validator_for(schema)
            return validator_cls(schema, format_checker=jsonschema.FormatChecker())
        except Exception as e:
            logger.warning(
                "Failed to load constraint schema from {}: {}, validation disabled",
                schema_path,
                e,
            )
            return None

    @staticmethod
    def _enrich_examples(existing: dict, new_constraint: dict) -> None:
        """Enrich an existing constraint's examples with the new episode reference.

        Appends new examples only if the episode_id is not already present.
        """
        existing_examples = existing.setdefault("examples", [])
        existing_episode_ids = {
            ex.get("episode_id") for ex in existing_examples
        }

        new_examples = new_constraint.get("examples", [])
        for example in new_examples:
            if example.get("episode_id") not in existing_episode_ids:
                existing_examples.append(example)
