"""Tests for StainingPipeline: amnesia staining + derivation propagation.

Tests:
- stain_from_amnesia() correctly stains matching premises
- Premises NOT referencing the constraint are NOT stained
- propagate_staining() stains child premises in derivation_chain
- Propagation visited set prevents infinite loops
- stain_from_policy_violation() stains contradicting premises
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.durability.amnesia import AmnesiaEvent
from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.schema import create_premise_schema
from src.pipeline.premise.staining import StainingPipeline
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """Create an in-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    create_premise_schema(c)
    yield c
    c.close()


@pytest.fixture
def registry(conn):
    """Create a PremiseRegistry with a prepared connection."""
    return PremiseRegistry(conn)


@pytest.fixture
def pipeline(registry):
    """Create a StainingPipeline."""
    return StainingPipeline(registry)


def _make_record(
    premise_id: str = "abc123def456abcd",
    claim: str = "Test claim",
    session_id: str = "sess-1",
    **kwargs,
) -> PremiseRecord:
    """Helper to create a PremiseRecord with defaults."""
    return PremiseRecord(
        premise_id=premise_id,
        claim=claim,
        session_id=session_id,
        **kwargs,
    )


def _make_amnesia_event(
    amnesia_id: str = "amnesia-1",
    session_id: str = "sess-1",
    constraint_id: str = "constraint-A",
) -> AmnesiaEvent:
    """Helper to create an AmnesiaEvent."""
    return AmnesiaEvent(
        amnesia_id=amnesia_id,
        session_id=session_id,
        constraint_id=constraint_id,
        constraint_type="behavioral_constraint",
        severity="warning",
        evidence=[],
        detected_at="2026-02-23T10:00:00Z",
    )


class TestStainFromAmnesia:
    """Tests for stain_from_amnesia()."""

    def test_stains_matching_premises(self, pipeline, registry):
        """Premises with validated_by referencing violated constraint should be stained."""
        registry.register(_make_record(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A evaluation",
        ))
        registry.register(_make_record(
            premise_id="p2",
            claim="API works",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A check",
        ))

        event = _make_amnesia_event(constraint_id="constraint-A")
        stained = pipeline.stain_from_amnesia([event])

        assert "p1" in stained
        assert "p2" in stained

        # Verify staining record
        p1 = registry.get("p1")
        assert p1.staining_record is not None
        assert p1.staining_record["stained"] is True
        assert "amnesia:amnesia-1" in p1.staining_record["stained_by"]

    def test_does_not_stain_unrelated(self, pipeline, registry):
        """Premises NOT referencing the constraint should NOT be stained."""
        registry.register(_make_record(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A evaluation",
        ))
        registry.register(_make_record(
            premise_id="p2",
            claim="Schema correct",
            session_id="sess-1",
            validated_by="Manual inspection of schema.sql",
        ))

        event = _make_amnesia_event(constraint_id="constraint-A")
        stained = pipeline.stain_from_amnesia([event])

        assert "p1" in stained
        assert "p2" not in stained

        p2 = registry.get("p2")
        # p2 should not be stained
        assert p2.staining_record is None or p2.staining_record.get("stained") is not True

    def test_does_not_stain_other_sessions(self, pipeline, registry):
        """Amnesia in sess-1 should not stain premises in sess-2."""
        registry.register(_make_record(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A",
        ))
        registry.register(_make_record(
            premise_id="p2",
            claim="File exists too",
            session_id="sess-2",
            validated_by="Confirmed via constraint-A",
        ))

        event = _make_amnesia_event(session_id="sess-1", constraint_id="constraint-A")
        stained = pipeline.stain_from_amnesia([event])

        assert "p1" in stained
        assert "p2" not in stained

    def test_skips_already_stained(self, pipeline, registry):
        """Already stained premises should not be re-stained."""
        registry.register(_make_record(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A",
            staining_record={"stained": True, "stained_by": "previous"},
        ))

        event = _make_amnesia_event(constraint_id="constraint-A")
        stained = pipeline.stain_from_amnesia([event])

        assert "p1" not in stained

    def test_multiple_amnesia_events(self, pipeline, registry):
        """Multiple amnesia events should each stain their matching premises."""
        registry.register(_make_record(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A",
        ))
        registry.register(_make_record(
            premise_id="p2",
            claim="Schema correct",
            session_id="sess-2",
            validated_by="Confirmed via constraint-B",
        ))

        events = [
            _make_amnesia_event(
                amnesia_id="am-1", session_id="sess-1", constraint_id="constraint-A"
            ),
            _make_amnesia_event(
                amnesia_id="am-2", session_id="sess-2", constraint_id="constraint-B"
            ),
        ]
        stained = pipeline.stain_from_amnesia(events)

        assert "p1" in stained
        assert "p2" in stained


