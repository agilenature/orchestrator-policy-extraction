"""Pydantic v2 models for premise registry records and parsed premise blocks.

Two models:

1. ParsedPremise: Represents a PREMISE block extracted from AI text output.
   Fields match the PREMISE declaration format in ~/.claude/CLAUDE.md.

2. PremiseRecord: Represents a row in the premise_registry DuckDB table.
   All 20 columns from the PREMISE-01 spec, with deterministic ID generation.

Both models are frozen (immutable) matching project patterns from
src/pipeline/models/episodes.py.

Exports:
    ParsedPremise: Parsed PREMISE block fields
    PremiseRecord: Full premise registry row with make_id classmethod
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict


class ParsedPremise(BaseModel, frozen=True):
    """A PREMISE block extracted from AI text output.

    Fields match the PREMISE declaration format:
        PREMISE: [claim]
        VALIDATED_BY: [evidence or UNVALIDATED]
        FOIL: [confusable] | [distinguishing property]
        SCOPE: [validity context]

    Attributes:
        claim: The PREMISE assertion text.
        validated_by: Evidence text or "UNVALIDATED -- reason".
        is_unvalidated: True when validated_by starts with "UNVALIDATED".
        foil: The confusable alternative, or None.
        distinguishing_prop: What distinguishes claim from foil, or None.
        scope: Validity context for the premise.
        derivation_chain: Cross-premise references detected in validated_by.
    """

    model_config = ConfigDict(populate_by_name=True)

    claim: str
    validated_by: str
    is_unvalidated: bool
    foil: str | None = None
    distinguishing_prop: str | None = None
    scope: str
    derivation_chain: list[dict] | None = None


class PremiseRecord(BaseModel, frozen=True):
    """A row in the premise_registry DuckDB table.

    All 20 columns from the PREMISE-01 spec. JSON columns are stored
    as Python dicts/lists and serialized to JSON strings for DuckDB.

    Attributes:
        premise_id: SHA-256(claim + session_id + tool_use_id)[:16].
        claim: The PREMISE assertion text.
        validated_by: Evidence text, or None.
        validation_context: Additional context about the validation.
        foil: The confusable alternative.
        distinguishing_prop: What distinguishes claim from foil.
        staleness_counter: Incremented each session where premise reused.
        staining_record: JSON dict with stained, stained_by, stained_at, ground_truth_pointer.
        ground_truth_pointer: JSON dict with session_id, episode_id, event_id, tool_use_id.
        project_scope: Project path where this premise was declared.
        session_id: Session where premise was declared.
        tool_use_id: The tool_use that this premise preceded.
        foil_path_outcomes: JSON list of foil path outcome records.
        divergence_patterns: JSON list of divergence pattern records.
        parent_episode_links: JSON list of parent episode link records.
        derivation_depth: Depth of derivation chain (0 = direct or circular).
        validation_calls_before_claim: Count of validation tool calls before this premise.
        derivation_chain: JSON list of derivation chain entries.
        created_at: ISO 8601 timestamp of creation.
        updated_at: ISO 8601 timestamp of last update.
    """

    model_config = ConfigDict(populate_by_name=True)

    premise_id: str
    claim: str
    validated_by: str | None = None
    validation_context: str | None = None
    foil: str | None = None
    distinguishing_prop: str | None = None
    staleness_counter: int = 0
    staining_record: dict | None = None
    ground_truth_pointer: dict | None = None
    project_scope: str | None = None
    session_id: str
    tool_use_id: str | None = None
    foil_path_outcomes: list[dict] | None = None
    divergence_patterns: list[dict] | None = None
    parent_episode_links: list[dict] | None = None
    derivation_depth: int = 0
    validation_calls_before_claim: int = 0
    derivation_chain: list[dict] | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def make_id(cls, claim: str, session_id: str, tool_use_id: str) -> str:
        """Generate a deterministic premise_id from claim + session + tool_use.

        Returns first 16 hex chars of SHA-256 hash, matching the project-wide
        ID convention (see AmnesiaDetector in src/pipeline/durability/amnesia.py).

        Args:
            claim: The PREMISE assertion text.
            session_id: Session where the premise was declared.
            tool_use_id: The tool_use_id that this premise preceded.

        Returns:
            16-character hex string.
        """
        return hashlib.sha256(
            (claim + session_id + tool_use_id).encode()
        ).hexdigest()[:16]
