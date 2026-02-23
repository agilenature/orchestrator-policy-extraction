"""Tests for PREMISE block regex parser.

Tests:
- Single PREMISE block parsing
- Multiple blocks in one text
- Missing FOIL separator
- UNVALIDATED prefix detection
- Extra whitespace handling
- Code-fenced blocks
- Empty text
- Cross-premise reference detection in validated_by
- FOIL_VERIFIED block parsing
"""

from __future__ import annotations

from src.pipeline.premise.parser import (
    parse_foil_verified_blocks,
    parse_premise_blocks,
)


class TestParsePremiseBlocksSingle:
    """Tests for parsing a single PREMISE block."""

    def test_standard_block(self):
        """Parse a standard 4-line PREMISE block."""
        text = (
            "PREMISE: File exists at /src/main.py\n"
            "VALIDATED_BY: Read output confirmed file presence\n"
            "FOIL: wrong file path | directory matches src/\n"
            "SCOPE: this project\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        p = results[0]
        assert p.claim == "File exists at /src/main.py"
        assert p.validated_by == "Read output confirmed file presence"
        assert p.is_unvalidated is False
        assert p.foil == "wrong file path"
        assert p.distinguishing_prop == "directory matches src/"
        assert p.scope == "this project"

    def test_unvalidated_premise(self):
        """Parse a PREMISE with UNVALIDATED status."""
        text = (
            "PREMISE: API uses v3 format\n"
            "VALIDATED_BY: UNVALIDATED -- need to check API docs\n"
            "FOIL: v2 format | response schema differences\n"
            "SCOPE: API module\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        p = results[0]
        assert p.is_unvalidated is True
        assert "UNVALIDATED" in p.validated_by

    def test_unvalidated_case_insensitive(self):
        """UNVALIDATED detection should be case-insensitive."""
        text = (
            "PREMISE: Some claim\n"
            "VALIDATED_BY: unvalidated -- reason\n"
            "FOIL: something else | difference\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].is_unvalidated is True


class TestParsePremiseBlocksFoil:
    """Tests for FOIL field parsing."""

    def test_foil_with_separator(self):
        """FOIL with ' | ' separator should split into foil and distinguishing_prop."""
        text = (
            "PREMISE: Test claim\n"
            "VALIDATED_BY: Evidence\n"
            "FOIL: wrong thing | correct property\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert results[0].foil == "wrong thing"
        assert results[0].distinguishing_prop == "correct property"

    def test_foil_without_separator(self):
        """FOIL without ' | ' should be entire field as foil, no distinguishing_prop."""
        text = (
            "PREMISE: Test claim\n"
            "VALIDATED_BY: Evidence\n"
            "FOIL: wrong thing without separator\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert results[0].foil == "wrong thing without separator"
        assert results[0].distinguishing_prop is None

    def test_foil_with_multiple_pipes(self):
        """FOIL with multiple ' | ' should split on first only."""
        text = (
            "PREMISE: Test claim\n"
            "VALIDATED_BY: Evidence\n"
            "FOIL: wrong thing | property one | property two\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert results[0].foil == "wrong thing"
        assert results[0].distinguishing_prop == "property one | property two"


class TestParsePremiseBlocksMultiple:
    """Tests for parsing multiple PREMISE blocks."""

    def test_two_blocks(self):
        """Parse two consecutive PREMISE blocks."""
        text = (
            "PREMISE: First claim\n"
            "VALIDATED_BY: First evidence\n"
            "FOIL: first foil | first prop\n"
            "SCOPE: first scope\n"
            "\n"
            "PREMISE: Second claim\n"
            "VALIDATED_BY: Second evidence\n"
            "FOIL: second foil | second prop\n"
            "SCOPE: second scope\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 2
        assert results[0].claim == "First claim"
        assert results[1].claim == "Second claim"

    def test_blocks_with_surrounding_text(self):
        """PREMISE blocks embedded in other text should still parse."""
        text = (
            "I need to check the file first.\n"
            "\n"
            "PREMISE: File exists at path\n"
            "VALIDATED_BY: Read output\n"
            "FOIL: wrong path | correct directory\n"
            "SCOPE: this project\n"
            "\n"
            "Now I will edit the file.\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].claim == "File exists at path"


class TestParsePremiseBlocksEdgeCases:
    """Tests for edge cases in PREMISE block parsing."""

    def test_empty_text(self):
        """Empty text should return empty list."""
        assert parse_premise_blocks("") == []

    def test_no_premise_blocks(self):
        """Text without PREMISE blocks should return empty list."""
        text = "This is regular text with no premise declarations."
        assert parse_premise_blocks(text) == []

    def test_leading_whitespace(self):
        """PREMISE blocks with leading whitespace should still parse."""
        text = (
            "  PREMISE: Indented claim\n"
            "  VALIDATED_BY: Indented evidence\n"
            "  FOIL: indented foil | indented prop\n"
            "  SCOPE: indented scope\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].claim == "Indented claim"

    def test_windows_line_endings(self):
        """PREMISE blocks with \\r\\n line endings should parse."""
        text = (
            "PREMISE: Windows claim\r\n"
            "VALIDATED_BY: Windows evidence\r\n"
            "FOIL: windows foil | windows prop\r\n"
            "SCOPE: windows scope\r\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].claim == "Windows claim"

    def test_trailing_whitespace_stripped(self):
        """Trailing whitespace on field values should be stripped."""
        text = (
            "PREMISE: claim with spaces   \n"
            "VALIDATED_BY: evidence with spaces   \n"
            "FOIL: foil with spaces | prop with spaces   \n"
            "SCOPE: scope with spaces   \n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].claim == "claim with spaces"
        assert results[0].scope == "scope with spaces"


class TestCrossPremiseReferences:
    """Tests for cross-premise reference detection in validated_by."""

    def test_16_hex_char_reference(self):
        """A 16-hex-char ID in validated_by should populate derivation_chain."""
        text = (
            "PREMISE: Derived claim\n"
            "VALIDATED_BY: Validated by premise a1b2c3d4e5f6a7b8\n"
            "FOIL: something else | difference\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].derivation_chain is not None
        assert len(results[0].derivation_chain) == 1
        assert results[0].derivation_chain[0]["derives_from"] == "a1b2c3d4e5f6a7b8"

    def test_no_references(self):
        """validated_by without premise references should have None derivation_chain."""
        text = (
            "PREMISE: Direct claim\n"
            "VALIDATED_BY: Read output confirmed\n"
            "FOIL: wrong | right\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert len(results) == 1
        assert results[0].derivation_chain is None

    def test_multiple_references(self):
        """Multiple premise IDs in validated_by should all be detected."""
        text = (
            "PREMISE: Multi-derived claim\n"
            "VALIDATED_BY: Based on a1b2c3d4e5f6a7b8 and b2c3d4e5f6a7b8c9\n"
            "FOIL: something | difference\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert results[0].derivation_chain is not None
        assert len(results[0].derivation_chain) == 2
        ids = {d["derives_from"] for d in results[0].derivation_chain}
        assert "a1b2c3d4e5f6a7b8" in ids
        assert "b2c3d4e5f6a7b8c9" in ids

    def test_premise_prefix_reference(self):
        """PREMISE-<id> pattern should be detected as a reference."""
        text = (
            "PREMISE: Prefixed claim\n"
            "VALIDATED_BY: Based on PREMISE-config-yaml\n"
            "FOIL: something | difference\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert results[0].derivation_chain is not None
        assert results[0].derivation_chain[0]["derives_from"] == "config-yaml"

    def test_duplicate_references_deduplicated(self):
        """Duplicate premise IDs in validated_by should be deduplicated."""
        text = (
            "PREMISE: Dup claim\n"
            "VALIDATED_BY: Based on a1b2c3d4e5f6a7b8 and also a1b2c3d4e5f6a7b8\n"
            "FOIL: something | difference\n"
            "SCOPE: test\n"
        )
        results = parse_premise_blocks(text)
        assert results[0].derivation_chain is not None
        assert len(results[0].derivation_chain) == 1


class TestParseFoilVerifiedBlocks:
    """Tests for FOIL_VERIFIED block parsing."""

    def test_standard_foil_verified(self):
        """Parse a standard FOIL_VERIFIED block."""
        text = (
            "FOIL_VERIFIED: File exists at /src/main.py\n"
            "VERIFIED_BY: Read tool returned content\n"
            "RESULT: File confirmed present with expected content\n"
        )
        results = parse_foil_verified_blocks(text)
        assert len(results) == 1
        assert results[0]["premise_claim"] == "File exists at /src/main.py"
        assert results[0]["verified_by"] == "Read tool returned content"
        assert results[0]["result"] == "File confirmed present with expected content"

    def test_empty_text(self):
        """Empty text should return empty list."""
        assert parse_foil_verified_blocks("") == []

    def test_no_foil_verified(self):
        """Text without FOIL_VERIFIED blocks should return empty list."""
        assert parse_foil_verified_blocks("Regular text here") == []

    def test_multiple_foil_verified(self):
        """Parse multiple FOIL_VERIFIED blocks."""
        text = (
            "FOIL_VERIFIED: Claim one\n"
            "VERIFIED_BY: Tool call one\n"
            "RESULT: Result one\n"
            "\n"
            "FOIL_VERIFIED: Claim two\n"
            "VERIFIED_BY: Tool call two\n"
            "RESULT: Result two\n"
        )
        results = parse_foil_verified_blocks(text)
        assert len(results) == 2
        assert results[0]["premise_claim"] == "Claim one"
        assert results[1]["premise_claim"] == "Claim two"
