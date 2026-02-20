#!/usr/bin/env python3
"""Extract escalation fixture slices from DuckDB (data/ope.db) into JSONL files.

One-off script for plan 09-05: extracts real O_CORR->T_RISKY and O_CORR->T_GIT_COMMIT
event sequences from the objectivism session database into minimal JSONL fixture files
used by tests/test_escalation_real_fixtures.py.

Provenance: Each output JSONL file includes comment headers documenting the session_id,
block/bypass event_ids, extraction date, and the DuckDB query used.

Usage:
    python scripts/extract_escalation_fixtures.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

# --- Configuration ---

DB_PATH = Path("data/ope.db")
FIXTURE_DIR = Path("tests/fixtures/escalation")
MAX_TEXT_LEN = 200

# Sequences to extract: (fixture_filename, session_id, block_event_id, bypass_event_id)
SEQUENCES = [
    {
        "filename": "session_01695e90_ocorr_trisky.jsonl",
        "session_id": "01695e90-4f8b-43a8-9104-2c64c2c39058",
        "block_event_id": "cd8a4ddb45e9ec7e",
        "bypass_event_id": "cf50a94e03b14f4e",
        "description": "O_CORR -> T_RISKY at gap=10 events (5 non-exempt: assistant_text + tool_results from Read calls)",
    },
    {
        "filename": "session_0326bf5e_ocorr_trisky.jsonl",
        "session_id": "0326bf5e-ec3e-4888-b5fd-26f169c63523",
        "block_event_id": "f25edf2c30e8e956",
        "bypass_event_id": "6d8e58aabf17cd24",
        "description": "O_CORR -> T_RISKY at gap=9 events (mostly Read exempt, 1 non-exempt assistant_text + tool_results)",
    },
    {
        "filename": "session_1cf6d12f_ocorr_tgitcommit.jsonl",
        "session_id": "1cf6d12f-aa46-4eb8-aeb2-b0511cde339f",
        "block_event_id": "840d0c5afa82aca9",
        "bypass_event_id": "4a59693a49eb49ae",
        "description": "O_CORR -> T_GIT_COMMIT via Edit then Bash. Intermediate events include Read (exempt) and Edit (non-exempt, bypass-eligible -- detector matches Edit first).",
    },
    {
        "filename": "session_1cf6d12f_ocorr_trisky.jsonl",
        "session_id": "1cf6d12f-aa46-4eb8-aeb2-b0511cde339f",
        "block_event_id": "9f8886ac044c6076",
        "bypass_event_id": "263b105bfa2d7b72",
        "description": "O_CORR -> T_RISKY with 18 non-exempt events intervening. With default window_turns=5 the window expires; requires window_turns>=19 to detect.",
    },
    {
        "filename": "session_0e3cf9a0_window_expired.jsonl",
        "session_id": "0e3cf9a0-abc2-4b7e-9e3b-01960517df77",
        "block_event_id": "f68c16da1695e054",
        "bypass_event_id": "aae5c9e0e979656f",
        "description": "Negative fixture: O_CORR -> T_RISKY with ~14 non-exempt events. Window expires with default window_turns=5.",
    },
]

# DuckDB query template for extracting an event slice
QUERY = """
    SELECT
        event_id,
        ts_utc,
        session_id,
        actor,
        event_type,
        primary_tag,
        primary_tag_confidence,
        secondary_tags,
        payload,
        links,
        risk_score,
        risk_factors,
        source_system,
        source_ref
    FROM events
    WHERE session_id = $1
    ORDER BY ts_utc
"""


def truncate_text(text: str, max_len: int = MAX_TEXT_LEN) -> str:
    """Truncate text to max_len chars, appending '[...truncated]' if truncated."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "[...truncated]"


def parse_json_column(value: str | None) -> dict | list:
    """Parse a JSON string column from DuckDB into a Python object."""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def format_timestamp(ts) -> str:
    """Convert a DuckDB timestamp to ISO 8601 string."""
    if ts is None:
        return ""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return str(ts)


