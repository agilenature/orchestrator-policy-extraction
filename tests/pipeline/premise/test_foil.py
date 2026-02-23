"""Tests for FoilInstantiator: three-tier matching + divergence detection.

Tests:
- instantiate() exact match via find_by_foil
- instantiate() keyword overlap fallback
- project_scope filtering
- current_session_id exclusion
- detect_divergence() with episode events
- detect_divergence() returns None when no episode data
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.premise.foil import DivergenceNode, FoilInstantiator, FoilMatch
from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.schema import create_premise_schema
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
def foil(registry, conn):
    """Create a FoilInstantiator with registry and connection."""
    return FoilInstantiator(registry, conn)


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


def _seed_premises(registry: PremiseRegistry) -> None:
    """Seed 8 premises across 3 sessions for testing."""
    premises = [
        _make_record(
            premise_id="p1", claim="The file exists at /src/main.py",
            session_id="sess-A", project_scope="/project-X",
            ground_truth_pointer={"episode_id": "ep-1", "session_id": "sess-A"},
        ),
        _make_record(
            premise_id="p2", claim="The API uses JSON format for responses",
            session_id="sess-A", project_scope="/project-X",
        ),
        _make_record(
            premise_id="p3", claim="The database schema has a users table",
            session_id="sess-B", project_scope="/project-X",
        ),
        _make_record(
            premise_id="p4", claim="Authentication uses JWT tokens with refresh rotation",
            session_id="sess-B", project_scope="/project-Y",
        ),
        _make_record(
            premise_id="p5", claim="The file exists at /src/utils.py with helper functions",
            session_id="sess-C", project_scope="/project-X",
        ),
        _make_record(
            premise_id="p6", claim="The configuration uses YAML format for settings",
            session_id="sess-C", project_scope="/project-X",
        ),
        _make_record(
            premise_id="p7", claim="The test suite covers authentication and authorization logic",
            session_id="sess-C", project_scope="/project-Y",
        ),
        _make_record(
            premise_id="p8", claim="The main module handles file parsing and validation",
            session_id="sess-A", project_scope="/project-X",
            ground_truth_pointer={"episode_id": "ep-2", "session_id": "sess-A"},
        ),
    ]
    for p in premises:
        registry.register(p)


class TestInstantiateExactMatch:
    """Tests for instantiate() exact match tier."""

    def test_exact_match_returns_results(self, foil, registry):
        """instantiate() should find exact claim matches via find_by_foil."""
        _seed_premises(registry)
        matches = foil.instantiate("file exists")
        assert len(matches) >= 1
        assert all(m.match_tier == "exact" for m in matches)
        claim_texts = [m.premise.claim for m in matches]
        assert any("file exists" in c.lower() for c in claim_texts)

    def test_exact_match_case_insensitive(self, foil, registry):
        """instantiate() should be case-insensitive for exact matches."""
        _seed_premises(registry)
        matches = foil.instantiate("FILE EXISTS")
        assert len(matches) >= 1

    def test_no_matches(self, foil, registry):
        """instantiate() should return empty list for unmatched foil."""
        _seed_premises(registry)
        matches = foil.instantiate("completely unrelated gibberish xyz")
        assert matches == []


class TestInstantiateKeywordOverlap:
    """Tests for instantiate() keyword overlap tier."""

    def test_keyword_fallback_when_few_exact(self, foil, registry):
        """Keyword tier activates when exact match returns <3 results."""
        _seed_premises(registry)
        # This foil has partial keyword overlap with multiple premises
        matches = foil.instantiate(
            "authentication tokens with refresh rotation and validation"
        )
        # Should find at least the exact or keyword matches
        assert len(matches) >= 1

    def test_keyword_overlap_count(self, foil, registry):
        """Keyword matches should report keyword_overlap count."""
        _seed_premises(registry)
        matches = foil.instantiate(
            "authentication tokens with refresh rotation and validation"
        )
        keyword_matches = [m for m in matches if m.match_tier == "keyword"]
        for m in keyword_matches:
            assert m.keyword_overlap >= 3


class TestProjectScopeFiltering:
    """Tests for project_scope filtering in instantiate()."""

    def test_scope_filters_results(self, foil, registry):
        """instantiate() with project_scope should only return matching scope."""
        _seed_premises(registry)
        matches = foil.instantiate("file exists", project_scope="/project-X")
        for m in matches:
            assert m.premise.project_scope == "/project-X"

    def test_scope_excludes_other_projects(self, foil, registry):
        """instantiate() should not return results from other projects."""
        _seed_premises(registry)
        matches = foil.instantiate(
            "authentication",
            project_scope="/project-X",
        )
        for m in matches:
            assert m.premise.project_scope == "/project-X"


class TestSessionExclusion:
    """Tests for current_session_id exclusion."""

    def test_excludes_current_session(self, foil, registry):
        """instantiate() should exclude the specified session."""
        _seed_premises(registry)
        matches = foil.instantiate(
            "file exists",
            current_session_id="sess-A",
        )
        for m in matches:
            assert m.premise.session_id != "sess-A"

    def test_includes_other_sessions(self, foil, registry):
        """instantiate() should include results from other sessions."""
        _seed_premises(registry)
        matches = foil.instantiate(
            "file exists",
            current_session_id="sess-B",
        )
        assert len(matches) >= 1
        session_ids = {m.premise.session_id for m in matches}
        assert "sess-B" not in session_ids


class TestDetectDivergence:
    """Tests for detect_divergence()."""

    def test_detects_divergence_with_events(self, foil, registry, conn):
        """detect_divergence() should identify first tool call divergence."""
        _seed_premises(registry)

        # Create episode and events for divergence detection
        conn.execute(
            "INSERT INTO episodes (episode_id, session_id, segment_id, timestamp) "
            "VALUES (?, ?, ?, CAST(? AS TIMESTAMPTZ))",
            ["ep-1", "sess-A", "seg-1", "2026-02-23T10:00:00Z"],
        )

        # Insert events with different tool types
        events = [
            ("ev-1", "2026-02-23T10:00:01Z", "sess-A", "ai_assistant",
             "tool_use", "Read", json.dumps({"tool_name": "Read"})),
            ("ev-2", "2026-02-23T10:00:02Z", "sess-A", "ai_assistant",
             "tool_use", "Read", json.dumps({"tool_name": "Read"})),
            ("ev-3", "2026-02-23T10:00:03Z", "sess-A", "ai_assistant",
             "tool_use", "Edit", json.dumps({"tool_name": "Edit"})),
        ]
        for eid, ts, sid, actor, etype, tag, payload in events:
            conn.execute(
                "INSERT INTO events (event_id, ts_utc, session_id, actor, "
                "event_type, primary_tag, payload, source_system, source_ref) "
                "VALUES (?, CAST(? AS TIMESTAMPTZ), ?, ?, ?, ?, ?, 'test', 'test')",
                [eid, ts, sid, actor, etype, tag, payload],
            )

        match = FoilMatch(
            premise=registry.get("p1"),
            match_tier="exact",
        )

        divergence = foil.detect_divergence(match)
        assert divergence is not None
        assert isinstance(divergence, DivergenceNode)
        assert divergence.episode_id == "ep-1"
        assert divergence.event_index >= 1

    def test_returns_none_without_episode(self, foil, registry):
        """detect_divergence() should return None when no episode data."""
        # Premise with no ground_truth_pointer
        record = _make_record(
            premise_id="p_no_gtp",
            claim="No ground truth",
            session_id="sess-X",
        )
        registry.register(record)

        match = FoilMatch(
            premise=record,
            match_tier="exact",
        )

        divergence = foil.detect_divergence(match)
        assert divergence is None

    def test_returns_none_without_events(self, foil, registry, conn):
        """detect_divergence() should return None when episode has no events."""
        record = _make_record(
            premise_id="p_no_events",
            claim="Has episode but no events",
            session_id="sess-Y",
            ground_truth_pointer={"episode_id": "ep-empty", "session_id": "sess-Y"},
        )
        registry.register(record)

        # Create episode without events
        conn.execute(
            "INSERT INTO episodes (episode_id, session_id, segment_id, timestamp) "
            "VALUES (?, ?, ?, CAST(? AS TIMESTAMPTZ))",
            ["ep-empty", "sess-Y", "seg-empty", "2026-02-23T11:00:00Z"],
        )

        match = FoilMatch(
            premise=record,
            match_tier="exact",
        )

        divergence = foil.detect_divergence(match)
        assert divergence is None


class TestMaxResults:
    """Tests for result limiting."""

    def test_max_10_results(self, foil, registry):
        """instantiate() should return at most 10 results."""
        # Register 15 premises with matching claims
        for i in range(15):
            registry.register(_make_record(
                premise_id=f"px{i:02d}",
                claim=f"The file exists at path number {i}",
                session_id=f"sess-{i}",
            ))

        matches = foil.instantiate("file exists")
        assert len(matches) <= 10
