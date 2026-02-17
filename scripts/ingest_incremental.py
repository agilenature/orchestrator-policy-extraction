#!/usr/bin/env python3
"""Incremental ingestion - process only new sessions.

Discovers new sessions using discover_new_sessions.py, then processes them
through the extraction pipeline. Optionally generates embeddings afterward.

Usage:
    # Dry run - show what would be ingested
    python scripts/ingest_incremental.py --dry-run

    # Ingest new sessions
    python scripts/ingest_incremental.py

    # Ingest + generate embeddings
    python scripts/ingest_incremental.py --embed

    # Ingest specific project only
    python scripts/ingest_incremental.py --project orchestrator-policy-extraction
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd: list[str], description: str, dry_run: bool = False) -> bool:
    """Run a shell command and return success status.

    Args:
        cmd: Command as list of strings.
        description: Human-readable description.
        dry_run: If True, print command but don't execute.

    Returns:
        True if command succeeded (or dry run), False otherwise.
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Running: {description}")
    print(f"  Command: {' '.join(cmd)}")

    if dry_run:
        return True

    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode != 0:
            # Non-zero usually means some sessions had validation errors (already logged).
            # Only treat it as a project-level failure if the process itself crashed (code >= 2).
            if result.returncode >= 2:
                print(f"  ✗ Fatal error (exit code {result.returncode})", file=sys.stderr)
                return False
            print(f"  ⚠ Completed with warnings (exit code {result.returncode}) — some sessions may have been skipped")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}", file=sys.stderr)
        return False


def ingest_incremental(
    db_path: str = "data/ope.db",
    project_filter: str | None = None,
    embed: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Incrementally ingest new sessions.

    Args:
        db_path: DuckDB database path.
        project_filter: If set, only process this project ID.
        embed: If True, generate embeddings after ingestion.
        dry_run: If True, show what would be done but don't execute.
        verbose: Verbose output.

    Returns:
        Stats dict with ingestion results.
    """
    # Discover new sessions
    print("=" * 70)
    print("INCREMENTAL INGESTION")
    print("=" * 70)
    print(f"\nTimestamp: {datetime.now().isoformat()}")
    print(f"Database: {db_path}")
    if project_filter:
        print(f"Project filter: {project_filter}")
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")

    # Import discovery logic
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.discover_new_sessions import discover_new_sessions

    result = discover_new_sessions(db_path=db_path, verbose=verbose)

    if result.get("error"):
        print(f"Error during discovery: {result['error']}", file=sys.stderr)
        return {"error": result["error"]}

    total_new = result["total_new_sessions"]
    print(f"\nDiscovered {total_new} new sessions")

    if total_new == 0:
        print("\n✓ All sessions already ingested. Nothing to do.")
        return {
            "sessions_processed": 0,
            "sessions_failed": 0,
            "embeddings_generated": False,
        }

    # Load projects
    projects_file = Path("data/projects.json")
    with open(projects_file) as f:
        registry = json.load(f)

    # Process each project with new sessions
    sessions_processed = 0
    sessions_failed = 0
    project_stats = []

    for project in registry.get("projects", []):
        project_id = project["id"]

        # Apply project filter
        if project_filter and project_id != project_filter:
            continue

        new_sessions = result["new_sessions_by_project"].get(project_id, [])
        if not new_sessions:
            continue

        data_status = project.get("data_status", {})
        sessions_location = data_status.get("sessions_location", "")
        git_location = data_status.get("git_location", "")

        if not sessions_location:
            print(f"\nSkipping {project_id}: No sessions location configured")
            continue

        print(f"\n{'─' * 70}")
        print(f"Processing: {project['name']} ({project_id})")
        print(f"  New sessions: {len(new_sessions)}")
        print(f"  Location: {sessions_location}")
        if git_location and git_location != "current_repository":
            print(f"  Git repo: {git_location}")

        # Build ingestion command
        # Expand ~ in paths
        sessions_path_expanded = str(Path(sessions_location).expanduser())

        cmd = [
            sys.executable,
            "-m",
            "src.pipeline.cli.extract",
            sessions_path_expanded,
            "--db",
            db_path,
        ]

        is_remote = git_location and bool(__import__("re").match(r"^(https?://|git@|ssh://)", git_location))
        if git_location and git_location != "current_repository" and not is_remote:
            git_path_expanded = str(Path(git_location).expanduser())
            cmd.extend(["--repo", git_path_expanded])

        if verbose:
            cmd.append("-v")

        # Run ingestion
        success = run_command(
            cmd,
            f"Ingest {len(new_sessions)} sessions from {project_id}",
            dry_run=dry_run,
        )

        if success:
            sessions_processed += len(new_sessions)
            project_stats.append({
                "project_id": project_id,
                "project_name": project["name"],
                "sessions": len(new_sessions),
                "status": "success" if not dry_run else "dry_run",
            })
        else:
            sessions_failed += len(new_sessions)
            project_stats.append({
                "project_id": project_id,
                "project_name": project["name"],
                "sessions": len(new_sessions),
                "status": "failed",
            })

    # Generate embeddings if requested
    embeddings_generated = False
    if embed and sessions_processed > 0 and not dry_run:
        print(f"\n{'─' * 70}")
        print("Generating embeddings for new episodes")

        embed_cmd = [
            sys.executable,
            "-m",
            "src.pipeline.cli.train",
            "embed",
            "--db",
            db_path,
        ]
        if verbose:
            embed_cmd.append("-v")

        embeddings_generated = run_command(
            embed_cmd,
            "Generate embeddings",
            dry_run=False,
        )

    # Summary
    print(f"\n{'═' * 70}")
    print("INGESTION SUMMARY")
    print(f"{'═' * 70}")
    print(f"  Sessions processed: {sessions_processed}")
    print(f"  Sessions failed:    {sessions_failed}")
    print(f"  Embeddings generated: {embeddings_generated}")

    if project_stats:
        print("\n  Per-project:")
        for stat in project_stats:
            status_icon = "✓" if stat["status"] == "success" else "✗"
            if stat["status"] == "dry_run":
                status_icon = "○"
            print(
                f"    {status_icon} {stat['project_name']}: "
                f"{stat['sessions']} sessions ({stat['status']})"
            )

    if not dry_run and sessions_processed > 0:
        print("\n✓ Ingestion complete!")
        print(f"\nNext steps:")
        if not embeddings_generated:
            print(f"  1. Generate embeddings: python -m src.pipeline.cli.train embed --db {db_path}")
        print(f"  2. Run shadow mode: python -m src.pipeline.cli.train shadow-run --db {db_path}")
        print(f"  3. View metrics: python -m src.pipeline.cli.train shadow-report --db {db_path}")

    return {
        "sessions_processed": sessions_processed,
        "sessions_failed": sessions_failed,
        "embeddings_generated": embeddings_generated,
        "project_stats": project_stats,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Incrementally ingest new Claude Code sessions"
    )
    parser.add_argument(
        "--db",
        default="data/ope.db",
        help="DuckDB database path (default: data/ope.db)",
    )
    parser.add_argument(
        "--project",
        help="Only process this project ID (default: all projects)",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate embeddings after ingestion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    result = ingest_incremental(
        db_path=args.db,
        project_filter=args.project,
        embed=args.embed,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    # Exit with error code if any sessions failed
    if result.get("sessions_failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
