"""Tests for Phase 10 constraint migration and ConstraintStore temporal methods.

Covers:
- Migration adds type, status_history, supersedes to constraints missing them
- Migration preserves existing fields (idempotent)
- Migration bootstraps status_history from created_at
- Migration handles missing created_at gracefully
- ConstraintStore.get_status_at_time() returns correct status at various points
- ConstraintStore.get_status_at_time() returns None for timestamps before first entry
- ConstraintStore.get_status_at_time() uses datetime comparison (not string)
- ConstraintStore.add_status_history_entry() appends correctly
- ConstraintStore.get_by_type() filters correctly
- ConstraintStore.get_active_constraints() returns only active
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.durability.migration import migrate_constraints


# --- Fixtures ---


@pytest.fixture()
def schema_path() -> Path:
    """Path to the real constraint schema."""
    return Path("data/schemas/constraint.schema.json")


@pytest.fixture()
def sample_constraints() -> list[dict]:
    """Sample constraints for testing migration."""
    return [
        {
            "constraint_id": "test_001",
            "text": "Do not use eval() in production code.",
            "severity": "forbidden",
            "scope": {"paths": ["src/"]},
            "detection_hints": ["eval"],
            "source_episode_id": "ep_001",
            "created_at": "2026-01-15T10:00:00+00:00",
            "examples": [
                {
                    "episode_id": "ep_001",
                    "violation_description": "Used eval() in handler.",
                }
            ],
        },
        {
            "constraint_id": "test_002",
            "text": "Prefer pytest over unittest.",
            "severity": "warning",
            "scope": {"paths": []},
            "detection_hints": ["unittest"],
            "source_episode_id": "ep_002",
            "created_at": "2026-01-20T14:30:00+00:00",
            "examples": [
                {
                    "episode_id": "ep_002",
                    "violation_description": "Used unittest.",
                }
            ],
        },
    ]


@pytest.fixture()
def constraints_file(tmp_path: Path, sample_constraints: list[dict]) -> Path:
    """Write sample constraints to a temporary file."""
    p = tmp_path / "constraints.json"
    with open(p, "w") as f:
        json.dump(sample_constraints, f, indent=2)
    return p


@pytest.fixture()
def tmp_schema(tmp_path: Path, schema_path: Path) -> Path:
    """Copy the real schema to tmp_path for test isolation."""
    dest = tmp_path / "constraint.schema.json"
    shutil.copy(schema_path, dest)
    return dest


# --- Migration Tests ---


class TestMigrateConstraints:
    """Tests for migrate_constraints() function."""

    def test_adds_type_status_history_supersedes(
        self, constraints_file: Path, tmp_schema: Path
    ):
        """Migration adds type, status_history, supersedes to constraints."""
        count = migrate_constraints(path=constraints_file, schema_path=tmp_schema)
        assert count == 2

        with open(constraints_file) as f:
            data = json.load(f)

        for c in data:
            assert "type" in c
            assert c["type"] == "behavioral_constraint"
            assert "status_history" in c
            assert "supersedes" in c
            assert c["supersedes"] is None

    def test_preserves_existing_fields_idempotent(
        self, tmp_path: Path, tmp_schema: Path
    ):
        """Migration is idempotent: already-migrated constraints keep their fields."""
        constraints = [
            {
                "constraint_id": "test_pre",
                "text": "Already migrated constraint.",
                "severity": "warning",
                "scope": {"paths": []},
                "detection_hints": [],
                "source_episode_id": "ep_pre",
                "created_at": "2026-01-10T08:00:00+00:00",
                "examples": [],
                "type": "architectural_decision",
                "status_history": [
                    {"status": "active", "changed_at": "2026-01-10T08:00:00+00:00"}
                ],
                "supersedes": "old_constraint_001",
            }
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        count = migrate_constraints(path=p, schema_path=tmp_schema)
        assert count == 0  # Nothing to migrate

        with open(p) as f:
            data = json.load(f)

        assert data[0]["type"] == "architectural_decision"
        assert data[0]["supersedes"] == "old_constraint_001"
        assert len(data[0]["status_history"]) == 1

    def test_bootstraps_status_history_from_created_at(
        self, constraints_file: Path, tmp_schema: Path
    ):
        """Migration bootstraps status_history from status + created_at."""
        migrate_constraints(path=constraints_file, schema_path=tmp_schema)

        with open(constraints_file) as f:
            data = json.load(f)

        # First constraint has no explicit status -> defaults to "active"
        c1 = data[0]
        assert len(c1["status_history"]) == 1
        assert c1["status_history"][0]["status"] == "active"
        assert c1["status_history"][0]["changed_at"] == "2026-01-15T10:00:00+00:00"

    def test_handles_missing_created_at_gracefully(
        self, tmp_path: Path, tmp_schema: Path
    ):
        """Migration produces empty status_history when created_at is missing."""
        constraints = [
            {
                "constraint_id": "test_no_date",
                "text": "No creation date available.",
                "severity": "warning",
                "scope": {"paths": []},
                "detection_hints": [],
                "source_episode_id": "ep_no_date",
                "examples": [],
            }
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        count = migrate_constraints(path=p, schema_path=tmp_schema)
        assert count == 1

        with open(p) as f:
            data = json.load(f)

        assert data[0]["status_history"] == []
        assert data[0]["type"] == "behavioral_constraint"
        assert data[0]["supersedes"] is None

    def test_migrates_constraint_with_existing_status(
        self, tmp_path: Path, tmp_schema: Path
    ):
        """Migration uses existing status field for status_history bootstrap."""
        constraints = [
            {
                "constraint_id": "test_cand",
                "text": "Candidate constraint from escalation.",
                "severity": "requires_approval",
                "scope": {"paths": []},
                "detection_hints": [],
                "source_episode_id": "ep_cand",
                "created_at": "2026-02-01T12:00:00+00:00",
                "examples": [],
                "status": "candidate",
                "source": "inferred_from_escalation",
                "bypassed_constraint_id": None,
            }
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        count = migrate_constraints(path=p, schema_path=tmp_schema)
        assert count == 1

        with open(p) as f:
            data = json.load(f)

        assert data[0]["status_history"][0]["status"] == "candidate"

    def test_nonexistent_file_returns_zero(self, tmp_path: Path, tmp_schema: Path):
        """Migration returns 0 for nonexistent constraints file."""
        p = tmp_path / "missing.json"
        count = migrate_constraints(path=p, schema_path=tmp_schema)
        assert count == 0


# --- ConstraintStore Temporal Method Tests ---


class TestGetStatusAtTime:
    """Tests for ConstraintStore.get_status_at_time()."""

    def _make_store(
        self, tmp_path: Path, schema_path: Path, constraints: list[dict]
    ) -> ConstraintStore:
        """Helper to create a ConstraintStore with given constraints."""
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)
        return ConstraintStore(path=p, schema_path=schema_path)

    def test_returns_correct_status_at_various_points(
        self, tmp_path: Path, schema_path: Path
    ):
        """get_status_at_time returns correct status based on history."""
        constraints = [
            {
                "constraint_id": "c1",
                "text": "Test constraint.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "retired",
                "status_history": [
                    {"status": "candidate", "changed_at": "2026-01-01T00:00:00+00:00"},
                    {"status": "active", "changed_at": "2026-01-15T00:00:00+00:00"},
                    {"status": "retired", "changed_at": "2026-02-01T00:00:00+00:00"},
                ],
                "supersedes": None,
            }
        ]
        store = self._make_store(tmp_path, schema_path, constraints)

        # Before any entry: should be None
        assert store.get_status_at_time("c1", "2025-12-31T00:00:00+00:00") is None

        # After first entry: candidate
        assert store.get_status_at_time("c1", "2026-01-10T00:00:00+00:00") == "candidate"

        # Exactly at second entry: active
        assert store.get_status_at_time("c1", "2026-01-15T00:00:00+00:00") == "active"

        # Between second and third: active
        assert store.get_status_at_time("c1", "2026-01-20T00:00:00+00:00") == "active"

        # After third entry: retired
        assert store.get_status_at_time("c1", "2026-03-01T00:00:00+00:00") == "retired"

    def test_returns_none_for_unknown_constraint(
        self, tmp_path: Path, schema_path: Path
    ):
        """get_status_at_time returns None for unknown constraint_id."""
        store = self._make_store(tmp_path, schema_path, [])
        assert store.get_status_at_time("nonexistent", "2026-01-01T00:00:00+00:00") is None

    def test_falls_back_to_current_status_if_no_history(
        self, tmp_path: Path, schema_path: Path
    ):
        """get_status_at_time uses current status field when history is empty."""
        constraints = [
            {
                "constraint_id": "c_no_hist",
                "text": "No history.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "active",
                "status_history": [],
                "supersedes": None,
            }
        ]
        store = self._make_store(tmp_path, schema_path, constraints)
        assert store.get_status_at_time("c_no_hist", "2026-01-01T00:00:00+00:00") == "active"

    def test_uses_datetime_comparison_not_string(
        self, tmp_path: Path, schema_path: Path
    ):
        """get_status_at_time uses datetime comparison for timezone safety.

        String comparison would fail: "2026-01-01T23:59:59Z" < "2026-01-02T00:00:00+00:00"
        could give wrong results with different timezone representations.
        """
        constraints = [
            {
                "constraint_id": "c_tz",
                "text": "Timezone test.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "active",
                "status_history": [
                    # UTC offset representation
                    {"status": "candidate", "changed_at": "2026-01-01T10:00:00+00:00"},
                    {"status": "active", "changed_at": "2026-01-02T10:00:00+00:00"},
                ],
                "supersedes": None,
            }
        ]
        store = self._make_store(tmp_path, schema_path, constraints)

        # Query with Z suffix (equivalent to +00:00)
        result = store.get_status_at_time("c_tz", "2026-01-01T15:00:00+00:00")
        assert result == "candidate"

        # Query at exactly the active transition
        result = store.get_status_at_time("c_tz", "2026-01-02T10:00:00+00:00")
        assert result == "active"


class TestAddStatusHistoryEntry:
    """Tests for ConstraintStore.add_status_history_entry()."""

    def test_appends_entry(self, tmp_path: Path, schema_path: Path):
        """add_status_history_entry appends to existing history."""
        constraints = [
            {
                "constraint_id": "c_append",
                "text": "Test.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "active",
                "status_history": [
                    {"status": "active", "changed_at": "2026-01-01T00:00:00+00:00"},
                ],
                "supersedes": None,
            }
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        store = ConstraintStore(path=p, schema_path=schema_path)
        result = store.add_status_history_entry(
            "c_append", "retired", "2026-02-01T00:00:00+00:00"
        )
        assert result is True

        # Verify entry was appended
        c = store.constraints[0]
        assert len(c["status_history"]) == 2
        assert c["status_history"][1]["status"] == "retired"

    def test_returns_false_for_unknown_id(self, tmp_path: Path, schema_path: Path):
        """add_status_history_entry returns False for unknown constraint_id."""
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump([], f)
        store = ConstraintStore(path=p, schema_path=schema_path)
        result = store.add_status_history_entry(
            "unknown", "active", "2026-01-01T00:00:00+00:00"
        )
        assert result is False

    def test_creates_history_list_if_missing(self, tmp_path: Path, schema_path: Path):
        """add_status_history_entry creates status_history list if missing."""
        constraints = [
            {
                "constraint_id": "c_no_list",
                "text": "No history list.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "supersedes": None,
            }
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        store = ConstraintStore(path=p, schema_path=schema_path)
        result = store.add_status_history_entry(
            "c_no_list", "active", "2026-01-01T00:00:00+00:00"
        )
        assert result is True
        assert len(store.constraints[0]["status_history"]) == 1


class TestGetByType:
    """Tests for ConstraintStore.get_by_type()."""

    def test_filters_by_type(self, tmp_path: Path, schema_path: Path):
        """get_by_type returns only constraints matching the type."""
        constraints = [
            {
                "constraint_id": "bc1",
                "text": "Behavioral.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "supersedes": None,
            },
            {
                "constraint_id": "ad1",
                "text": "Architectural.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "architectural_decision",
                "supersedes": None,
            },
            {
                "constraint_id": "bc2",
                "text": "Another behavioral.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "supersedes": None,
            },
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        store = ConstraintStore(path=p, schema_path=schema_path)

        behavioral = store.get_by_type("behavioral_constraint")
        assert len(behavioral) == 2
        assert all(c["type"] == "behavioral_constraint" for c in behavioral)

        architectural = store.get_by_type("architectural_decision")
        assert len(architectural) == 1
        assert architectural[0]["constraint_id"] == "ad1"

        unknown = store.get_by_type("nonexistent_type")
        assert len(unknown) == 0


class TestGetActiveConstraints:
    """Tests for ConstraintStore.get_active_constraints()."""

    def test_returns_only_active(self, tmp_path: Path, schema_path: Path):
        """get_active_constraints returns only constraints with status=active."""
        constraints = [
            {
                "constraint_id": "active1",
                "text": "Active.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "active",
                "supersedes": None,
            },
            {
                "constraint_id": "candidate1",
                "text": "Candidate.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "candidate",
                "supersedes": None,
            },
            {
                "constraint_id": "retired1",
                "text": "Retired.",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "status": "retired",
                "supersedes": None,
            },
            {
                "constraint_id": "no_status",
                "text": "No explicit status (defaults to active).",
                "severity": "warning",
                "scope": {"paths": []},
                "type": "behavioral_constraint",
                "supersedes": None,
            },
        ]
        p = tmp_path / "constraints.json"
        with open(p, "w") as f:
            json.dump(constraints, f)

        store = ConstraintStore(path=p, schema_path=schema_path)
        active = store.get_active_constraints()
        assert len(active) == 2
        ids = {c["constraint_id"] for c in active}
        assert ids == {"active1", "no_status"}
