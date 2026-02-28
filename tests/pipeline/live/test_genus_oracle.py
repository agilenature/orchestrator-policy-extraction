"""Tests for GenusOracleHandler (Phase 25-03).

Covers: empty input, missing table, no matches, partial matches, top-1 selection,
instance extraction, valid flag, repo scoping, instance boost, confidence capping.

Fixtures seed axis_edges with known genus_of entries (CRAD + module boundary
dissolution) and bus_sessions for repo scoping.
"""
from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.ddf.topology.schema import create_topology_schema
from src.pipeline.live.bus.schema import create_bus_schema
from src.pipeline.live.genus_oracle import GenusOracleHandler, _tokenize


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_conn():
    """In-memory DuckDB with topology + bus schemas created."""
    conn = duckdb.connect(":memory:")
    create_topology_schema(conn)
    create_bus_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def oracle(db_conn):
    """GenusOracleHandler wired to the in-memory DuckDB."""
    return GenusOracleHandler(db_conn)


@pytest.fixture
def seeded_db(db_conn):
    """Seed axis_edges with two genus_of entries and a bus_session.

    - CRAD genus (corpus-relative identity retrieval) with 2 instances
    - module boundary dissolution with 1 instance
    - bus_session for test-session-1 in orchestrator-policy-extraction repo
    """
    # CRAD genus: 2 instances, high quality
    db_conn.execute(
        "INSERT INTO axis_edges (edge_id, axis_a, axis_b, relationship_text, "
        "activation_condition, evidence, abstraction_level, status, "
        "trunk_quality, created_session_id, created_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "edge-crad-001",
            "corpus-relative identity retrieval",
            "searchability-failure",
            "genus_of",
            json.dumps("problem-context"),
            json.dumps({
                "instances": [
                    "A7 per-file searchability failure",
                    "MOTM dedup failure",
                ],
                "source": "genus_check_gate",
                "session_id": "test-session-1",
            }),
            3,
            "candidate",
            0.8,
            "test-session-1",
            "2026-02-28T00:00:00Z",
        ],
    )

    # Module boundary dissolution: 1 instance
    db_conn.execute(
        "INSERT INTO axis_edges (edge_id, axis_a, axis_b, relationship_text, "
        "activation_condition, evidence, abstraction_level, status, "
        "trunk_quality, created_session_id, created_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "edge-mod-001",
            "module boundary dissolution",
            "import-failure",
            "genus_of",
            json.dumps("problem-context"),
            json.dumps({
                "instances": ["import failure"],
                "source": "genus_check_gate",
                "session_id": "test-session-2",
            }),
            3,
            "candidate",
            0.7,
            "test-session-2",
            "2026-02-28T00:00:00Z",
        ],
    )

    # Register bus_session for repo scoping
    db_conn.execute(
        "INSERT INTO bus_sessions (session_id, run_id, registered_at, repo) "
        "VALUES (?, ?, ?, ?)",
        [
            "test-session-1",
            "run-1",
            "2026-02-28T00:00:00Z",
            "orchestrator-policy-extraction",
        ],
    )

    return db_conn


@pytest.fixture
def seeded_oracle(seeded_db):
    """GenusOracleHandler wired to the seeded in-memory DuckDB."""
    return GenusOracleHandler(seeded_db)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_query_empty_problem(seeded_oracle):
    """query_genus('') returns null genus, confidence 0.0."""
    result = seeded_oracle.query_genus("")
    assert result["genus"] is None
    assert result["confidence"] == 0.0
    assert result["valid"] is False
    assert result["instances"] == []


def test_query_no_axis_edges_table(db_conn):
    """Oracle with conn that has NO axis_edges table returns null genus."""
    # Create a fresh conn with only bus schema (no topology)
    conn = duckdb.connect(":memory:")
    create_bus_schema(conn)
    # Drop axis_edges if create_bus_schema happened to create it indirectly
    try:
        conn.execute("DROP TABLE IF EXISTS axis_edges")
    except Exception:
        pass
    oracle = GenusOracleHandler(conn)
    result = oracle.query_genus("corpus relative identity retrieval")
    assert result["genus"] is None
    assert result["confidence"] == 0.0
    conn.close()


