"""Tests for ConstraintExtractor.

TDD tests for constraint extraction from correct/block episode reactions.

Covers:
1. Reaction filtering (only correct/block produce constraints)
2. Severity assignment (forbidden, requires_approval, warning)
3. Scope inference (message paths > episode paths > repo-wide)
4. Text normalization (strip prefixes, capitalize, ensure period)
5. Detection hints (quoted strings, file paths, prohibition-adjacent terms)
6. Constraint ID determinism (SHA-256 hash of text + scope)
7. Full extraction flow (complete constraint dict with all fields)
"""

from __future__ import annotations

import pytest

from src.pipeline.models.config import load_config
from src.pipeline.constraint_extractor import ConstraintExtractor


@pytest.fixture
def config():
    """Load pipeline config for ConstraintExtractor."""
    return load_config("data/config.yaml")


@pytest.fixture
def extractor(config):
    """Create a ConstraintExtractor with real config."""
    return ConstraintExtractor(config)


def _make_episode(
    reaction_label: str = "correct",
    reaction_message: str = "Don't use regex for XML parsing.",
    reaction_confidence: float = 0.85,
    scope_paths: list[str] | None = None,
    episode_id: str = "ep-test-001",
    timestamp: str = "2026-02-11T12:00:00Z",
) -> dict:
    """Helper to create a minimal episode dict for testing."""
    episode = {
        "episode_id": episode_id,
        "timestamp": timestamp,
        "orchestrator_action": {
            "mode": "Implement",
            "scope": {"paths": scope_paths or []},
        },
        "outcome": {
            "reaction": {
                "label": reaction_label,
                "message": reaction_message,
                "confidence": reaction_confidence,
            },
        },
    }
    return episode


# --- 1. Reaction filtering ---


class TestReactionFiltering:
    """Only correct and block reactions produce constraints."""

    def test_approve_returns_none(self, extractor):
        ep = _make_episode(reaction_label="approve", reaction_message="yes, looks good")
        assert extractor.extract(ep) is None

    def test_question_returns_none(self, extractor):
        ep = _make_episode(reaction_label="question", reaction_message="why did you do that?")
        assert extractor.extract(ep) is None

    def test_redirect_returns_none(self, extractor):
        ep = _make_episode(reaction_label="redirect", reaction_message="switch to the other task")
        assert extractor.extract(ep) is None

    def test_unknown_returns_none(self, extractor):
        ep = _make_episode(reaction_label="unknown", reaction_message="hmm")
        assert extractor.extract(ep) is None

    def test_correct_returns_constraint(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="Don't use regex.")
        result = extractor.extract(ep)
        assert result is not None
        assert "constraint_id" in result

    def test_block_returns_constraint(self, extractor):
        ep = _make_episode(reaction_label="block", reaction_message="Stop doing that.")
        result = extractor.extract(ep)
        assert result is not None
        assert "constraint_id" in result

    def test_missing_reaction_returns_none(self, extractor):
        ep = {"episode_id": "ep-1", "outcome": {}}
        assert extractor.extract(ep) is None

    def test_empty_message_returns_none(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="")
        assert extractor.extract(ep) is None

    def test_whitespace_only_message_returns_none(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="   ")
        assert extractor.extract(ep) is None


# --- 2. Severity assignment ---


class TestSeverityAssignment:
    """Block -> forbidden; correct -> requires_approval or warning based on keywords."""

    def test_block_always_forbidden(self, extractor):
        ep = _make_episode(reaction_label="block", reaction_message="Stop using eval.")
        result = extractor.extract(ep)
        assert result["severity"] == "forbidden"

    def test_block_forbidden_regardless_of_preferred_keywords(self, extractor):
        ep = _make_episode(reaction_label="block", reaction_message="Use something else.")
        result = extractor.extract(ep)
        assert result["severity"] == "forbidden"

    def test_correct_with_dont_keyword(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="don't use regex for XML")
        result = extractor.extract(ep)
        assert result["severity"] == "requires_approval"

    def test_correct_with_never_keyword(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="never deploy without tests")
        result = extractor.extract(ep)
        assert result["severity"] == "requires_approval"

    def test_correct_with_avoid_keyword(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="avoid eval in production")
        result = extractor.extract(ep)
        assert result["severity"] == "requires_approval"

    def test_correct_with_do_not_keyword(self, extractor):
        ep = _make_episode(reaction_label="correct", reaction_message="do not hardcode secrets")
        result = extractor.extract(ep)
        assert result["severity"] == "requires_approval"

    def test_correct_with_preferred_keyword_use(self, extractor):
        ep = _make_episode(
            reaction_label="correct",
            reaction_message="use pytest instead of unittest",
        )
        result = extractor.extract(ep)
        assert result["severity"] == "warning"

    def test_correct_with_preferred_keyword_prefer(self, extractor):
        ep = _make_episode(
            reaction_label="correct",
            reaction_message="prefer async over sync calls",
        )
        result = extractor.extract(ep)
        assert result["severity"] == "warning"

    def test_correct_with_both_forbidden_and_preferred(self, extractor):
        """Forbidden keywords take precedence over preferred."""
        ep = _make_episode(
            reaction_label="correct",
            reaction_message="don't use jQuery, prefer vanilla JS",
        )
        result = extractor.extract(ep)
        assert result["severity"] == "requires_approval"

    def test_correct_with_no_keywords_defaults_requires_approval(self, extractor):
        ep = _make_episode(
            reaction_label="correct",
            reaction_message="that needs a different approach entirely",
        )
        result = extractor.extract(ep)
        assert result["severity"] == "requires_approval"


