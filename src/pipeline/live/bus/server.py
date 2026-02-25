"""Starlette server for the OPE Governance Bus.

Exposes three session-facing endpoints over a Unix socket:
- POST /api/register   — register a session with session_id + run_id
- POST /api/deregister — mark a session as deregistered
- POST /api/check      — return active constraints and interventions

The server fails open: DuckDB write failures return 200 with empty
payload, never 500. Sessions must never be blocked by bus errors.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import duckdb
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .models import CheckResponse
from .schema import create_bus_schema
from ..governor.daemon import GovernorDaemon

SOCKET_PATH = os.environ.get("OPE_BUS_SOCKET", "/tmp/ope-governance-bus.sock")


def create_app(
    db_path: str = "data/ope.db",
    daemon: object | None = None,
) -> Starlette:
    """Create the Governance Bus Starlette application.

    Args:
        db_path: Path to DuckDB database file.
        daemon: Optional GovernorDaemon instance. If None, a default
               GovernorDaemon is created that reads constraints.json.

    Returns:
        Configured Starlette app with /api/register, /api/deregister,
        /api/check routes.
    """
    conn = duckdb.connect(db_path)
    create_bus_schema(conn)

    _daemon = daemon if daemon is not None else GovernorDaemon(db_path=db_path)

    async def register(request: Request) -> JSONResponse:
        """Register a session on the governance bus.

        Reads body once, then uses cached result in error handling.
        Fails open: malformed body or DuckDB error returns 200.
        """
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({
                "status": "registered",
                "session_id": "",
                "run_id": "",
            })

        session_id = body.get("session_id", "")
        run_id = body.get("run_id", session_id)  # fallback for pre-OpenClaw
        repo = body.get("repo", None)
        project_dir = body.get("project_dir", None)
        transcript_path = body.get("transcript_path", None)

        try:
            conn.execute(
                "INSERT OR REPLACE INTO bus_sessions "
                "(session_id, run_id, registered_at, repo, project_dir, transcript_path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [session_id, run_id, datetime.now(timezone.utc).isoformat(),
                 repo, project_dir, transcript_path],
            )
        except Exception:
            pass  # Fail open: DuckDB error does not block session

        return JSONResponse({
            "status": "registered",
            "session_id": session_id,
            "run_id": run_id,
            "repo": repo,
        })

    async def deregister(request: Request) -> JSONResponse:
        """Deregister a session from the governance bus."""
        try:
            body = await request.json()
            session_id = body.get("session_id", "")
            event_count = body.get("event_count", None)
            outcome = body.get("outcome", None)
            conn.execute(
                "UPDATE bus_sessions SET status='deregistered', "
                "last_seen_at=?, event_count=?, outcome=? WHERE session_id=?",
                [datetime.now(timezone.utc).isoformat(),
                 event_count, outcome, session_id],
            )
        except Exception:
            pass  # Fail open
        return JSONResponse({"status": "deregistered"})

    async def check(request: Request) -> JSONResponse:
        """Check for active constraints and interventions.

        Calls the GovernorDaemon to read active constraints from
        constraints.json and return a severity-ordered briefing.
        Fails open: any error returns empty constraints/interventions.
        """
        try:
            body = await request.json()
            briefing = _daemon.get_briefing(
                body.get("session_id", ""),
                body.get("run_id", ""),
                repo=body.get("repo", None),
            )
            return JSONResponse({
                "constraints": briefing.constraints,
                "interventions": briefing.interventions,
                "epistemological_signals": [],
            })
        except Exception:
            return JSONResponse(CheckResponse().model_dump())

    async def push_link(request: Request) -> JSONResponse:
        """Accept and persist a causal push link to the push_links table.

        Required: parent_decision_id, child_decision_id, transition_trigger,
        migration_run_id. Optional: link_id (auto-generated if absent),
        repo_boundary, captured_at. Fails open: DuckDB write errors return
        200 with warning. Returns 400 only for missing required fields.
        """
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"status": "error", "detail": "invalid JSON body"},
                status_code=400,
            )

        required = [
            "parent_decision_id",
            "child_decision_id",
            "transition_trigger",
            "migration_run_id",
        ]
        missing = [f for f in required if not body.get(f)]
        if missing:
            return JSONResponse(
                {
                    "status": "error",
                    "detail": f"missing required fields: {', '.join(missing)}",
                },
                status_code=400,
            )

        parent_id = body["parent_decision_id"]
        child_id = body["child_decision_id"]
        trigger = body["transition_trigger"]
        run_id = body["migration_run_id"]
        repo_boundary = body.get("repo_boundary", None)

        link_id = body.get("link_id", "")
        if not link_id:
            raw = f"link:{parent_id}:{child_id}:{trigger}"
            link_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

        captured_at = body.get(
            "captured_at", datetime.now(timezone.utc).isoformat()
        )

        try:
            conn.execute(
                "INSERT OR REPLACE INTO push_links "
                "(link_id, parent_decision_id, child_decision_id, "
                "transition_trigger, repo_boundary, migration_run_id, "
                "captured_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    link_id,
                    parent_id,
                    child_id,
                    trigger,
                    repo_boundary,
                    run_id,
                    captured_at,
                ],
            )
        except Exception:
            return JSONResponse({
                "status": "accepted",
                "link_id": link_id,
                "warning": "push link accepted but DuckDB write failed",
            })

        return JSONResponse({"status": "accepted", "link_id": link_id})

    return Starlette(routes=[
        Route("/api/register", register, methods=["POST"]),
        Route("/api/deregister", deregister, methods=["POST"]),
        Route("/api/check", check, methods=["POST"]),
        Route("/api/push-link", push_link, methods=["POST"]),
    ])
