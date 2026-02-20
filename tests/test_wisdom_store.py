"""Tests for wisdom models and WisdomStore.

Covers:
- _make_wisdom_id determinism and format
- WisdomEntity.create() factory
- WisdomEntity frozen behavior
- WisdomRef construction
- EnrichedRecommendation construction
- WisdomStore CRUD: add, get, update, delete
- WisdomStore list: all and filtered
- WisdomStore search: by tags and by scope
- WisdomStore upsert: insert new and replace existing
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.wisdom.models import (
    EnrichedRecommendation,
    WisdomEntity,
    WisdomRef,
    _make_wisdom_id,
)
from src.pipeline.wisdom.store import WisdomStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path for isolated tests."""
    return tmp_path / "test_wisdom.db"


@pytest.fixture
def store(db_path: Path) -> WisdomStore:
    """Provide a WisdomStore with empty database."""
    return WisdomStore(db_path)


@pytest.fixture
def sample_entity() -> WisdomEntity:
    """A breakthrough entity for reuse across tests."""
    return WisdomEntity.create(
        "breakthrough",
        "DuckDB array columns",
        "VARCHAR[] columns accept Python lists directly",
        context_tags=["duckdb", "schema", "arrays"],
        scope_paths=["src/pipeline/storage/"],
        confidence=0.95,
        source_document="REUSABLE_KNOWLEDGE_GUIDE.md",
        source_phase=7,
    )


@pytest.fixture
def populated_store(store: WisdomStore) -> WisdomStore:
    """Store pre-populated with 4 entities (one of each type)."""
    entities = [
        WisdomEntity.create(
            "breakthrough",
            "Frozen Pydantic models",
            "Use model_copy(update={}) for modifications",
            context_tags=["pydantic", "patterns"],
            scope_paths=["src/pipeline/models/"],
        ),
        WisdomEntity.create(
            "dead_end",
            "jsonwebtoken in Edge runtime",
            "CJS import fails in Edge; use jose instead",
            context_tags=["auth", "edge", "cjs"],
            scope_paths=["src/auth/"],
        ),
        WisdomEntity.create(
            "scope_decision",
            "No pyarrow dependency",
            "Use DuckDB native COPY TO for Parquet export",
            context_tags=["duckdb", "export"],
            scope_paths=[],  # Repo-wide
        ),
        WisdomEntity.create(
            "method_decision",
            "Staging table upsert pattern",
            "CREATE TEMP TABLE -> UPDATE -> INSERT -> DROP for DuckDB upserts",
            context_tags=["duckdb", "patterns"],
            scope_paths=["src/pipeline/storage/"],
        ),
    ]
    for e in entities:
        store.add(e)
    return store


# ---------------------------------------------------------------------------
# Model tests: _make_wisdom_id
# ---------------------------------------------------------------------------


class TestMakeWisdomId:
    """Tests for the _make_wisdom_id helper function."""

    def test_deterministic(self) -> None:
        """Same inputs always produce the same ID."""
        id1 = _make_wisdom_id("breakthrough", "Test title")
        id2 = _make_wisdom_id("breakthrough", "Test title")
        assert id1 == id2

    def test_format(self) -> None:
        """ID has w- prefix and 16 hex characters."""
        wid = _make_wisdom_id("dead_end", "Some title")
        assert wid.startswith("w-")
        hex_part = wid[2:]
        assert len(hex_part) == 16
        # Verify all chars are valid hex
        int(hex_part, 16)

    def test_different_type_different_id(self) -> None:
        """Different entity types produce different IDs for same title."""
        id1 = _make_wisdom_id("breakthrough", "Same title")
        id2 = _make_wisdom_id("dead_end", "Same title")
        assert id1 != id2

    def test_different_title_different_id(self) -> None:
        """Different titles produce different IDs for same type."""
        id1 = _make_wisdom_id("breakthrough", "Title A")
        id2 = _make_wisdom_id("breakthrough", "Title B")
        assert id1 != id2


# ---------------------------------------------------------------------------
# Model tests: WisdomEntity
# ---------------------------------------------------------------------------


