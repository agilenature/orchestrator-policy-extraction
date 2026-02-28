"""Tests for FundamentalityChecker (Phase 24 genus validation)."""

from __future__ import annotations

import pytest

from src.pipeline.premise.fundamentality import FundamentalityChecker, FundamentalityResult


class TestFundamentalityChecker:
    """Tests for FundamentalityChecker.check()."""

    def setup_method(self):
        self.checker = FundamentalityChecker()

    def test_valid_genus_with_causal_word(self):
        """Genus with causal indicator word + 2 instances -> valid."""
        result = self.checker.check(
            genus_name="corpus-relative identity retrieval",
            instances=["A7 failure", "MOTM dedup failure"],
        )
        assert result.valid is True
        assert result.instance_count == 2

    def test_valid_genus_three_words_no_causal(self):
        """3+ word genus without exact causal word -> valid (structural proxy)."""
        result = self.checker.check(
            genus_name="per file searchability",
            instances=["A7 failure", "Library search failure"],
        )
        assert result.valid is True

    def test_invalid_zero_instances(self):
        """Genus with no instances -> invalid."""
        result = self.checker.check(
            genus_name="identity retrieval",
            instances=[],
        )
        assert result.valid is False
        assert "0 instance(s)" in result.reason

    def test_invalid_one_instance(self):
        """Genus with only 1 instance -> invalid."""
        result = self.checker.check(
            genus_name="identity retrieval",
            instances=["only one"],
        )
        assert result.valid is False
        assert "1 instance(s)" in result.reason

    def test_invalid_empty_genus_name(self):
        """Empty genus name -> invalid."""
        result = self.checker.check(
            genus_name="",
            instances=["inst1", "inst2"],
        )
        assert result.valid is False
        assert "empty" in result.reason

    def test_invalid_no_causal_one_word(self):
        """Single-word genus without causal indicator -> invalid."""
        result = self.checker.check(
            genus_name="searchability",
            instances=["inst1", "inst2"],
        )
        assert result.valid is False
        assert "causal" in result.reason

    def test_valid_two_word_causal(self):
        """Two-word genus with causal indicator word -> valid."""
        result = self.checker.check(
            genus_name="drift detection",
            instances=["inst1", "inst2"],
        )
        assert result.valid is True

    def test_instances_none_treated_as_zero(self):
        """instances=None treated as empty list -> invalid."""
        result = self.checker.check(
            genus_name="valid thing here",
            instances=None,
        )
        assert result.valid is False
        assert "0 instance(s)" in result.reason

    def test_a7_crad_test_case(self):
        """The key A7/CRAD validation from research: correct genus identification."""
        result = self.checker.check(
            genus_name="corpus-relative identity retrieval",
            instances=[
                "A7 per-file searchability failure",
                "Objectivism Library shared-aspect collision",
            ],
        )
        assert result.valid is True
        assert result.instance_count == 2