class TestPropagateStaining:
    """Tests for propagate_staining() (Stolen Concept detection)."""

    def test_propagates_to_children(self, pipeline, registry):
        """Stained parent should stain children in derivation_chain."""
        # Register parent (already stained)
        registry.register(_make_record(
            premise_id="parent-1",
            claim="Parent premise",
            session_id="sess-1",
            staining_record={"stained": True, "stained_by": "amnesia:am-1"},
        ))
        # Register child that derives from parent
        registry.register(_make_record(
            premise_id="child-1",
            claim="Child premise",
            session_id="sess-1",
            derivation_chain=[{"derives_from": "parent-1"}],
        ))

        propagated = pipeline.propagate_staining()

        assert "child-1" in propagated
        child = registry.get("child-1")
        assert child.staining_record is not None
        assert child.staining_record["stained"] is True
        assert "propagation:parent-1" in child.staining_record["stained_by"]

    def test_transitive_propagation(self, pipeline, registry):
        """Staining should propagate transitively: grandparent -> parent -> child."""
        registry.register(_make_record(
            premise_id="grandparent",
            claim="Grandparent premise",
            session_id="sess-1",
            staining_record={"stained": True, "stained_by": "amnesia:am-1"},
        ))
        registry.register(_make_record(
            premise_id="parent",
            claim="Parent premise",
            session_id="sess-1",
            derivation_chain=[{"derives_from": "grandparent"}],
        ))
        registry.register(_make_record(
            premise_id="child",
            claim="Child premise",
            session_id="sess-1",
            derivation_chain=[{"derives_from": "parent"}],
        ))

        propagated = pipeline.propagate_staining()

        assert "parent" in propagated
        assert "child" in propagated

    def test_no_infinite_loop(self, pipeline, registry):
        """Circular derivation chains should not cause infinite loops."""
        # Create circular chain: A derives from B, B derives from A
        registry.register(_make_record(
            premise_id="cycle-A",
            claim="Cycle A",
            session_id="sess-1",
            staining_record={"stained": True, "stained_by": "test"},
            derivation_chain=[{"derives_from": "cycle-B"}],
        ))
        registry.register(_make_record(
            premise_id="cycle-B",
            claim="Cycle B",
            session_id="sess-1",
            derivation_chain=[{"derives_from": "cycle-A"}],
        ))

        # Should complete without hanging
        propagated = pipeline.propagate_staining()
        # cycle-B should be stained (via cycle-A which is already stained)
        assert "cycle-B" in propagated

    def test_does_not_stain_unrelated(self, pipeline, registry):
        """Premises not in the derivation chain should not be stained."""
        registry.register(_make_record(
            premise_id="stained-parent",
            claim="Stained parent",
            session_id="sess-1",
            staining_record={"stained": True, "stained_by": "test"},
        ))
        registry.register(_make_record(
            premise_id="unrelated",
            claim="Unrelated premise",
            session_id="sess-1",
            # No derivation chain at all
        ))

        propagated = pipeline.propagate_staining()
        assert "unrelated" not in propagated


class TestStainFromPolicyViolation:
    """Tests for stain_from_policy_violation()."""

    def test_stains_contradicting_premise(self, pipeline, registry):
        """Premise claiming constraint 'does not apply' should be stained."""
        registry.register(_make_record(
            premise_id="p1",
            claim="The validation constraint does not apply to this case",
            session_id="sess-1",
        ))

        stained = pipeline.stain_from_policy_violation("constraint-X", "sess-1")

        assert "p1" in stained
        p1 = registry.get("p1")
        assert p1.staining_record is not None
        assert "policy_violation:constraint-X" in p1.staining_record["stained_by"]

    def test_stains_not_relevant_claim(self, pipeline, registry):
        """Premise claiming constraint is 'not relevant' should be stained."""
        registry.register(_make_record(
            premise_id="p1",
            claim="This rule is not relevant for the current context",
            session_id="sess-1",
        ))

        stained = pipeline.stain_from_policy_violation("constraint-Y", "sess-1")
        assert "p1" in stained

    def test_does_not_stain_normal_premise(self, pipeline, registry):
        """Normal premises should not be stained by policy violation."""
        registry.register(_make_record(
            premise_id="p1",
            claim="The file exists at /src/main.py",
            session_id="sess-1",
        ))

        stained = pipeline.stain_from_policy_violation("constraint-Z", "sess-1")
        assert stained == []

    def test_case_insensitive_matching(self, pipeline, registry):
        """Contradiction markers should be matched case-insensitively."""
        registry.register(_make_record(
            premise_id="p1",
            claim="The rule Does Not Apply here",
            session_id="sess-1",
        ))

        stained = pipeline.stain_from_policy_violation("constraint-W", "sess-1")
        assert "p1" in stained
