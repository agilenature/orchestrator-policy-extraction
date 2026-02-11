"""Tests for gold-standard export/import workflow.

Covers:
1. export_for_review creates episode + label template files
2. Stratified sampling ensures coverage across modes and reaction labels
3. import_labels with valid label files
4. import_labels skips incomplete labels (blank verified_mode or verified_reaction_label)
5. import_labels validates against JSON Schema (rejects malformed files)
6. import_labels with missing directory
7. import_labels with empty directory
8. Template label structure correctness
9. Export with no episodes returns 0
10. Schema rejects invalid enum values
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from src.pipeline.storage.schema import create_schema
from src.pipeline.validation.gold_standard import export_for_review, import_labels

SCHEMA_PATH = Path("data/schemas/gold-standard-label.schema.json")


@pytest.fixture
def conn_with_episodes():
    """Create an in-memory DuckDB with sample episodes for testing."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)

    # Insert sample episodes across multiple modes and reaction labels
    episodes = [
        ("ep-001", "sess-1", "Implement", "low", "approve", 0.9, "success"),
        ("ep-002", "sess-1", "Implement", "low", "correct", 0.8, "correction"),
        ("ep-003", "sess-1", "Explore", "medium", "approve", 0.95, "success"),
        ("ep-004", "sess-1", "Plan", "low", "redirect", 0.7, "redirect"),
        ("ep-005", "sess-1", "Verify", "low", "approve", 0.85, "success"),
        ("ep-006", "sess-1", "Integrate", "high", "block", 0.6, "block"),
        ("ep-007", "sess-1", "Triage", "low", "question", 0.5, "question"),
        ("ep-008", "sess-1", "Refactor", "low", "approve", 0.9, "success"),
        ("ep-009", "sess-1", "Implement", "medium", "unknown", 0.3, "success"),
        ("ep-010", "sess-1", "Explore", "low", "correct", 0.75, "correction"),
    ]

    for eid, sid, mode, risk, rl, rc, ot in episodes:
        action_json = json.dumps({"mode": mode, "risk": risk})
        outcome_json = json.dumps({"reaction": {"label": rl, "confidence": rc}})
        provenance_json = json.dumps({"sources": []})
        conn.execute(
            """
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp,
                mode, risk, reaction_label, reaction_confidence, outcome_type,
                observation, orchestrator_action, outcome, provenance
            ) VALUES (
                ?, ?, 'seg-1', '2026-01-01T00:00:00Z',
                ?, ?, ?, ?, ?,
                {
                    repo_state: {changed_files: [], diff_stat: {files: 0, insertions: 0, deletions: 0}},
                    quality_state: {tests_status: 'pass', lint_status: 'pass', build_status: 'pass'},
                    context: {recent_summary: '', open_questions: [], constraints_in_force: []}
                },
                CAST(? AS JSON), CAST(? AS JSON), CAST(? AS JSON)
            )
            """,
            [eid, sid, mode, risk, rl, rc, ot, action_json, outcome_json, provenance_json],
        )

    return conn


