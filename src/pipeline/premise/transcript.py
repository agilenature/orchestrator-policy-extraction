"""Backward JSONL scanner for extracting assistant text from Claude Code transcripts.

Provides efficient backward reading from JSONL session files to extract the most
recent assistant text blocks and count validation-class tool calls. Designed for
the PAG PreToolUse hook which needs to find PREMISE declarations in the AI's
recent output without reading the full transcript.

Performance target: <5ms for 50 lines of a 14MB file.

Exports:
    read_recent_assistant_text: Extract recent assistant text blocks
    count_validation_calls_since_last_user: Count Read/Grep/Glob/WebFetch calls
"""

from __future__ import annotations

import json
from pathlib import Path


# Validation-class tools (produce evidence, don't mutate state)
VALIDATION_TOOLS = frozenset({"Read", "Grep", "Glob", "WebFetch"})


def read_recent_assistant_text(
    transcript_path: str, max_lines: int = 50
) -> list[str]:
    """Read the most recent assistant text blocks from a JSONL transcript.

    Reads backward from EOF to find assistant entries with text content.
    Returns text strings in chronological order (oldest first from the
    scanned window).

    Args:
        transcript_path: Path to the Claude Code session JSONL file.
        max_lines: Maximum number of lines to read from the end of file.

    Returns:
        List of text strings from assistant entries, oldest first.
        Empty list if file not found, empty, or contains no assistant text.
    """
    path = Path(transcript_path)
    if not path.exists():
        return []

    try:
        file_size = path.stat().st_size
    except OSError:
        return []

    if file_size == 0:
        return []

    # Read backward from EOF: estimate ~2KB per line for chunk sizing
    chunk_size = min(file_size, max_lines * 2000)

    try:
        with open(path, "rb") as f:
            f.seek(max(0, file_size - chunk_size))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    lines = raw.strip().split("\n")[-max_lines:]

    texts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        if obj.get("type") != "assistant":
            continue

        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        texts.append(text)

    return texts


def count_validation_calls_since_last_user(
    transcript_path: str, max_lines: int = 200
) -> int:
    """Count validation-class tool calls since the last user message.

    Reads backward from EOF with a larger window. Scans lines in reverse
    chronological order. Counts assistant entries with tool_use content
    where the tool name is in {Read, Grep, Glob, WebFetch}. Stops counting
    when a user-type entry is encountered (the boundary).

    This implements the validation_calls_before_claim field for
    Ad Ignorantiam detection (RQR=0).

    Args:
        transcript_path: Path to the Claude Code session JSONL file.
        max_lines: Maximum number of lines to read from the end of file.

    Returns:
        Count of validation tool calls since last user message.
        0 if file not found, empty, or no validation calls found.
    """
    path = Path(transcript_path)
    if not path.exists():
        return 0

    try:
        file_size = path.stat().st_size
    except OSError:
        return 0

    if file_size == 0:
        return 0

    chunk_size = min(file_size, max_lines * 2000)

    try:
        with open(path, "rb") as f:
            f.seek(max(0, file_size - chunk_size))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return 0

    lines = raw.strip().split("\n")[-max_lines:]

    # Reverse to scan from most recent to oldest
    count = 0
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        entry_type = obj.get("type", "")

        # Stop at user boundary
        if entry_type == "user":
            break

        if entry_type != "assistant":
            continue

        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_name = item.get("name", "")
                    if tool_name in VALIDATION_TOOLS:
                        count += 1

    return count
