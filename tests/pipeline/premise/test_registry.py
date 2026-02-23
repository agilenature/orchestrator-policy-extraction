"""Tests for PremiseRegistry DuckDB CRUD operations.

Tests:
- Register + get roundtrip (all fields preserved including JSON)
- get_by_session returns correct premises in order
- get_stained returns only stained premises
- stain() updates staining_record correctly
- update_staleness increments counter
- find_by_foil returns matching premises and respects exclusions
- backfill_parent_episodes on test data
- count() returns correct total
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.schema import create_premise_schema
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """Create an in-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


@pytest.fixture
def registry(conn):
    """Create a PremiseRegistry with a prepared connection."""
    return PremiseRegistry(conn)


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


class TestRegisterAndGet:
    """Tests for register + get roundtrip."""

    def test_register_and_get_minimal(self, registry):
        """Register a minimal record and retrieve it."""
        record = _make_record()
        registry.register(record)
        result = registry.get("abc123def456abcd")
        assert result is not None
        assert result.premise_id == "abc123def456abcd"
        assert result.claim == "Test claim"
        assert result.session_id == "sess-1"

    def test_register_and_get_full(self, registry):
        """Register a full record with all fields and retrieve it."""
        record = _make_record(
            validated_by="Read output confirmed",
            validation_context="File exists at path",
            foil="wrong path",
            distinguishing_prop="correct directory",
            staleness_counter=2,
            staining_record={"stained": False},
            ground_truth_pointer={"session_id": "s1", "episode_id": "e1"},
            project_scope="/path/to/project",
            tool_use_id="toolu_01abc",
            foil_path_outcomes=[{"episode_id": "e2"}],
            divergence_patterns=[{"tool_call_claim": "Edit"}],
            parent_episode_links=[{"episode_id": "e0"}],
            derivation_depth=3,
            validation_calls_before_claim=5,
            derivation_chain=[{"derives_from": "xyz123"}],
            created_at="2026-02-23T12:00:00Z",
            updated_at="2026-02-23T12:00:00Z",
        )
        registry.register(record)
        result = registry.get("abc123def456abcd")
        assert result is not None
        assert result.validated_by == "Read output confirmed"
        assert result.foil == "wrong path"
        assert result.staleness_counter == 2
        assert result.staining_record == {"stained": False}
        assert result.ground_truth_pointer == {"session_id": "s1", "episode_id": "e1"}
        assert result.derivation_depth == 3
        assert result.validation_calls_before_claim == 5
        assert result.derivation_chain == [{"derives_from": "xyz123"}]

    def test_get_nonexistent(self, registry):
        """get() for nonexistent premise_id should return None."""
        result = registry.get("nonexistent_id")
        assert result is None

    def test_register_upsert(self, registry):
        """register() should update existing record on same premise_id."""
        record1 = _make_record(claim="Original claim")
        registry.register(record1)

        record2 = _make_record(claim="Updated claim")
        registry.register(record2)

        result = registry.get("abc123def456abcd")
        assert result.claim == "Updated claim"
        assert registry.count() == 1


class TestGetBySession:
    """Tests for get_by_session."""

    def test_returns_premises_for_session(self, registry):
        """get_by_session should return all premises for the given session."""
        registry.register(_make_record(
            premise_id="p1", claim="Claim 1", session_id="sess-A",
            created_at="2026-02-23T10:00:00Z",
        ))
        registry.register(_make_record(
            premise_id="p2", claim="Claim 2", session_id="sess-A",
            created_at="2026-02-23T10:05:00Z",
        ))
        registry.register(_make_record(
            premise_id="p3", claim="Claim 3", session_id="sess-B",
        ))

        results = registry.get_by_session("sess-A")
        assert len(results) == 2
        assert results[0].premise_id == "p1"
        assert results[1].premise_id == "p2"

    def test_returns_empty_for_unknown_session(self, registry):
        """get_by_session should return empty list for unknown session."""
        results = registry.get_by_session("nonexistent")
        assert results == []


class TestGetStained:
    """Tests for get_stained."""

    def test_returns_only_stained(self, registry):
        """get_stained should return only premises with stained=true."""
        registry.register(_make_record(
            premise_id="p1",
            staining_record={"stained": True, "stained_by": "amnesia-1"},
        ))
        registry.register(_make_record(
            premise_id="p2",
            staining_record={"stained": False},
        ))
        registry.register(_make_record(
            premise_id="p3",
            # No staining_record at all
        ))

        results = registry.get_stained()
        assert len(results) == 1
        assert results[0].premise_id == "p1"

    def test_filter_by_project_scope(self, registry):
        """get_stained should filter by project_scope when provided."""
        registry.register(_make_record(
            premise_id="p1",
            staining_record={"stained": True},
            project_scope="/project-A",
        ))
        registry.register(_make_record(
            premise_id="p2",
            staining_record={"stained": True},
            project_scope="/project-B",
        ))

        results = registry.get_stained(project_scope="/project-A")
        assert len(results) == 1
        assert results[0].premise_id == "p1"


