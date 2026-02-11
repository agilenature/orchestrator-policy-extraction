"""DuckDB-based JSONL loading and normalization for Claude Code session files.

Uses DuckDB's native read_json_auto() to load JSONL files directly into
queryable tables -- no Python line-by-line parsing. Python transforms the
DuckDB query results into CanonicalEvent objects.

Critical actor identification (Pitfall 1 from research):
- type='assistant' -> actor='executor'
- type='user' AND no tool_result blocks AND isMeta is not true -> actor='human_orchestrator'
- type='user' AND content contains tool_result blocks -> actor='tool'
- type='user' AND isMeta=true -> actor='system'
- type='system' -> actor='system'

Filters out irrelevant record types: progress, file-history-snapshot, queue-operation.

Exports:
    load_jsonl_to_duckdb: Load a JSONL file into DuckDB via read_json_auto()
    normalize_jsonl_events: Transform raw records into CanonicalEvent instances
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
from loguru import logger

from src.pipeline.models.events import CanonicalEvent


# Regex to extract commit hashes from git commit output
# Matches: [branch hash] or [branch (root-commit) hash]
GIT_COMMIT_PATTERN = re.compile(r"\[[\w/.()-]+\s+([0-9a-f]{7,40})\]")

# Record types to skip (irrelevant to pipeline, ~45% of records)
SKIP_TYPES = {"progress", "file-history-snapshot", "queue-operation"}


def load_jsonl_to_duckdb(
    conn: duckdb.DuckDBPyConnection,
    jsonl_path: str | Path,
    session_id: str,
) -> int:
    """Load a Claude Code JSONL file into DuckDB using read_json_auto().

    Uses DuckDB's native JSONL parser (not Python line-by-line parsing).
    The raw records are stored in a 'raw_records' table for subsequent
    querying and normalization.

    Args:
        conn: DuckDB connection to load data into.
        jsonl_path: Path to the JSONL session file.
        session_id: Session identifier (typically from filename UUID).

    Returns:
        Count of raw records loaded.

    Raises:
        FileNotFoundError: If the JSONL file does not exist.
        duckdb.Error: If DuckDB fails to parse the JSONL file.
    """
    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

    logger.info("Loading JSONL file via DuckDB read_json_auto: {}", jsonl_path.name)

    # Use DuckDB's native JSONL reader with union_by_name to handle
    # heterogeneous record schemas across line types
    conn.execute(
        """
        CREATE OR REPLACE TABLE raw_records AS
        SELECT *, ? AS _session_id
        FROM read_json_auto(
            ?,
            format='newline_delimited',
            union_by_name=true
        )
        """,
        [session_id, str(jsonl_path)],
    )

    count = conn.execute("SELECT count(*) FROM raw_records").fetchone()[0]
    logger.info("Loaded {} raw records from {}", count, jsonl_path.name)

    return count


def normalize_jsonl_events(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> list[CanonicalEvent]:
    """Transform raw DuckDB records into canonical events.

    Queries the raw_records table (created by load_jsonl_to_duckdb),
    filters out irrelevant types, identifies actors correctly, and
    produces CanonicalEvent instances.

    DuckDB handles the JSONL file I/O; Python transforms the in-memory
    query results into typed CanonicalEvent objects.

    Args:
        conn: DuckDB connection with raw_records table populated.
        session_id: Session identifier for event ID generation.

    Returns:
        List of CanonicalEvent instances, one per meaningful content block.
    """
    # Discover which columns exist in raw_records -- JSONL files have
    # heterogeneous schemas, so some columns may be absent in small files
    existing_cols = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'raw_records'"
        ).fetchall()
    }

    # Build SELECT with fallback NULLs for missing columns
    desired_columns = [
        ("type", "type"),
        ("uuid", "uuid"),
        ('"timestamp"', "timestamp"),
        ("parentUuid", "parentUuid"),
        ("isSidechain", "isSidechain"),
        ("isMeta", "isMeta"),
        ("message", "message"),
        ("toolUseResult", "toolUseResult"),
        ("sourceToolAssistantUUID", "sourceToolAssistantUUID"),
        ("subtype", "subtype"),
        ("durationMs", "durationMs"),
        ("sessionId", "sessionId"),
        ("_session_id", "_session_id"),
    ]

    select_parts = []
    for col_expr, col_name in desired_columns:
        # Strip quotes for existence check
        bare_name = col_name
        if bare_name in existing_cols:
            select_parts.append(f'{col_expr} AS "{col_name}"')
        else:
            select_parts.append(f'NULL AS "{col_name}"')

    select_clause = ", ".join(select_parts)

    # Build WHERE clause with available columns
    where_parts = ["type NOT IN ('progress', 'file-history-snapshot', 'queue-operation')"]
    if "isSidechain" in existing_cols:
        where_parts.append("(isSidechain IS NULL OR isSidechain = false)")

    where_clause = " AND ".join(where_parts)

    # Order by timestamp if available
    order_clause = 'ORDER BY "timestamp" ASC NULLS LAST' if "timestamp" in existing_cols else ""

    query = f"SELECT {select_clause} FROM raw_records WHERE {where_clause} {order_clause}"

    rows = conn.execute(query).fetchall()

    column_names = [col_name for _, col_name in desired_columns]

    events: list[CanonicalEvent] = []

    for row in rows:
        record = dict(zip(column_names, row))
        try:
            new_events = _parse_record(record, session_id)
            events.extend(new_events)
        except Exception as e:
            logger.warning(
                "Failed to parse record uuid={}: {}",
                record.get("uuid", "?"),
                e,
            )

    logger.info(
        "Normalized {} canonical events from {} filtered records",
        len(events),
        len(rows),
    )

    return events


def _parse_record(record: dict[str, Any], session_id: str) -> list[CanonicalEvent]:
    """Parse a single raw record into one or more CanonicalEvent instances.

    Assistant messages with multiple content blocks (thinking, text, tool_use)
    produce separate events per block. Other record types produce one event.
    """
    rec_type = record.get("type")

    if rec_type == "assistant":
        return _parse_assistant(record, session_id)
    elif rec_type == "user":
        return _parse_user(record, session_id)
    elif rec_type == "system":
        return _parse_system(record, session_id)
    else:
        logger.debug("Skipping unknown record type: {}", rec_type)
        return []


def _parse_assistant(record: dict[str, Any], session_id: str) -> list[CanonicalEvent]:
    """Parse an assistant record into events (one per content block).

    A single assistant JSONL record may have content blocks like
    [thinking, text, tool_use]. Each block produces a separate
    CanonicalEvent with uuid+"_N" for uniqueness.
    """
    message = _get_message_dict(record.get("message"))
    content_blocks = message.get("content", [])
    if not isinstance(content_blocks, list):
        content_blocks = []

    ts = _parse_timestamp(record.get("timestamp"))
    uuid_base = str(record.get("uuid", ""))
    parent_uuid = _str_or_none(record.get("parentUuid"))

    events: list[CanonicalEvent] = []

    for idx, block in enumerate(content_blocks):
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")
        turn_id = f"{uuid_base}_{idx}" if len(content_blocks) > 1 else uuid_base

        if block_type == "thinking":
            event_type = "assistant_thinking"
            text = block.get("thinking", "")
            payload = {
                "common": {"text": "", "reasoning": text},
                "details": {},
            }
        elif block_type == "text":
            event_type = "assistant_text"
            text = block.get("text", "")
            payload = {
                "common": {"text": text},
                "details": {},
            }
        elif block_type == "tool_use":
            event_type = "tool_use"
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})
            tool_id = block.get("id", "")

            # Extract command text for Bash-type tools
            command_text = ""
            if isinstance(tool_input, dict):
                command_text = tool_input.get("command", "") or tool_input.get(
                    "description", ""
                )

            # Extract files_touched from tool input
            files_touched = _extract_files_from_tool_input(tool_name, tool_input)

            payload = {
                "common": {
                    "text": command_text,
                    "tool_name": tool_name,
                    "files_touched": files_touched,
                },
                "details": {
                    "tool_use_id": tool_id,
                    "tool_input": _safe_serialize(tool_input),
                },
            }
        else:
            logger.debug("Skipping unknown assistant block type: {}", block_type)
            continue

        links: dict[str, Any] = {}
        if parent_uuid:
            links["parent_uuid"] = parent_uuid

        event_id = CanonicalEvent.make_event_id(
            source_system="claude_jsonl",
            session_id=session_id,
            turn_id=turn_id,
            ts_utc=ts.isoformat(),
            actor="executor",
            event_type=event_type,
        )

        events.append(
            CanonicalEvent(
                event_id=event_id,
                ts_utc=ts,
                session_id=session_id,
                actor="executor",
                event_type=event_type,
                payload=payload,
                links=links,
                source_system="claude_jsonl",
                source_ref=f"{session_id}:{uuid_base}",
            )
        )

    return events


def _parse_user(record: dict[str, Any], session_id: str) -> list[CanonicalEvent]:
    """Parse a user record, correctly identifying actor subtype.

    Critical distinction (Pitfall 1):
    - isMeta=true -> system (skip or tag as metadata)
    - content contains tool_result blocks -> tool
    - otherwise -> human_orchestrator
    """
    is_meta = record.get("isMeta")
    message = _get_message_dict(record.get("message"))
    content = message.get("content")
    ts = _parse_timestamp(record.get("timestamp"))
    uuid = str(record.get("uuid", ""))
    parent_uuid = _str_or_none(record.get("parentUuid"))
    source_tool_uuid = _str_or_none(record.get("sourceToolAssistantUUID"))

    # Check if content is a list with tool_result blocks
    has_tool_result = False
    tool_result_blocks: list[dict] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                has_tool_result = True
                tool_result_blocks.append(block)

    # Determine actor (Pitfall 1 from research)
    if is_meta is True:
        actor = "system"
        event_type = "system_event"
        text = _extract_text_content(content)
        payload = {
            "common": {"text": text},
            "details": {"is_meta": True},
        }
    elif has_tool_result:
        actor = "tool"
        event_type = "tool_result"

        # Extract tool result content
        tool_use_result = record.get("toolUseResult")
        stdout = ""
        stderr = ""
        is_error = False

        if isinstance(tool_use_result, dict):
            stdout = tool_use_result.get("stdout", "") or ""
            stderr = tool_use_result.get("stderr", "") or ""
        elif isinstance(tool_use_result, str):
            # Sometimes DuckDB returns it as a JSON string
            try:
                parsed = json.loads(tool_use_result)
                if isinstance(parsed, dict):
                    stdout = parsed.get("stdout", "") or ""
                    stderr = parsed.get("stderr", "") or ""
            except (json.JSONDecodeError, TypeError):
                stdout = tool_use_result

        # Get tool_use_id and error status from content blocks
        tool_use_id = ""
        result_text = ""
        for block in tool_result_blocks:
            tool_use_id = block.get("tool_use_id", "") or ""
            block_content = block.get("content", "")
            if isinstance(block_content, str):
                result_text = block_content
            elif isinstance(block_content, list):
                # Sometimes content is a list of content parts
                for part in block_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        result_text += part.get("text", "")
                    elif isinstance(part, str):
                        result_text += part
            is_error = block.get("is_error", False) or False

        # Use stdout if result_text is short/empty
        display_text = stdout if len(stdout) > len(result_text) else result_text

        # Extract commit hash from git output
        commit_hash = _extract_commit_hash(display_text)

        payload = {
            "common": {
                "text": display_text,
                "error_message": stderr if stderr else None,
            },
            "details": {
                "tool_use_id": tool_use_id,
                "is_error": is_error,
                "stdout": stdout,
                "stderr": stderr,
            },
        }

        links: dict[str, Any] = {}
        if parent_uuid:
            links["parent_uuid"] = parent_uuid
        if tool_use_id:
            links["tool_use_id"] = tool_use_id
        if source_tool_uuid:
            links["source_tool_uuid"] = source_tool_uuid
        if commit_hash:
            links["commit_hash"] = commit_hash

        event_id = CanonicalEvent.make_event_id(
            source_system="claude_jsonl",
            session_id=session_id,
            turn_id=uuid,
            ts_utc=ts.isoformat(),
            actor=actor,
            event_type=event_type,
        )

        return [
            CanonicalEvent(
                event_id=event_id,
                ts_utc=ts,
                session_id=session_id,
                actor=actor,
                event_type=event_type,
                payload=payload,
                links=links,
                source_system="claude_jsonl",
                source_ref=f"{session_id}:{uuid}",
            )
        ]
    else:
        actor = "human_orchestrator"
        event_type = "user_msg"
        text = _extract_text_content(content)
        payload = {
            "common": {"text": text},
            "details": {},
        }

    links = {}
    if parent_uuid:
        links["parent_uuid"] = parent_uuid

    event_id = CanonicalEvent.make_event_id(
        source_system="claude_jsonl",
        session_id=session_id,
        turn_id=uuid,
        ts_utc=ts.isoformat(),
        actor=actor,
        event_type=event_type,
    )

    return [
        CanonicalEvent(
            event_id=event_id,
            ts_utc=ts,
            session_id=session_id,
            actor=actor,
            event_type=event_type,
            payload=payload,
            links=links,
            source_system="claude_jsonl",
            source_ref=f"{session_id}:{uuid}",
        )
    ]


def _parse_system(record: dict[str, Any], session_id: str) -> list[CanonicalEvent]:
    """Parse a system record (turn_duration, compact_boundary, etc.)."""
    ts = _parse_timestamp(record.get("timestamp"))
    uuid = str(record.get("uuid", ""))
    parent_uuid = _str_or_none(record.get("parentUuid"))
    subtype = record.get("subtype", "")
    duration_ms = record.get("durationMs")

    payload: dict[str, Any] = {
        "common": {
            "text": f"system:{subtype}",
            "duration_ms": duration_ms,
        },
        "details": {
            "subtype": subtype,
        },
    }

    links: dict[str, Any] = {}
    if parent_uuid:
        links["parent_uuid"] = parent_uuid

    event_id = CanonicalEvent.make_event_id(
        source_system="claude_jsonl",
        session_id=session_id,
        turn_id=uuid,
        ts_utc=ts.isoformat(),
        actor="system",
        event_type="system_event",
    )

    return [
        CanonicalEvent(
            event_id=event_id,
            ts_utc=ts,
            session_id=session_id,
            actor="system",
            event_type="system_event",
            payload=payload,
            links=links,
            source_system="claude_jsonl",
            source_ref=f"{session_id}:{uuid}",
        )
    ]


# --- Helper functions ---


def _get_message_dict(message: Any) -> dict:
    """Extract message as a dict, handling DuckDB STRUCT types.

    DuckDB returns nested structs as Python dicts or named tuples.
    This normalizes them to plain dicts.

    IMPORTANT: DuckDB's union_by_name schema unification may return
    message.content as a JSON string (not a parsed list) because the
    content field is heterogeneous across record types (string for user
    messages, array of objects for assistant messages). We detect this
    and parse the JSON string back into a Python list.
    """
    if message is None:
        return {}
    if isinstance(message, dict):
        result = dict(message)
    else:
        # DuckDB struct types -- convert to dict
        try:
            result = dict(message)
        except (TypeError, ValueError):
            try:
                if hasattr(message, "_asdict"):
                    result = message._asdict()
                else:
                    return {}
            except Exception:
                return {}

    # DuckDB may return content as a JSON string due to union_by_name
    # schema unification. Parse it back to Python objects if needed.
    content = result.get("content")
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            result["content"] = parsed
        except (json.JSONDecodeError, TypeError):
            pass  # Keep as string (likely a user text message)

    return result


def _parse_timestamp(ts: Any) -> datetime:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime.

    Handles the format used by Claude Code: '2026-02-10T23:29:13.335Z'
    Falls back to current UTC time if parsing fails.
    """
    if ts is None:
        logger.debug("Missing timestamp, using current UTC time")
        return datetime.now(timezone.utc)

    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts

    ts_str = str(ts)
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.warning("Failed to parse timestamp '{}', using current UTC", ts_str)
        return datetime.now(timezone.utc)


