#!/usr/bin/env python3
"""SessionStart hook -- OPE Control Plane Integration.

Called by Claude Code at session start. Registers with the OPE Governance Bus
and writes a constraint briefing to stdout (user-visible channel).

Always exits 0 (fail-open). Bus unavailability is not a session blocker.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
from datetime import datetime, timezone

_BUS_SOCKET = os.environ.get("OPE_BUS_SOCKET", "/tmp/ope-governance-bus.sock")
_OPE_RUN_ID = os.environ.get("OPE_RUN_ID", "")
_OPE_SESSION_ID = os.environ.get("OPE_SESSION_ID", "")


def _post_json(path: str, payload: dict) -> dict:
    """POST JSON to bus over Unix socket. Returns response or {} on error."""
    try:
        body = json.dumps(payload).encode()
        conn = http.client.HTTPConnection("localhost", timeout=1.0)
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.settimeout(1.0)
        conn.sock.connect(_BUS_SOCKET)
        conn.request("POST", path, body=body,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        return json.loads(resp.read())
    except Exception:
        return {}


def main() -> None:
    """Register with bus and print constraint briefing to stdout."""
    session_id = _OPE_SESSION_ID or f"session-{datetime.now(timezone.utc).isoformat()}"
    run_id = _OPE_RUN_ID or session_id  # fallback pre-OpenClaw

    # Register with bus
    _post_json("/api/register", {"session_id": session_id, "run_id": run_id})

    # Get constraint briefing
    check = _post_json("/api/check", {
        "session_id": session_id,
        "run_id": run_id,
        "premise_data": {},
    })

    constraints = check.get("constraints", [])
    if constraints:
        count = len(constraints)
        print(f"\n[OPE] {count} active constraint(s) for this session.", flush=True)
        forbidden = [c for c in constraints if c.get("severity") == "forbidden"]
        if forbidden:
            print(
                f"[OPE] {len(forbidden)} FORBIDDEN constraint(s) in scope:",
                flush=True,
            )
            for c in forbidden[:3]:
                print(
                    f"[OPE]   - {c.get('text', c.get('id', ''))[:80]}",
                    flush=True,
                )
    # else: bus unavailable or no constraints -- silent


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open always
    sys.exit(0)
