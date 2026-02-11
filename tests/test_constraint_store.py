"""Tests for ConstraintStore -- JSON file manager with dedup and validation.

Tests cover:
- Basic operations (load, save, count)
- Deduplication (add returns True/False, examples enrichment, idempotency)
- Validation (valid passes, invalid rejected, missing schema graceful)
- Edge cases (empty store, all optional fields, large store)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.constraint_store import ConstraintStore


# --- Helper functions ---


def _make_constraint(
    constraint_id: str = "abc123def456",
    text: str = "Always use type hints in Python functions.",
    severity: str = "requires_approval",
    scope_paths: list[str] | None = None,
    source_episode_id: str = "ep-001",
    created_at: str = "2026-02-11T12:00:00Z",
    detection_hints: list[str] | None = None,
    examples: list[dict] | None = None,
) -> dict:
    """Build a valid constraint dict matching constraint.schema.json."""
    constraint = {
        "constraint_id": constraint_id,
        "text": text,
        "severity": severity,
        "scope": {"paths": scope_paths or []},
    }
    if detection_hints is not None:
        constraint["detection_hints"] = detection_hints
    if source_episode_id is not None:
        constraint["source_episode_id"] = source_episode_id
    if created_at is not None:
        constraint["created_at"] = created_at
    if examples is not None:
        constraint["examples"] = examples
    else:
        constraint["examples"] = [
            {
                "episode_id": source_episode_id,
                "violation_description": text,
            }
        ]
    return constraint


# Schema path for tests (relative to project root)
_SCHEMA_PATH = Path("data/schemas/constraint.schema.json")


# --- Basic Operations ---


class TestBasicOperations:
    """Tests for ConstraintStore load/save/count."""

    def test_store_loads_empty_when_file_does_not_exist(self, tmp_path):
        """Store initializes with empty list when JSON file doesn't exist."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        assert store.count == 0
        assert store.constraints == []

    def test_store_loads_existing_constraints_from_file(self, tmp_path):
        """Store loads existing constraints from a pre-populated JSON file."""
        json_path = tmp_path / "constraints.json"
        existing = [_make_constraint("id-1"), _make_constraint("id-2")]
        json_path.write_text(json.dumps(existing, indent=2))

        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)
        assert store.count == 2
        assert store.constraints[0]["constraint_id"] == "id-1"
        assert store.constraints[1]["constraint_id"] == "id-2"

    def test_save_creates_file_and_writes_constraints(self, tmp_path):
        """save() creates the JSON file and writes constraints."""
        json_path = tmp_path / "subdir" / "constraints.json"
        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)

        store.add(_make_constraint("id-1"))
        store.save()

        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert len(data) == 1
        assert data[0]["constraint_id"] == "id-1"

    def test_save_returns_correct_count(self, tmp_path):
        """save() returns the total number of constraints written."""
        json_path = tmp_path / "constraints.json"
        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)

        store.add(_make_constraint("id-1"))
        store.add(_make_constraint("id-2"))
        result = store.save()

        assert result == 2


# --- Deduplication ---


class TestDeduplication:
    """Tests for constraint deduplication behavior."""

    def test_add_returns_true_for_new_constraint(self, tmp_path):
        """add() returns True when adding a new (non-duplicate) constraint."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        result = store.add(_make_constraint("id-new"))
        assert result is True
        assert store.added_count == 1

    def test_add_returns_false_for_duplicate_constraint_id(self, tmp_path):
        """add() returns False when constraint_id already exists."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        store.add(_make_constraint("id-dup"))
        result = store.add(_make_constraint("id-dup"))
        assert result is False
        assert store.count == 1
        assert store.added_count == 1

    def test_duplicate_detection_enriches_examples_array(self, tmp_path):
        """When adding a duplicate, the existing constraint's examples are enriched."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        first = _make_constraint(
            "id-enrich",
            examples=[{"episode_id": "ep-1", "violation_description": "First violation"}],
        )
        second = _make_constraint(
            "id-enrich",
            examples=[{"episode_id": "ep-2", "violation_description": "Second violation"}],
        )

        store.add(first)
        store.add(second)  # Should enrich, not add

        stored = store.constraints[0]
        assert len(stored["examples"]) == 2
        episode_ids = [ex["episode_id"] for ex in stored["examples"]]
        assert "ep-1" in episode_ids
        assert "ep-2" in episode_ids

    def test_duplicate_enrichment_does_not_add_same_episode_twice(self, tmp_path):
        """Enrichment skips examples with the same episode_id."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        constraint = _make_constraint(
            "id-same",
            examples=[{"episode_id": "ep-1", "violation_description": "Violation"}],
        )

        store.add(constraint)
        # Try to enrich with same episode_id
        store.add(constraint)

        stored = store.constraints[0]
        assert len(stored["examples"]) == 1

    def test_rerun_idempotency_no_new_additions(self, tmp_path):
        """Re-adding the same constraints produces no new additions."""
        json_path = tmp_path / "constraints.json"
        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)

        constraints = [_make_constraint(f"id-{i}") for i in range(5)]
        for c in constraints:
            store.add(c)
        store.save()

        # Reload and re-add the same constraints
        store2 = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)
        for c in constraints:
            result = store2.add(c)
            assert result is False

        assert store2.count == 5
        assert store2.added_count == 0