def test_query_no_genus_edges(oracle):
    """axis_edges exists but has no genus_of rows. Returns null genus."""
    result = oracle.query_genus("corpus relative identity retrieval")
    assert result["genus"] is None
    assert result["confidence"] == 0.0


def test_query_matching_genus_name(seeded_oracle):
    """Full genus name match yields high confidence (>= 0.5)."""
    result = seeded_oracle.query_genus(
        "corpus relative identity retrieval problem"
    )
    assert result["genus"] == "corpus-relative identity retrieval"
    assert result["confidence"] >= 0.5
    assert result["valid"] is True


def test_query_partial_match(seeded_oracle):
    """Partial match (2/4 genus tokens) yields confidence > 0."""
    result = seeded_oracle.query_genus("identity retrieval")
    assert result["genus"] is not None
    assert result["confidence"] > 0


def test_query_no_match(seeded_oracle):
    """Completely unrelated query returns null genus."""
    result = seeded_oracle.query_genus(
        "completely unrelated database migration"
    )
    # Either null genus or very low confidence
    if result["genus"] is not None:
        assert result["confidence"] < 0.1


def test_query_returns_top1_by_confidence(seeded_oracle):
    """With two genus_of edges, query matching CRAD tokens returns CRAD, not module."""
    result = seeded_oracle.query_genus(
        "corpus relative identity retrieval"
    )
    assert result["genus"] == "corpus-relative identity retrieval"


def test_query_instances_from_evidence(seeded_oracle):
    """Returned instances list contains the seeded instance names."""
    result = seeded_oracle.query_genus(
        "corpus relative identity retrieval"
    )
    assert result["genus"] is not None
    # instances should be from the CRAD evidence
    assert len(result["instances"]) > 0
    assert "A7 per-file searchability failure" in result["instances"]


def test_query_valid_true_when_two_instances(seeded_oracle):
    """CRAD genus has 2 instances, so valid should be True."""
    result = seeded_oracle.query_genus(
        "corpus relative identity retrieval"
    )
    assert result["valid"] is True


def test_query_valid_false_when_one_instance(seeded_oracle):
    """module boundary dissolution has 1 instance, so valid should be False."""
    result = seeded_oracle.query_genus("module boundary dissolution")
    assert result["genus"] == "module boundary dissolution"
    assert result["valid"] is False


def test_query_repo_scoped(seeded_oracle, seeded_db):
    """Repo scoping: matches for registered repo, null for unregistered."""
    # test-session-1 is in orchestrator-policy-extraction
    result = seeded_oracle.query_genus(
        "corpus relative identity retrieval",
        repo="orchestrator-policy-extraction",
    )
    assert result["genus"] == "corpus-relative identity retrieval"

    # other-repo has no bus_session registered
    result_other = seeded_oracle.query_genus(
        "corpus relative identity retrieval",
        repo="other-repo",
    )
    assert result_other["genus"] is None


def test_query_instance_boost(seeded_oracle):
    """Instance name mention boosts scoring -- matches CRAD via instance name."""
    result = seeded_oracle.query_genus(
        "A7 per-file searchability failure"
    )
    # Instance boost should help match CRAD even when genus name tokens
    # don't all appear in the query. "searchability" and "failure" appear
    # in the instance name.
    assert result["genus"] is not None
    assert result["confidence"] > 0


def test_confidence_capped_at_one(seeded_oracle):
    """Even with full genus + instance match, confidence <= 1.0."""
    result = seeded_oracle.query_genus(
        "corpus relative identity retrieval A7 per-file searchability "
        "failure MOTM dedup failure"
    )
    assert result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# _tokenize unit tests
# ---------------------------------------------------------------------------


def test_tokenize_removes_stopwords():
    """_tokenize removes stopwords and short tokens."""
    tokens = _tokenize("corpus relative identity retrieval")
    assert tokens == {"corpus", "relative", "identity", "retrieval"}


def test_tokenize_handles_hyphens():
    """_tokenize splits on hyphens (via regex [a-zA-Z]+)."""
    tokens = _tokenize("corpus-relative")
    assert tokens == {"corpus", "relative"}
