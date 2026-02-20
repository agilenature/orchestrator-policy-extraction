"""Header-hierarchy Markdown parser for governance documents.

Extracts structured entities from Markdown documents by classifying
H2/H3 sections via keyword matching. Supports failure stories (H3
sub-headings), assumptions (bullet lists), and decision sections.

Uses only Python ``re`` stdlib -- no external parsing dependencies.

Exports:
    ParsedEntity: Single extracted entity with type, title, content
    ParsedSection: Intermediate section representation
    GovDocParser: Main parser class
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedEntity:
    """A single entity extracted from a governance document.

    Attributes:
        entity_type: One of dead_end, assumption, scope_decision, method_decision.
        title: Human-readable title (H3 text or list item first line).
        content: Full body text of the entity.
        source_section: The H2 section header this was extracted from.
    """

    entity_type: str
    title: str
    content: str
    source_section: str


@dataclass
class ParsedSection:
    """An intermediate representation of a classified Markdown section.

    Attributes:
        header_level: 2 or 3 (from ## or ###).
        header_text: The raw header text after the # symbols.
        section_type: Classified type or empty string if unclassified.
        body: Text content between this header and the next same-or-higher-level header.
    """

    header_level: int
    header_text: str
    section_type: str
    body: str


class GovDocParser:
    """Markdown parser that extracts governance entities from H2/H3 sections.

    Classification uses case-insensitive keyword substring matching
    against a predefined set of section keywords. "Decisions" alone
    does NOT match -- the header must specifically say "Scope Decisions"
    or "Method Decisions" to avoid ambiguity.

    Usage::

        parser = GovDocParser()
        entities = parser.parse_document(content, source_id="premortem")
    """

    SECTION_KEYWORDS: dict[str, list[str]] = {
        "failure_story": ["failure stories", "ways we could fail", "dead ends"],
        "assumption": ["assumptions", "key assumptions", "core assumptions"],
        "scope_decision": ["scope decisions"],
        "method_decision": ["method decisions"],
    }

    _ENTITY_TYPE_MAP: dict[str, str] = {
        "failure_story": "dead_end",
        "assumption": "assumption",
        "scope_decision": "scope_decision",
        "method_decision": "method_decision",
    }

    _HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    _LIST_ITEM_RE = re.compile(r"^[-*]\s+(.+)", re.MULTILINE)
    _NUMBERED_ITEM_RE = re.compile(r"^\d+\.\s+(.+)", re.MULTILINE)

    def parse_document(
        self, content: str, source_id: str = ""
    ) -> list[ParsedEntity]:
        """Parse a Markdown document and extract typed entities.

        Steps:
            1. Find all H2/H3 headers via regex.
            2. Classify each header via keyword substring matching.
            3. Extract body text between headers.
            4. Within classified H2 sections, extract entities from
               H3 sub-headings or top-level list items.

        Args:
            content: Raw Markdown text.
            source_id: Identifier for the source document.

        Returns:
            List of ParsedEntity instances extracted from the document.
        """
        headers = list(self._HEADER_RE.finditer(content))
        if not headers:
            return []

        # Build sections with body text
        sections: list[ParsedSection] = []
        for i, match in enumerate(headers):
            level = len(match.group(1))
            text = match.group(2).strip()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
            body = content[start:end].strip()
            section_type = self._classify_header(text) or ""
            sections.append(ParsedSection(level, text, section_type, body))

        # Extract entities from classified H2 sections
        entities: list[ParsedEntity] = []
        for i, section in enumerate(sections):
            if section.header_level != 2 or not section.section_type:
                continue

            entity_type = self._ENTITY_TYPE_MAP[section.section_type]

            # Collect H3 sub-sections that belong to this H2
            h3_sections = self._collect_h3_children(sections, i)

            if h3_sections:
                # Each H3 block = one entity
                for h3 in h3_sections:
                    entities.append(
                        ParsedEntity(
                            entity_type=entity_type,
                            title=h3.header_text,
                            content=h3.body,
                            source_section=section.header_text,
                        )
                    )
            else:
                # Extract from list items in the section body
                list_entities = self._extract_list_entities(
                    section.body, entity_type, section.header_text
                )
                entities.extend(list_entities)

        return entities

    def _classify_header(self, text: str) -> str | None:
        """Classify a header by case-insensitive keyword substring matching.

        Args:
            text: The header text (without # prefix).

        Returns:
            Section type string or None if no keywords match.
        """
        lower = text.lower()
        for section_type, keywords in self.SECTION_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return section_type
        return None

    def _collect_h3_children(
        self, sections: list[ParsedSection], parent_idx: int
    ) -> list[ParsedSection]:
        """Collect H3 sections that are children of the H2 at parent_idx.

        Stops when another H2 (or higher) is encountered.

        Args:
            sections: All parsed sections.
            parent_idx: Index of the parent H2 section.

        Returns:
            List of H3 ParsedSection children.
        """
        children: list[ParsedSection] = []
        for j in range(parent_idx + 1, len(sections)):
            if sections[j].header_level <= 2:
                break
            if sections[j].header_level == 3:
                children.append(sections[j])
        return children

    def _extract_list_entities(
        self, body: str, entity_type: str, source_section: str
    ) -> list[ParsedEntity]:
        """Extract entities from bullet or numbered list items.

        Handles multi-line list items by treating continuation lines
        (lines that do not start a new list item and are not blank) as
        part of the preceding item. Only top-level items are extracted;
        nested sub-items are included in the parent item's content.

        Args:
            body: The section body text.
            entity_type: Entity type to assign to each item.
            source_section: Parent section header for provenance.

        Returns:
            List of ParsedEntity for each list item.
        """
        entities: list[ParsedEntity] = []
        lines = body.split("\n")
        current_item: list[str] | None = None

        # Pattern for top-level list items (bullet or numbered)
        item_re = re.compile(r"^(?:[-*]|\d+\.)\s+(.+)")

        for line in lines:
            match = item_re.match(line)
            if match:
                # Flush previous item
                if current_item is not None:
                    self._flush_list_item(
                        current_item, entity_type, source_section, entities
                    )
                current_item = [match.group(1).strip()]
            elif current_item is not None and line.strip():
                # Continuation line (indented or otherwise non-empty)
                current_item.append(line.strip())

        # Flush final item
        if current_item is not None:
            self._flush_list_item(
                current_item, entity_type, source_section, entities
            )

        return entities

    @staticmethod
    def _flush_list_item(
        item_lines: list[str],
        entity_type: str,
        source_section: str,
        entities: list[ParsedEntity],
    ) -> None:
        """Create a ParsedEntity from accumulated list item lines.

        The first line becomes the title; all lines form the content.

        Args:
            item_lines: Lines belonging to this list item.
            entity_type: Entity type to assign.
            source_section: Parent section header.
            entities: List to append the new entity to.
        """
        title = item_lines[0]
        content = " ".join(item_lines)
        entities.append(
            ParsedEntity(
                entity_type=entity_type,
                title=title,
                content=content,
                source_section=source_section,
            )
        )
