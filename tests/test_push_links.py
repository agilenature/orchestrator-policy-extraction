"""Tests for the /api/push-link handler (Phase 20-03).

Covers push link validation, auto-generated IDs, DuckDB persistence,
idempotent writes, and T1 round-trip (POST -> DuckDB SELECT -> all fields match).

Uses httpx AsyncClient with ASGITransport for endpoint testing.
File-based DuckDB with separate verification connections to avoid
write-lock conflicts with create_app().
"""

from __future__ import annotations

import hashlib

import pytest
import duckdb
from httpx import ASGITransport, AsyncClient

from src.pipeline.live.bus.server import create_app
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """File-based DuckDB path for push link tests."""
    return str(tmp_path / "push_links_test.db")


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
# T1 round-trip test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_link_round_trip_t1(client, db_path):
    """POST full push link payload, then SELECT from DuckDB -- all 7 fields match."""
    payload = {
        "link_id": "T1-integration",
        "parent_decision_id": "D1-slice-decomp",
        "child_decision_id": "D2-engine-gate",
        "transition_trigger": "T1_slice_decomposition",
        "repo_boundary": "modernizing-tool -> ope",
        "migration_run_id": "run-integration-001",
        "captured_at": "2026-01-15T12:00:00+00:00",
    }
    resp = await client.post("/api/push-link", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["link_id"] == "T1-integration"

    # Verify all 7 fields in DuckDB
    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT link_id, parent_decision_id, child_decision_id, "
        "transition_trigger, repo_boundary, migration_run_id, captured_at "
        "FROM push_links WHERE link_id='T1-integration'"
    ).fetchone()
    verify_conn.close()

    assert row is not None, "Push link not found in DuckDB"
    assert row[0] == "T1-integration"
    assert row[1] == "D1-slice-decomp"
    assert row[2] == "D2-engine-gate"
    assert row[3] == "T1_slice_decomposition"
    assert row[4] == "modernizing-tool -> ope"
    assert row[5] == "run-integration-001"
    # DuckDB returns datetime objects for TIMESTAMPTZ; compare as UTC
    from datetime import datetime, timezone
    expected_dt = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    actual_dt = row[6].astimezone(timezone.utc) if hasattr(row[6], "astimezone") else row[6]
    assert actual_dt.year == expected_dt.year
    assert actual_dt.month == expected_dt.month
    assert actual_dt.day == expected_dt.day
    assert actual_dt.hour == expected_dt.hour


