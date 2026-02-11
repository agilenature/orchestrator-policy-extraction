"""Tests for GenusValidator and its five validation layers.

Covers:
1. SchemaLayer: delegates to EpisodeValidator, rejects invalid episodes
2. EvidenceGroundingLayer: warnings for mode-specific evidence gaps
3. NonContradictionLayer: warnings for mode/gate contradictions
4. ConstraintEnforcementLayer: severity-aware constraint checking
5. EpisodeIntegrityLayer: structural integrity checks
6. GenusValidator: composed validation, warning vs error distinction
"""

from __future__ import annotations

import copy

import pytest

from src.pipeline.validation.layers import (
    EvidenceGroundingLayer,
    NonContradictionLayer,
    ConstraintEnforcementLayer,
    EpisodeIntegrityLayer,
    SchemaLayer,
)
from src.pipeline.validation.genus_validator import GenusValidator
from src.pipeline.episode_validator import EpisodeValidator


# --- Fixtures ---


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


@pytest.fixture
def episode_validator() -> EpisodeValidator:
    """Create a real EpisodeValidator for SchemaLayer tests."""
    return EpisodeValidator()


@pytest.fixture
def sample_constraints() -> list[dict]:
    """Sample constraints for ConstraintEnforcementLayer tests."""
    return [
        {
            "constraint_id": "c-001",
            "text": "Never push to main directly",
            "severity": "forbidden",
            "scope": {"paths": ["src/"]},
            "detection_hints": ["git push origin main"],
        },
        {
            "constraint_id": "c-002",
            "text": "Requires approval for database changes",
            "severity": "requires_approval",
            "scope": {"paths": ["src/db/", "migrations/"]},
            "detection_hints": ["ALTER TABLE", "DROP TABLE"],
        },
        {
            "constraint_id": "c-003",
            "text": "Be careful with config changes",
            "severity": "warning",
            "scope": {"paths": ["config/"]},
            "detection_hints": [],
        },
        {
            "constraint_id": "c-004",
            "text": "No force pushing anywhere",
            "severity": "forbidden",
            "scope": {"paths": []},  # repo-wide
            "detection_hints": ["git push --force"],
        },
    ]


# ============================================================
# Layer A: SchemaLayer
# ============================================================


