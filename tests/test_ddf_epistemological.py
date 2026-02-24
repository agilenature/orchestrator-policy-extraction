"""Tests for epistemological origin classification (DDF-07).

Covers:
- classify_epistemological_origin for reactive/principled/inductive episodes
- ConstraintExtractor integration (sets both fields)
- ConstraintStore backward compatibility (legacy constraints get defaults)
- Constraint schema validation with new fields
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.ddf.epistemological import classify_epistemological_origin
from src.pipeline.constraint_extractor import ConstraintExtractor
from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.models.config import PipelineConfig


# --- classify_epistemological_origin tests ---


class TestClassifyEpistemologicalOrigin:
    """Tests for the classify_epistemological_origin function."""

    def test_classify_block_episode_is_reactive(self):
        """Block reaction -> reactive with confidence 0.9."""
        episode = {
            "outcome": {"reaction": {"label": "block", "message": "Stop that"}},
            "mode": "Implement",
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "reactive"
        assert confidence == 0.9

    def test_classify_correct_episode_is_reactive(self):
        """Correct reaction -> reactive with confidence 0.8."""
        episode = {
            "outcome": {"reaction": {"label": "correct", "message": "Fix it"}},
            "mode": "Implement",
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "reactive"
        assert confidence == 0.8

    def test_escalate_mode_not_reactive(self):
        """Block reaction with ESCALATE mode should NOT be reactive."""
        episode = {
            "outcome": {"reaction": {"label": "block", "message": "Stop"}},
            "mode": "ESCALATE",
        }
        origin, confidence = classify_epistemological_origin(episode)
        # Falls through to default since no constraints_in_force
        assert origin == "principled"
        assert confidence == 1.0

    def test_classify_supervised_is_principled(self):
        """SUPERVISED mode -> principled with confidence 0.7."""
        episode = {
            "outcome": {"reaction": {"label": "approve", "message": "OK"}},
            "mode": "SUPERVISED",
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "principled"
        assert confidence == 0.7

    def test_classify_with_constraints_in_force_is_principled(self):
        """Active constraints in observation context -> principled with confidence 0.7."""
        episode = {
            "outcome": {"reaction": {"label": "approve", "message": "Good"}},
            "mode": "Implement",
            "observation": {
                "context": {
                    "constraints_in_force": ["no-rm-rf", "always-test"],
                }
            },
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "principled"
        assert confidence == 0.7

    def test_classify_with_many_examples_is_inductive(self):
        """3+ examples -> inductive with confidence 0.6."""
        episode = {
            "outcome": {},
            "mode": "Verify",
            "examples": [
                {"episode_id": "ep1", "violation_description": "x"},
                {"episode_id": "ep2", "violation_description": "y"},
                {"episode_id": "ep3", "violation_description": "z"},
            ],
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "inductive"
        assert confidence == 0.6

    def test_classify_with_many_detection_hints_is_inductive(self):
        """3+ detection hints -> inductive with confidence 0.6."""
        episode = {
            "outcome": {},
            "mode": "Verify",
            "detection_hints": ["pattern_a", "pattern_b", "pattern_c"],
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "inductive"
        assert confidence == 0.6

    def test_classify_default_is_principled(self):
        """No matching conditions -> principled with confidence 1.0."""
        episode = {
            "outcome": {"reaction": {"label": "approve", "message": "OK"}},
            "mode": "Explore",
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "principled"
        assert confidence == 1.0

    def test_classify_empty_episode(self):
        """Empty episode dict -> default principled."""
        origin, confidence = classify_epistemological_origin({})
        assert origin == "principled"
        assert confidence == 1.0

    def test_classify_reactive_takes_priority_over_principled(self):
        """Reactive check runs before principled check."""
        episode = {
            "outcome": {"reaction": {"label": "block", "message": "Stop"}},
            "mode": "SUPERVISED",  # Would match principled, but reactive wins
        }
        # SUPERVISED mode should not block reactive since mode != ESCALATE
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "reactive"
        assert confidence == 0.9


# --- ConstraintExtractor integration tests ---


class TestExtractorSetsEpistemologicalFields:
    """Tests that ConstraintExtractor.extract() sets both epistemological fields."""

    def test_extractor_sets_epistemological_fields(self):
        """ConstraintExtractor.extract() includes epistemological_origin and confidence."""
        config = PipelineConfig(
            constraint_patterns={
                "forbidden": ["don't", "never"],
                "required": ["must", "always"],
                "preferred": ["use", "prefer"],
            }
        )
        extractor = ConstraintExtractor(config)

        episode = {
            "episode_id": "ep-001",
            "outcome": {
                "reaction": {"label": "block", "message": "Don't use eval()"}
            },
            "mode": "Implement",
            "timestamp": "2026-01-01T00:00:00Z",
        }

        constraint = extractor.extract(episode)
        assert constraint is not None
        assert constraint["epistemological_origin"] == "reactive"
        assert constraint["epistemological_confidence"] == 0.9

    def test_extractor_correct_reaction_reactive(self):
        """Correct reaction gets reactive origin with confidence 0.8."""
        config = PipelineConfig(
            constraint_patterns={
                "forbidden": ["don't", "never"],
                "required": ["must"],
                "preferred": ["use"],
            }
        )
        extractor = ConstraintExtractor(config)

        episode = {
            "episode_id": "ep-002",
            "outcome": {
                "reaction": {"label": "correct", "message": "Use imports not eval"}
            },
            "mode": "Implement",
            "timestamp": "2026-01-01T00:00:00Z",
        }

        constraint = extractor.extract(episode)
        assert constraint is not None
        assert constraint["epistemological_origin"] == "reactive"
        assert constraint["epistemological_confidence"] == 0.8


# --- ConstraintStore backward compatibility tests ---


class TestConstraintStoreBackwardCompat:
    """Tests that ConstraintStore handles legacy constraints without epistemological fields."""

    def test_constraint_store_reads_legacy(self, tmp_path):
        """Old constraint without epistemological fields gets defaults."""
        constraints_file = tmp_path / "constraints.json"
        legacy_data = [
            {
                "constraint_id": "abc123",
                "text": "Never use eval.",
                "severity": "forbidden",
                "scope": {"paths": []},
            }
        ]
        constraints_file.write_text(json.dumps(legacy_data))

        store = ConstraintStore(
            path=constraints_file,
            schema_path=Path("data/schemas/constraint.schema.json"),
        )

        constraints = store.constraints
        assert len(constraints) == 1
        assert constraints[0]["epistemological_origin"] == "principled"
        assert constraints[0]["epistemological_confidence"] == 1.0

    def test_constraint_store_writes_new_fields(self, tmp_path):
        """Saved constraint includes both epistemological fields."""
        constraints_file = tmp_path / "constraints.json"
        constraints_file.write_text("[]")

        store = ConstraintStore(
            path=constraints_file,
            schema_path=Path("data/schemas/constraint.schema.json"),
        )
        store.add({
            "constraint_id": "test-001",
            "text": "Always test first.",
            "severity": "warning",
            "scope": {"paths": []},
            "epistemological_origin": "reactive",
            "epistemological_confidence": 0.9,
        })
        store.save()

        # Reload and check
        with open(constraints_file) as f:
            saved = json.load(f)

        assert saved[0]["epistemological_origin"] == "reactive"
        assert saved[0]["epistemological_confidence"] == 0.9

    def test_constraint_store_preserves_existing_values(self, tmp_path):
        """Constraints with existing epistemological fields are not overwritten."""
        constraints_file = tmp_path / "constraints.json"
        data = [
            {
                "constraint_id": "abc456",
                "text": "Use strict mode.",
                "severity": "warning",
                "scope": {"paths": []},
                "epistemological_origin": "inductive",
                "epistemological_confidence": 0.6,
            }
        ]
        constraints_file.write_text(json.dumps(data))

        store = ConstraintStore(
            path=constraints_file,
            schema_path=Path("data/schemas/constraint.schema.json"),
        )
        constraints = store.constraints
        assert constraints[0]["epistemological_origin"] == "inductive"
        assert constraints[0]["epistemological_confidence"] == 0.6


# --- Schema validation tests ---


class TestConstraintSchemaValidation:
    """Tests that constraint schema validates with epistemological fields."""

    def test_constraint_schema_validates(self):
        """Constraint with epistemological_origin passes schema validation."""
        import jsonschema

        schema_path = Path("data/schemas/constraint.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        constraint = {
            "constraint_id": "schema-test-001",
            "text": "Always validate input.",
            "severity": "warning",
            "scope": {"paths": []},
            "epistemological_origin": "principled",
            "epistemological_confidence": 0.7,
        }

        # Should not raise
        jsonschema.validate(constraint, schema)

    def test_constraint_schema_rejects_invalid_origin(self):
        """Invalid epistemological_origin value fails schema validation."""
        import jsonschema

        schema_path = Path("data/schemas/constraint.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        constraint = {
            "constraint_id": "schema-test-002",
            "text": "Always validate input.",
            "severity": "warning",
            "scope": {"paths": []},
            "epistemological_origin": "invalid_value",
            "epistemological_confidence": 0.7,
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(constraint, schema)

    def test_constraint_schema_rejects_out_of_range_confidence(self):
        """Confidence > 1.0 fails schema validation."""
        import jsonschema

        schema_path = Path("data/schemas/constraint.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        constraint = {
            "constraint_id": "schema-test-003",
            "text": "Always validate.",
            "severity": "warning",
            "scope": {"paths": []},
            "epistemological_origin": "reactive",
            "epistemological_confidence": 1.5,
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(constraint, schema)
