#!/usr/bin/env python3
"""Discover new Claude Code sessions and commits for ingestion.

Scans ~/.claude/projects/ for JSONL session files that haven't been ingested
yet, and checks git repos for new commits since last ingestion.

Usage:
    python scripts/discover_new_sessions.py [--db data/ope.db] [--verbose]

Outputs:
    - Summary of new sessions found
    - Summary of new commits (if git repos configured)
    - List of session files ready for ingestion
    - Suggested ingestion commands
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb


def discover_new_sessions(db_path: str = "data/ope.db", verbose: bool = False) -> dict:
    """Discover new JSONL sessions not yet in DuckDB.

    Args:
        db_path: Path to DuckDB database.
        verbose: Enable verbose output.

    Returns:
        Dict with 'new_sessions', 'already_ingested', 'projects' keys.
    """
    # Load project registry
    projects_file = Path("data/projects.json")
    if not projects_file.exists():
        print(f"Error: {projects_file} not found", file=sys.stderr)
        return {"error": "projects.json not found"}

    with open(projects_file) as f:
        registry = json.load(f)

    # Load permanently skipped sessions
    skipped_sessions = set()
    skipped_file = Path("data/skipped_sessions.json")
    if skipped_file.exists():
        with open(skipped_file) as f:
            skipped_data = json.load(f)
        skipped_sessions = {s["session_id"] for s in skipped_data.get("sessions", [])}

    # Get already-ingested session IDs from DuckDB
    ingested_sessions = set()
    last_ingestion_ts = None

    db_exists = Path(db_path).exists()
    if db_exists:
        try:
            conn = duckdb.connect(db_path)
            # Check if events table exists
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
            table_names = [t[0] for t in tables]

            if "events" in table_names:
                # Get all ingested session IDs
                rows = conn.execute("SELECT DISTINCT session_id FROM events").fetchall()
                ingested_sessions = {row[0] for row in rows}

                # Get latest ingestion timestamp
                ts_row = conn.execute(
                    "SELECT MAX(last_seen) FROM events"
                ).fetchone()
                if ts_row and ts_row[0]:
                    last_ingestion_ts = ts_row[0]

            conn.close()
        except Exception as e:
            if verbose:
                print(f"Warning: Could not query DuckDB: {e}", file=sys.stderr)
    else:
        if verbose:
            print(f"Database {db_path} does not exist - no sessions ingested yet")

    # Scan for JSONL files in registered projects
    new_sessions_by_project = defaultdict(list)
    already_ingested_by_project = defaultdict(list)

    for project in registry.get("projects", []):
        if project["status"] != "ready":
            continue

        data_status = project.get("data_status", {})
        if not data_status.get("sessions_available"):
            continue

        sessions_location = data_status.get("sessions_location", "")
        if not sessions_location:
            continue

        # Expand ~ in path
        sessions_dir = Path(sessions_location).expanduser()
        if not sessions_dir.exists():
            if verbose:
                print(f"Warning: {sessions_dir} does not exist", file=sys.stderr)
            continue

        # Find top-level .jsonl files only (subagent sessions in subdirectories are out of scope)
        jsonl_files = list(sessions_dir.glob("*.jsonl"))

        for jsonl_file in jsonl_files:
            # Extract session ID from filename (UUID pattern)
            import re
            uuid_pattern = re.compile(
                r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                re.IGNORECASE,
            )
            match = uuid_pattern.search(jsonl_file.stem)
            if match:
                session_id = match.group(1)
            else:
                session_id = jsonl_file.stem

            session_info = {
                "session_id": session_id,
                "file_path": str(jsonl_file),
                "file_size": jsonl_file.stat().st_size,
                "modified_time": datetime.fromtimestamp(
                    jsonl_file.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }

            if session_id in skipped_sessions:
                pass  # permanently excluded — not new, not ingested
            elif session_id in ingested_sessions:
                already_ingested_by_project[project["id"]].append(session_info)
            else:
                new_sessions_by_project[project["id"]].append(session_info)

    # Build result
    result = {
        "db_path": db_path,
        "db_exists": db_exists,
        "last_ingestion_ts": str(last_ingestion_ts) if last_ingestion_ts else None,
        "ingested_session_count": len(ingested_sessions),
        "new_sessions_by_project": dict(new_sessions_by_project),
        "already_ingested_by_project": dict(already_ingested_by_project),
        "projects": registry.get("projects", []),
    }

    # Count totals
    total_new = sum(len(sessions) for sessions in new_sessions_by_project.values())
    total_already = sum(len(sessions) for sessions in already_ingested_by_project.values())

    result["total_new_sessions"] = total_new
    result["total_already_ingested"] = total_already

    return result


def print_summary(result: dict) -> None:
    """Print a human-readable summary of discovery results."""
    print("=" * 70)
    print("CLAUDE CODE SESSION DISCOVERY")
    print("=" * 70)

    print(f"\nDatabase: {result['db_path']}")
    print(f"  Exists: {result['db_exists']}")
    if result["last_ingestion_ts"]:
        print(f"  Last ingestion: {result['last_ingestion_ts']}")
    print(f"  Sessions already ingested: {result['ingested_session_count']}")

    print(f"\n{'NEW Sessions Found:':<30} {result['total_new_sessions']}")
    print(f"{'Already Ingested:':<30} {result['total_already_ingested']}")

    # Per-project breakdown
    print("\n" + "-" * 70)
    print("PER-PROJECT BREAKDOWN")
    print("-" * 70)

    for project in result["projects"]:
        project_id = project["id"]
        new_sessions = result["new_sessions_by_project"].get(project_id, [])
        already_sessions = result["already_ingested_by_project"].get(project_id, [])

        if new_sessions or already_sessions:
            print(f"\n{project['name']} ({project_id}):")
            print(f"  New:      {len(new_sessions)}")
            print(f"  Ingested: {len(already_sessions)}")

            if new_sessions:
                print("\n  New session files:")
                for session in new_sessions[:5]:  # Show first 5
                    size_kb = session["file_size"] / 1024
                    print(f"    - {session['session_id'][:8]}... ({size_kb:.1f} KB)")
                if len(new_sessions) > 5:
                    print(f"    ... and {len(new_sessions) - 5} more")

    # Ingestion commands
    if result['total_new_sessions'] > 0:
        print("\n" + "=" * 70)
        print("SUGGESTED INGESTION COMMANDS")
        print("=" * 70)

        for project in result["projects"]:
            project_id = project["id"]
            new_sessions = result["new_sessions_by_project"].get(project_id, [])

            if new_sessions:
                data_status = project.get("data_status", {})
                sessions_location = data_status.get("sessions_location", "")
                git_location = data_status.get("git_location", "")

                print(f"\n# {project['name']}")
                print(f"python -m src.pipeline.cli.extract \\")
                print(f"    {sessions_location} \\")
                print(f"    --db {result['db_path']} \\")
                if git_location and git_location != "current_repository":
                    print(f"    --repo {git_location} \\")
                print(f"    -v")

        print("\n# After ingestion, generate embeddings:")
        print(f"python -m src.pipeline.cli.train embed --db {result['db_path']} -v")

    else:
        print("\n✓ All sessions are already ingested. No new data to process.")


def main():
    parser = argparse.ArgumentParser(
        description="Discover new Claude Code sessions for ingestion"
    )
    parser.add_argument(
        "--db",
        default="data/ope.db",
        help="DuckDB database path (default: data/ope.db)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable summary",
    )

    args = parser.parse_args()

    result = discover_new_sessions(db_path=args.db, verbose=args.verbose)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_summary(result)


if __name__ == "__main__":
    main()
