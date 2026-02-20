"""Tests for the governance dual-store ingestor.

Covers constraint writing, wisdom writing, severity heuristics,
co-occurrence linkage, dry-run mode, idempotency, and DECISIONS.md
handling (scope/method decisions produce only wisdom, not constraints).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.governance.ingestor import GovDocIngestor, GovIngestResult
from src.pipeline.wisdom.store import WisdomStore


@pytest.fixture
def constraint_store(tmp_path: Path) -> ConstraintStore:
    """ConstraintStore with isolated tmp_path and schema."""
    return ConstraintStore(
        path=tmp_path / "constraints.json",
        schema_path=Path("data/schemas/constraint.schema.json"),
    )


@pytest.fixture
def wisdom_store(tmp_path: Path) -> WisdomStore:
    """WisdomStore using a temp DuckDB file."""
    return WisdomStore(db_path=tmp_path / "test_wisdom.duckdb")


@pytest.fixture
def premortem_file(tmp_path: Path) -> Path:
    """A minimal pre-mortem fixture with 2 stories and 3 assumptions."""
    content = """# Test Pre-Mortem

## Failure Stories

### Story 1: Bad Library
We tried pybreaker but it uses consecutive failure counting, not percentage-based.

### Story 2: Wrong Pattern
The single-step upload assumption was incorrect.

## Key Assumptions

- Actual scan result counts must be verified by machine-checkable queries
- Constraint violations must never be silently overridden
- All uploads must be gated on completion verification
"""
    p = tmp_path / "test_premortem.md"
    p.write_text(content)
    return p


@pytest.fixture
def decisions_file(tmp_path: Path) -> Path:
    """A DECISIONS.md fixture with scope and method decisions only."""
    content = """# DECISIONS.md

## Scope Decisions

- Only process unknown-category files for AI metadata extraction
- Exclude PDF and EPUB formats from upload pipeline

## Method Decisions

- Use batch API for production extraction runs
"""
    p = tmp_path / "DECISIONS.md"
    p.write_text(content)
    return p


# --- Basic ingestion tests ---


class TestBasicIngestion:
    """Tests for core ingest_file behavior."""

    def test_ingest_writes_constraints_and_wisdom(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        result = ingestor.ingest_file(premortem_file)

        assert result.constraints_added == 3
        assert result.wisdom_added == 2
        assert constraint_store.count == 3
        assert len(wisdom_store.list()) == 2

    def test_constraint_fields(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(premortem_file)

        constraints = constraint_store.constraints
        assert len(constraints) == 3
        for c in constraints:
            assert c["source"] == "govern_ingest"
            assert c["type"] == "behavioral_constraint"
            assert c["status"] == "active"
            assert "source_excerpt" in c
            assert c["source_excerpt"] != ""
            assert isinstance(c["status_history"], list)
            assert len(c["status_history"]) == 1

    def test_wisdom_entities_are_dead_end_type(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(premortem_file)

        entities = wisdom_store.list()
        assert all(e.entity_type == "dead_end" for e in entities)
        assert all("governance" in e.context_tags for e in entities)
        assert all("pre-mortem" in e.context_tags for e in entities)


# --- Severity tests ---


class TestSeverityHeuristic:
    """Tests for forbidden-language severity detection."""

    def test_default_severity_requires_approval(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """## Key Assumptions

- All uploads must be gated on completion verification
"""
        p = tmp_path / "normal.md"
        p.write_text(content)
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(p)

        constraints = constraint_store.constraints
        assert len(constraints) == 1
        assert constraints[0]["severity"] == "requires_approval"

    def test_must_not_triggers_forbidden(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """## Key Assumptions

- Agents must not override authorization constraints silently
"""
        p = tmp_path / "forbidden.md"
        p.write_text(content)
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(p)

        assert constraint_store.constraints[0]["severity"] == "forbidden"

    def test_never_triggers_forbidden(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """## Key Assumptions

- Failed operations should never be accepted without retry
"""
        p = tmp_path / "never.md"
        p.write_text(content)
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(p)

        assert constraint_store.constraints[0]["severity"] == "forbidden"

    def test_do_not_triggers_forbidden(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """## Key Assumptions