# ---------------------------------------------------------------------------
# Auto-generated link_id tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_link_auto_generates_link_id(client, db_path):
    """POST without link_id returns a non-empty 16-char hex ID, stored in DuckDB."""
    resp = await client.post(
        "/api/push-link",
        json={
            "parent_decision_id": "P-auto",
            "child_decision_id": "C-auto",
            "transition_trigger": "T7_gate_to_canary",
            "migration_run_id": "run-auto-001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    link_id = data["link_id"]
    assert len(link_id) == 16
    assert all(c in "0123456789abcdef" for c in link_id)

    # Verify in DuckDB
    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT link_id FROM push_links WHERE link_id=?", [link_id]
    ).fetchone()
    verify_conn.close()
    assert row is not None


@pytest.mark.asyncio
async def test_push_link_deterministic_id_generation(client):
    """POST same content twice produces the same auto-generated link_id."""
    payload = {
        "parent_decision_id": "P-det",
        "child_decision_id": "C-det",
        "transition_trigger": "T1_slice_decomposition",
        "migration_run_id": "run-det-001",
    }
    resp1 = await client.post("/api/push-link", json=payload)
    resp2 = await client.post("/api/push-link", json=payload)
    assert resp1.json()["link_id"] == resp2.json()["link_id"]

    # Verify the ID matches the expected hash
    raw = "link:P-det:C-det:T1_slice_decomposition"
    expected = hashlib.sha256(raw.encode()).hexdigest()[:16]
    assert resp1.json()["link_id"] == expected


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_link_validates_required_fields(client):
    """POST missing parent_decision_id returns 400 with detail."""
    resp = await client.post(
        "/api/push-link",
        json={
            "child_decision_id": "C-val",
            "transition_trigger": "T1",
            "migration_run_id": "run-val",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert "parent_decision_id" in data["detail"]


@pytest.mark.asyncio
async def test_push_link_missing_multiple_required_fields(client):
    """POST empty body returns 400 listing all missing fields."""
    resp = await client.post("/api/push-link", json={})
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert "parent_decision_id" in data["detail"]
    assert "child_decision_id" in data["detail"]
    assert "transition_trigger" in data["detail"]
    assert "migration_run_id" in data["detail"]


@pytest.mark.asyncio
async def test_push_link_malformed_json_returns_400(client):
    """POST with non-JSON body returns 400."""
    resp = await client.post(
        "/api/push-link",
        content=b"this is not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert "invalid JSON" in data["detail"]


# ---------------------------------------------------------------------------
# Optional field tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_link_repo_boundary_optional(client, db_path):
    """POST without repo_boundary stores NULL in DuckDB."""
    resp = await client.post(
        "/api/push-link",
        json={
            "link_id": "no-repo-boundary",
            "parent_decision_id": "P-opt",
            "child_decision_id": "C-opt",
            "transition_trigger": "T8_failure_to_writeback",
            "migration_run_id": "run-opt-001",
        },
    )
    assert resp.status_code == 200

    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT repo_boundary FROM push_links WHERE link_id='no-repo-boundary'"
    ).fetchone()
    verify_conn.close()
    assert row is not None
    assert row[0] is None


# ---------------------------------------------------------------------------
# Idempotency and timestamp tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_link_idempotent_insert(client, db_path):
    """POST same link_id twice with different child_decision_id updates the row."""
    payload1 = {
        "link_id": "idempotent-001",
        "parent_decision_id": "P-idem",
        "child_decision_id": "C-idem-v1",
        "transition_trigger": "T1",
        "migration_run_id": "run-idem",
    }
    payload2 = {**payload1, "child_decision_id": "C-idem-v2"}

    resp1 = await client.post("/api/push-link", json=payload1)
    resp2 = await client.post("/api/push-link", json=payload2)
    assert resp1.status_code == 200
    assert resp2.status_code == 200

    # DuckDB has the updated child_decision_id
    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT child_decision_id FROM push_links WHERE link_id='idempotent-001'"
    ).fetchone()
    verify_conn.close()
    assert row[0] == "C-idem-v2"


@pytest.mark.asyncio
async def test_push_link_captured_at_defaults_to_server_time(client, db_path):
    """POST without captured_at stores a non-null timestamp in DuckDB."""
    resp = await client.post(
        "/api/push-link",
        json={
            "link_id": "auto-time-001",
            "parent_decision_id": "P-time",
            "child_decision_id": "C-time",
            "transition_trigger": "T1",
            "migration_run_id": "run-time",
        },
    )
    assert resp.status_code == 200

    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT captured_at FROM push_links WHERE link_id='auto-time-001'"
    ).fetchone()
    verify_conn.close()
    assert row is not None
    assert row[0] is not None
    # Should be an ISO 8601 string containing a date
    assert "202" in str(row[0])


@pytest.mark.asyncio
async def test_push_link_custom_captured_at_honored(client, db_path):
    """POST with explicit captured_at stores that value in DuckDB."""
    resp = await client.post(
        "/api/push-link",
        json={
            "link_id": "custom-time-001",
            "parent_decision_id": "P-custom",
            "child_decision_id": "C-custom",
            "transition_trigger": "T1",
            "migration_run_id": "run-custom",
            "captured_at": "2026-01-15T00:00:00Z",
        },
    )
    assert resp.status_code == 200

    verify_conn = duckdb.connect(db_path)
    row = verify_conn.execute(
        "SELECT captured_at FROM push_links WHERE link_id='custom-time-001'"
    ).fetchone()
    verify_conn.close()
    assert row is not None
    # DuckDB returns datetime objects for TIMESTAMPTZ; convert to UTC for comparison
    from datetime import timezone as tz
    actual_dt = row[0].astimezone(tz.utc) if hasattr(row[0], "astimezone") else row[0]
    assert actual_dt.year == 2026
    assert actual_dt.month == 1
    assert actual_dt.day == 15
    assert actual_dt.hour == 0
