"""Session scope extraction from event payloads.

Derives file paths touched during a session from tool call event payloads.
Supports Read/Edit/Write tools (file_path in payload.details) and Bash
commands (file path patterns in payload.common.text).

Exports:
    extract_session_scope
"""

from __future__ import annotations

import json
import re


# Compiled regex for file paths in Bash command text.
# Matches paths with at least one / and a file extension, or known source
# directory prefixes. Avoids matching URLs (http://, https://) and other
# non-file-path patterns.
_FILE_PATH_RE = re.compile(
    r"""(?<![a-zA-Z:])           # Not preceded by letter or colon (avoids http://)
    (?:                          # Two alternatives:
        (?:[a-zA-Z0-9_./-]+/    # Path with at least one /
         [a-zA-Z0-9_.-]+        # filename
         \.[a-zA-Z0-9]{1,10})   # extension (1-10 chars)
    |                            # OR
        (?:src|tests|lib|docs|config|data|scripts)  # known source dirs
        /[a-zA-Z0-9_./-]+       # rest of path
    )""",
    re.VERBOSE,
)


def _parse_payload(payload) -> dict:
    """Parse payload that may be a dict or JSON string.

    DuckDB may return payload as a JSON string. Handle both cases
    gracefully (same pattern as runner.py).

    Args:
        payload: Dict or JSON string payload.

    Returns:
        Parsed dict, or empty dict if parsing fails.
    """
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _normalize_path(path: str) -> str:
    """Normalize a file path for consistent comparison.

    Strips leading ./ and normalizes double slashes.

    Args:
        path: Raw file path string.

    Returns:
        Normalized path string.
    """
    # Strip leading ./
    while path.startswith("./"):
        path = path[2:]
    # Collapse double slashes
    while "//" in path:
        path = path.replace("//", "/")
    # Strip trailing /
    path = path.rstrip("/")
    return path


def extract_session_scope(events: list[dict]) -> list[str]:
    """Derive session scope paths from tool call event payloads.

    Extracts file paths from:
    - payload.details.file_path (Read/Edit/Write tools)
    - payload.common.text for Bash commands (regex for file paths)

    Empty result means repo-wide scope per locked decision 6.

    Args:
        events: List of event dicts with payload field.

    Returns:
        Sorted unique list of file paths, or [] if none found.
    """
    paths: set[str] = set()

    for event in events:
        payload = _parse_payload(event.get("payload"))
        if not payload:
            continue

        # Extract from details.file_path (Read/Edit/Write tools)
        details = payload.get("details")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (json.JSONDecodeError, TypeError):
                details = None
        if isinstance(details, dict):
            file_path = details.get("file_path")
            if file_path and isinstance(file_path, str):
                normalized = _normalize_path(file_path)
                if normalized:
                    paths.add(normalized)

        # Extract from common.text (Bash commands)
        common = payload.get("common")
        if isinstance(common, str):
            try:
                common = json.loads(common)
            except (json.JSONDecodeError, TypeError):
                common = None
        if isinstance(common, dict):
            text = common.get("text")
            if text and isinstance(text, str):
                matches = _FILE_PATH_RE.findall(text)
                for match in matches:
                    normalized = _normalize_path(match)
                    if normalized:
                        paths.add(normalized)

    return sorted(paths)
