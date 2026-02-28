"""PREMISE block regex parser for extracting structured premises from AI text.

Parses PREMISE declaration blocks from AI text output (conversation text,
JSONL transcript entries) into structured ParsedPremise objects. Also parses
FOIL_VERIFIED blocks.

The PREMISE block format (from ~/.claude/CLAUDE.md):
    PREMISE: [claim]
    VALIDATED_BY: [evidence or UNVALIDATED]
    FOIL: [confusable] | [distinguishing property]
    SCOPE: [validity context]

The FOIL_VERIFIED block format:
    FOIL_VERIFIED: [premise claim]
    VERIFIED_BY: [specific tool call and output]
    RESULT: [what was confirmed]

Parser is tolerant of:
- Optional leading whitespace on each line
- \\r\\n or \\n line endings
- Missing FOIL separator (| )
- Blocks inside markdown code fences
- Extra whitespace around field values

Cross-premise reference detection:
    After parsing each PREMISE block, scans the validated_by text for
    references to other premise IDs (16-hex-char strings matching the
    make_id output format, or PREMISE- prefixed identifiers).

Exports:
    PREMISE_BLOCK_RE: Pre-compiled regex for PREMISE blocks
    FOIL_VERIFIED_BLOCK_RE: Pre-compiled regex for FOIL_VERIFIED blocks
    parse_premise_blocks: Extract ParsedPremise objects from text
    parse_foil_verified_blocks: Extract FOIL_VERIFIED dicts from text
"""

from __future__ import annotations

import re

from src.pipeline.premise.models import ParsedPremise


# Pre-compiled regex for PREMISE blocks.
# Tolerant: allows optional leading whitespace, handles \r\n or \n,
# captures multi-word field values up to the next field or end of block.
PREMISE_BLOCK_RE = re.compile(
    r"^\s*PREMISE:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*VALIDATED_BY:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*FOIL:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*SCOPE:\s*(.+?)[ \t]*(?:\r?\n)"
    r"(?:^\s*GENUS:\s*(.+?)[ \t]*(?:\r?\n|$))?",
    re.MULTILINE,
)

# Pre-compiled regex for FOIL_VERIFIED blocks.
FOIL_VERIFIED_BLOCK_RE = re.compile(
    r"^\s*FOIL_VERIFIED:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*VERIFIED_BY:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*RESULT:\s*(.+?)[ \t]*(?:\r?\n|$)",
    re.MULTILINE,
)

# Regex for detecting cross-premise references in validated_by text.
# Matches 16-hex-char IDs (the make_id output format) or PREMISE-<id> patterns.
_PREMISE_ID_REF_RE = re.compile(r"\b([0-9a-f]{16})\b")
_PREMISE_PREFIX_REF_RE = re.compile(r"\bPREMISE-(\S+)")


def parse_premise_blocks(text: str) -> list[ParsedPremise]:
    """Extract all PREMISE blocks from a text string.

    Parses the text for PREMISE declaration blocks and returns structured
    ParsedPremise objects. Handles multiple blocks in one text, blocks
    inside code fences, and various formatting variations.

    After parsing each block, scans validated_by for cross-premise
    references and populates derivation_chain if found.

    Args:
        text: Raw AI text output that may contain PREMISE blocks.

    Returns:
        List of ParsedPremise objects, one per block found.
    """
    if not text:
        return []

    results: list[ParsedPremise] = []

    for match in PREMISE_BLOCK_RE.finditer(text):
        claim = match.group(1).strip()
        validated_by = match.group(2).strip()
        foil_line = match.group(3).strip()
        scope = match.group(4).strip()

        # Detect UNVALIDATED status (case-insensitive)
        is_unvalidated = validated_by.upper().startswith("UNVALIDATED")

        # Split FOIL on " | " for foil vs distinguishing_prop
        if " | " in foil_line:
            parts = foil_line.split(" | ", 1)
            foil = parts[0].strip()
            distinguishing_prop = parts[1].strip()
        else:
            foil = foil_line if foil_line else None
            distinguishing_prop = None

        # Detect cross-premise references in validated_by
        derivation_chain = _detect_cross_references(validated_by)

        # Parse optional GENUS field (group 5)
        genus_line = match.group(5)
        genus_name = None
        genus_instances: list[str] | None = None
        if genus_line:
            genus_line = genus_line.strip()
            if " | INSTANCES: " in genus_line:
                parts = genus_line.split(" | INSTANCES: ", 1)
                genus_name = parts[0].strip()
                raw_instances = parts[1].strip()
                raw_instances = raw_instances.strip("[]")
                genus_instances = [i.strip() for i in raw_instances.split(",") if i.strip()]
            else:
                genus_name = genus_line

        results.append(
            ParsedPremise(
                claim=claim,
                validated_by=validated_by,
                is_unvalidated=is_unvalidated,
                foil=foil,
                distinguishing_prop=distinguishing_prop,
                scope=scope,
                derivation_chain=derivation_chain,
                genus_name=genus_name,
                genus_instances=genus_instances,
            )
        )

    return results


def parse_foil_verified_blocks(text: str) -> list[dict]:
    """Extract all FOIL_VERIFIED blocks from a text string.

    Parses the text for FOIL_VERIFIED declaration blocks and returns
    dicts with keys: premise_claim, verified_by, result.

    Args:
        text: Raw AI text output that may contain FOIL_VERIFIED blocks.

    Returns:
        List of dicts, one per FOIL_VERIFIED block found.
    """
    if not text:
        return []

    results: list[dict] = []

    for match in FOIL_VERIFIED_BLOCK_RE.finditer(text):
        results.append(
            {
                "premise_claim": match.group(1).strip(),
                "verified_by": match.group(2).strip(),
                "result": match.group(3).strip(),
            }
        )

    return results


def _detect_cross_references(validated_by: str) -> list[dict] | None:
    """Detect cross-premise references in validated_by text.

    Scans for:
    - 16-hex-char IDs matching the make_id output format
    - PREMISE-<identifier> patterns

    Args:
        validated_by: The validated_by field text from a PREMISE block.

    Returns:
        List of derivation_chain entries, or None if no references found.
    """
    refs: list[dict] = []
    seen: set[str] = set()

    # Check for 16-hex-char premise IDs
    for match in _PREMISE_ID_REF_RE.finditer(validated_by):
        ref_id = match.group(1)
        if ref_id not in seen:
            refs.append({"derives_from": ref_id})
            seen.add(ref_id)

    # Check for PREMISE-<id> patterns
    for match in _PREMISE_PREFIX_REF_RE.finditer(validated_by):
        ref_id = match.group(1)
        if ref_id not in seen:
            refs.append({"derives_from": ref_id})
            seen.add(ref_id)

    return refs if refs else None