def _str_or_none(value: Any) -> str | None:
    """Convert a value to string or None, handling UUID objects from DuckDB."""
    if value is None:
        return None
    return str(value)


def _extract_text_content(content: Any) -> str:
    """Extract text from message content (string or list of content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "") or block.get("content", "")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content else ""


def _extract_commit_hash(text: str) -> str | None:
    """Extract a git commit hash from command output.

    Matches patterns like: [main ccd6533] Initial commit...
    Also handles: [main (root-commit) ccd6533] ...
    """
    if not text:
        return None
    match = GIT_COMMIT_PATTERN.search(text)
    return match.group(1) if match else None


def _extract_files_from_tool_input(
    tool_name: str, tool_input: Any
) -> list[str]:
    """Extract file paths from tool input based on tool type."""
    if not isinstance(tool_input, dict):
        return []

    files = []
    # Read, Write, Edit tools have file_path
    file_path = tool_input.get("file_path")
    if file_path:
        files.append(str(file_path))
    # Glob tool has pattern
    # Grep tool has path
    path = tool_input.get("path")
    if path and tool_name in ("Grep", "Glob"):
        files.append(str(path))

    return files


def _safe_serialize(obj: Any) -> Any:
    """Make an object JSON-serializable by converting non-standard types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    # Fallback for DuckDB types, UUIDs, etc.
    return str(obj)
