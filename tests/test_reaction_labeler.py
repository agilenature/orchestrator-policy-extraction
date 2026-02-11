"""Tests for ReactionLabeler.

TDD tests for reaction classification of human messages following episode boundaries.

Covers:
1. Strong approve patterns (go ahead, yes, LGTM, looks good)
2. Weak approve patterns (ok, sure, fine, proceed)
3. Strong correct patterns (no do it differently, that's wrong)
4. Weak correct patterns (fix it, instead)
5. Strong block patterns (STOP, never do that, NO at start)
6. Weak block patterns (don't, avoid)
7. Strong redirect patterns (switch to, first fix, different direction)
8. Weak redirect patterns (before that, priority)
9. Strong question patterns (why?, what about, how does, explain)
10. Weak question patterns (trailing ?)
11. O_CORR tag override -> correct at 0.9
12. O_DIR tag implicit approval -> approve at 0.5
13. No next message -> None
14. Ambiguous text -> unknown at 0.3
15. Priority: block > correct > redirect > question > approve
16. Case insensitivity
17. Multiple-word messages with mixed signals
18. Empty/whitespace messages
"""

from __future__ import annotations

import pytest

from src.pipeline.models.config import load_config
from src.pipeline.reaction_labeler import ReactionLabeler


@pytest.fixture
def config():
    """Load pipeline config for ReactionLabeler."""
    return load_config("data/config.yaml")


@pytest.fixture
def labeler(config):
    """Create a ReactionLabeler with real config."""
    return ReactionLabeler(config)


def _make_human_msg(text: str, tags: list[str] | None = None) -> dict:
    """Helper to create a human message event dict."""
    msg = {
        "actor": "human_orchestrator",
        "event_type": "user_msg",
        "payload": {"text": text},
    }
    if tags:
        msg["tags"] = tags
    return msg


# --- Strong approve patterns ---


class TestStrongApprove:
    """Strong approve patterns should produce confidence >= 0.7."""

    def test_looks_good_go_ahead(self, labeler):
        msg = _make_human_msg("Looks good, go ahead")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7

    def test_yes(self, labeler):
        msg = _make_human_msg("yes")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7

    def test_lgtm(self, labeler):
        msg = _make_human_msg("LGTM")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7

    def test_approved(self, labeler):
        msg = _make_human_msg("approved")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7

    def test_yeah(self, labeler):
        msg = _make_human_msg("yeah that's fine")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7


# --- Weak approve patterns ---


class TestWeakApprove:
    """Weak approve patterns should produce confidence >= 0.5 but < 0.7."""

    def test_ok(self, labeler):
        msg = _make_human_msg("ok")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert 0.5 <= result["confidence"] < 0.7

    def test_sure(self, labeler):
        msg = _make_human_msg("sure")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert 0.5 <= result["confidence"] < 0.7

    def test_fine(self, labeler):
        msg = _make_human_msg("fine")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert 0.5 <= result["confidence"] < 0.7

    def test_proceed(self, labeler):
        msg = _make_human_msg("proceed")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert 0.5 <= result["confidence"] < 0.7

    def test_that_works(self, labeler):
        msg = _make_human_msg("that works")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert 0.5 <= result["confidence"] < 0.7


# --- Strong correct patterns ---


class TestStrongCorrect:
    """Strong correct patterns should produce confidence >= 0.7."""

    def test_no_do_it_differently(self, labeler):
        msg = _make_human_msg("No, do it differently")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert result["confidence"] >= 0.7

    def test_thats_wrong(self, labeler):
        msg = _make_human_msg("that's wrong")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert result["confidence"] >= 0.7

    def test_change_it_to(self, labeler):
        msg = _make_human_msg("change it to use async instead")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert result["confidence"] >= 0.7

    def test_thats_not_right(self, labeler):
        msg = _make_human_msg("that's not right")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert result["confidence"] >= 0.7


# --- Weak correct patterns ---


class TestWeakCorrect:
    """Weak correct patterns should produce confidence >= 0.5 but < 0.7."""

    def test_fix_it(self, labeler):
        msg = _make_human_msg("fix it")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert 0.5 <= result["confidence"] < 0.7

    def test_instead(self, labeler):
        msg = _make_human_msg("use pytest instead")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert 0.5 <= result["confidence"] < 0.7


# --- Strong block patterns ---


class TestStrongBlock:
    """Strong block patterns should produce confidence >= 0.7."""

    def test_stop(self, labeler):
        msg = _make_human_msg("STOP")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7

    def test_never_do_that(self, labeler):
        msg = _make_human_msg("never do that")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7

    def test_no_at_start(self, labeler):
        msg = _make_human_msg("NO!")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7

    def test_dont_do_that(self, labeler):
        msg = _make_human_msg("don't do that")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7


# --- Weak block patterns ---


class TestWeakBlock:
    """Weak block patterns should produce confidence >= 0.5 but < 0.7."""

    def test_dont(self, labeler):
        msg = _make_human_msg("don't")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert 0.5 <= result["confidence"] < 0.7

    def test_avoid(self, labeler):
        msg = _make_human_msg("avoid that approach")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert 0.5 <= result["confidence"] < 0.7


# --- Strong redirect patterns ---