# --- Validation ---


class TestValidation:
    """Tests for JSON Schema validation in ConstraintStore."""

    def test_valid_constraint_passes_validation(self, tmp_path):
        """A well-formed constraint passes validation and is added."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        constraint = _make_constraint("id-valid")
        result = store.add(constraint)
        assert result is True

    def test_invalid_constraint_missing_required_field_rejected(self, tmp_path):
        """A constraint missing a required field is rejected by validation."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        # Missing 'severity' which is required
        invalid = {
            "constraint_id": "id-invalid",
            "text": "Some constraint",
            "scope": {"paths": []},
        }
        result = store.add(invalid)
        assert result is False
        assert store.count == 0

    def test_invalid_constraint_bad_severity_rejected(self, tmp_path):
        """A constraint with invalid severity enum value is rejected."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        invalid = _make_constraint("id-bad-sev", severity="critical")
        result = store.add(invalid)
        assert result is False
        assert store.count == 0

    def test_missing_schema_file_validation_skipped(self, tmp_path):
        """When schema file is missing, validation is skipped and constraint is added."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=tmp_path / "nonexistent_schema.json",
        )
        constraint = _make_constraint("id-no-schema")
        result = store.add(constraint)
        assert result is True
        assert store.count == 1


# --- Edge Cases ---


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_constraints_serializes_to_empty_array(self, tmp_path):
        """An empty store serializes to [] in JSON."""
        json_path = tmp_path / "constraints.json"
        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)
        store.save()

        data = json.loads(json_path.read_text())
        assert data == []

    def test_constraint_with_all_optional_fields(self, tmp_path):
        """A constraint with all optional fields populated is stored correctly."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        constraint = _make_constraint(
            "id-full",
            detection_hints=["regex", "xml"],
            source_episode_id="ep-full",
            created_at="2026-02-11T12:00:00Z",
            examples=[
                {"episode_id": "ep-full", "violation_description": "Used regex for XML"},
            ],
        )
        result = store.add(constraint)
        assert result is True

        stored = store.constraints[0]
        assert stored["detection_hints"] == ["regex", "xml"]
        assert stored["source_episode_id"] == "ep-full"
        assert stored["created_at"] == "2026-02-11T12:00:00Z"
        assert len(stored["examples"]) == 1

    def test_large_store_loads_correctly(self, tmp_path):
        """A store with 100+ constraints loads and operates correctly."""
        json_path = tmp_path / "constraints.json"

        # Pre-populate with 150 constraints
        constraints = [_make_constraint(f"id-{i:04d}", text=f"Constraint number {i}.") for i in range(150)]
        json_path.write_text(json.dumps(constraints, indent=2))

        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)
        assert store.count == 150

        # Add one more
        new_constraint = _make_constraint("id-new", text="A brand new constraint.")
        result = store.add(new_constraint)
        assert result is True
        assert store.count == 151

        # Duplicate of existing
        dup_result = store.add(_make_constraint("id-0050", text="Constraint number 50."))
        assert dup_result is False
        assert store.count == 151

    def test_corrupted_json_file_handled_gracefully(self, tmp_path):
        """A corrupted JSON file results in empty store (not crash)."""
        json_path = tmp_path / "constraints.json"
        json_path.write_text("this is not valid json{{{")

        store = ConstraintStore(path=json_path, schema_path=_SCHEMA_PATH)
        assert store.count == 0

    def test_constraints_property_returns_copy(self, tmp_path):
        """The constraints property returns a copy, not a reference."""
        store = ConstraintStore(
            path=tmp_path / "constraints.json",
            schema_path=_SCHEMA_PATH,
        )
        store.add(_make_constraint("id-copy"))

        copy = store.constraints
        copy.clear()  # Mutating the copy should not affect the store
        assert store.count == 1
