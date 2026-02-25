"""Integration tests for the OPE Governance Bus (Phase 19-05).

Validates cross-session run_id grouping, constraint delivery, fail-open
behavior, and bus read-channel enforcement. These are the Phase 19
validation criterion tests: two sessions sharing the same OPE_RUN_ID
register with the bus and both appear in bus_sessions under that run_id.
"""

from __future__ import annotations

import json

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.live.bus.schema import create_bus_schema
from src.pipeline.live.bus.server import create_app
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """Temporary DuckDB path for integration tests."""
    return str(tmp_path / "integration.db")


@pytest.fixture
def constraints_file(tmp_path, monkeypatch):
    """Create a constraints.json with one active constraint in tmp_path/data/."""
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    path = data_dir / "constraints.json"
    path.write_text(json.dumps([
        {
            "id": "c1",
            "ccd_axis": "identity-firewall",
            "severity": "forbidden",
            "text": "Builder must not validate its own artifacts",
            "status": "active",
        },
    ]))
    return path


# ---------------------------------------------------------------------------
# Cross-session run_id grouping tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCrossSessionRunId:
    """Validate run_id-based cross-session grouping in DuckDB."""

    async def test_two_sessions_same_run_id_grouped_in_db(self, db_path):
        """THE critical test: Session A + Session B both register with shared
        run_id; DuckDB bus_sessions has both records under same run_id."""
        app = create_app(db_path=db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_a = await client.post(
                "/api/register",
                json={"session_id": "session-A", "run_id": "run-42"},
            )
            r_b = await client.post(
                "/api/register",
                json={"session_id": "session-B", "run_id": "run-42"},
            )
            assert r_a.status_code == 200
            assert r_b.status_code == 200

        # Verify both sessions present under run_id in DuckDB
        # Note: cannot use read_only=True while server connection is open
        conn = duckdb.connect(db_path)
        rows = conn.execute(
            "SELECT session_id FROM bus_sessions "
            "WHERE run_id='run-42' ORDER BY session_id"
        ).fetchall()
        session_ids = [r[0] for r in rows]
        assert "session-A" in session_ids
        assert "session-B" in session_ids
        assert len(session_ids) == 2
        conn.close()

    async def test_cross_session_constraint_delivery(
        self, db_path, constraints_file
    ):
        """Both sessions under same run_id receive the same constraint list
        via /api/check. Verifies the cross-session briefing path."""
        daemon = GovernorDaemon(db_path=db_path)
        app = create_app(db_path=db_path, daemon=daemon)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/register",
                json={"session_id": "session-A", "run_id": "run-99"},
            )
            await client.post(
                "/api/register",
                json={"session_id": "session-B", "run_id": "run-99"},
            )

            r_a = await client.post(
                "/api/check",
                json={"session_id": "session-A", "run_id": "run-99"},
            )
            r_b = await client.post(
                "/api/check",
                json={"session_id": "session-B", "run_id": "run-99"},
            )

        constraints_a = r_a.json()["constraints"]
        constraints_b = r_b.json()["constraints"]
        assert len(constraints_a) == 1
        assert len(constraints_b) == 1
        assert constraints_a[0]["id"] == constraints_b[0]["id"]
        assert constraints_a[0]["id"] == "c1"

    async def test_sessions_cannot_write_constraints_via_bus(self, db_path):
        """Bus API has no endpoint for sessions to write constraints.
        Structural enforcement: read-channel only."""
        app = create_app(db_path=db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/constraints",
                json={"id": "c-malicious", "severity": "forbidden"},
            )
        # 404 or 405 -- endpoint does not exist on bus
        assert r.status_code in (404, 405)

    async def test_run_id_fallback_when_not_provided(self, db_path):
        """If run_id absent from register body, session_id used as fallback.
        Pre-OpenClaw behavior: sessions are isolated islands."""
        app = create_app(db_path=db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/register",
                json={"session_id": "session-orphan"},
            )
        assert r.status_code == 200
        assert r.json()["run_id"] == "session-orphan"

        # Verify in DuckDB that run_id equals session_id
        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT run_id FROM bus_sessions "
            "WHERE session_id='session-orphan'"
        ).fetchone()
        assert row is not None
        assert row[0] == "session-orphan"
        conn.close()


# ---------------------------------------------------------------------------
# Fail-open behavior tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFailOpen:
    """Verify the bus fails open -- errors never block sessions."""

    async def test_deregister_unknown_session_returns_200(self, db_path):
        """Deregistering a session that was never registered returns 200.
        Fail-open: unknown session is not an error."""
        app = create_app(db_path=db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/deregister",
                json={"session_id": "never-registered"},
            )
        assert r.status_code == 200
        assert r.json()["status"] == "deregistered"

    async def test_check_with_no_constraints_file_returns_empty(
        self, db_path, tmp_path, monkeypatch
    ):
        """When constraints.json is absent, /api/check returns empty list.
        Fail-open: missing constraint file is not an error."""
        monkeypatch.chdir(tmp_path)
        app = create_app(db_path=db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/check",
                json={"session_id": "s1", "run_id": "r1"},
            )
        assert r.status_code == 200
        assert r.json()["constraints"] == []
        assert r.json()["interventions"] == []

    async def test_register_malformed_body_returns_200(self, db_path):
        """Malformed JSON body on /api/register returns 200, not 500.
        Fail-open: bad requests do not crash the bus."""
        app = create_app(db_path=db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/register",
                content=b"this is not json",
                headers={"content-type": "application/json"},
            )
        assert r.status_code == 200
        assert r.json()["status"] == "registered"


# ---------------------------------------------------------------------------
# Bus CLI tests
# ---------------------------------------------------------------------------


class TestBusCLI:
    """Verify bus CLI start and status commands."""

    def test_status_no_socket(self, tmp_path):
        """bus status reports 'not running' when socket does not exist."""
        from click.testing import CliRunner

        from src.pipeline.cli.bus import bus_group

        runner = CliRunner()
        result = runner.invoke(
            bus_group,
            ["status", "--socket", str(tmp_path / "nonexistent.sock")],
        )
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_start_exits_1_when_socket_exists(self, tmp_path):
        """bus start exits 1 when socket file already exists."""
        from click.testing import CliRunner

        from src.pipeline.cli.bus import bus_group

        socket_path = str(tmp_path / "existing.sock")
        open(socket_path, "w").close()  # simulate existing socket
        runner = CliRunner()
        result = runner.invoke(
            bus_group,
            ["start", "--socket", socket_path, "--db", ":memory:"],
        )
        assert result.exit_code == 1
        assert "already" in result.output
