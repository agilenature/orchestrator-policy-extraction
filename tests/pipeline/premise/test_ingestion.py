"""Tests for staging ingestion: JSONL to DuckDB premise_registry bridge.

Tests:
- ingest_staging with valid records -- all ingested, staging cleared
- ingest_staging with empty staging -- returns zeros
- ingest_staging with malformed + valid -- partial ingestion, errors counted
- derivation_depth computation
- Begging the Question detection (circular self-reference)
- Begging the Question NOT triggered when no circular reference
- run_staining with matching amnesia events
- run_staining with no matching premises
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from src.pipeline.durability.amnesia import AmnesiaEvent
from src.pipeline.premise.ingestion import ingest_staging, run_staining
from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.schema import create_premise_schema
from src.pipeline.premise.staging import append_to_staging
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


def _staging_path(tmp_path: Path) -> str:
    """Return a unique staging path within tmp_path."""
    return str(tmp_path / "premise_staging.jsonl")


def _make_staging_record(
    premise_id: str = "test-premise-1",
    claim: str = "Test claim",
    session_id: str = "sess-1",
    **kwargs,
) -> dict:
    """Create a staging record dict."""
    record = {
        "premise_id": premise_id,
        "claim": claim,
        "session_id": session_id,
    }
    record.update(kwargs)
    return record


class TestIngestStagingValid:
    """Tests for ingest_staging with valid records."""

    def test_ingests_three_valid_records(self, registry, tmp_path):
        """Three valid records should all be ingested and staging cleared."""
        path = _staging_path(tmp_path)
        records = [
            _make_staging_record("p1", "Claim one", "sess-1"),
            _make_staging_record("p2", "Claim two", "sess-1"),
            _make_staging_record("p3", "Claim three", "sess-2"),
        ]
        append_to_staging(records, path)

        stats = ingest_staging(registry, path)

        assert stats["ingested"] == 3
        assert stats["errors"] == 0
        assert stats["skipped"] == 0
        assert stats["begging_the_question"] == 0

        # Verify records in registry
        assert registry.get("p1") is not None
        assert registry.get("p2") is not None
        assert registry.get("p3") is not None

        # Staging should be cleared
        staging_file = Path(path)
        assert staging_file.exists()
        assert staging_file.read_text().strip() == ""

    def test_records_have_correct_fields(self, registry, tmp_path):
        """Ingested records should preserve all fields."""
        path = _staging_path(tmp_path)
        record = _make_staging_record(
            "p1", "File exists at path", "sess-1",
            validated_by="Read output confirmed",
            foil="wrong path",
            distinguishing_prop="correct directory",
            project_scope="/project-X",
        )
        append_to_staging([record], path)

        stats = ingest_staging(registry, path)
        assert stats["ingested"] == 1

        p = registry.get("p1")
        assert p.claim == "File exists at path"
        assert p.validated_by == "Read output confirmed"
        assert p.foil == "wrong path"
        assert p.project_scope == "/project-X"


class TestIngestStagingEmpty:
    """Tests for ingest_staging with empty staging."""

    def test_empty_returns_zeros(self, registry, tmp_path):
        """Empty staging file should return all zeros."""
        path = _staging_path(tmp_path)
        stats = ingest_staging(registry, path)
        assert stats == {
            "ingested": 0,
            "skipped": 0,
            "errors": 0,
            "begging_the_question": 0,
        }

    def test_no_staging_file(self, registry, tmp_path):
        """Non-existent staging file should return all zeros."""
        path = str(tmp_path / "nonexistent.jsonl")
        stats = ingest_staging(registry, path)
        assert stats["ingested"] == 0


class TestIngestStagingPartial:
    """Tests for ingest_staging with malformed records."""

    def test_partial_ingestion(self, registry, tmp_path):
        """One malformed + two valid should ingest 2, error 1."""
        path = _staging_path(tmp_path)

        # Write records manually (one malformed without required field)
        records = [
            _make_staging_record("p1", "Valid claim one", "sess-1"),
            {"claim": "Missing premise_id"},  # Malformed: no premise_id
            _make_staging_record("p3", "Valid claim three", "sess-2"),
        ]
        append_to_staging(records, path)

        stats = ingest_staging(registry, path)

        assert stats["ingested"] == 2
        assert stats["errors"] == 1

        assert registry.get("p1") is not None
        assert registry.get("p3") is not None


class TestDerivationDepth:
    """Tests for derivation_depth computation."""

    def test_computes_depth_from_chain(self, registry, tmp_path):
        """Ingested premise with derivation_chain should have correct depth."""
        path = _staging_path(tmp_path)
        record = _make_staging_record(
            "p1", "Derived claim", "sess-1",
            derivation_chain=[
                {"derives_from": "abc123"},
                {"derives_from": "def456"},
            ],
        )
        append_to_staging([record], path)

        stats = ingest_staging(registry, path)
        assert stats["ingested"] == 1

        p = registry.get("p1")
        assert p.derivation_depth == 2

    def test_no_chain_leaves_depth_zero(self, registry, tmp_path):
        """Premise without derivation_chain should have depth 0."""
        path = _staging_path(tmp_path)
        record = _make_staging_record("p1", "Direct claim", "sess-1")
        append_to_staging([record], path)

        stats = ingest_staging(registry, path)
        p = registry.get("p1")
        assert p.derivation_depth == 0


class TestBeggingTheQuestion:
    """Tests for Begging the Question detection."""

    def test_detects_circular_self_reference(self, registry, tmp_path):
        """Premise whose own ID appears in derivation_chain should be stained."""
        path = _staging_path(tmp_path)
        record = _make_staging_record(
            "circular-1", "I derive from myself", "sess-1",
            derivation_chain=[
                {"derives_from": "other-premise"},
                {"derives_from": "circular-1"},  # Self-reference!
            ],
        )
        append_to_staging([record], path)

        stats = ingest_staging(registry, path)

        assert stats["begging_the_question"] == 1
        assert stats["ingested"] == 1

        p = registry.get("circular-1")
        assert p.staining_record is not None
        assert p.staining_record["stained"] is True
        assert p.staining_record["stained_by"] == "begging_the_question"
        assert p.staleness_counter == 1

    def test_no_circular_no_staining(self, registry, tmp_path):
        """Premise without circular reference should NOT be stained."""
        path = _staging_path(tmp_path)
        record = _make_staging_record(
            "normal-1", "Normal derivation", "sess-1",
            derivation_chain=[
                {"derives_from": "parent-a"},
                {"derives_from": "parent-b"},
            ],
        )
        append_to_staging([record], path)

        stats = ingest_staging(registry, path)

        assert stats["begging_the_question"] == 0

        p = registry.get("normal-1")
        assert p.staining_record is None or p.staining_record.get("stained") is not True

    def test_depth_still_computed_when_circular(self, registry, tmp_path):
        """Circular premise should still have correct derivation_depth."""
        path = _staging_path(tmp_path)
        record = _make_staging_record(
            "circular-2", "Circular with depth", "sess-1",
            derivation_chain=[
                {"derives_from": "circular-2"},
                {"derives_from": "other"},
                {"derives_from": "another"},
            ],
        )
        append_to_staging([record], path)

        stats = ingest_staging(registry, path)
        p = registry.get("circular-2")
        assert p.derivation_depth == 3
        assert stats["begging_the_question"] == 1


class TestRunStaining:
    """Tests for run_staining integration."""

    def test_stains_matching_premises(self, registry):
        """run_staining should stain premises matching amnesia events."""
        # Register a premise referencing a constraint
        registry.register(PremiseRecord(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Confirmed via constraint-A evaluation",
        ))

        amnesia_events = [
            AmnesiaEvent(
                amnesia_id="am-1",
                session_id="sess-1",
                constraint_id="constraint-A",
                constraint_type="behavioral_constraint",
                severity="warning",
                evidence=[],
                detected_at="2026-02-23T10:00:00Z",
            )
        ]

        stats = run_staining(registry, amnesia_events)

        assert stats["direct_stains"] == 1
        p = registry.get("p1")
        assert p.staining_record is not None
        assert p.staining_record["stained"] is True

    def test_no_matching_premises(self, registry):
        """run_staining with no matching premises should return zero stains."""
        # Register a premise NOT referencing the constraint
        registry.register(PremiseRecord(
            premise_id="p1",
            claim="File exists",
            session_id="sess-1",
            validated_by="Manual inspection",
        ))

        amnesia_events = [
            AmnesiaEvent(
                amnesia_id="am-1",
                session_id="sess-1",
                constraint_id="constraint-X",
                constraint_type="behavioral_constraint",
                severity="warning",
                evidence=[],
                detected_at="2026-02-23T10:00:00Z",
            )
        ]

        stats = run_staining(registry, amnesia_events)
        assert stats["direct_stains"] == 0
        assert stats["propagated_stains"] == 0

    def test_staining_with_propagation(self, registry):
        """run_staining should propagate staining through derivation chains."""
        # Parent premise that will be stained
        registry.register(PremiseRecord(
            premise_id="parent-1",
            claim="Parent claim",
            session_id="sess-1",
            validated_by="Confirmed via constraint-B",
        ))
        # Child that derives from parent
        registry.register(PremiseRecord(
            premise_id="child-1",
            claim="Child claim",
            session_id="sess-1",
            derivation_chain=[{"derives_from": "parent-1"}],
        ))

        amnesia_events = [
            AmnesiaEvent(
                amnesia_id="am-2",
                session_id="sess-1",
                constraint_id="constraint-B",
                constraint_type="behavioral_constraint",
                severity="forbidden",
                evidence=[],
                detected_at="2026-02-23T10:00:00Z",
            )
        ]

        stats = run_staining(registry, amnesia_events)

        assert stats["direct_stains"] == 1
        assert stats["propagated_stains"] == 1

        parent = registry.get("parent-1")
        child = registry.get("child-1")
        assert parent.staining_record["stained"] is True
        assert child.staining_record["stained"] is True

    def test_empty_amnesia_events(self, registry):
        """run_staining with empty events should return zeros."""
        stats = run_staining(registry, [])
        assert stats == {"direct_stains": 0, "propagated_stains": 0}