class TestStain:
    """Tests for stain()."""

    def test_stain_updates_record(self, registry):
        """stain() should set staining_record with correct fields."""
        registry.register(_make_record(premise_id="p1"))
        registry.stain("p1", "amnesia-42", {"session_id": "s1"})

        result = registry.get("p1")
        assert result.staining_record is not None
        assert result.staining_record["stained"] is True
        assert result.staining_record["stained_by"] == "amnesia-42"
        assert "stained_at" in result.staining_record
        assert result.staining_record["ground_truth_pointer"] == {"session_id": "s1"}


class TestUpdateStaleness:
    """Tests for update_staleness."""

    def test_increments_counter(self, registry):
        """update_staleness should increment staleness_counter by 1."""
        registry.register(_make_record(premise_id="p1", staleness_counter=0))
        registry.update_staleness("p1")

        result = registry.get("p1")
        assert result.staleness_counter == 1

    def test_multiple_increments(self, registry):
        """Multiple calls should increment cumulatively."""
        registry.register(_make_record(premise_id="p1", staleness_counter=0))
        registry.update_staleness("p1")
        registry.update_staleness("p1")
        registry.update_staleness("p1")

        result = registry.get("p1")
        assert result.staleness_counter == 3


class TestFindByFoil:
    """Tests for find_by_foil."""

    def test_matches_claim_text(self, registry):
        """find_by_foil should find premises whose claim contains the foil text."""
        registry.register(_make_record(
            premise_id="p1", claim="The file exists at /src/main.py",
        ))
        registry.register(_make_record(
            premise_id="p2", claim="The API uses JSON format",
        ))

        results = registry.find_by_foil("file exists")
        assert len(results) == 1
        assert results[0].premise_id == "p1"

    def test_case_insensitive(self, registry):
        """find_by_foil should be case-insensitive (ILIKE)."""
        registry.register(_make_record(
            premise_id="p1", claim="FILE EXISTS at path",
        ))

        results = registry.find_by_foil("file exists")
        assert len(results) == 1

    def test_respects_project_scope(self, registry):
        """find_by_foil should filter by project_scope when provided."""
        registry.register(_make_record(
            premise_id="p1", claim="file exists A",
            project_scope="/project-A",
        ))
        registry.register(_make_record(
            premise_id="p2", claim="file exists B",
            project_scope="/project-B",
        ))

        results = registry.find_by_foil("file exists", project_scope="/project-A")
        assert len(results) == 1
        assert results[0].premise_id == "p1"

    def test_excludes_session(self, registry):
        """find_by_foil should exclude specified session."""
        registry.register(_make_record(
            premise_id="p1", claim="file exists", session_id="sess-current",
        ))
        registry.register(_make_record(
            premise_id="p2", claim="file exists", session_id="sess-other",
        ))

        results = registry.find_by_foil("file exists", exclude_session="sess-current")
        assert len(results) == 1
        assert results[0].premise_id == "p2"

    def test_respects_limit(self, registry):
        """find_by_foil should respect the limit parameter."""
        for i in range(5):
            registry.register(_make_record(
                premise_id=f"p{i}", claim=f"file exists {i}",
                session_id=f"sess-{i}",
            ))

        results = registry.find_by_foil("file exists", limit=3)
        assert len(results) == 3

    def test_no_matches(self, registry):
        """find_by_foil should return empty list when no matches."""
        registry.register(_make_record(
            premise_id="p1", claim="completely unrelated",
        ))

        results = registry.find_by_foil("nonexistent text")
        assert results == []


class TestCount:
    """Tests for count()."""

    def test_empty_registry(self, registry):
        """count() on empty registry should return 0."""
        assert registry.count() == 0

    def test_after_registers(self, registry):
        """count() should return total number of premises."""
        registry.register(_make_record(premise_id="p1"))
        registry.register(_make_record(premise_id="p2"))
        registry.register(_make_record(premise_id="p3"))
        assert registry.count() == 3


class TestBackfillParentEpisodes:
    """Tests for backfill_parent_episodes."""

    def test_backfill_three_episodes_two_sessions(self, conn, registry):
        """Backfill should assign correct parent links across 2 sessions."""
        # Insert test episodes
        episodes = [
            ("ep-1a", "sess-A", "seg-1a", "2026-02-23T10:00:00Z"),
            ("ep-2a", "sess-A", "seg-2a", "2026-02-23T10:05:00Z"),
            ("ep-1b", "sess-B", "seg-1b", "2026-02-23T10:02:00Z"),
        ]
        for eid, sid, seg_id, ts in episodes:
            conn.execute(
                "INSERT INTO episodes (episode_id, session_id, segment_id, timestamp) "
                "VALUES (?, ?, ?, CAST(? AS TIMESTAMPTZ))",
                [eid, sid, seg_id, ts],
            )

        affected = registry.backfill_parent_episodes()
        assert affected == 1  # Only ep-2a should have a parent

        results = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT episode_id, parent_episode_id FROM episodes"
            ).fetchall()
        }
        assert results["ep-1a"] is None
        assert results["ep-2a"] == "ep-1a"
        assert results["ep-1b"] is None