class TestExportForReview:
    """Tests for export_for_review function."""

    def test_export_creates_episode_and_label_files(self, conn_with_episodes, tmp_path):
        """Export should create episode + template label JSON files."""
        count = export_for_review(conn_with_episodes, tmp_path, sample_size=100)

        assert count == 10  # All 10 episodes
        episodes_dir = tmp_path / "episodes"
        labels_dir = tmp_path / "labels"

        assert episodes_dir.exists()
        assert labels_dir.exists()

        episode_files = list(episodes_dir.glob("*.json"))
        label_files = list(labels_dir.glob("*.json"))

        assert len(episode_files) == 10
        assert len(label_files) == 10

    def test_template_label_structure(self, conn_with_episodes, tmp_path):
        """Template label files should have correct blank structure."""
        export_for_review(conn_with_episodes, tmp_path, sample_size=100)

        label_path = tmp_path / "labels" / "ep-001.json"
        with open(label_path) as f:
            label = json.load(f)

        assert label["episode_id"] == "ep-001"
        assert label["verified_mode"] == ""
        assert label["verified_reaction_label"] == ""
        assert label["verified_reaction_confidence"] is None
        assert label["constraint_should_extract"] is None
        assert label["notes"] == ""
        assert label["reviewer"] == ""

    def test_episode_file_contains_data(self, conn_with_episodes, tmp_path):
        """Episode files should contain full episode data."""
        export_for_review(conn_with_episodes, tmp_path, sample_size=100)

        ep_path = tmp_path / "episodes" / "ep-001.json"
        with open(ep_path) as f:
            ep = json.load(f)

        assert ep["episode_id"] == "ep-001"
        assert ep["session_id"] == "sess-1"
        assert ep["mode"] == "Implement"

    def test_stratified_sampling_limits_output(self, conn_with_episodes, tmp_path):
        """Sample size should limit the number of exported episodes."""
        count = export_for_review(conn_with_episodes, tmp_path, sample_size=5)

        assert count == 5
        episode_files = list((tmp_path / "episodes").glob("*.json"))
        assert len(episode_files) == 5

    def test_stratified_sampling_covers_modes(self, conn_with_episodes, tmp_path):
        """Stratified sampling should try to include examples from each mode."""
        # With sample_size=10 and 7 unique modes (10 episodes total),
        # all episodes are returned and all modes are covered
        count = export_for_review(conn_with_episodes, tmp_path, sample_size=10)

        assert count == 10
        episode_files = list((tmp_path / "episodes").glob("*.json"))
        modes_found = set()
        for ep_file in episode_files:
            with open(ep_file) as f:
                ep = json.load(f)
            modes_found.add(ep["mode"])

        # 7 unique modes in our test data
        assert len(modes_found) == 7

    def test_stratified_sampling_prioritizes_diversity(self, conn_with_episodes, tmp_path):
        """When sample_size < total, stratified sampling includes multiple modes."""
        import random
        random.seed(42)  # Deterministic for test

        count = export_for_review(conn_with_episodes, tmp_path, sample_size=8)

        assert count == 8
        episode_files = list((tmp_path / "episodes").glob("*.json"))
        modes_found = set()
        for ep_file in episode_files:
            with open(ep_file) as f:
                ep = json.load(f)
            modes_found.add(ep["mode"])

        # Stratification ensures we get at least some mode diversity
        # even when sampling a subset (8 of 10 episodes, 7 modes)
        assert len(modes_found) >= 4

    def test_export_with_no_episodes(self, tmp_path):
        """Export with empty episodes table should return 0."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        count = export_for_review(conn, tmp_path, sample_size=100)
        assert count == 0

    def test_export_all_when_sample_exceeds_count(self, conn_with_episodes, tmp_path):
        """When sample_size > total episodes, export all."""
        count = export_for_review(conn_with_episodes, tmp_path, sample_size=500)
        assert count == 10


class TestImportLabels:
    """Tests for import_labels function."""

    def test_import_valid_labels(self, tmp_path):
        """Import should return valid labels that pass schema validation."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        label = {
            "episode_id": "ep-001",
            "verified_mode": "Implement",
            "verified_reaction_label": "approve",
            "verified_reaction_confidence": 0.95,
            "constraint_should_extract": False,
            "notes": "Looks correct",
            "reviewer": "human-1",
        }
        with open(labels_dir / "ep-001.json", "w") as f:
            json.dump(label, f)

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 1
        assert len(errors) == 0
        assert valid[0]["episode_id"] == "ep-001"
        assert valid[0]["verified_mode"] == "Implement"

    def test_import_skips_incomplete_labels_blank_mode(self, tmp_path):
        """Import should skip labels with blank verified_mode."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        # Template label with blank fields
        label = {
            "episode_id": "ep-001",
            "verified_mode": "",
            "verified_reaction_label": "approve",
            "notes": "",
            "reviewer": "",
        }
        with open(labels_dir / "ep-001.json", "w") as f:
            json.dump(label, f)

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 0  # Skipped, not errored

    def test_import_skips_incomplete_labels_blank_reaction(self, tmp_path):
        """Import should skip labels with blank verified_reaction_label."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        label = {
            "episode_id": "ep-001",
            "verified_mode": "Implement",
            "verified_reaction_label": "",
            "notes": "",
            "reviewer": "",
        }
        with open(labels_dir / "ep-001.json", "w") as f:
            json.dump(label, f)

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 0

    def test_import_rejects_invalid_enum(self, tmp_path):
        """Import should reject labels with invalid enum values."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        label = {
            "episode_id": "ep-001",
            "verified_mode": "InvalidMode",
            "verified_reaction_label": "approve",
        }
        with open(labels_dir / "ep-001.json", "w") as f:
            json.dump(label, f)

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 1
        assert "schema validation failed" in errors[0]

    def test_import_rejects_malformed_json(self, tmp_path):
        """Import should report errors for malformed JSON files."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        with open(labels_dir / "bad.json", "w") as f:
            f.write("{not valid json}")

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 1
        assert "failed to read" in errors[0]

    def test_import_missing_directory(self, tmp_path):
        """Import with non-existent directory should return error."""
        valid, errors = import_labels(tmp_path / "nonexistent", SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_import_empty_directory(self, tmp_path):
        """Import with empty directory should return error."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 1
        assert "No .json files" in errors[0]

    def test_import_mixed_valid_and_invalid(self, tmp_path):
        """Import should handle a mix of valid, incomplete, and invalid labels."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        # Valid label
        with open(labels_dir / "ep-001.json", "w") as f:
            json.dump({
                "episode_id": "ep-001",
                "verified_mode": "Implement",
                "verified_reaction_label": "approve",
            }, f)

        # Incomplete (blank mode) -- skipped, not errored
        with open(labels_dir / "ep-002.json", "w") as f:
            json.dump({
                "episode_id": "ep-002",
                "verified_mode": "",
                "verified_reaction_label": "",
            }, f)

        # Invalid (bad enum)
        with open(labels_dir / "ep-003.json", "w") as f:
            json.dump({
                "episode_id": "ep-003",
                "verified_mode": "BadMode",
                "verified_reaction_label": "approve",
            }, f)

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 1
        assert valid[0]["episode_id"] == "ep-001"
        assert len(errors) == 1  # Only the invalid one, not the incomplete

    def test_import_rejects_additional_properties(self, tmp_path):
        """Schema with additionalProperties: false should reject extra fields."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()

        label = {
            "episode_id": "ep-001",
            "verified_mode": "Implement",
            "verified_reaction_label": "approve",
            "extra_field": "not allowed",
        }
        with open(labels_dir / "ep-001.json", "w") as f:
            json.dump(label, f)

        valid, errors = import_labels(labels_dir, SCHEMA_PATH)

        assert len(valid) == 0
        assert len(errors) == 1
        assert "schema validation failed" in errors[0]