class TestWisdomEntity:
    """Tests for WisdomEntity creation and behavior."""

    def test_create_factory(self) -> None:
        """create() generates wisdom_id automatically."""
        entity = WisdomEntity.create(
            "breakthrough", "Test", "Description"
        )
        expected_id = _make_wisdom_id("breakthrough", "Test")
        assert entity.wisdom_id == expected_id
        assert entity.entity_type == "breakthrough"
        assert entity.title == "Test"
        assert entity.description == "Description"

    def test_create_with_kwargs(self) -> None:
        """create() passes through additional keyword arguments."""
        entity = WisdomEntity.create(
            "dead_end",
            "Bad approach",
            "Details",
            context_tags=["tag1"],
            scope_paths=["src/"],
            confidence=0.5,
            source_document="doc.md",
            source_phase=3,
        )
        assert entity.context_tags == ["tag1"]
        assert entity.scope_paths == ["src/"]
        assert entity.confidence == 0.5
        assert entity.source_document == "doc.md"
        assert entity.source_phase == 3

    def test_frozen(self) -> None:
        """WisdomEntity is immutable (frozen=True)."""
        entity = WisdomEntity.create("breakthrough", "T", "D")
        with pytest.raises(Exception):
            entity.title = "New"  # type: ignore[misc]

    def test_defaults(self) -> None:
        """Default values for optional fields."""
        entity = WisdomEntity.create("breakthrough", "T", "D")
        assert entity.context_tags == []
        assert entity.scope_paths == []
        assert entity.confidence == 1.0
        assert entity.source_document is None
        assert entity.source_phase is None
        assert entity.embedding is None


# ---------------------------------------------------------------------------
# Model tests: WisdomRef and EnrichedRecommendation
# ---------------------------------------------------------------------------


class TestWisdomRef:
    """Tests for WisdomRef model."""

    def test_construction(self) -> None:
        """WisdomRef constructs with all required fields."""
        ref = WisdomRef(
            wisdom_id="w-abc123",
            entity_type="dead_end",
            title="Bad approach",
            relevance_score=0.85,
            is_dead_end_warning=True,
            description="Do not use this",
        )
        assert ref.wisdom_id == "w-abc123"
        assert ref.is_dead_end_warning is True
        assert ref.relevance_score == 0.85


class TestEnrichedRecommendation:
    """Tests for EnrichedRecommendation model."""

    def test_construction(self) -> None:
        """EnrichedRecommendation wraps a recommendation with wisdom refs."""
        ref = WisdomRef(
            wisdom_id="w-123",
            entity_type="breakthrough",
            title="Discovery",
            relevance_score=0.9,
        )
        enriched = EnrichedRecommendation(
            recommendation={"mode": "Implement"},
            wisdom_refs=[ref],
            has_dead_end_warning=False,
        )
        assert len(enriched.wisdom_refs) == 1
        assert enriched.has_dead_end_warning is False


# ---------------------------------------------------------------------------
# Store tests: add and get
# ---------------------------------------------------------------------------


class TestWisdomStoreAdd:
    """Tests for WisdomStore.add()."""

    def test_add_and_get(self, store: WisdomStore, sample_entity: WisdomEntity) -> None:
        """add() inserts and get() retrieves the entity."""
        wid = store.add(sample_entity)
        assert wid == sample_entity.wisdom_id

        got = store.get(wid)
        assert got is not None
        assert got.wisdom_id == sample_entity.wisdom_id
        assert got.title == sample_entity.title
        assert got.description == sample_entity.description
        assert got.entity_type == sample_entity.entity_type
        assert got.context_tags == sample_entity.context_tags
        assert got.scope_paths == sample_entity.scope_paths
        assert got.confidence == sample_entity.confidence
        assert got.source_document == sample_entity.source_document
        assert got.source_phase == sample_entity.source_phase

    def test_add_duplicate_raises(self, store: WisdomStore, sample_entity: WisdomEntity) -> None:
        """add() raises ValueError on duplicate wisdom_id."""
        store.add(sample_entity)
        with pytest.raises(ValueError, match="already exists"):
            store.add(sample_entity)


