#!/usr/bin/env python3
"""SessionStart hook -- OPE Control Plane Integration.

Called by Claude Code at session start. Registers with the OPE Governance Bus
and writes a constraint briefing to stdout (user-visible channel).

Always exits 0 (fail-open). Bus unavailability is not a session blocker.
When the bus is unreachable, emits BUS_REGISTRATION_FAILED to the session
events staging JSONL so the governing orchestrator can identify sessions
with degraded causal chain coverage.
"""
from __future__ import annotations

import http.client
import json
import os
import pathlib
import socket
import sys
from datetime import datetime, timezone

_BUS_SOCKET = os.environ.get("OPE_BUS_SOCKET", "/tmp/ope-governance-bus.sock")
_OPE_RUN_ID = os.environ.get("OPE_RUN_ID", "")
_OPE_SESSION_ID = os.environ.get("OPE_SESSION_ID", "")
_OPE_REPO = os.environ.get("OPE_REPO", "")
_OPE_PROJECT_DIR = os.environ.get("OPE_PROJECT_DIR", "")
_OPE_TRANSCRIPT_PATH = os.environ.get("OPE_TRANSCRIPT_PATH", "")
_STAGING_PATH = os.environ.get(
    "OPE_SESSION_STAGING_PATH", "data/session_events_staging.jsonl"
)


def _append_event_to_staging(event: dict) -> None:
    """Append a governance event to the session events staging JSONL file.

    Lightweight: no external imports, no file locking (hook runs once per
    session).  Creates parent directory if needed.
    """
    try:
        path = pathlib.Path(_STAGING_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass  # fail-open: event write failure does not block session


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
    openclaw_unavailable = not bool(_OPE_RUN_ID)

    # Build register payload with optional metadata fields
    register_payload: dict = {"session_id": session_id, "run_id": run_id}
    if openclaw_unavailable:
        register_payload["openclaw_unavailable"] = True
    if _OPE_REPO:
        register_payload["repo"] = _OPE_REPO
    if _OPE_PROJECT_DIR:
        register_payload["project_dir"] = _OPE_PROJECT_DIR
    if _OPE_TRANSCRIPT_PATH:
        register_payload["transcript_path"] = _OPE_TRANSCRIPT_PATH

    # Register with bus
    result = _post_json("/api/register", register_payload)

    # Emit BUS_REGISTRATION_FAILED when bus is unreachable
    if not result:
        _append_event_to_staging({
            "event_type": "BUS_REGISTRATION_FAILED",
            "session_id": session_id,
            "run_id": run_id,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "openclaw_unavailable": openclaw_unavailable,
        })

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

    # Relevant documentation (Phase 21)
    relevant_docs = check.get("relevant_docs", [])
    if relevant_docs:
        print(f"\n[OPE] {len(relevant_docs)} relevant doc(s) for this session:", flush=True)
        for doc in relevant_docs[:3]:
            path = doc.get("doc_path", "")
            axis = doc.get("ccd_axis", "")
            desc = doc.get("description_cache") or ""
            desc = desc[:80]
            print(f"[OPE]   - {path} (axis: {axis})", flush=True)
            if desc:
                print(f"[OPE]     {desc}", flush=True)
    # else: no docs -- silent

    # Genus hint (Phase 25)
    genus_count = check.get("genus_count", 0)
    if genus_count > 0:
        print(
            f"\n[OPE] GENUS: {genus_count} prior genera available "
            f"-- /genus-first before writing",
            flush=True,
        )
    # else: no genera -- silent


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open always
    sys.exit(0)
