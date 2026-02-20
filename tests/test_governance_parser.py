"""Tests for the governance Markdown parser.

Covers header classification, H3 sub-heading extraction, bullet and
numbered list extraction, multi-line continuation, edge cases, and
mixed-section documents.
"""

from __future__ import annotations

import pytest

from src.pipeline.governance.parser import GovDocParser, ParsedEntity


@pytest.fixture
def parser() -> GovDocParser:
    return GovDocParser()


# --- Header classification tests ---


class TestClassifyHeader:
    """Tests for _classify_header keyword matching."""

    def test_failure_stories_classified(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Failure Stories") == "failure_story"

    def test_ways_we_could_fail_variant(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Ways We Could Fail") == "failure_story"

    def test_dead_ends_variant(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Dead Ends") == "failure_story"

    def test_key_assumptions_classified(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Key Assumptions") == "assumption"

    def test_assumptions_classified(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Assumptions") == "assumption"

    def test_core_assumptions_classified(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Core Assumptions") == "assumption"

    def test_scope_decisions_classified(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Scope Decisions") == "scope_decision"

    def test_method_decisions_classified(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Method Decisions") == "method_decision"

    def test_bare_decisions_does_not_match(self, parser: GovDocParser) -> None:
        """Bare 'Decisions' header is ambiguous and should NOT match."""
        assert parser._classify_header("Decisions") is None

    def test_case_insensitive(self, parser: GovDocParser) -> None:
        assert parser._classify_header("FAILURE STORIES") == "failure_story"
        assert parser._classify_header("key assumptions") == "assumption"

    def test_unrecognized_header(self, parser: GovDocParser) -> None:
        assert parser._classify_header("Architecture Overview") is None


# --- H3 sub-heading extraction ---


class TestH3SubheadingExtraction:
    """Tests for extracting entities from H3 blocks under classified H2."""

    def test_h3_stories_produce_dead_end_entities(
        self, parser: GovDocParser
    ) -> None:
        doc = """## Failure Stories

### Story 1: Bad Library Choice
We tried pybreaker but it failed.

### Story 2: Wrong API Pattern
The single-step upload did not work.
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 2
        assert all(e.entity_type == "dead_end" for e in entities)
        assert entities[0].title == "Story 1: Bad Library Choice"
        assert entities[1].title == "Story 2: Wrong API Pattern"

    def test_h3_body_captured(self, parser: GovDocParser) -> None:
        doc = """## Failure Stories

### Story 1: Test
First line of body.
Second line of body.
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 1
        assert "First line of body." in entities[0].content
        assert "Second line of body." in entities[0].content

    def test_h3_stops_at_next_h2(self, parser: GovDocParser) -> None:
        doc = """## Failure Stories

### Story 1: Only One
Content here.

## Key Assumptions

- Assumption A
"""
        entities = parser.parse_document(doc)
        dead_ends = [e for e in entities if e.entity_type == "dead_end"]
        assumptions = [e for e in entities if e.entity_type == "assumption"]
        assert len(dead_ends) == 1
        assert len(assumptions) == 1


# --- List item extraction ---


class TestListItemExtraction:
    """Tests for bullet and numbered list item entity extraction."""

    def test_bullet_items_produce_assumption_entities(
        self, parser: GovDocParser
    ) -> None:
        doc = """## Key Assumptions

- First assumption statement
- Second assumption statement
- Third assumption statement
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 3
        assert all(e.entity_type == "assumption" for e in entities)

    def test_numbered_items_extracted(self, parser: GovDocParser) -> None:
        doc = """## Key Assumptions

1. First numbered assumption
2. Second numbered assumption
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 2

    def test_multiline_list_item_continuation(
        self, parser: GovDocParser
    ) -> None:
        doc = """## Key Assumptions

- First assumption with more detail
  that continues on the next line
- Second assumption
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 2
        assert "continues on the next line" in entities[0].content

    def test_asterisk_bullets(self, parser: GovDocParser) -> None:
        doc = """## Assumptions

* Star bullet one
* Star bullet two
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 2


# --- Edge cases ---


class TestEdgeCases:
    """Tests for empty sections, missing headers, and other edge cases."""

    def test_empty_section_produces_zero_entities(
        self, parser: GovDocParser
    ) -> None:
        doc = """## Failure Stories

## Key Assumptions

- One assumption
"""
        entities = parser.parse_document(doc)
        # Failure Stories section is empty (no H3s, no list items)
        dead_ends = [e for e in entities if e.entity_type == "dead_end"]
        assumptions = [e for e in entities if e.entity_type == "assumption"]
        assert len(dead_ends) == 0
        assert len(assumptions) == 1

    def test_no_matching_headers_produces_zero_entities(
        self, parser: GovDocParser
    ) -> None:
        doc = """## Architecture Overview

Some text here.

## Implementation Details

More text.
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 0

    def test_document_with_no_headers(self, parser: GovDocParser) -> None:
        doc = "Just plain text with no headers at all."
        entities = parser.parse_document(doc)
        assert len(entities) == 0

    def test_empty_document(self, parser: GovDocParser) -> None:
        entities = parser.parse_document("")
        assert len(entities) == 0

    def test_source_section_tracked(self, parser: GovDocParser) -> None:
        doc = """## Key Assumptions

- Test assumption
"""
        entities = parser.parse_document(doc)
        assert entities[0].source_section == "Key Assumptions"


# --- Mixed sections ---


class TestMixedSections:
    """Tests for documents with multiple classified section types."""

    def test_mixed_failure_stories_and_assumptions(
        self, parser: GovDocParser
    ) -> None:
        doc = """# Pre-Mortem

## Failure Stories

### Story 1: Bad Choice
Description of what went wrong.

### Story 2: Another Fail
Another description.

## Key Assumptions

- Must validate inputs before processing
- Never trust external API status codes blindly
- All uploads must be verified against remote state
"""
        entities = parser.parse_document(doc)
        dead_ends = [e for e in entities if e.entity_type == "dead_end"]
        assumptions = [e for e in entities if e.entity_type == "assumption"]
        assert len(dead_ends) == 2
        assert len(assumptions) == 3

    def test_scope_decision_entity_type(self, parser: GovDocParser) -> None:
        doc = """## Scope Decisions

- Only process unknown-category files
- Exclude PDF and EPUB formats
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 2
        assert all(e.entity_type == "scope_decision" for e in entities)

    def test_method_decision_entity_type(self, parser: GovDocParser) -> None:
        doc = """## Method Decisions

- Use batch API for production extraction
- Sequential processing for discovery phase only
"""
        entities = parser.parse_document(doc)
        assert len(entities) == 2
        assert all(e.entity_type == "method_decision" for e in entities)

    def test_full_document_with_all_section_types(
        self, parser: GovDocParser
    ) -> None:
        doc = """# Governance Doc

## Failure Stories

### Story 1: Test
Failed attempt.

## Key Assumptions

- Assumption one
- Assumption two

## Scope Decisions

- Scope decision one

## Method Decisions

- Method decision one
"""
        entities = parser.parse_document(doc)
        types = {e.entity_type for e in entities}
        assert types == {"dead_end", "assumption", "scope_decision", "method_decision"}
        assert len(entities) == 5