class TestWisdomStoreGet:
    """Tests for WisdomStore.get()."""

    def test_get_not_found(self, store: WisdomStore) -> None:
        """get() returns None for nonexistent wisdom_id."""
        result = store.get("w-nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Store tests: update
# ---------------------------------------------------------------------------


class TestWisdomStoreUpdate:
    """Tests for WisdomStore.update()."""

    def test_update_happy_path(self, store: WisdomStore, sample_entity: WisdomEntity) -> None:
        """update() replaces fields for existing entity."""
        store.add(sample_entity)

        updated = sample_entity.model_copy(
            update={
                "description": "Updated description",
                "confidence": 0.5,
                "context_tags": ["new-tag"],
            }
        )
        store.update(updated)

        got = store.get(sample_entity.wisdom_id)
        assert got is not None
        assert got.description == "Updated description"
        assert got.confidence == 0.5
        assert got.context_tags == ["new-tag"]

    def test_update_not_found_raises(self, store: WisdomStore) -> None:
        """update() raises ValueError for nonexistent entity."""
        entity = WisdomEntity.create("breakthrough", "Nonexistent", "Desc")
        with pytest.raises(ValueError, match="not found"):
            store.update(entity)


# ---------------------------------------------------------------------------
# Store tests: delete
# ---------------------------------------------------------------------------


class TestWisdomStoreDelete:
    """Tests for WisdomStore.delete()."""

    def test_delete_existing(self, store: WisdomStore, sample_entity: WisdomEntity) -> None:
        """delete() removes an existing entity."""
        store.add(sample_entity)
        store.delete(sample_entity.wisdom_id)
        assert store.get(sample_entity.wisdom_id) is None

    def test_delete_idempotent(self, store: WisdomStore) -> None:
        """delete() does not raise for nonexistent entity."""
        store.delete("w-nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Store tests: list
# ---------------------------------------------------------------------------


class TestWisdomStoreList:
    """Tests for WisdomStore.list()."""

    def test_list_all(self, populated_store: WisdomStore) -> None:
        """list() returns all entities when no filter."""
        results = populated_store.list()
        assert len(results) == 4

    def test_list_by_entity_type(self, populated_store: WisdomStore) -> None:
        """list(entity_type=...) filters correctly."""
        breakthroughs = populated_store.list(entity_type="breakthrough")
        assert len(breakthroughs) == 1
        assert breakthroughs[0].entity_type == "breakthrough"

        dead_ends = populated_store.list(entity_type="dead_end")
        assert len(dead_ends) == 1
        assert dead_ends[0].entity_type == "dead_end"

    def test_list_empty_type(self, store: WisdomStore) -> None:
        """list() returns empty list when no entities exist."""
        results = store.list()
        assert results == []


# ---------------------------------------------------------------------------
# Store tests: search_by_tags
# ---------------------------------------------------------------------------


class TestWisdomStoreSearchByTags:
    """Tests for WisdomStore.search_by_tags()."""

    def test_search_match(self, populated_store: WisdomStore) -> None:
        """search_by_tags finds entities matching any given tag."""
        results = populated_store.search_by_tags(["pydantic"])
        assert len(results) == 1
        assert results[0].title == "Frozen Pydantic models"

    def test_search_multiple_tags(self, populated_store: WisdomStore) -> None:
        """search_by_tags with OR semantics matches any tag."""
        results = populated_store.search_by_tags(["auth", "duckdb"])
        # Should match: dead_end (auth), scope_decision (duckdb), method_decision (duckdb)
        assert len(results) == 3

    def test_search_no_match(self, populated_store: WisdomStore) -> None:
        """search_by_tags returns empty list when no tags match."""
        results = populated_store.search_by_tags(["nonexistent"])
        assert results == []

    def test_search_empty_tags(self, populated_store: WisdomStore) -> None:
        """search_by_tags with empty list returns nothing."""
        results = populated_store.search_by_tags([])
        assert results == []


# ---------------------------------------------------------------------------
# Store tests: search_by_scope
# ---------------------------------------------------------------------------


class TestWisdomStoreSearchByScope:
    """Tests for WisdomStore.search_by_scope()."""

    def test_search_match(self, populated_store: WisdomStore) -> None:
        """search_by_scope finds entities with matching scope_path."""
        results = populated_store.search_by_scope("src/pipeline/models/")
        # Should match: breakthrough (exact path) + scope_decision (empty = repo-wide)
        assert len(results) == 2
        types = {r.entity_type for r in results}
        assert "breakthrough" in types
        assert "scope_decision" in types

    def test_search_repo_wide_always_included(self, populated_store: WisdomStore) -> None:
        """Entities with empty scope_paths are always returned."""
        results = populated_store.search_by_scope("any/random/path/")
        # Only scope_decision has empty scope_paths
        assert len(results) == 1
        assert results[0].entity_type == "scope_decision"

    def test_search_no_match_except_repo_wide(self, populated_store: WisdomStore) -> None:
        """Non-matching scope still returns repo-wide entities."""
        results = populated_store.search_by_scope("totally/different/")
        repo_wide = [r for r in results if r.scope_paths == []]
        assert len(repo_wide) == 1


# ---------------------------------------------------------------------------
# Store tests: upsert
# ---------------------------------------------------------------------------


class TestWisdomStoreUpsert:
    """Tests for WisdomStore.upsert()."""

    def test_upsert_insert_new(self, store: WisdomStore) -> None:
        """upsert() inserts when entity does not exist."""
        entity = WisdomEntity.create("breakthrough", "New entry", "Description")
        wid = store.upsert(entity)
        got = store.get(wid)
        assert got is not None
        assert got.title == "New entry"

    def test_upsert_replace_existing(self, store: WisdomStore) -> None:
        """upsert() replaces when entity already exists."""
        entity = WisdomEntity.create("breakthrough", "Entry", "Original")
        store.add(entity)

        updated = entity.model_copy(update={"description": "Replaced"})
        store.upsert(updated)

        got = store.get(entity.wisdom_id)
        assert got is not None
        assert got.description == "Replaced"
