"""Git history adapter -- parse git log into canonical events.

Runs `git log` via subprocess to extract commit history and transforms
each commit into a CanonicalEvent with actor='executor' (Claude Code
makes the commits) and event_type='git_commit'.

Commit hashes are stored in links.commit_hash for temporal alignment
with JSONL events in the normalizer.

Exports:
    parse_git_history: Parse git log into CanonicalEvent instances
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.pipeline.models.events import CanonicalEvent

# Separator for git log format fields (unlikely to appear in commit messages)
_GIT_LOG_SEP = "|||"

# git log format: hash, ISO author date, author name, subject
_GIT_LOG_FORMAT = f"%H{_GIT_LOG_SEP}%aI{_GIT_LOG_SEP}%an{_GIT_LOG_SEP}%s"


def parse_git_history(
    repo_path: str | Path,
    session_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[CanonicalEvent]:
    """Parse git log output into canonical events.

    Runs `git log --format=... --name-only` to get commit metadata and
    changed files. Each commit becomes a CanonicalEvent.

    Args:
        repo_path: Path to the git repository root.
        session_id: Optional session ID to associate events with.
            Defaults to 'git-<repo_name>'.
        since: Optional git date filter (e.g., '2026-01-01').
        until: Optional git date filter (e.g., '2026-02-11').

    Returns:
        List of CanonicalEvent instances, one per commit,
        ordered from oldest to newest.
    """
    repo_path = Path(repo_path).resolve()

    if session_id is None:
        session_id = f"git-{repo_path.name}"

    cmd = [
        "git",
        "-C",
        str(repo_path),
        "log",
        f"--format={_GIT_LOG_FORMAT}",
        "--name-only",
    ]

    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")

    logger.info("Running git log in {}", repo_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error("git log failed: {}", e.stderr)
        return []
    except FileNotFoundError:
        logger.error("git not found on PATH")
        return []
    except subprocess.TimeoutExpired:
        logger.error("git log timed out after 30 seconds")
        return []

    output = result.stdout.strip()
    if not output:
        logger.info("No git commits found")
        return []

    events = _parse_git_log_output(output, session_id)

    # Reverse to get chronological order (oldest first)
    events.reverse()

    logger.info("Parsed {} git commit events from {}", len(events), repo_path.name)
    return events


def _parse_git_log_output(
    output: str, session_id: str
) -> list[CanonicalEvent]:
    """Parse raw git log output into events.

    Git log with --name-only outputs:

        <hash>|||<date>|||<author>|||<subject>
        <blank line>
        file1.py
        file2.py
        <hash>|||<date>|||<author>|||<subject>
        <blank line>
        file3.py

    We detect header lines by the presence of the ||| separator,
    then collect subsequent non-header, non-blank lines as files.
    """
    events: list[CanonicalEvent] = []
    lines = output.split("\n")

    # Parse into commit groups: find header lines, collect files until next header
    commits: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_files: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _GIT_LOG_SEP in stripped:
            # This is a header line for a new commit
            if current_header is not None:
                commits.append((current_header, current_files))
            current_header = stripped
            current_files = []
        elif stripped:
            # Non-blank, non-header line = file path
            current_files.append(stripped)
        # Blank lines are ignored

    # Don't forget the last commit
    if current_header is not None:
        commits.append((current_header, current_files))

    for header, changed_files in commits:
        parts = header.split(_GIT_LOG_SEP)
        if len(parts) < 4:
            logger.warning("Malformed git log header: {}", header[:80])
            continue

        commit_hash = parts[0].strip()
        date_str = parts[1].strip()
        author = parts[2].strip()
        subject = parts[3].strip()

        # Parse author date (ISO 8601 with timezone)
        ts = _parse_git_timestamp(date_str)

        # Build canonical event
        event_id = CanonicalEvent.make_event_id(
            source_system="git",
            session_id=session_id,
            turn_id=commit_hash,
            ts_utc=ts.isoformat(),
            actor="executor",
            event_type="git_commit",
        )

        payload = {
            "common": {
                "text": subject,
                "files_touched": changed_files,
            },
            "details": {
                "git": {
                    "commit_hash": commit_hash,
                    "author": author,
                    "files_changed": changed_files,
                }
            },
        }

        links = {
            "commit_hash": commit_hash,
        }

        events.append(
            CanonicalEvent(
                event_id=event_id,
                ts_utc=ts,
                session_id=session_id,
                actor="executor",
                event_type="git_commit",
                payload=payload,
                links=links,
                source_system="git",
                source_ref=commit_hash,
            )
        )

    return events


def _parse_git_timestamp(date_str: str) -> datetime:
    """Parse a git ISO 8601 timestamp to timezone-aware UTC datetime.

    Git author dates include timezone offsets like:
    2026-02-10T23:29:13-05:00

    Normalizes to UTC.
    """
    try:
        dt = datetime.fromisoformat(date_str)
        # Convert to UTC
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as e:
        logger.warning("Failed to parse git timestamp '{}': {}", date_str, e)
        return datetime.now(timezone.utc)
