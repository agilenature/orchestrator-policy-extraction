"""Integration tests for Phase 20: Causal Chain Completion.

Validates all 6 structural gaps identified by Phase 20's gap analysis.
Each test class maps to one gap from GOVERNING-ORCHESTRATOR-ARCHITECTURE.md.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.live.bus.models import CheckResponse
from src.pipeline.live.bus.server import create_app
from src.pipeline.live.governor.daemon import GovernorDaemon


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "integration.db")


@pytest.fixture
def constraints_path(tmp_path):
    return str(tmp_path / "data" / "constraints.json")


def _write_constraints(path, constraints):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(constraints))


# --- Gap 1: Bus registration schema incomplete --------------------------------

@pytest.mark.asyncio
class TestGap1_BusSchema:

    async def test_register_stores_repo_project_dir_transcript(self, db_path):
        app = create_app(db_path=db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/register", json={
                "session_id": "gap1-session",
                "run_id": "gap1-run",
                "repo": "orchestrator-policy-extraction",
                "project_dir": "/Users/david/projects/ope",
                "transcript_path": "/tmp/session.jsonl",
            })
        assert r.status_code == 200
        assert r.json().get("repo") == "orchestrator-policy-extraction"

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT repo, project_dir, transcript_path FROM bus_sessions WHERE session_id='gap1-session'"
        ).fetchone()
        conn.close()
        assert row[0] == "orchestrator-policy-extraction"
        assert row[1] == "/Users/david/projects/ope"
        assert row[2] == "/tmp/session.jsonl"

    async def test_deregister_stores_event_count_and_outcome(self, db_path):
        app = create_app(db_path=db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/register", json={"session_id": "gap1-dereg", "run_id": "r1"})
            await c.post("/api/deregister", json={
                "session_id": "gap1-dereg", "event_count": 157, "outcome": "completed",
            })

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT status, event_count, outcome FROM bus_sessions WHERE session_id='gap1-dereg'"
        ).fetchone()
        conn.close()
        assert row[0] == "deregistered"
        assert row[1] == 157
        assert row[2] == "completed"

    async def test_cross_session_repo_visible_in_bus_sessions(self, db_path):
        app = create_app(db_path=db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/register", json={"session_id": "s-ope", "run_id": "run-99", "repo": "ope"})
            await c.post("/api/register", json={"session_id": "s-mt", "run_id": "run-99", "repo": "modernizing-tool"})

        conn = duckdb.connect(db_path)
        rows = conn.execute(
            "SELECT session_id, repo FROM bus_sessions WHERE run_id='run-99' ORDER BY session_id"
        ).fetchall()
        conn.close()
        repos = {r[0]: r[1] for r in rows}
        assert repos["s-mt"] == "modernizing-tool"
        assert repos["s-ope"] == "ope"


# --- Gap 2: Push links at T1/T7/T8 not implemented ---------------------------

@pytest.mark.asyncio
class TestGap2_PushLinks:

    async def test_push_link_t1_round_trip(self, db_path):
        app = create_app(db_path=db_path)
        payload = {
            "link_id": "T1-integration",
            "parent_decision_id": "D1-slice-decomposition",
            "child_decision_id": "D2-engine1-migration",
            "transition_trigger": "T1",
            "repo_boundary": "migration-workbox -> platform-core",
            "migration_run_id": "run-42",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/push-link", json=payload)
        assert r.status_code == 200
        assert r.json()["link_id"] == "T1-integration"

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT parent_decision_id, child_decision_id, transition_trigger, repo_boundary, migration_run_id "
            "FROM push_links WHERE link_id='T1-integration'"
        ).fetchone()
        conn.close()
        assert row[0] == "D1-slice-decomposition"
        assert row[1] == "D2-engine1-migration"
        assert row[2] == "T1"
        assert row[3] == "migration-workbox -> platform-core"
        assert row[4] == "run-42"

    async def test_push_link_t7_and_t8_coexist(self, db_path):
        app = create_app(db_path=db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/push-link", json={"link_id": "T7-link", "parent_decision_id": "D7", "child_decision_id": "D8", "transition_trigger": "T7", "migration_run_id": "run-42"})
            await c.post("/api/push-link", json={"link_id": "T8-link", "parent_decision_id": "D8", "child_decision_id": "D10", "transition_trigger": "T8", "migration_run_id": "run-42"})

        conn = duckdb.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM push_links").fetchone()[0]
        triggers = {r[0] for r in conn.execute("SELECT transition_trigger FROM push_links").fetchall()}
        conn.close()
        assert count == 2
        assert "T7" in triggers
        assert "T8" in triggers

    async def test_push_link_cross_run_isolation(self, db_path):
        app = create_app(db_path=db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post("/api/push-link", json={"link_id": "run1-link", "parent_decision_id": "D1", "child_decision_id": "D2", "transition_trigger": "T1", "migration_run_id": "run-1"})
            await c.post("/api/push-link", json={"link_id": "run2-link", "parent_decision_id": "D1", "child_decision_id": "D2", "transition_trigger": "T1", "migration_run_id": "run-2"})

        conn = duckdb.connect(db_path)
        run1 = conn.execute("SELECT COUNT(*) FROM push_links WHERE migration_run_id='run-1'").fetchone()[0]
        run2 = conn.execute("SELECT COUNT(*) FROM push_links WHERE migration_run_id='run-2'").fetchone()[0]
        conn.close()
        assert run1 == 1
        assert run2 == 1


# --- Gap 3: BUS_REGISTRATION_FAILED event not emitted ------------------------

class TestGap3_RegistrationFailed:

    def test_bus_unavailable_emits_event_to_staging(self, tmp_path):
        from src.pipeline.live.hooks import session_start as ss
        staging = str(tmp_path / "staging.jsonl")
        with (
            patch.object(ss, "_post_json", return_value={}),
            patch.object(ss, "_OPE_RUN_ID", "run-42"),
            patch.object(ss, "_OPE_SESSION_ID", "s-gap3"),
            patch.object(ss, "_STAGING_PATH", staging),
        ):
            ss.main()

        lines = pathlib.Path(staging).read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert event["event_type"] == "BUS_REGISTRATION_FAILED"
        assert event["session_id"] == "s-gap3"
        assert event["run_id"] == "run-42"
        assert "attempted_at" in event

    def test_bus_available_no_failed_event(self, tmp_path):
        from src.pipeline.live.hooks import session_start as ss
        staging = str(tmp_path / "staging.jsonl")

        def mock_post(path, payload):
            if path == "/api/register":
                return {"status": "registered", "session_id": "s1", "run_id": "r1"}
            return {"constraints": [], "interventions": []}

        with (
            patch.object(ss, "_post_json", side_effect=mock_post),
            patch.object(ss, "_OPE_SESSION_ID", "s-ok"),
            patch.object(ss, "_OPE_RUN_ID", "run-42"),
            patch.object(ss, "_STAGING_PATH", staging),
        ):
            ss.main()

        p = pathlib.Path(staging)
        assert not p.exists() or p.stat().st_size == 0


# --- Gap 4: GovernorDaemon repo scope filter ----------------------------------

@pytest.mark.asyncio
class TestGap4_RepoScope:

    async def test_scoped_constraint_not_delivered_to_wrong_repo(self, db_path, constraints_path):
        _write_constraints(constraints_path, [
            {"id": "mw-only", "severity": "forbidden", "status": "active", "repo_scope": ["migration-workbox"]},
            {"id": "universal", "severity": "warning", "status": "active"},
        ])
        daemon = GovernorDaemon(db_path=db_path, constraints_path=constraints_path)
        app = create_app(db_path=db_path, daemon=daemon)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/check", json={"session_id": "s1", "run_id": "r1", "repo": "platform-core"})
        ids = [c["id"] for c in r.json()["constraints"]]
        assert "mw-only" not in ids
        assert "universal" in ids

    async def test_scoped_constraint_delivered_to_matching_repo(self, db_path, constraints_path):
        _write_constraints(constraints_path, [
            {"id": "mw-only", "severity": "forbidden", "status": "active", "repo_scope": ["migration-workbox"]},
        ])
        daemon = GovernorDaemon(db_path=db_path, constraints_path=constraints_path)
        app = create_app(db_path=db_path, daemon=daemon)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/check", json={"session_id": "s1", "run_id": "r1", "repo": "migration-workbox"})
        ids = [c["id"] for c in r.json()["constraints"]]
        assert "mw-only" in ids


# --- Gap 5: openclaw_unavailable flag -----------------------------------------

class TestGap5_OpenclawFlag:

    def test_openclaw_unavailable_true_when_run_id_absent(self, tmp_path):
        from src.pipeline.live.hooks import session_start as ss
        calls = []

        def mock_post(path, payload):
            calls.append((path, payload))
            return {"status": "registered", "session_id": "s1", "run_id": "r1"}

        staging = str(tmp_path / "staging.jsonl")
        with (
            patch.object(ss, "_post_json", side_effect=mock_post),
            patch.object(ss, "_OPE_RUN_ID", ""),
            patch.object(ss, "_OPE_SESSION_ID", "s-gap5"),
            patch.object(ss, "_STAGING_PATH", staging),
        ):
            ss.main()
        reg = [c for c in calls if c[0] == "/api/register"]
        assert reg[0][1].get("openclaw_unavailable") is True

    def test_openclaw_unavailable_absent_when_run_id_present(self, tmp_path):
        from src.pipeline.live.hooks import session_start as ss
        calls = []

        def mock_post(path, payload):
            calls.append((path, payload))
            if path == "/api/register":
                return {"status": "registered", "session_id": "s1", "run_id": "run-42"}
            return {"constraints": [], "interventions": []}

        staging = str(tmp_path / "staging.jsonl")
        with (
            patch.object(ss, "_post_json", side_effect=mock_post),
            patch.object(ss, "_OPE_RUN_ID", "run-42"),
            patch.object(ss, "_OPE_SESSION_ID", "s-gap5b"),
            patch.object(ss, "_STAGING_PATH", staging),
        ):
            ss.main()
        reg = [c for c in calls if c[0] == "/api/register"]
        assert "openclaw_unavailable" not in reg[0][1]


# --- Gap 6: Epistemological signals stub --------------------------------------

@pytest.mark.asyncio
class TestGap6_EpistemologicalSignals:

    async def test_check_response_has_epistemological_signals_field(self, db_path):
        app = create_app(db_path=db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/check", json={"session_id": "s1", "run_id": "r1"})
        data = r.json()
        assert "epistemological_signals" in data
        assert data["epistemological_signals"] == []


def test_gap6_check_response_model_has_field():
    """CheckResponse Pydantic model includes epistemological_signals field."""
    cr = CheckResponse()
    dump = cr.model_dump()
    assert "epistemological_signals" in dump
    assert dump["epistemological_signals"] == []
