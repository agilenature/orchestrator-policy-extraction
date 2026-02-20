"""Tests for WisdomIngestor.

Covers:
- ingest_list adds new entries correctly
- ingest_list updates existing entries on re-run
- ingest_list skips entries with invalid entity_type
- ingest_list skips entries with missing title or description
- ingest_file loads from JSON file (array format)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.wisdom.ingestor import IngestResult, WisdomIngestor
from src.pipeline.wisdom.models import WisdomEntity, _make_wisdom_id
from src.pipeline.wisdom.store import WisdomStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path for isolated tests."""
    return tmp_path / "test_ingestor.db"


@pytest.fixture
def store(db_path: Path) -> WisdomStore:
    """Provide a WisdomStore with empty database."""
    return WisdomStore(db_path)


@pytest.fixture
def ingestor(store: WisdomStore) -> WisdomIngestor:
    """Provide a WisdomIngestor backed by an empty store."""
    return WisdomIngestor(store)


@pytest.fixture
def sample_entries() -> list[dict]:
    """Return a list of valid wisdom entry dicts for testing."""
    return [
        {
            "entity_type": "breakthrough",
            "title": "Observation-context separation",
            "description": "Context events come from preceding episode",
            "context_tags": ["episode", "observation"],
            "scope_paths": ["src/pipeline/population/"],
            "confidence": 0.95,
            "source_document": "REUSABLE_KNOWLEDGE_GUIDE.md",
            "source_phase": 7,
        },
        {
            "entity_type": "dead_end",
            "title": "pybreaker for circuit breaker",
            "description": "pybreaker tracks consecutive failures, not percentage-based rate",
            "context_tags": ["circuit-breaker", "api"],
            "confidence": 0.8,
        },
        {
            "entity_type": "scope_decision",
            "title": "Count-query verification for completion",
            "description": "Completion criteria must be a database count query",
            "source_document": "VALIDATION_GATE_AUDIT.md",
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ingest_list_adds_new_entries(
    ingestor: WisdomIngestor,
    store: WisdomStore,
    sample_entries: list[dict],
) -> None:
    """Ingesting new entries should add them all with correct counts."""
    result = ingestor.ingest_list(sample_entries)

    assert result.added == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == []

    # Verify entities exist in the store
    all_entities = store.list()
    assert len(all_entities) == 3

    # Verify fields are correctly mapped
    wid = _make_wisdom_id("breakthrough", "Observation-context separation")
    entity = store.get(wid)
    assert entity is not None
    assert entity.entity_type == "breakthrough"
    assert entity.title == "Observation-context separation"
    assert entity.confidence == 0.95
    assert "episode" in entity.context_tags
    assert entity.source_document == "REUSABLE_KNOWLEDGE_GUIDE.md"
    assert entity.source_phase == 7

    # Verify defaults for optional fields
    dead_end_id = _make_wisdom_id("dead_end", "pybreaker for circuit breaker")
    dead_end = store.get(dead_end_id)
    assert dead_end is not None
    assert dead_end.scope_paths == []
    assert dead_end.source_document is None
    assert dead_end.source_phase is None


def test_ingest_list_updates_existing_entries(
    ingestor: WisdomIngestor,
    store: WisdomStore,
    sample_entries: list[dict],
) -> None:
    """Re-ingesting the same entries should update, not duplicate."""
    # First ingest
    result1 = ingestor.ingest_list(sample_entries)
    assert result1.added == 3
    assert result1.updated == 0

    # Modify one entry's description and re-ingest all
    modified_entries = [dict(e) for e in sample_entries]
    modified_entries[0]["description"] = "Updated description for testing"

    result2 = ingestor.ingest_list(modified_entries)
    assert result2.added == 0
    assert result2.updated == 3
    assert result2.skipped == 0

    # Verify the update took effect
    wid = _make_wisdom_id("breakthrough", "Observation-context separation")
    entity = store.get(wid)
    assert entity is not None
    assert entity.description == "Updated description for testing"

    # Verify total count is still 3 (no duplicates)
    assert len(store.list()) == 3


def test_ingest_list_skips_invalid_entity_type(
    ingestor: WisdomIngestor,
) -> None:
    """Entries with invalid entity_type should be skipped with error."""
    entries = [
        {
            "entity_type": "invalid_type",
            "title": "Some title",
            "description": "Some description",
        },
        {
            "entity_type": "",
            "title": "Empty type",
            "description": "Description",
        },
        {
            "entity_type": "breakthrough",
            "title": "Valid entry",
            "description": "This one should succeed",
        },
    ]

    result = ingestor.ingest_list(entries)

    assert result.added == 1
    assert result.skipped == 2
    assert len(result.errors) == 2
    assert "Invalid entity_type: 'invalid_type'" in result.errors[0]
    assert "Invalid entity_type: ''" in result.errors[1]


def test_ingest_list_skips_missing_title(
    ingestor: WisdomIngestor,
) -> None:
    """Entries missing title or description should be skipped."""
    entries = [
        {
            "entity_type": "breakthrough",
            "title": "",
            "description": "Has description but no title",
        },
        {
            "entity_type": "dead_end",
            "title": "Has title but no description",
            "description": "",
        },
        {
            "entity_type": "scope_decision",
            "title": "  ",
            "description": "Whitespace-only title",
        },
        {
            "entity_type": "method_decision",
            "title": "Valid title",
            "description": "Valid description",
        },
    ]

    result = ingestor.ingest_list(entries)

    assert result.added == 1
    assert result.skipped == 3
    assert all("Missing title or description" in e for e in result.errors)


def test_ingest_file_loads_json(
    ingestor: WisdomIngestor,
    store: WisdomStore,
    tmp_path: Path,
    sample_entries: list[dict],
) -> None:
    """ingest_file should load entries from a JSON file."""
    # Write sample entries as JSON array
    json_path = tmp_path / "test_wisdom.json"
    json_path.write_text(json.dumps(sample_entries))

    result = ingestor.ingest_file(json_path)

    assert result.added == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert len(store.list()) == 3

    # Also test the {entries: [...]} format
    store2_path = tmp_path / "test_ingestor2.db"
    store2 = WisdomStore(store2_path)
    ingestor2 = WisdomIngestor(store2)

    json_path2 = tmp_path / "test_wisdom2.json"
    json_path2.write_text(json.dumps({"entries": sample_entries}))

    result2 = ingestor2.ingest_file(json_path2)
    assert result2.added == 3
    assert len(store2.list()) == 3
