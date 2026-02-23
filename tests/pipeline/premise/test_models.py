"""Tests for premise registry Pydantic models.

Tests:
- PremiseRecord.make_id() determinism and format
- ParsedPremise field validation and defaults
- Frozen immutability for both models
"""

from __future__ import annotations

import pytest

from src.pipeline.premise.models import ParsedPremise, PremiseRecord


class TestPremiseRecordMakeId:
    """Tests for PremiseRecord.make_id() deterministic ID generation."""

    def test_make_id_returns_16_hex_chars(self):
        """make_id should return exactly 16 hex characters."""
        result = PremiseRecord.make_id("test claim", "session-1", "tool-1")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_make_id_deterministic(self):
        """Same inputs should always produce same ID."""
        id1 = PremiseRecord.make_id("claim A", "sess-1", "tool-1")
        id2 = PremiseRecord.make_id("claim A", "sess-1", "tool-1")
        assert id1 == id2

    def test_make_id_different_inputs_differ(self):
        """Different inputs should produce different IDs."""
        id1 = PremiseRecord.make_id("claim A", "sess-1", "tool-1")
        id2 = PremiseRecord.make_id("claim B", "sess-1", "tool-1")
        id3 = PremiseRecord.make_id("claim A", "sess-2", "tool-1")
        id4 = PremiseRecord.make_id("claim A", "sess-1", "tool-2")
        assert len({id1, id2, id3, id4}) == 4

    def test_make_id_matches_sha256_prefix(self):
        """make_id should match SHA-256 hash prefix of concatenated inputs."""
        import hashlib

        claim = "test claim"
        session_id = "session-1"
        tool_use_id = "tool-1"
        expected = hashlib.sha256(
            (claim + session_id + tool_use_id).encode()
        ).hexdigest()[:16]
        assert PremiseRecord.make_id(claim, session_id, tool_use_id) == expected


class TestPremiseRecordModel:
    """Tests for PremiseRecord Pydantic model."""

    def test_minimal_record(self):
        """PremiseRecord should create with only required fields."""
        record = PremiseRecord(
            premise_id="abc123def456abcd",
            claim="Test claim",
            session_id="sess-1",
        )
        assert record.premise_id == "abc123def456abcd"
        assert record.claim == "Test claim"
        assert record.session_id == "sess-1"
        assert record.staleness_counter == 0
        assert record.derivation_depth == 0
        assert record.validation_calls_before_claim == 0

    def test_full_record(self):
        """PremiseRecord should accept all 20 fields."""
        record = PremiseRecord(
            premise_id="abc123def456abcd",
            claim="Test claim",
            validated_by="Read output confirmed",
            validation_context="File exists at path",
            foil="wrong path",
            distinguishing_prop="correct directory",
            staleness_counter=3,
            staining_record={"stained": True, "stained_by": "amnesia-1"},
            ground_truth_pointer={"session_id": "s1", "episode_id": "e1"},
            project_scope="/path/to/project",
            session_id="sess-1",
            tool_use_id="toolu_01abc",
            foil_path_outcomes=[{"episode_id": "e2", "outcome": "diverged"}],
            divergence_patterns=[{"tool_call_claim": "Edit", "tool_call_foil": "Write"}],
            parent_episode_links=[{"episode_id": "e0", "relationship": "parent"}],
            derivation_depth=2,
            validation_calls_before_claim=3,
            derivation_chain=[{"derives_from": "abc123def456abcd"}],
            created_at="2026-02-23T12:00:00Z",
            updated_at="2026-02-23T12:00:00Z",
        )
        assert record.staleness_counter == 3
        assert record.staining_record["stained"] is True
        assert record.derivation_depth == 2

    def test_frozen_immutability(self):
        """PremiseRecord should be immutable (frozen=True)."""
        record = PremiseRecord(
            premise_id="abc123def456abcd",
            claim="Test claim",
            session_id="sess-1",
        )
        with pytest.raises(Exception):
            record.claim = "Modified claim"

    def test_json_column_defaults_none(self):
        """JSON columns should default to None."""
        record = PremiseRecord(
            premise_id="abc123def456abcd",
            claim="Test claim",
            session_id="sess-1",
        )
        assert record.staining_record is None
        assert record.ground_truth_pointer is None
        assert record.foil_path_outcomes is None
        assert record.divergence_patterns is None
        assert record.parent_episode_links is None
        assert record.derivation_chain is None


class TestParsedPremiseModel:
    """Tests for ParsedPremise Pydantic model."""

    def test_basic_parsed_premise(self):
        """ParsedPremise should create with required fields."""
        premise = ParsedPremise(
            claim="File exists at /src/main.py",
            validated_by="Read output line 1",
            is_unvalidated=False,
            foil="wrong file path",
            distinguishing_prop="directory matches src/",
            scope="this project",
        )
        assert premise.claim == "File exists at /src/main.py"
        assert premise.is_unvalidated is False
        assert premise.foil == "wrong file path"
        assert premise.derivation_chain is None

    def test_unvalidated_premise(self):
        """ParsedPremise should correctly represent UNVALIDATED state."""
        premise = ParsedPremise(
            claim="API uses v3 format",
            validated_by="UNVALIDATED -- need to check docs",
            is_unvalidated=True,
            scope="API module",
        )
        assert premise.is_unvalidated is True
        assert premise.foil is None
        assert premise.distinguishing_prop is None

    def test_with_derivation_chain(self):
        """ParsedPremise should accept derivation_chain list."""
        premise = ParsedPremise(
            claim="Config file format is YAML",
            validated_by="Validated by premise a1b2c3d4e5f6a7b8",
            is_unvalidated=False,
            foil="JSON config",
            distinguishing_prop="file extension .yaml",
            scope="this project",
            derivation_chain=[{"derives_from": "a1b2c3d4e5f6a7b8"}],
        )
        assert len(premise.derivation_chain) == 1
        assert premise.derivation_chain[0]["derives_from"] == "a1b2c3d4e5f6a7b8"

    def test_frozen_immutability(self):
        """ParsedPremise should be immutable (frozen=True)."""
        premise = ParsedPremise(
            claim="Test",
            validated_by="Test",
            is_unvalidated=False,
            scope="test",
        )
        with pytest.raises(Exception):
            premise.claim = "Modified"