class TestSchemaLayer:
    """Tests for SchemaLayer wrapping EpisodeValidator."""

    def test_valid_episode_passes(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """A schema-valid episode passes Layer A."""
        layer = SchemaLayer(episode_validator)
        is_valid, errors = layer.validate(valid_episode)
        assert is_valid is True
        assert errors == []

    def test_missing_required_field_fails(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Missing a required field causes Layer A to reject."""
        episode = copy.deepcopy(valid_episode)
        del episode["observation"]
        layer = SchemaLayer(episode_validator)
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert len(errors) > 0
        assert any("observation" in e for e in errors)

    def test_invalid_mode_enum_fails(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Invalid mode enum triggers schema layer failure."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "InvalidMode"
        layer = SchemaLayer(episode_validator)
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert len(errors) > 0


# ============================================================
# Layer B: EvidenceGroundingLayer
# ============================================================


class TestEvidenceGroundingLayer:
    """Tests for EvidenceGroundingLayer (warnings only, never hard fail)."""

    def test_implement_with_scope_paths_passes(self, valid_episode: dict) -> None:
        """Implement mode with scope.paths defined is valid."""
        layer = EvidenceGroundingLayer()
        is_valid, errors = layer.validate(valid_episode)
        assert is_valid is True
        assert errors == []

    def test_implement_empty_scope_paths_warns(self, valid_episode: dict) -> None:
        """Implement mode with empty scope.paths produces a warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Implement"
        episode["orchestrator_action"]["scope"] = {"paths": []}
        layer = EvidenceGroundingLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True  # warnings do not fail
        assert len(errors) == 1
        assert errors[0].startswith("warning:evidence:")
        assert "scope paths" in errors[0].lower() or "Implement" in errors[0]

    def test_verify_no_test_results_warns(self, valid_episode: dict) -> None:
        """Verify mode with no test results in outcome produces a warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Verify"
        episode["outcome"] = {
            "reward_signals": {"objective": {}},
        }
        layer = EvidenceGroundingLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert len(errors) >= 1
        assert any(e.startswith("warning:evidence:") for e in errors)
        assert any("Verify" in e or "test" in e.lower() for e in errors)

    def test_integrate_no_git_events_warns(self, valid_episode: dict) -> None:
        """Integrate mode with no git events in outcome produces a warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Integrate"
        episode["outcome"] = {
            "reward_signals": {"objective": {}},
        }
        layer = EvidenceGroundingLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert len(errors) >= 1
        assert any(e.startswith("warning:evidence:") for e in errors)
        assert any("Integrate" in e or "git" in e.lower() for e in errors)

    def test_explore_with_scope_paths_is_valid(self, valid_episode: dict) -> None:
        """Explore mode with scope.paths defined is acceptable (no warning)."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Explore"
        episode["orchestrator_action"]["scope"] = {"paths": ["src/"]}
        layer = EvidenceGroundingLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        # Explore with paths is fine, no evidence warning

    def test_always_returns_true(self, valid_episode: dict) -> None:
        """Evidence grounding layer never returns is_valid=False."""
        # Even with worst-case data, is_valid is always True
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Implement"
        episode["orchestrator_action"]["scope"] = {"paths": []}
        layer = EvidenceGroundingLayer()
        is_valid, _ = layer.validate(episode)
        assert is_valid is True


# ============================================================
# Layer C: NonContradictionLayer
# ============================================================


class TestNonContradictionLayer:
    """Tests for NonContradictionLayer (warnings only)."""

    def test_explore_with_write_allowed_warns(self, valid_episode: dict) -> None:
        """Explore mode with write_allowed gate produces a warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Explore"
        episode["orchestrator_action"]["gates"] = [{"type": "write_allowed"}]
        layer = NonContradictionLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert len(errors) >= 1
        assert any(e.startswith("warning:contradiction:") for e in errors)
        assert any("Explore" in e and "write_allowed" in e for e in errors)

    def test_implement_with_no_write_before_plan_warns(
        self, valid_episode: dict
    ) -> None:
        """Implement mode with no_write_before_plan gate produces a warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Implement"
        episode["orchestrator_action"]["gates"] = [{"type": "no_write_before_plan"}]
        layer = NonContradictionLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert len(errors) >= 1
        assert any(e.startswith("warning:contradiction:") for e in errors)
        assert any("no_write_before_plan" in e for e in errors)

    def test_implement_with_scope_no_contradiction(
        self, valid_episode: dict
    ) -> None:
        """Implement with scope.paths and normal gates is fine (no contradiction)."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Implement"
        episode["orchestrator_action"]["gates"] = [{"type": "run_tests"}]
        layer = NonContradictionLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert errors == []

    def test_always_returns_true(self, valid_episode: dict) -> None:
        """Non-contradiction layer never returns is_valid=False."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Explore"
        episode["orchestrator_action"]["gates"] = [{"type": "write_allowed"}]
        layer = NonContradictionLayer()
        is_valid, _ = layer.validate(episode)
        assert is_valid is True

    def test_no_gates_no_contradiction(self, valid_episode: dict) -> None:
        """Episode with no gates has no contradictions."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["gates"] = []
        layer = NonContradictionLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert errors == []


# ============================================================
# Layer D: ConstraintEnforcementLayer
# ============================================================


class TestConstraintEnforcementLayer:
    """Tests for ConstraintEnforcementLayer (severity-aware)."""

    def test_forbidden_scope_overlap_rejects(
        self, valid_episode: dict, sample_constraints: list[dict]
    ) -> None:
        """Episode overlapping with forbidden constraint scope is rejected."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["scope"] = {"paths": ["src/main.py"]}
        layer = ConstraintEnforcementLayer(sample_constraints)
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("forbidden" in e.lower() or "c-001" in e for e in errors)

    def test_requires_approval_warns(
        self, valid_episode: dict, sample_constraints: list[dict]
    ) -> None:
        """Episode overlapping requires_approval constraint produces warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["scope"] = {"paths": ["src/db/models.py"]}
        layer = ConstraintEnforcementLayer(sample_constraints)
        is_valid, errors = layer.validate(episode)
        # Still has forbidden c-001 (src/ overlap) but also should have requires_approval
        warnings = [e for e in errors if e.startswith("warning:")]
        assert any("requires_approval" in w or "c-002" in w for w in warnings)

    def test_warning_severity_warns(
        self, valid_episode: dict, sample_constraints: list[dict]
    ) -> None:
        """Episode overlapping warning constraint produces warning."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["scope"] = {"paths": ["config/app.yaml"]}
        layer = ConstraintEnforcementLayer(sample_constraints)
        is_valid, errors = layer.validate(episode)
        warnings = [e for e in errors if e.startswith("warning:")]
        assert any("warning" in w.lower() and "c-003" in w for w in warnings)

    def test_no_scope_overlap_passes(
        self, valid_episode: dict, sample_constraints: list[dict]
    ) -> None:
        """Episode with no scope overlap passes (except repo-wide)."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["scope"] = {"paths": ["docs/README.md"]}
        layer = ConstraintEnforcementLayer(sample_constraints)
        is_valid, errors = layer.validate(episode)
        # c-004 is repo-wide (forbidden), so it still fails
        assert is_valid is False
        assert any("c-004" in e for e in errors)

    def test_repo_wide_constraint_applies_to_all(
        self, valid_episode: dict
    ) -> None:
        """Repo-wide constraint (empty paths) applies to all episodes."""
        constraints = [
            {
                "constraint_id": "c-wide",
                "text": "No force pushing",
                "severity": "forbidden",
                "scope": {"paths": []},
                "detection_hints": [],
            },
        ]
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["scope"] = {"paths": ["any/path"]}
        layer = ConstraintEnforcementLayer(constraints)
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("c-wide" in e for e in errors)

    def test_no_constraints_passes(self, valid_episode: dict) -> None:
        """With no constraints, episode passes."""
        layer = ConstraintEnforcementLayer([])
        is_valid, errors = layer.validate(valid_episode)
        assert is_valid is True
        assert errors == []

    def test_requires_approval_does_not_reject(self, valid_episode: dict) -> None:
        """requires_approval severity produces warning, not rejection."""
        constraints = [
            {
                "constraint_id": "c-approval",
                "text": "Needs approval for DB changes",
                "severity": "requires_approval",
                "scope": {"paths": ["tests/"]},
                "detection_hints": [],
            },
        ]
        layer = ConstraintEnforcementLayer(constraints)
        is_valid, errors = layer.validate(valid_episode)
        assert is_valid is True
        assert len(errors) >= 1
        assert all(e.startswith("warning:") for e in errors)


# ============================================================
# Layer E: EpisodeIntegrityLayer
# ============================================================


class TestEpisodeIntegrityLayer:
    """Tests for EpisodeIntegrityLayer (hard failures)."""

    def test_valid_episode_passes(self, valid_episode: dict) -> None:
        """A structurally sound episode passes integrity checks."""
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(valid_episode)
        assert is_valid is True
        assert errors == []

    def test_missing_episode_id_fails(self, valid_episode: dict) -> None:
        """Missing episode_id causes integrity failure."""
        episode = copy.deepcopy(valid_episode)
        del episode["episode_id"]
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("episode_id" in e for e in errors)

    def test_empty_episode_id_fails(self, valid_episode: dict) -> None:
        """Empty string episode_id causes integrity failure."""
        episode = copy.deepcopy(valid_episode)
        episode["episode_id"] = ""
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("episode_id" in e for e in errors)

    def test_missing_provenance_sources_fails(self, valid_episode: dict) -> None:
        """Missing provenance.sources causes integrity failure."""
        episode = copy.deepcopy(valid_episode)
        episode["provenance"] = {"sources": []}
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("provenance" in e.lower() or "sources" in e.lower() for e in errors)

    def test_confidence_out_of_range_fails(self, valid_episode: dict) -> None:
        """Reaction confidence out of [0,1] range causes integrity failure."""
        episode = copy.deepcopy(valid_episode)
        episode["outcome"]["reaction"] = {
            "label": "approve",
            "message": "good",
            "confidence": 1.5,
        }
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("confidence" in e.lower() for e in errors)

    def test_negative_confidence_fails(self, valid_episode: dict) -> None:
        """Negative reaction confidence causes integrity failure."""
        episode = copy.deepcopy(valid_episode)
        episode["outcome"]["reaction"] = {
            "label": "approve",
            "message": "good",
            "confidence": -0.1,
        }
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("confidence" in e.lower() for e in errors)

    def test_valid_confidence_passes(self, valid_episode: dict) -> None:
        """Reaction confidence in [0,1] range passes."""
        episode = copy.deepcopy(valid_episode)
        episode["outcome"]["reaction"] = {
            "label": "approve",
            "message": "good",
            "confidence": 0.85,
        }
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is True
        assert errors == []

    def test_no_provenance_key_fails(self, valid_episode: dict) -> None:
        """Episode missing provenance key entirely fails."""
        episode = copy.deepcopy(valid_episode)
        del episode["provenance"]
        layer = EpisodeIntegrityLayer()
        is_valid, errors = layer.validate(episode)
        assert is_valid is False
        assert any("provenance" in e.lower() for e in errors)


# ============================================================
# GenusValidator (Composed)
# ============================================================


class TestGenusValidatorComposition:
    """Tests for GenusValidator composing all five layers."""

    def test_all_layers_pass(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """When all layers pass, GenusValidator returns (True, [])."""
        gv = GenusValidator.default(
            episode_validator=episode_validator,
            constraints=[],
        )
        is_valid, errors = gv.validate(valid_episode)
        assert is_valid is True
        assert errors == []

    def test_schema_failure_reported(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Schema failure is reported in composite result."""
        episode = copy.deepcopy(valid_episode)
        del episode["observation"]
        gv = GenusValidator.default(
            episode_validator=episode_validator,
            constraints=[],
        )
        is_valid, errors = gv.validate(episode)
        assert is_valid is False
        assert len(errors) > 0

    def test_warnings_do_not_cause_failure(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Warnings from evidence/contradiction layers do not cause overall failure."""
        episode = copy.deepcopy(valid_episode)
        # Set up evidence gap warning: Implement + empty scope
        episode["orchestrator_action"]["scope"] = {"paths": []}
        gv = GenusValidator.default(
            episode_validator=episode_validator,
            constraints=[],
        )
        is_valid, errors = gv.validate(episode)
        assert is_valid is True
        # Should have warning(s) but still pass
        warnings = [e for e in errors if e.startswith("warning:")]
        assert len(warnings) >= 1

    def test_errors_plus_warnings_reported(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Both errors and warnings are collected in the result."""
        episode = copy.deepcopy(valid_episode)
        # Create an integrity error: empty episode_id
        episode["episode_id"] = ""
        # Create evidence warning: Implement + empty scope
        episode["orchestrator_action"]["scope"] = {"paths": []}
        gv = GenusValidator.default(
            episode_validator=episode_validator,
            constraints=[],
        )
        is_valid, errors = gv.validate(episode)
        assert is_valid is False
        # Should have both warnings and hard errors
        warnings = [e for e in errors if e.startswith("warning:")]
        hard_errors = [e for e in errors if not e.startswith("warning:")]
        assert len(warnings) >= 1
        assert len(hard_errors) >= 1

    def test_custom_layers(self, valid_episode: dict) -> None:
        """GenusValidator accepts custom list of layers."""

        class AlwaysFailLayer:
            def validate(self, episode: dict) -> tuple[bool, list[str]]:
                return (False, ["always fails"])

        gv = GenusValidator([AlwaysFailLayer()])
        is_valid, errors = gv.validate(valid_episode)
        assert is_valid is False
        assert "always fails" in errors

    def test_validate_batch(
        self, episode_validator: EpisodeValidator, valid_episode: dict
    ) -> None:
        """Batch validation returns correct summary."""
        invalid = copy.deepcopy(valid_episode)
        del invalid["observation"]
        gv = GenusValidator.default(
            episode_validator=episode_validator,
            constraints=[],
        )
        result = gv.validate_batch([valid_episode, invalid, valid_episode])
        assert result["valid"] == 2
        assert result["invalid"] == 1
        assert len(result["errors"]) == 1

    def test_default_factory_creates_five_layers(
        self, episode_validator: EpisodeValidator
    ) -> None:
        """GenusValidator.default() creates an instance with 5 layers."""
        gv = GenusValidator.default(
            episode_validator=episode_validator,
            constraints=[],
        )
        assert len(gv._layers) == 5


# ============================================================
# Integration: Warning prefix convention
# ============================================================


class TestWarningConvention:
    """Tests that the warning prefix convention is consistent."""

    def test_evidence_warnings_prefixed(self, valid_episode: dict) -> None:
        """EvidenceGroundingLayer warnings start with 'warning:evidence:'."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Implement"
        episode["orchestrator_action"]["scope"] = {"paths": []}
        layer = EvidenceGroundingLayer()
        _, errors = layer.validate(episode)
        for err in errors:
            assert err.startswith("warning:evidence:"), f"Bad prefix: {err}"

    def test_contradiction_warnings_prefixed(self, valid_episode: dict) -> None:
        """NonContradictionLayer warnings start with 'warning:contradiction:'."""
        episode = copy.deepcopy(valid_episode)
        episode["orchestrator_action"]["mode"] = "Explore"
        episode["orchestrator_action"]["gates"] = [{"type": "write_allowed"}]
        layer = NonContradictionLayer()
        _, errors = layer.validate(episode)
        for err in errors:
            assert err.startswith("warning:contradiction:"), f"Bad prefix: {err}"

    def test_constraint_warnings_prefixed(self, valid_episode: dict) -> None:
        """ConstraintEnforcementLayer warnings start with 'warning:constraint:'."""
        constraints = [
            {
                "constraint_id": "c-warn",
                "text": "Watch out",
                "severity": "warning",
                "scope": {"paths": ["tests/"]},
                "detection_hints": [],
            },
        ]
        layer = ConstraintEnforcementLayer(constraints)
        _, errors = layer.validate(valid_episode)
        warnings = [e for e in errors if e.startswith("warning:")]
        assert len(warnings) >= 1
        for w in warnings:
            assert w.startswith("warning:constraint:"), f"Bad prefix: {w}"

    def test_integrity_errors_not_prefixed_warning(
        self, valid_episode: dict
    ) -> None:
        """EpisodeIntegrityLayer errors are NOT prefixed with 'warning:'."""
        episode = copy.deepcopy(valid_episode)
        episode["episode_id"] = ""
        layer = EpisodeIntegrityLayer()
        _, errors = layer.validate(episode)
        for err in errors:
            assert not err.startswith("warning:"), f"Integrity errors should not be warnings: {err}"