# --- 3. Scope inference ---


class TestScopeInference:
    """Scope follows: reaction message paths > episode scope paths > empty (repo-wide)."""

    def test_paths_from_reaction_message(self, extractor):
        ep = _make_episode(
            reaction_message="don't modify src/pipeline/tagger.py directly",
        )
        result = extractor.extract(ep)
        assert "src/pipeline/tagger.py" in result["scope"]["paths"]

    def test_directory_path_from_message(self, extractor):
        ep = _make_episode(
            reaction_message="don't touch files in src/pipeline/storage/writer.py",
        )
        result = extractor.extract(ep)
        paths = result["scope"]["paths"]
        assert any("src/pipeline/storage/writer.py" in p for p in paths)

    def test_fallback_to_episode_scope_paths(self, extractor):
        ep = _make_episode(
            reaction_message="don't do that",
            scope_paths=["src/pipeline/runner.py"],
        )
        result = extractor.extract(ep)
        assert result["scope"]["paths"] == ["src/pipeline/runner.py"]

    def test_empty_scope_when_no_paths_anywhere(self, extractor):
        ep = _make_episode(
            reaction_message="don't do that",
            scope_paths=[],
        )
        result = extractor.extract(ep)
        assert result["scope"]["paths"] == []

    def test_multiple_paths_in_message(self, extractor):
        ep = _make_episode(
            reaction_message="don't modify config.yaml or schema.json directly",
        )
        result = extractor.extract(ep)
        paths = result["scope"]["paths"]
        assert len(paths) >= 2

    def test_message_paths_take_precedence_over_episode_scope(self, extractor):
        ep = _make_episode(
            reaction_message="don't modify src/pipeline/tagger.py directly",
            scope_paths=["src/pipeline/runner.py"],
        )
        result = extractor.extract(ep)
        assert "src/pipeline/tagger.py" in result["scope"]["paths"]
        # Episode scope path should NOT be used when message has paths
        assert "src/pipeline/runner.py" not in result["scope"]["paths"]


# --- 4. Text normalization ---


class TestTextNormalization:
    """Strip prefixes, capitalize, ensure period."""

    def test_strips_no_prefix(self, extractor):
        ep = _make_episode(reaction_message="no, don't use regex")
        result = extractor.extract(ep)
        assert not result["text"].lower().startswith("no,")

    def test_strips_nope_prefix(self, extractor):
        ep = _make_episode(reaction_message="nope, use lxml instead")
        result = extractor.extract(ep)
        assert not result["text"].lower().startswith("nope")

    def test_strips_wrong_prefix(self, extractor):
        ep = _make_episode(reaction_message="wrong, use the other approach")
        result = extractor.extract(ep)
        assert not result["text"].lower().startswith("wrong")

    def test_strips_thats_wrong_prefix(self, extractor):
        ep = _make_episode(reaction_message="that's wrong, use pytest instead")
        result = extractor.extract(ep)
        assert not result["text"].lower().startswith("that's wrong")

    def test_capitalizes_first_letter(self, extractor):
        ep = _make_episode(reaction_message="use pytest instead of unittest")
        result = extractor.extract(ep)
        assert result["text"][0].isupper()

    def test_ensures_period_at_end(self, extractor):
        ep = _make_episode(reaction_message="use pytest instead of unittest")
        result = extractor.extract(ep)
        assert result["text"].endswith(".")

    def test_preserves_existing_period(self, extractor):
        ep = _make_episode(reaction_message="Use pytest instead.")
        result = extractor.extract(ep)
        assert result["text"] == "Use pytest instead."
        assert not result["text"].endswith("..")

    def test_preserves_exclamation_mark(self, extractor):
        ep = _make_episode(reaction_message="Never do that!")
        result = extractor.extract(ep)
        assert result["text"].endswith("!")
        assert not result["text"].endswith("!.")

    def test_clean_text_passes_through(self, extractor):
        ep = _make_episode(reaction_message="Always run tests before pushing.")
        result = extractor.extract(ep)
        assert result["text"] == "Always run tests before pushing."


# --- 5. Detection hints ---


