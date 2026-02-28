"""Integration test for /api/genus-consult endpoint.

Simulates a non-OPE session (data/ope.db absent, OPE_BUS_SOCKET set)
querying the bus for genus identification. Seeds axis_edges with the
A7/CRAD genus_of entry and verifies the full round-trip.
"""
import json
import pytest
import duckdb
from httpx import AsyncClient, ASGITransport

from src.pipeline.live.bus.server import create_app
from src.pipeline.live.bus.schema import create_bus_schema
from src.pipeline.ddf.topology.schema import create_topology_schema


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_integration.db")


@pytest.fixture
def seeded_app(db_path):
    """Create app with seeded genus_of data in axis_edges."""
    # Pre-seed the database with both schemas + genus data
    conn = duckdb.connect(db_path)
    create_topology_schema(conn)  # creates axis_edges table
    create_bus_schema(conn)   # creates bus_sessions

    # Seed the A7/CRAD genus_of edge
    conn.execute(
        "INSERT INTO axis_edges (edge_id, axis_a, axis_b, relationship_text, "
        "activation_condition, evidence, abstraction_level, status, "
        "trunk_quality, created_session_id, created_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "edge-crad-integration",
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
                "session_id": "ope-session-1",
            }),
            3,
            "candidate",
            0.8,
            "ope-session-1",
            "2026-02-28T00:00:00Z",
        ],
    )

    # Register a bus_session for repo scoping
    conn.execute(
        "INSERT INTO bus_sessions (session_id, run_id, registered_at, repo) "
        "VALUES (?, ?, ?, ?)",
        ["ope-session-1", "run-1", "2026-02-28T00:00:00Z",
         "orchestrator-policy-extraction"],
    )
    conn.close()

    return create_app(db_path=db_path)


@pytest.fixture
def client(seeded_app):
    transport = ASGITransport(app=seeded_app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_genus_consult_returns_crad_for_identity_retrieval(client):
    """Non-OPE session receives valid genus for identity retrieval problem."""
    resp = await client.post("/api/genus-consult", json={
        "problem": "corpus relative identity retrieval issue with searchability",
        "session_id": "non-ope-session-1",
        "repo": "orchestrator-policy-extraction",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["genus"] == "corpus-relative identity retrieval"
    assert data["valid"] is True
    assert data["confidence"] > 0.5
    assert len(data["instances"]) == 2
    assert "A7 per-file searchability failure" in data["instances"]


@pytest.mark.asyncio
async def test_genus_consult_returns_null_for_unrelated_problem(client):
    """Unrelated problem returns null genus."""
    resp = await client.post("/api/genus-consult", json={
        "problem": "database migration SQL syntax error",
        "session_id": "non-ope-session-2",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["genus"] is None
    assert data["valid"] is False
    assert data["confidence"] == 0.0
    assert data["instances"] == []


@pytest.mark.asyncio
async def test_genus_consult_fails_open_on_empty_body(client):
    """Empty body returns null genus, not error."""
    resp = await client.post("/api/genus-consult", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["genus"] is None
    assert data["confidence"] == 0.0


@pytest.mark.asyncio
async def test_genus_consult_repo_scoping(client):
    """Query with wrong repo returns no match (session not in that repo)."""
    resp = await client.post("/api/genus-consult", json={
        "problem": "corpus relative identity retrieval",
        "session_id": "non-ope-session-3",
        "repo": "some-other-repo",
    })
    assert resp.status_code == 200
    data = resp.json()
    # No genus_of edges from sessions in "some-other-repo"
    assert data["genus"] is None


@pytest.mark.asyncio
async def test_genus_consult_instance_name_boost(client):
    """Problem mentioning A7 should match via instance name boost."""
    resp = await client.post("/api/genus-consult", json={
        "problem": "A7 per-file searchability failure keeps recurring",
        "session_id": "non-ope-session-4",
    })
    assert resp.status_code == 200
    data = resp.json()
    # Should match via instance boost even if genus name tokens
    # don't fully match
    assert data["genus"] == "corpus-relative identity retrieval"
    assert data["confidence"] > 0.0