- Do not proceed with uncertain state operations
"""
        p = tmp_path / "donot.md"
        p.write_text(content)
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(p)

        assert constraint_store.constraints[0]["severity"] == "forbidden"


# --- Dry-run tests ---


class TestDryRun:
    """Tests for dry_run mode."""

    def test_dry_run_returns_counts_without_writing(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        result = ingestor.ingest_file(premortem_file, dry_run=True)

        assert result.constraints_added == 3
        assert result.wisdom_added == 2
        # Stores remain empty
        assert constraint_store.count == 0
        assert len(wisdom_store.list()) == 0


# --- Idempotency tests ---


class TestIdempotency:
    """Tests for re-ingestion idempotency."""

    def test_second_ingestion_skips_constraints(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)

        result1 = ingestor.ingest_file(premortem_file)
        assert result1.constraints_added == 3
        assert result1.wisdom_added == 2

        result2 = ingestor.ingest_file(premortem_file)
        assert result2.constraints_added == 0
        assert result2.constraints_skipped == 3
        # Wisdom uses upsert, so second run updates
        assert result2.wisdom_updated == 2
        assert result2.wisdom_added == 0

        # Store counts unchanged
        assert constraint_store.count == 3
        assert len(wisdom_store.list()) == 2


# --- Co-occurrence linkage tests ---


class TestCoOccurrenceLinkage:
    """Tests for related_constraint_ids in wisdom metadata."""

    def test_dead_end_wisdom_has_related_constraint_ids(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(premortem_file)

        wisdom_entities = wisdom_store.list()
        for entity in wisdom_entities:
            assert entity.metadata is not None
            assert "related_constraint_ids" in entity.metadata
            # Should have all 3 constraint IDs
            assert len(entity.metadata["related_constraint_ids"]) == 3

    def test_constraint_ids_are_strings(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        premortem_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(premortem_file)

        wisdom_entities = wisdom_store.list()
        for entity in wisdom_entities:
            for cid in entity.metadata["related_constraint_ids"]:
                assert isinstance(cid, str)
                assert len(cid) == 16  # SHA-256 truncated


# --- DECISIONS.md tests ---


class TestDecisionsSections:
    """Tests for scope_decision/method_decision handling."""

    def test_decisions_produce_only_wisdom_not_constraints(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        decisions_file: Path,
    ) -> None:
        """DECISIONS.md scope/method sections produce wisdom, NOT constraints."""
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        result = ingestor.ingest_file(decisions_file)

        # No constraints from DECISIONS.md
        assert result.constraints_added == 0
        assert constraint_store.count == 0

        # Wisdom entities for scope and method decisions
        assert result.wisdom_added == 3
        entities = wisdom_store.list()
        types = {e.entity_type for e in entities}
        assert types == {"scope_decision", "method_decision"}

    def test_scope_decision_context_tags(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        decisions_file: Path,
    ) -> None:
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(decisions_file)

        entities = wisdom_store.list()
        for entity in entities:
            assert "governance" in entity.context_tags
            assert "decisions" in entity.context_tags

    def test_decisions_wisdom_has_no_related_constraints(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        decisions_file: Path,
    ) -> None:
        """DECISIONS.md has no assumptions, so no constraint IDs to link."""
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(decisions_file)

        entities = wisdom_store.list()
        for entity in entities:
            # metadata should be None or have empty related_constraint_ids
            if entity.metadata and "related_constraint_ids" in entity.metadata:
                assert entity.metadata["related_constraint_ids"] == []


# --- Error handling tests ---


class TestErrorHandling:
    """Tests for edge cases and error conditions."""

    def test_zero_entities_returns_warning(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """# Just a Title

Some text with no governance sections.
"""
        p = tmp_path / "empty.md"
        p.write_text(content)
        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        result = ingestor.ingest_file(p)

        assert result.total_entities == 0
        assert len(result.errors) == 1
        assert "No entities parsed" in result.errors[0]


# --- GovIngestResult model tests ---


class TestGovIngestResult:
    """Tests for the result model computed properties."""

    def test_total_entities(self) -> None:
        result = GovIngestResult(
            constraints_added=3,
            constraints_skipped=1,
            wisdom_added=2,
            wisdom_updated=1,
            wisdom_skipped=0,
        )
        assert result.total_entities == 7

    def test_is_bulk_true(self) -> None:
        result = GovIngestResult(
            constraints_added=3, wisdom_added=2, bulk_threshold=5
        )
        assert result.is_bulk is True

    def test_is_bulk_false(self) -> None:
        result = GovIngestResult(
            constraints_added=2, wisdom_added=1, bulk_threshold=5
        )
        assert result.is_bulk is False
