"""Tests for the VerdictCollector.

Verifies interactive verdict collection with injectable input function,
covering accept/reject shortcuts, invalid input looping, and opinion
handling.
"""

from __future__ import annotations

from src.pipeline.review.collector import VerdictCollector
from src.pipeline.review.models import ReviewVerdict


def _mock_input(*responses):
    """Return an input_fn that yields responses in sequence."""
    it = iter(responses)
    return lambda prompt: next(it)


class TestVerdictCollector:
    """Tests for VerdictCollector.collect()."""

    def test_accept_returns_accept_verdict(self):
        """Input 'accept' returns (ACCEPT, None)."""
        collector = VerdictCollector(input_fn=_mock_input("accept", ""))
        verdict, opinion = collector.collect()

        assert verdict == ReviewVerdict.ACCEPT
        assert opinion is None

    def test_shortcut_a_returns_accept(self):
        """Input 'a' returns (ACCEPT, None)."""
        collector = VerdictCollector(input_fn=_mock_input("a", ""))
        verdict, opinion = collector.collect()

        assert verdict == ReviewVerdict.ACCEPT
        assert opinion is None

    def test_reject_with_opinion(self):
        """Input 'reject' then opinion text returns (REJECT, 'opinion')."""
        collector = VerdictCollector(
            input_fn=_mock_input("reject", "The label is wrong")
        )
        verdict, opinion = collector.collect()

        assert verdict == ReviewVerdict.REJECT
        assert opinion == "The label is wrong"

    def test_shortcut_r_returns_reject(self):
        """Input 'r' returns (REJECT, ...)."""
        collector = VerdictCollector(input_fn=_mock_input("r", ""))
        verdict, opinion = collector.collect()

        assert verdict == ReviewVerdict.REJECT
        assert opinion is None

    def test_invalid_input_loops_until_valid(self):
        """Invalid input followed by 'accept' loops then returns ACCEPT."""
        collector = VerdictCollector(
            input_fn=_mock_input("maybe", "yes", "accept", "")
        )
        verdict, opinion = collector.collect()

        assert verdict == ReviewVerdict.ACCEPT
        assert opinion is None

    def test_empty_opinion_returns_none(self):
        """Empty string (Enter pressed) returns None opinion."""
        collector = VerdictCollector(input_fn=_mock_input("accept", ""))
        verdict, opinion = collector.collect()

        assert opinion is None

    def test_whitespace_only_opinion_returns_none(self):
        """Whitespace-only opinion returns None after strip."""
        collector = VerdictCollector(input_fn=_mock_input("accept", "   "))
        verdict, opinion = collector.collect()

        assert opinion is None

    def test_case_insensitive_verdict(self):
        """'ACCEPT', 'Accept', 'REJECT' all work."""
        collector = VerdictCollector(input_fn=_mock_input("ACCEPT", ""))
        verdict, _ = collector.collect()
        assert verdict == ReviewVerdict.ACCEPT

        collector = VerdictCollector(input_fn=_mock_input("Reject", "note"))
        verdict, opinion = collector.collect()
        assert verdict == ReviewVerdict.REJECT
        assert opinion == "note"