class TestStrongRedirect:
    """Strong redirect patterns should produce confidence >= 0.7."""

    def test_switch_to(self, labeler):
        msg = _make_human_msg("switch to the other approach")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "redirect"
        assert result["confidence"] >= 0.7

    def test_first_fix(self, labeler):
        msg = _make_human_msg("first fix the tests")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "redirect"
        assert result["confidence"] >= 0.7

    def test_different_direction(self, labeler):
        msg = _make_human_msg("let's go a different direction")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "redirect"
        assert result["confidence"] >= 0.7

    def test_instead_focus(self, labeler):
        msg = _make_human_msg("instead focus on the API first")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "redirect"
        assert result["confidence"] >= 0.7


# --- Weak redirect patterns ---


class TestWeakRedirect:
    """Weak redirect patterns should produce confidence >= 0.5 but < 0.7."""

    def test_before_that(self, labeler):
        msg = _make_human_msg("before that, handle the edge case")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "redirect"
        assert 0.5 <= result["confidence"] < 0.7

    def test_priority(self, labeler):
        msg = _make_human_msg("the priority is getting tests green")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "redirect"
        assert 0.5 <= result["confidence"] < 0.7


# --- Strong question patterns ---


class TestStrongQuestion:
    """Strong question patterns should produce confidence >= 0.7."""

    def test_why_question(self, labeler):
        msg = _make_human_msg("why did you do that?")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "question"
        assert result["confidence"] >= 0.7

    def test_what_about(self, labeler):
        msg = _make_human_msg("what about error handling?")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "question"
        assert result["confidence"] >= 0.7

    def test_how_does(self, labeler):
        msg = _make_human_msg("how does this handle concurrency?")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "question"
        assert result["confidence"] >= 0.7

    def test_explain(self, labeler):
        msg = _make_human_msg("explain the approach")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "question"
        assert result["confidence"] >= 0.7


# --- Weak question patterns ---


class TestWeakQuestion:
    """Weak question patterns should produce confidence >= 0.5 but < 0.7."""

    def test_trailing_question_mark(self, labeler):
        msg = _make_human_msg("is that correct?")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "question"
        assert 0.5 <= result["confidence"] < 0.7


# --- Special cases ---


class TestSpecialCases:
    """Special case handling: O_CORR, O_DIR, None, unknown."""

    def test_o_corr_tag_overrides_text(self, labeler):
        """O_CORR tagged message returns correct at 0.9 regardless of text."""
        msg = _make_human_msg("looks good to me", tags=["O_CORR"])
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert result["confidence"] == 0.9

    def test_o_dir_implicit_approval(self, labeler):
        """O_DIR tagged message without correction words returns approve at 0.5."""
        msg = _make_human_msg("now implement the login page", tags=["O_DIR"])
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] == 0.5

    def test_o_dir_with_correction_keywords_not_implicit(self, labeler):
        """O_DIR tagged with correction keywords should classify by text, not implicit."""
        msg = _make_human_msg("no, fix it first", tags=["O_DIR"])
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        # Should detect correction/block, not implicit approve
        assert result["label"] in ("correct", "block")
        assert result["confidence"] > 0.5

    def test_no_next_message_returns_none(self, labeler):
        """No next message (None) returns None."""
        result = labeler.label(None, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is None

    def test_ambiguous_text_returns_unknown(self, labeler):
        """Ambiguous text with no pattern match returns unknown at 0.3."""
        msg = _make_human_msg("hmm")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "unknown"
        assert result["confidence"] == 0.3


# --- Priority ordering ---


class TestPriorityOrdering:
    """Block > correct > redirect > question > approve priority."""

    def test_block_over_redirect(self, labeler):
        """'No, stop and switch to a different approach' -> block, not redirect."""
        msg = _make_human_msg("No, stop and switch to a different approach")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7

    def test_block_over_correct(self, labeler):
        """'stop, that's wrong' -> block (higher priority than correct)."""
        msg = _make_human_msg("stop, that's wrong")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7

    def test_correct_over_question(self, labeler):
        """'no, use a different method' -> correct, not question."""
        msg = _make_human_msg("no, use a different method")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "correct"
        assert result["confidence"] >= 0.7


# --- Case insensitivity ---


class TestCaseInsensitivity:
    """Patterns should match regardless of case."""

    def test_yes_uppercase(self, labeler):
        msg = _make_human_msg("YES")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7

    def test_stop_lowercase(self, labeler):
        msg = _make_human_msg("stop")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "block"
        assert result["confidence"] >= 0.7

    def test_lgtm_mixed_case(self, labeler):
        msg = _make_human_msg("Lgtm")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7


# --- Edge cases ---


class TestEdgeCases:
    """Edge cases: empty messages, whitespace, JSON payloads."""

    def test_empty_message_text(self, labeler):
        """Empty text should return unknown."""
        msg = _make_human_msg("")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "unknown"
        assert result["confidence"] == 0.3

    def test_whitespace_only(self, labeler):
        """Whitespace-only text should return unknown."""
        msg = _make_human_msg("   ")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "unknown"
        assert result["confidence"] == 0.3

    def test_json_string_payload(self, labeler):
        """Payload as JSON string should be parsed correctly."""
        import json

        msg = {
            "actor": "human_orchestrator",
            "event_type": "user_msg",
            "payload": json.dumps({"text": "yes go ahead"}),
        }
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["label"] == "approve"
        assert result["confidence"] >= 0.7

    def test_result_includes_message(self, labeler):
        """Result dict should include the original message text."""
        msg = _make_human_msg("LGTM")
        result = labeler.label(msg, episode_end_trigger="T_TEST", episode_outcome="success")
        assert result is not None
        assert result["message"] == "LGTM"
