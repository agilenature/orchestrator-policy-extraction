"""Tests for EpisodeValidator.

Covers:
1. Valid episode passes validation
2. Missing required field fails (remove observation)
3. Invalid mode enum fails (mode = "InvalidMode")
4. Invalid reaction label fails
5. Invalid confidence range fails (confidence = 1.5)
6. Empty provenance sources fails (sources = [])
7. Invalid timestamp format fails
8. Batch validation returns correct counts
"""

from __future__ import annotations

import copy

import pytest

from src.pipeline.episode_validator import EpisodeValidator


@pytest.fixture
def validator() -> EpisodeValidator:
    """Create an EpisodeValidator with the default schema path."""
    return EpisodeValidator()


@pytest.fixture
def valid_episode() -> dict:
    """A minimal valid episode dict matching the JSON Schema."""
    return {
        "episode_id": "test-001",
        "timestamp": "2024-01-01T00:00:00Z",
        "project": {
            "repo_path": "/test/repo",
        },
        "observation": {
            "repo_state": {
                "changed_files": ["src/main.py"],
                "diff_stat": {"files": 1, "insertions": 10, "deletions": 2},
            },
            "quality_state": {
                "tests": {"status": "pass"},
                "lint": {"status": "unknown"},
            },
            "context": {
                "recent_summary": "Just implemented feature X",
                "open_questions": [],
                "constraints_in_force": [],
            },
        },
        "orchestrator_action": {
            "mode": "Implement",
            "goal": "Add tests for feature X",
            "scope": {"paths": ["tests/"]},
            "executor_instruction": "Write unit tests for the new feature",
            "gates": [{"type": "run_tests"}],
            "risk": "low",
        },
        "outcome": {
            "executor_effects": {
                "tool_calls_count": 5,
                "files_touched": ["tests/test_feature.py"],
                "commands_ran": ["pytest tests/"],
            },
            "quality": {
                "tests_status": "pass",
                "lint_status": "pass",
                "diff_stat": {"files": 1, "insertions": 30, "deletions": 0},
            },
            "reward_signals": {
                "objective": {
                    "tests": 1.0,
                    "lint": 1.0,
                    "diff_risk": 0.1,
                },
            },
        },
        "provenance": {
            "sources": [
                {"type": "claude_jsonl", "ref": "session_abc123.jsonl:100-200"},
            ],
        },
    }


class TestEpisodeValidatorValid:
    """Tests for valid episode validation."""

    def test_valid_episode_passes(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """A well-formed episode passes validation."""
        is_valid, errors = validator.validate(valid_episode)
        assert is_valid, f"Valid episode should pass, but got errors: {errors}"
        assert errors == []

    def test_valid_episode_with_optional_fields(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """A valid episode with optional fields passes validation."""
        episode = copy.deepcopy(valid_episode)
        episode["phase"] = "01-foundation"
        episode["task_id"] = "TASK-001"
        episode["labels"] = {"episode_type": "decision_point", "notes": "test note"}
        episode["outcome"]["reaction"] = {
            "label": "approve",
            "message": "Looks good",
            "confidence": 0.9,
        }
        episode["constraints_extracted"] = [
            {
                "constraint_id": "c-001",
                "text": "Never push to main directly",
                "severity": "forbidden",
                "scope": {"paths": [".github/"]},
                "detection_hints": ["git push origin main"],
            }
        ]

        is_valid, errors = validator.validate(episode)
        assert is_valid, f"Valid episode with optionals should pass, got: {errors}"


class TestEpisodeValidatorMissingFields:
    """Tests for missing required fields."""

    def test_missing_observation_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Removing a required field causes validation failure."""
        episode = copy.deepcopy(valid_episode)
        del episode["observation"]
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("observation" in e for e in errors), f"Expected observation error, got: {errors}"

    def test_missing_episode_id_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Removing episode_id causes validation failure."""
        episode = copy.deepcopy(valid_episode)
        del episode["episode_id"]
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("episode_id" in e for e in errors), f"Expected episode_id error, got: {errors}"


class TestEpisodeValidatorEnumViolations:
    """Tests for enum value violations."""

    def test_invalid_mode_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """An invalid mode enum value fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "InvalidMode"
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("mode" in e.lower() or "InvalidMode" in e for e in errors), (
            f"Expected mode error, got: {errors}"
        )

    def test_invalid_reaction_label_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """An invalid reaction label fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["outcome"]["reaction"] = {
            "label": "invalid_label",
            "message": "test",
            "confidence": 0.5,
        }
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("label" in e.lower() or "invalid_label" in e for e in errors), (
            f"Expected label error, got: {errors}"
        )

    def test_invalid_risk_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """An invalid risk value fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["risk"] = "extreme"
        is_valid, errors = validator.validate(episode)
        assert not is_valid


class TestEpisodeValidatorConfidence:
    """Tests for confidence range validation."""

    def test_confidence_above_1_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Confidence > 1.0 fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["outcome"]["reaction"] = {
            "label": "approve",
            "message": "looks good",
            "confidence": 1.5,
        }
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("confidence" in e.lower() or "1.5" in e for e in errors), (
            f"Expected confidence error, got: {errors}"
        )

    def test_confidence_below_0_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Confidence < 0.0 fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["outcome"]["reaction"] = {
            "label": "approve",
            "message": "looks good",
            "confidence": -0.1,
        }
        is_valid, errors = validator.validate(episode)
        assert not is_valid


class TestEpisodeValidatorProvenance:
    """Tests for provenance validation."""

    def test_empty_provenance_sources_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Empty provenance sources list fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["provenance"]["sources"] = []
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("source" in e.lower() for e in errors), (
            f"Expected provenance source error, got: {errors}"
        )


class TestEpisodeValidatorTimestamp:
    """Tests for timestamp validation."""

    def test_invalid_timestamp_format_fails(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """An invalid timestamp format fails validation."""
        episode = copy.deepcopy(valid_episode)
        episode["timestamp"] = "not-a-timestamp"
        is_valid, errors = validator.validate(episode)
        assert not is_valid
        assert any("timestamp" in e.lower() or "date" in e.lower() or "format" in e.lower() for e in errors), (
            f"Expected timestamp format error, got: {errors}"
        )


class TestEpisodeValidatorBatch:
    """Tests for batch validation."""

    def test_batch_returns_correct_counts(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Batch validation returns correct valid/invalid counts."""
        invalid_episode = copy.deepcopy(valid_episode)
        del invalid_episode["observation"]

        episodes = [
            valid_episode,
            invalid_episode,
            copy.deepcopy(valid_episode),
            invalid_episode,
        ]

        result = validator.validate_batch(episodes)
        assert result["valid"] == 2
        assert result["invalid"] == 2
        assert len(result["errors"]) == 2
        # Check error indices
        error_indices = [e["index"] for e in result["errors"]]
        assert error_indices == [1, 3]

    def test_batch_all_valid(
        self, validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Batch with all valid episodes returns zero invalid."""
        episodes = [copy.deepcopy(valid_episode) for _ in range(3)]
        result = validator.validate_batch(episodes)
        assert result["valid"] == 3
        assert result["invalid"] == 0
        assert result["errors"] == []

    def test_batch_empty(self, validator: EpisodeValidator) -> None:
        """Batch with no episodes returns zero counts."""
        result = validator.validate_batch([])
        assert result["valid"] == 0
        assert result["invalid"] == 0
        assert result["errors"] == []
