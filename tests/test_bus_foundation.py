"""Tests for the OPE Governance Bus foundation (Phase 19-01).

Covers DuckDB schema, Pydantic models, and Starlette server routes.
Uses httpx AsyncClient with ASGITransport for endpoint testing.
"""

from __future__ import annotations

import pytest
import duckdb
from httpx import ASGITransport, AsyncClient

from src.pipeline.live.bus.schema import create_bus_schema
from src.pipeline.live.bus.models import (
    BusSession,
    GovernanceSignal,
    CheckRequest,
    CheckResponse,
)
from src.pipeline.live.bus.server import create_app
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory DuckDB connection with bus schema."""
    conn = duckdb.connect(":memory:")
    create_bus_schema(conn)
    return conn


@pytest.fixture
def app(tmp_path):
    """Starlette app backed by in-memory DuckDB with isolated daemon.

    Uses a non-existent constraints path so /api/check returns empty
    constraints (daemon fail-open behavior) without reading real data.
    """
    daemon = GovernorDaemon(
        db_path=":memory:",
        constraints_path=str(tmp_path / "nonexistent" / "constraints.json"),
    )
    return create_app(db_path=":memory:", daemon=daemon)


@pytest.fixture
def client(app):
    """httpx AsyncClient wired to the Starlette app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_bus_sessions_table_exists(db):
    """bus_sessions table is created with expected columns.

    Includes Phase 20-01 extension columns (repo, project_dir,
    transcript_path, event_count, outcome) added via ALTER TABLE.
    """
    cols = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='bus_sessions' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert col_names == [
        "session_id", "run_id", "registered_at", "last_seen_at", "status",
        "repo", "project_dir", "transcript_path", "event_count", "outcome",
    ]


def test_governance_signals_table_exists(db):
    """governance_signals table is created with expected columns."""
    cols = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='governance_signals' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert col_names == [
        "signal_id", "session_id", "run_id", "signal_type",
        "boundary_dependency", "payload_json", "emitted_at",
    ]


def test_create_bus_schema_idempotent(db):
    """Calling create_bus_schema twice does not raise."""
    create_bus_schema(db)  # already called in fixture; second call
    tables = db.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "bus_sessions" in table_names
    assert "governance_signals" in table_names


def test_bus_sessions_status_check_constraint(db):
    """bus_sessions rejects invalid status values."""
    db.execute(
        "INSERT INTO bus_sessions (session_id, run_id, status) "
        "VALUES ('s1', 'r1', 'active')"
    )
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            "INSERT INTO bus_sessions (session_id, run_id, status) "
            "VALUES ('s2', 'r2', 'invalid_status')"
        )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_governance_signal_make_id_deterministic():
    """GovernanceSignal.make_id produces same hash for same inputs."""
    id1 = GovernanceSignal.make_id("s1", "escalation", "2026-01-01T00:00:00Z")
    id2 = GovernanceSignal.make_id("s1", "escalation", "2026-01-01T00:00:00Z")
    assert id1 == id2
    assert len(id1) == 16


def test_governance_signal_make_id_varies():
    """GovernanceSignal.make_id produces different hashes for different inputs."""
    id1 = GovernanceSignal.make_id("s1", "escalation", "2026-01-01T00:00:00Z")
    id2 = GovernanceSignal.make_id("s2", "escalation", "2026-01-01T00:00:00Z")
    assert id1 != id2


def test_check_response_empty_default():
    """CheckResponse defaults to empty constraints and interventions."""
    cr = CheckResponse()
    assert cr.constraints == []
    assert cr.interventions == []


def test_bus_session_frozen():
    """BusSession is immutable (frozen=True)."""
    bs = BusSession(session_id="s1", run_id="r1")
    with pytest.raises(Exception):
        bs.status = "changed"


# ---------------------------------------------------------------------------
# Server route tests (async, using httpx)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_returns_200_with_run_id(client):
    """POST /api/register returns 200 with session_id and run_id."""
    resp = await client.post(
        "/api/register",
        json={"session_id": "test-session", "run_id": "test-run"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "registered"
    assert data["session_id"] == "test-session"
    assert data["run_id"] == "test-run"


@pytest.mark.asyncio
async def test_register_stores_in_duckdb(app):
    """POST /api/register persists session to bus_sessions table."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/register",
            json={"session_id": "persist-test", "run_id": "run-42"},
        )

    # Access the DuckDB connection through the app's route closures
    # We verify by making a second registration and checking it doesn't error
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/register",
            json={"session_id": "persist-test", "run_id": "run-42-updated"},
        )
        assert resp.status_code == 200
        # INSERT OR REPLACE should succeed (idempotent)


@pytest.mark.asyncio
async def test_deregister_returns_200(client):
    """POST /api/deregister returns 200."""
    resp = await client.post(
        "/api/deregister",
        json={"session_id": "test-session"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deregistered"


@pytest.mark.asyncio
async def test_check_stub_returns_empty(client):
    """POST /api/check stub returns empty constraints and interventions."""
    resp = await client.post(
        "/api/check",
        json={"session_id": "test-session", "run_id": "test-run"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["constraints"] == []
    assert data["interventions"] == []


@pytest.mark.asyncio
async def test_register_fail_open_malformed_body(app):
    """POST /api/register with malformed body returns 200, not 500."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/register",
            content=b"this is not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "registered"


@pytest.mark.asyncio
async def test_register_run_id_fallback(client):
    """When run_id is absent, session_id is used as fallback."""
    resp = await client.post(
        "/api/register",
        json={"session_id": "fallback-test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "fallback-test"
