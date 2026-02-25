"""Tests for the OPE Governance Bus schema extension (Phase 20-01).

Covers DuckDB schema changes (bus_sessions new columns, push_links table),
updated server routes (register with repo, deregister with outcome,
push-link stub), and new Pydantic models (PushLink, CheckResponse update).

Uses httpx AsyncClient with ASGITransport for endpoint testing.
File-based DuckDB with read_only=True verification connections to avoid
write-lock conflicts with the create_app() connection.
"""

from __future__ import annotations

import pytest
import duckdb
from httpx import ASGITransport, AsyncClient

from src.pipeline.live.bus.schema import create_bus_schema, PUSH_LINKS_DDL
from src.pipeline.live.bus.models import PushLink, CheckResponse
from src.pipeline.live.bus.server import create_app
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory DuckDB connection with full bus schema (including extensions)."""
    conn = duckdb.connect(":memory:")
    create_bus_schema(conn)
    return conn


@pytest.fixture
def db_path(tmp_path):
    """File-based DuckDB path for endpoint tests that need verification reads."""
    return str(tmp_path / "test_bus.db")


@pytest.fixture
def app(db_path, tmp_path):
    """Starlette app backed by file-based DuckDB with isolated daemon."""
    daemon = GovernorDaemon(
        db_path=":memory:",
        constraints_path=str(tmp_path / "nonexistent" / "constraints.json"),
    )
    return create_app(db_path=db_path, daemon=daemon)


@pytest.fixture
def client(app):
    """httpx AsyncClient wired to the Starlette app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_bus_sessions_has_repo_column(db):
    """bus_sessions table includes the new repo column."""
    cols = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='bus_sessions' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert "repo" in col_names
    assert "project_dir" in col_names
    assert "transcript_path" in col_names
    assert "event_count" in col_names
    assert "outcome" in col_names


def test_bus_sessions_has_10_columns(db):
    """bus_sessions table has all 10 columns (original 5 + 5 new)."""
    cols = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='bus_sessions' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert col_names == [
        "session_id", "run_id", "registered_at", "last_seen_at", "status",
        "repo", "project_dir", "transcript_path", "event_count", "outcome",
    ]


def test_push_links_table_exists(db):
    """push_links table is created with the 7-column schema."""
    cols = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='push_links' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert col_names == [
        "link_id", "parent_decision_id", "child_decision_id",
        "transition_trigger", "repo_boundary", "migration_run_id",
        "captured_at",
    ]


def test_schema_extension_idempotent(db):
    """Calling create_bus_schema twice with extensions does not raise."""
    create_bus_schema(db)  # second call -- already called in fixture
    cols = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='bus_sessions' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert "repo" in col_names
    # push_links still exists
    tables = db.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "push_links" in table_names


def test_new_columns_nullable(db):
    """New bus_sessions columns accept NULL values (no NOT NULL constraint)."""
    db.execute(
        "INSERT INTO bus_sessions (session_id, run_id) "
        "VALUES ('null-test', 'run-1')"
    )
    row = db.execute(
        "SELECT repo, project_dir, transcript_path, event_count, outcome "
        "FROM bus_sessions WHERE session_id='null-test'"
    ).fetchone()
    assert row == (None, None, None, None, None)


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_with_repo(client, db_path):
    """POST /api/register stores repo, project_dir, transcript_path."""
    resp = await client.post(
        "/api/register",
        json={
            "session_id": "repo-test",
            "run_id": "run-42",
            "repo": "orchestrator-policy-extraction",
            "project_dir": "/Users/david/projects/ope",
            "transcript_path": "/tmp/session.jsonl",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] == "orchestrator-policy-extraction"

    # Verify in DuckDB using a second connection (same process, no read_only
    # flag -- DuckDB disallows mixed read_only/read_write to same file)
    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT repo, project_dir, transcript_path FROM bus_sessions "
        "WHERE session_id='repo-test'"
    ).fetchone()
    verify_conn.close()
    assert row == (
        "orchestrator-policy-extraction",
        "/Users/david/projects/ope",
        "/tmp/session.jsonl",
    )


@pytest.mark.asyncio
async def test_register_without_repo(client):
    """POST /api/register without repo fields returns repo=None."""
    resp = await client.post(
        "/api/register",
        json={"session_id": "no-repo-test", "run_id": "run-43"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] is None


@pytest.mark.asyncio
async def test_deregister_with_event_count(client, db_path):
    """POST /api/deregister stores event_count and outcome."""
    # Register first
    await client.post(
        "/api/register",
        json={"session_id": "dereg-test", "run_id": "run-44"},
    )
    # Deregister with metadata
    resp = await client.post(
        "/api/deregister",
        json={
            "session_id": "dereg-test",
            "event_count": 42,
            "outcome": "completed",
        },
    )
    assert resp.status_code == 200

    # Verify in DuckDB
    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT event_count, outcome, status FROM bus_sessions "
        "WHERE session_id='dereg-test'"
    ).fetchone()
    verify_conn.close()
    assert row == (42, "completed", "deregistered")


@pytest.mark.asyncio
async def test_deregister_without_event_count(client, db_path):
    """POST /api/deregister without event_count/outcome stores NULL."""
    await client.post(
        "/api/register",
        json={"session_id": "dereg-null-test", "run_id": "run-45"},
    )
    resp = await client.post(
        "/api/deregister",
        json={"session_id": "dereg-null-test"},
    )
    assert resp.status_code == 200

    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT event_count, outcome FROM bus_sessions "
        "WHERE session_id='dereg-null-test'"
    ).fetchone()
    verify_conn.close()
    assert row == (None, None)


@pytest.mark.asyncio
async def test_check_includes_epistemological_signals(client):
    """POST /api/check response includes epistemological_signals: []."""
    resp = await client.post(
        "/api/check",
        json={"session_id": "epi-test", "run_id": "run-46"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "epistemological_signals" in data
    assert data["epistemological_signals"] == []


@pytest.mark.asyncio
async def test_push_link_stub_returns_200(client):
    """POST /api/push-link stub returns 200 with accepted status."""
    resp = await client.post(
        "/api/push-link",
        json={
            "link_id": "link-001",
            "parent_decision_id": "parent-001",
            "child_decision_id": "child-001",
            "transition_trigger": "T1_slice_decomposition",
            "migration_run_id": "run-47",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["link_id"] == "link-001"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_push_link_model_fields():
    """PushLink model has all 7 fields with correct defaults."""
    pl = PushLink(
        link_id="link-test",
        parent_decision_id="parent-1",
        child_decision_id="child-1",
        transition_trigger="T1",
        migration_run_id="run-1",
    )
    assert pl.link_id == "link-test"
    assert pl.repo_boundary is None
    assert pl.captured_at == ""


def test_push_link_model_frozen():
    """PushLink model is immutable (frozen=True)."""
    pl = PushLink(
        link_id="link-frozen",
        parent_decision_id="p",
        child_decision_id="c",
        transition_trigger="T1",
        migration_run_id="r",
    )
    with pytest.raises(Exception):
        pl.link_id = "changed"