class TestDetectionHints:
    """Extract quoted strings, file paths, and prohibition-adjacent terms."""

    def test_quoted_strings_extracted(self, extractor):
        ep = _make_episode(reaction_message='Use "lxml" instead of regex')
        result = extractor.extract(ep)
        assert "lxml" in result["detection_hints"]

    def test_file_paths_as_hints(self, extractor):
        ep = _make_episode(
            reaction_message="don't modify src/pipeline/tagger.py directly",
        )
        result = extractor.extract(ep)
        assert any("tagger.py" in h for h in result["detection_hints"])

    def test_prohibition_adjacent_dont_use(self, extractor):
        ep = _make_episode(reaction_message="don't use regex for XML")
        result = extractor.extract(ep)
        assert "regex" in result["detection_hints"]

    def test_prohibition_adjacent_avoid(self, extractor):
        ep = _make_episode(reaction_message="avoid eval in production code")
        result = extractor.extract(ep)
        assert "eval" in result["detection_hints"]

    def test_prohibition_adjacent_never_use(self, extractor):
        ep = _make_episode(reaction_message="never use jQuery in this project")
        result = extractor.extract(ep)
        assert "jQuery" in result["detection_hints"]

    def test_multiple_hints_from_one_message(self, extractor):
        ep = _make_episode(
            reaction_message='don\'t use "eval" or "exec" in src/pipeline/runner.py',
        )
        result = extractor.extract(ep)
        hints = result["detection_hints"]
        assert len(hints) >= 2

    def test_empty_hints_when_no_patterns(self, extractor):
        ep = _make_episode(reaction_message="that needs improvement")
        result = extractor.extract(ep)
        assert isinstance(result["detection_hints"], list)


# --- 6. Constraint ID determinism ---


class TestConstraintIdDeterminism:
    """IDs are deterministic SHA-256 hashes enabling dedup."""

    def test_same_text_same_scope_same_id(self, extractor):
        ep1 = _make_episode(
            reaction_message="don't use regex",
            scope_paths=["src/a.py"],
        )
        ep2 = _make_episode(
            reaction_message="don't use regex",
            scope_paths=["src/a.py"],
        )
        r1 = extractor.extract(ep1)
        r2 = extractor.extract(ep2)
        assert r1["constraint_id"] == r2["constraint_id"]

    def test_different_text_different_id(self, extractor):
        ep1 = _make_episode(reaction_message="don't use regex")
        ep2 = _make_episode(reaction_message="don't use eval")
        r1 = extractor.extract(ep1)
        r2 = extractor.extract(ep2)
        assert r1["constraint_id"] != r2["constraint_id"]

    def test_same_text_different_scope_different_id(self, extractor):
        ep1 = _make_episode(
            reaction_message="don't use regex",
            scope_paths=["src/a.py"],
        )
        ep2 = _make_episode(
            reaction_message="don't use regex",
            scope_paths=["src/b.py"],
        )
        r1 = extractor.extract(ep1)
        r2 = extractor.extract(ep2)
        assert r1["constraint_id"] != r2["constraint_id"]

    def test_id_is_16_hex_chars(self, extractor):
        ep = _make_episode(reaction_message="don't use regex")
        result = extractor.extract(ep)
        cid = result["constraint_id"]
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)


# --- 7. Full extraction flow ---


class TestFullExtractionFlow:
    """End-to-end: correct/block reactions produce complete constraint dicts."""

    def test_correct_reaction_full_constraint(self, extractor):
        ep = _make_episode(
            reaction_label="correct",
            reaction_message="No, don't use regex for XML parsing. Use lxml instead.",
            scope_paths=["src/parser.py"],
            episode_id="ep-full-001",
            timestamp="2026-02-11T15:00:00Z",
        )
        result = extractor.extract(ep)
        assert result is not None
        assert result["severity"] == "requires_approval"
        assert result["source_episode_id"] == "ep-full-001"
        assert result["created_at"] == "2026-02-11T15:00:00Z"
        # Text should be normalized (no "No, " prefix)
        assert not result["text"].lower().startswith("no,")

    def test_block_reaction_full_constraint(self, extractor):
        ep = _make_episode(
            reaction_label="block",
            reaction_message="Never push to main without CI passing",
            episode_id="ep-full-002",
            timestamp="2026-02-11T16:00:00Z",
        )
        result = extractor.extract(ep)
        assert result is not None
        assert result["severity"] == "forbidden"
        assert result["source_episode_id"] == "ep-full-002"

    def test_constraint_has_all_required_schema_fields(self, extractor):
        ep = _make_episode(reaction_message="don't use eval")
        result = extractor.extract(ep)
        required_keys = {"constraint_id", "text", "severity", "scope"}
        assert required_keys.issubset(result.keys())
        assert "paths" in result["scope"]

    def test_source_episode_and_created_at_populated(self, extractor):
        ep = _make_episode(
            episode_id="ep-meta-001",
            timestamp="2026-02-11T18:00:00Z",
            reaction_message="avoid hardcoded secrets",
        )
        result = extractor.extract(ep)
        assert result["source_episode_id"] == "ep-meta-001"
        assert result["created_at"] == "2026-02-11T18:00:00Z"

    def test_examples_array_populated(self, extractor):
        ep = _make_episode(
            episode_id="ep-ex-001",
            reaction_message="don't use eval in production",
        )
        result = extractor.extract(ep)
        assert "examples" in result
        assert len(result["examples"]) == 1
        assert result["examples"][0]["episode_id"] == "ep-ex-001"