def build_event_dict(row: tuple) -> dict:
    """Build a JSONL-ready event dict from a DuckDB row."""
    (
        event_id, ts_utc, session_id, actor, event_type,
        primary_tag, primary_tag_confidence, secondary_tags,
        payload, links, risk_score, risk_factors,
        source_system, source_ref,
    ) = row

    # Parse JSON columns
    payload_dict = parse_json_column(payload)
    secondary_tags_list = parse_json_column(secondary_tags)
    links_dict = parse_json_column(links)
    risk_factors_list = parse_json_column(risk_factors)

    if not isinstance(secondary_tags_list, list):
        secondary_tags_list = []
    if not isinstance(links_dict, dict):
        links_dict = {}
    if not isinstance(risk_factors_list, list):
        risk_factors_list = []

    # Truncate payload text but preserve tool_name and file_path
    common = payload_dict.get("common", {})
    if isinstance(common, dict):
        text = common.get("text", "")
        if isinstance(text, str):
            common["text"] = truncate_text(text)

    # Preserve details.file_path if present
    details = payload_dict.get("details", {})
    if isinstance(details, dict):
        # Keep file_path as-is
        pass

    return {
        "event_id": event_id,
        "ts_utc": format_timestamp(ts_utc),
        "session_id": session_id,
        "actor": actor,
        "event_type": event_type,
        "primary_tag": primary_tag or "",
        "primary_tag_confidence": float(primary_tag_confidence) if primary_tag_confidence is not None else 0.0,
        "secondary_tags": secondary_tags_list,
        "payload": payload_dict,
        "links": links_dict,
        "risk_score": float(risk_score) if risk_score is not None else 0.0,
        "risk_factors": risk_factors_list,
        "source_system": source_system or "claude_jsonl",
        "source_ref": "extracted_from_ope_db",
    }


def extract_slice(
    con: duckdb.DuckDBPyConnection,
    session_id: str,
    block_event_id: str,
    bypass_event_id: str,
) -> list[dict]:
    """Extract event slice from block_event through bypass_event + 1 event after.

    Returns list of event dicts in timestamp order.
    """
    rows = con.execute(QUERY, [session_id]).fetchall()

    # Find indices
    block_idx = None
    bypass_idx = None
    for i, row in enumerate(rows):
        if row[0] == block_event_id:
            block_idx = i
        if row[0] == bypass_event_id:
            bypass_idx = i

    if block_idx is None:
        raise ValueError(f"Block event {block_event_id} not found in session {session_id}")
    if bypass_idx is None:
        raise ValueError(f"Bypass event {bypass_event_id} not found in session {session_id}")

    # Extract: 1 event before O_CORR through bypass + 1 event after
    start = max(0, block_idx - 1)
    end = min(len(rows) - 1, bypass_idx + 1)

    return [build_event_dict(rows[i]) for i in range(start, end + 1)]


def write_fixture(
    filepath: Path,
    events: list[dict],
    seq: dict,
    extraction_date: str,
) -> None:
    """Write events to a JSONL file with provenance comments."""
    with open(filepath, "w") as f:
        # Provenance header
        f.write(f"# Escalation fixture extracted from data/ope.db\n")
        f.write(f"# Session: {seq['session_id']}\n")
        f.write(f"# Block event (O_CORR): {seq['block_event_id']}\n")
        f.write(f"# Bypass event: {seq['bypass_event_id']}\n")
        f.write(f"# Description: {seq['description']}\n")
        f.write(f"# Extraction date: {extraction_date}\n")
        f.write(f"# Query: SELECT ... FROM events WHERE session_id = '{seq['session_id']}' ORDER BY ts_utc\n")
        f.write(f"# Slice: block_event - 1 event through bypass_event + 1 event\n")
        f.write(f"# Payload text truncated to {MAX_TEXT_LEN} chars\n")

        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def main() -> None:
    """Extract all escalation fixture slices."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    extraction_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    con = duckdb.connect(str(DB_PATH), read_only=True)

    for seq in SEQUENCES:
        filepath = FIXTURE_DIR / seq["filename"]
        print(f"Extracting {seq['filename']}...")

        events = extract_slice(
            con,
            seq["session_id"],
            seq["block_event_id"],
            seq["bypass_event_id"],
        )
        write_fixture(filepath, events, seq, extraction_date)
        print(f"  -> {len(events)} events written to {filepath}")

    con.close()
    print(f"\nDone. {len(SEQUENCES)} fixtures written to {FIXTURE_DIR}/")


if __name__ == "__main__":
    main()
