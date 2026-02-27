"""Subprocess-based code search via ripgrep (rg) with grep fallback.

Provides ``query_code()`` -- the code query backend for the unified
discriminated query interface.  Searches source files using ``rg`` (ripgrep)
when available, falling back to ``grep`` otherwise.

Fail-open: any error returns ``[]``.

Exports:
    query_code: File/line code search via subprocess
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_code(
    query: str,
    search_dir: str = "src/",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Search source files for *query*, returning file:line results.

    Uses ripgrep (``rg``) when available for fast, type-filtered search.
    Falls back to ``grep -rn`` otherwise.

    Args:
        query: Text pattern to search for (passed as literal to rg/grep).
        search_dir: Directory to search in.
        top_n: Maximum number of results to return.

    Returns:
        List of dicts with keys ``source``, ``file_path``, ``line_number``,
        ``content_preview``, ``match_reason``.  Returns ``[]`` on any error
        (fail-open).
    """
    if not query or not query.strip():
        return []

    try:
        cmd = _build_command(query, search_dir)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # returncode 0 = matches found, 1 = no matches, 2+ = error
        if result.returncode not in (0, 1):
            return []

        return _parse_output(result.stdout, top_n)

    except Exception:
        logger.debug("query_code failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_command(query: str, search_dir: str) -> list[str]:
    """Build the search command, preferring rg over grep."""
    rg_path = shutil.which("rg")
    if rg_path:
        return [
            rg_path,
            "-n",
            "-i",
            "--max-count", "3",
            "--type", "py",
            "--type", "md",
            query,
            search_dir,
        ]
    return [
        "grep",
        "-rn",
        "-i",
        "--include=*.py",
        "--include=*.md",
        query,
        search_dir,
    ]


def _parse_output(stdout: str, top_n: int) -> list[dict[str, Any]]:
    """Parse rg/grep output lines into result dicts.

    Expected format: ``file:line:content``
    """
    results: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(":", maxsplit=2)
        if len(parts) < 3:
            continue
        file_path, line_num_str, content = parts
        try:
            line_number = int(line_num_str)
        except ValueError:
            continue

        preview = content.strip()
        if len(preview) > 120:
            preview = preview[:120]

        results.append(
            {
                "source": "code",
                "file_path": file_path,
                "line_number": line_number,
                "content_preview": preview,
                "match_reason": "text match",
            }
        )
        if len(results) >= top_n:
            break

    return results
