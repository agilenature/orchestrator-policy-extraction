"""Starlette server for the OPE Governance Bus.

Exposes three session-facing endpoints over a Unix socket:
- POST /api/register   — register a session with session_id + run_id
- POST /api/deregister — mark a session as deregistered
- POST /api/check      — return active constraints and interventions

The server fails open: DuckDB write failures return 200 with empty
payload, never 500. Sessions must never be blocked by bus errors.
"""

from __future__ import annotations

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

        try:
            conn.execute(
                "INSERT OR REPLACE INTO bus_sessions "
                "(session_id, run_id, registered_at) VALUES (?, ?, ?)",
                [session_id, run_id, datetime.now(timezone.utc).isoformat()],
            )
        except Exception:
            pass  # Fail open: DuckDB error does not block session

        return JSONResponse({
            "status": "registered",
            "session_id": session_id,
            "run_id": run_id,
        })

    async def deregister(request: Request) -> JSONResponse:
        """Deregister a session from the governance bus."""
        try:
            body = await request.json()
            session_id = body.get("session_id", "")
            conn.execute(
                "UPDATE bus_sessions SET status='deregistered', "
                "last_seen_at=? WHERE session_id=?",
                [datetime.now(timezone.utc).isoformat(), session_id],
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
            )
            return JSONResponse({
                "constraints": briefing.constraints,
                "interventions": briefing.interventions,
            })
        except Exception:
            return JSONResponse(CheckResponse().model_dump())

    return Starlette(routes=[
        Route("/api/register", register, methods=["POST"]),
        Route("/api/deregister", deregister, methods=["POST"]),
        Route("/api/check", check, methods=["POST"]),
    ])
