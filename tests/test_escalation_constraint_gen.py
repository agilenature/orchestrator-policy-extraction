"""Tests for EscalationConstraintGenerator -- three-tier constraint auto-generation.

TDD RED phase: Tests written against the behavior spec before implementation.
Covers:
- Three-tier severity logic (block->forbidden, silence->requires_approval, approve->None)
- Constraint text template format
- Deterministic constraint ID generation
- Detection hints matching for existing constraints
- Operation type inference from command text
- Resource path inference from bypass_resource field
- Schema compatibility (status=candidate, source=inferred_from_escalation)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.escalation.models import EscalationCandidate
from src.pipeline.escalation.constraint_gen import EscalationConstraintGenerator


# --- Fixtures ---


def _make_candidate(**overrides) -> EscalationCandidate:
    """Create a test EscalationCandidate with sensible defaults."""
    defaults = {
        "session_id": "test-session-001",
        "block_event_id": "evt-block-001",
        "block_event_tag": "O_GATE",
        "bypass_event_id": "evt-bypass-001",
        "bypass_tool_name": "Bash",
        "bypass_command": "git push origin main --force",
        "bypass_resource": "src/",
        "window_turns_used": 2,
        "confidence": 1.0,
        "detector_version": "v1",
    }
    defaults.update(overrides)
    return EscalationCandidate(**defaults)


@pytest.fixture
def generator():
    """Create a default EscalationConstraintGenerator."""
    return EscalationConstraintGenerator()


@pytest.fixture
def candidate():
    """Create a default test candidate."""
    return _make_candidate()


# --- Three-tier severity logic ---


class TestThreeTierSeverity:
    """Test the three-tier reaction -> severity mapping."""

    def test_block_reaction_produces_forbidden(self, generator, candidate):
        """reaction='block' -> severity='forbidden'."""
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert result["severity"] == "forbidden"

    def test_correct_reaction_produces_forbidden(self, generator, candidate):
        """reaction='correct' -> severity='forbidden'."""
        result = generator.generate(candidate, reaction="correct")
        assert result is not None
        assert result["severity"] == "forbidden"

    def test_none_reaction_produces_requires_approval(self, generator, candidate):
        """reaction=None (silence) -> severity='requires_approval'."""
        result = generator.generate(candidate, reaction=None)
        assert result is not None
        assert result["severity"] == "requires_approval"

    def test_approve_reaction_returns_none(self, generator, candidate):
        """reaction='approve' -> None (no constraint generated)."""
        result = generator.generate(candidate, reaction="approve")
        assert result is None

    def test_redirect_reaction_produces_requires_approval(self, generator, candidate):
        """reaction='redirect' -> severity='requires_approval' (treat like silence)."""
        result = generator.generate(candidate, reaction="redirect")
        assert result is not None
        assert result["severity"] == "requires_approval"

    def test_question_reaction_produces_requires_approval(self, generator, candidate):
        """reaction='question' -> severity='requires_approval'."""
        result = generator.generate(candidate, reaction="question")
        assert result is not None
        assert result["severity"] == "requires_approval"


# --- Constraint text template ---


class TestConstraintTextTemplate:
    """Test that constraint text follows the locked template format."""

    def test_text_follows_template_format(self, generator):
        """Generated text must match the locked template."""
        candidate = _make_candidate(
            bypass_tool_name="Bash",
            bypass_command="git push origin main --force",
            bypass_resource="src/",
            block_event_tag="O_GATE",
        )
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        text = result["text"]
        # Template: "Forbid {tool} performing {op} on {resource} without prior approval
        #            following a rejected {gate} gate"
        assert text.startswith("Forbid Bash performing")
        assert "push" in text
        assert "without prior approval" in text
        assert "following a rejected O_GATE gate" in text

    def test_text_with_o_corr_gate(self, generator):
        """Template uses O_CORR gate type when block_event_tag is O_CORR."""
        candidate = _make_candidate(block_event_tag="O_CORR")
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert "following a rejected O_CORR gate" in result["text"]

    def test_text_with_different_tool(self, generator):
        """Template uses the actual bypass tool name."""
        candidate = _make_candidate(
            bypass_tool_name="Write",
            bypass_command="write file.py content",
            bypass_resource="src/main.py",
        )
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert result["text"].startswith("Forbid Write performing")

    def test_text_with_no_resource_uses_any_path(self, generator):
        """When bypass_resource is empty, use 'any path'."""
        candidate = _make_candidate(bypass_resource="")
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert "on any path" in result["text"]


# --- Status and source fields ---


class TestStatusAndSource:
    """Test that generated constraints always have correct status and source."""

    def test_status_always_candidate(self, generator, candidate):
        """All generated constraints must have status='candidate'."""
        for reaction in ("block", "correct", None, "redirect", "question"):
            result = generator.generate(candidate, reaction=reaction)
            if result is not None:
                assert result["status"] == "candidate", (
                    f"reaction={reaction!r} produced status={result['status']!r}"
                )

    def test_source_always_inferred_from_escalation(self, generator, candidate):
        """All generated constraints must have source='inferred_from_escalation'."""
        for reaction in ("block", "correct", None, "redirect", "question"):
            result = generator.generate(candidate, reaction=reaction)
            if result is not None:
                assert result["source"] == "inferred_from_escalation", (
                    f"reaction={reaction!r} produced source={result['source']!r}"
                )


# --- Constraint ID generation ---


class TestConstraintIdGeneration:
    """Test deterministic SHA-256 constraint ID generation."""

    def test_id_is_deterministic(self, generator, candidate):
        """Same inputs -> same constraint_id."""
        r1 = generator.generate(candidate, reaction="block")
        r2 = generator.generate(candidate, reaction="block")
        assert r1 is not None and r2 is not None
        assert r1["constraint_id"] == r2["constraint_id"]

    def test_id_is_16_hex_chars(self, generator, candidate):
        """constraint_id should be 16 hex characters."""
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        cid = result["constraint_id"]
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)

    def test_different_candidates_produce_different_ids(self, generator):
        """Different escalation candidates produce different constraint_ids."""
        c1 = _make_candidate(bypass_tool_name="Bash", bypass_command="git push")
        c2 = _make_candidate(bypass_tool_name="Write", bypass_command="write file")
        r1 = generator.generate(c1, reaction="block")
        r2 = generator.generate(c2, reaction="block")
        assert r1 is not None and r2 is not None
        assert r1["constraint_id"] != r2["constraint_id"]

    def test_id_uses_o_esc_id_components(self, generator):
        """ID is SHA-256(o_esc_id + constraint_target_signature).

        o_esc_id is derived from block+bypass event IDs.
        constraint_target_signature = tool_name:operation_type:resource_path_prefix.
        """
        c1 = _make_candidate(
            block_event_id="evt-a",
            bypass_event_id="evt-b",
            bypass_tool_name="Bash",
            bypass_command="git push",
            bypass_resource="src/",
        )
        c2 = _make_candidate(
            block_event_id="evt-a",
            bypass_event_id="evt-b",
            bypass_tool_name="Bash",
            bypass_command="git push",
            bypass_resource="src/",
        )
        r1 = generator.generate(c1, reaction="block")
        r2 = generator.generate(c2, reaction="block")
        assert r1["constraint_id"] == r2["constraint_id"]

        # Change bypass event ID -> different o_esc_id -> different constraint_id
        c3 = _make_candidate(
            block_event_id="evt-a",
            bypass_event_id="evt-c",
            bypass_tool_name="Bash",
            bypass_command="git push",
            bypass_resource="src/",
        )
        r3 = generator.generate(c3, reaction="block")
        assert r3["constraint_id"] != r1["constraint_id"]


# --- Operation type inference ---


class TestOperationTypeInference:
    """Test inference of operation_type from bypass command text."""

    def test_git_push_infers_push(self, generator):
        """'git push' -> operation_type = 'push'."""
        c = _make_candidate(bypass_command="git push origin main --force")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "push" in result["text"]

    def test_rm_infers_delete(self, generator):
        """'rm file' -> operation_type = 'delete'."""
        c = _make_candidate(bypass_command="rm -rf /tmp/important")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "delete" in result["text"]

    def test_pip_install_infers_execute(self, generator):
        """'pip install' -> operation_type = 'execute'."""
        c = _make_candidate(bypass_command="pip install malicious-package")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "execute" in result["text"]

    def test_write_command_infers_write(self, generator):
        """Write tool with content -> operation_type = 'write'."""
        c = _make_candidate(
            bypass_tool_name="Write",
            bypass_command="write to file.py",
        )
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "write" in result["text"]

    def test_unknown_command_uses_execute_default(self, generator):
        """Unknown command type defaults to 'execute'."""
        c = _make_candidate(bypass_command="some-custom-tool --flag")
        result = generator.generate(c, reaction="block")
        assert result is not None
        # Should use 'execute' as default operation type
        assert "execute" in result["text"]


# --- Resource path inference ---


class TestResourcePathInference:
    """Test resource path inference from bypass_resource field."""

    def test_resource_from_bypass_resource(self, generator):
        """bypass_resource is used directly in constraint text."""
        c = _make_candidate(bypass_resource="src/api/auth.py")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "src/api/auth.py" in result["text"]

    def test_empty_resource_uses_any_path(self, generator):
        """Empty bypass_resource -> 'any path'."""
        c = _make_candidate(bypass_resource="")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "any path" in result["text"]

    def test_resource_in_scope_paths(self, generator):
        """bypass_resource appears in scope.paths."""
        c = _make_candidate(bypass_resource="src/")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "src/" in result["scope"]["paths"]


# --- Detection hints ---


class TestDetectionHints:
    """Test detection_hints content for constraint matching."""

    def test_hints_include_tool_name(self, generator):
        """detection_hints should include the bypass tool name."""
        c = _make_candidate(bypass_tool_name="Bash")
        result = generator.generate(c, reaction="block")
        assert result is not None
        assert "Bash" in result["detection_hints"]

    def test_hints_include_command_signature(self, generator):
        """detection_hints should include key command elements."""
        c = _make_candidate(bypass_command="git push origin main --force")
        result = generator.generate(c, reaction="block")
        assert result is not None
        hints = result["detection_hints"]
        assert any("git push" in h or "push" in h for h in hints)


# --- find_matching_constraint ---


class TestFindMatchingConstraint:
    """Test finding existing constraints by detection_hints overlap."""

    def test_finds_match_by_detection_hints_overlap(self, generator):
        """Returns constraint_id when detection_hints overlap."""
        existing = [
            {
                "constraint_id": "existing-001",
                "text": "Do not use force push",
                "severity": "forbidden",
                "scope": {"paths": ["src/"]},
                "detection_hints": ["Bash", "git push"],
            }
        ]
        candidate = _make_candidate(
            bypass_tool_name="Bash",
            bypass_command="git push origin main --force",
        )
        match = generator.find_matching_constraint(candidate, existing)
        assert match == "existing-001"

    def test_returns_none_when_no_overlap(self, generator):
        """Returns None when no detection_hints overlap."""
        existing = [
            {
                "constraint_id": "existing-001",
                "text": "Do not use eval",
                "severity": "forbidden",
                "scope": {"paths": ["src/"]},
                "detection_hints": ["eval", "exec"],
            }
        ]
        candidate = _make_candidate(
            bypass_tool_name="Bash",
            bypass_command="git push origin main",
        )
        match = generator.find_matching_constraint(candidate, existing)
        assert match is None

    def test_returns_none_for_empty_constraints_list(self, generator, candidate):
        """Returns None when there are no existing constraints."""
        match = generator.find_matching_constraint(candidate, [])
        assert match is None

    def test_finds_match_by_tool_and_path(self, generator):
        """Matches when tool name and path overlap in hints."""
        existing = [
            {
                "constraint_id": "existing-002",
                "text": "Protect src/ from unauthorized writes",
                "severity": "requires_approval",
                "scope": {"paths": ["src/"]},
                "detection_hints": ["Write", "src/"],
            }
        ]
        candidate = _make_candidate(
            bypass_tool_name="Write",
            bypass_resource="src/main.py",
        )
        match = generator.find_matching_constraint(candidate, existing)
        assert match == "existing-002"


# --- Output dict format ---


class TestOutputDictFormat:
    """Test the full output dict structure for ConstraintStore compatibility."""

    def test_has_all_required_fields(self, generator, candidate):
        """Generated constraint has all fields for ConstraintStore."""
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert "constraint_id" in result
        assert "text" in result
        assert "severity" in result
        assert "scope" in result
        assert "paths" in result["scope"]
        assert "detection_hints" in result
        assert "source_episode_id" in result
        assert "created_at" in result
        assert "status" in result
        assert "source" in result
        assert "examples" in result

    def test_source_episode_id_is_empty_string(self, generator, candidate):
        """source_episode_id should be empty string (filled later)."""
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert result["source_episode_id"] == ""

    def test_examples_is_empty_list(self, generator, candidate):
        """examples should be empty list initially."""
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert result["examples"] == []

    def test_created_at_is_iso_datetime(self, generator, candidate):
        """created_at should be a valid ISO datetime string."""
        result = generator.generate(candidate, reaction="block")
        assert result is not None
        assert "T" in result["created_at"]  # Basic ISO format check

    def test_validates_against_constraint_schema(self, generator, candidate):
        """Generated constraint must pass constraint.schema.json validation."""
        schema_path = Path("data/schemas/constraint.schema.json")
        if not schema_path.exists():
            pytest.skip("constraint.schema.json not found")

        import jsonschema

        with open(schema_path) as f:
            schema = json.load(f)

        result = generator.generate(candidate, reaction="block")
        assert result is not None
        # Should not raise
        jsonschema.validate(result, schema)

    def test_validates_requires_approval_against_schema(self, generator, candidate):
        """requires_approval constraint also passes schema validation."""
        schema_path = Path("data/schemas/constraint.schema.json")
        if not schema_path.exists():
            pytest.skip("constraint.schema.json not found")

        import jsonschema

        with open(schema_path) as f:
            schema = json.load(f)

        result = generator.generate(candidate, reaction=None)
        assert result is not None
        jsonschema.validate(result, schema)


# --- Linking via bypassed_constraint_id ---


class TestBypassedConstraintLinking:
    """Test that generated constraints link to existing constraints via bypassed_constraint_id."""

    def test_sets_bypassed_constraint_id_when_match_found(self, generator):
        """When find_matching_constraint returns an ID, it's set on the result."""
        existing = [
            {
                "constraint_id": "existing-abc",
                "text": "No force push",
                "severity": "forbidden",
                "scope": {"paths": []},
                "detection_hints": ["Bash", "git push"],
            }
        ]
        candidate = _make_candidate(
            bypass_tool_name="Bash",
            bypass_command="git push origin main --force",
        )
        result = generator.generate(
            candidate, reaction="block", existing_constraints=existing
        )
        assert result is not None
        assert result.get("bypassed_constraint_id") == "existing-abc"

    def test_no_bypassed_constraint_id_when_no_match(self, generator, candidate):
        """When no match, bypassed_constraint_id should be None."""
        result = generator.generate(candidate, reaction="block", existing_constraints=[])
        assert result is not None
        assert result.get("bypassed_constraint_id") is None
