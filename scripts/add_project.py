#!/usr/bin/env python3
"""Add or update a project in the data/projects.json registry.

The positional argument can be either:
  - A project filesystem path:  /Users/david/projects/my-project
  - A Claude sessions path:     ~/.claude/projects/-Users-david-projects-my-project/

If an existing project matches (by sessions_location or ID), the entry is updated.
The --git flag accepts both local paths and remote URLs.

Usage:
    python scripts/add_project.py /Users/david/projects/my-project
    python scripts/add_project.py ~/.claude/projects/-Users-david-projects-my-project/
    python scripts/add_project.py /Users/david/projects/my-project --git https://github.com/org/repo.git
    python scripts/add_project.py /Users/david/projects/my-project --name "My Project Name"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def is_sessions_path(path: str) -> bool:
    """Return True if the path is under ~/.claude/projects/."""
    expanded = Path(path).expanduser()
    claude_projects = Path("~/.claude/projects").expanduser()
    try:
        expanded.relative_to(claude_projects)
        return True
    except ValueError:
        return False


def sessions_path_to_sessions_location(sessions_path: str) -> str:
    """Normalise a sessions path to the ~/... tilde form stored in the registry."""
    expanded = Path(sessions_path).expanduser()
    home = Path.home()
    try:
        rel = expanded.relative_to(home)
        return f"~/{rel}/"
    except ValueError:
        return str(expanded) + "/"


def sessions_path_to_project_id(sessions_path: str) -> str:
    """Extract project ID from a Claude sessions directory name.

    The directory name is the project path with '/' replaced by '-':
      -Users-david-projects-modernizing-tool -> modernizing-tool

    Strategy: look for common parent-directory markers and take everything after
    the last one. Falls back to the last hyphen-delimited token.
    """
    name = Path(sessions_path).expanduser().name  # e.g. -Users-david-projects-modernizing-tool
    markers = ["-projects-", "-dev-", "-src-", "-code-", "-work-", "-repos-"]
    for marker in markers:
        if marker in name:
            suffix = name.split(marker)[-1]
            if suffix:
                return suffix
    # Fallback: last non-empty hyphen token
    parts = [p for p in name.split("-") if p]
    return parts[-1] if parts else name


def project_path_to_sessions_location(project_path: str) -> str:
    """Convert a project filesystem path to its ~/.claude/projects/ encoded location.

    /Users/david/projects/my-project -> ~/.claude/projects/-Users-david-projects-my-project/
    """
    encoded = project_path.replace("/", "-")
    return f"~/.claude/projects/{encoded}/"


def path_to_id(project_path: str) -> str:
    return Path(project_path).name


def id_to_name(project_id: str) -> str:
    return project_id.replace("-", " ").replace("_", " ").title()


def is_remote_url(path: str) -> bool:
    return bool(re.match(r"^(https?://|git@|ssh://)", path))


def count_sessions(sessions_location: str) -> int:
    d = Path(sessions_location).expanduser()
    return len(list(d.glob("*.jsonl"))) if d.exists() else 0


def find_existing(projects: list, project_id: str, sessions_location: str) -> dict | None:
    """Find an existing project by ID or by sessions_location (handles mis-derived IDs)."""
    by_id = next((p for p in projects if p["id"] == project_id), None)
    if by_id:
        return by_id
    by_sessions = next(
        (p for p in projects
         if p.get("data_status", {}).get("sessions_location") == sessions_location),
        None,
    )
    return by_sessions


def main():
    parser = argparse.ArgumentParser(
        description="Add or update a project in data/projects.json"
    )
    parser.add_argument(
        "project_path",
        help=(
            "Project filesystem path (e.g. /Users/david/projects/my-project) "
            "or Claude sessions path (e.g. ~/.claude/projects/-Users-david-projects-my-project/)"
        ),
    )
    parser.add_argument(
        "--git",
        dest="git_path",
        default=None,
        help="Git repo location — local path or remote URL (defaults to project_path for filesystem paths)",
    )
    parser.add_argument(
        "--name",
        dest="name",
        default=None,
        help="Human-readable project name (derived from path if omitted)",
    )
    parser.add_argument(
        "--registry",
        default="data/projects.json",
        help="Path to projects registry (default: data/projects.json)",
    )

    args = parser.parse_args()
    raw_path = args.project_path.rstrip("/")

    if is_sessions_path(raw_path):
        sessions_location = sessions_path_to_sessions_location(raw_path)
        project_id = sessions_path_to_project_id(raw_path)
        git_location = args.git_path or None
    else:
        sessions_location = project_path_to_sessions_location(raw_path)
        project_id = path_to_id(raw_path)
        git_location = args.git_path or raw_path

    if git_location and not is_remote_url(git_location):
        git_location = git_location.rstrip("/")

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"Error: {registry_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(registry_path) as f:
        registry = json.load(f)

    projects = registry.setdefault("projects", [])

    # Match by ID first, then by sessions_location (handles mis-derived IDs from sessions paths)
    existing = find_existing(projects, project_id, sessions_location)
    if existing:
        project_id = existing["id"]  # use the canonical ID from the registry

    project_name = args.name or (existing["name"] if existing else id_to_name(project_id))

    sessions_dir = Path(sessions_location).expanduser()
    sessions_available = sessions_dir.exists()
    session_count = count_sessions(sessions_location)

    data_status = {
        "sessions_available": sessions_available,
        "sessions_location": sessions_location,
        "git_clone_needed": False,
        "metadata_complete": False,
    }
    if git_location:
        data_status["git_location"] = git_location
    if sessions_available:
        data_status["session_count"] = session_count

    if existing:
        action = "Updated"
        existing["status"] = "ready" if sessions_available else existing.get("status", "pending_processing")
        existing.setdefault("data_status", {}).update(data_status)
        if args.name:
            existing["name"] = project_name
    else:
        action = "Added"
        projects.append({
            "id": project_id,
            "name": project_name,
            "metadata_path": f"data/raw/{project_id}/metadata.json",
            "status": "ready" if sessions_available else "pending_processing",
            "added_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "notes": "",
            "data_status": data_status,
        })

    registry["statistics"] = {
        "total_projects": len(projects),
        "ready_projects": sum(1 for p in projects if p["status"] == "ready"),
        "pending_projects": sum(1 for p in projects if p["status"] != "ready"),
        "total_sessions": sum(p.get("data_status", {}).get("session_count", 0) for p in projects),
        "total_commits": registry.get("statistics", {}).get("total_commits", 0),
        "commits_with_session_ids": registry.get("statistics", {}).get("commits_with_session_ids", 0),
        "commits_with_claude_attribution": registry.get("statistics", {}).get("commits_with_claude_attribution", 0),
    }
    registry["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")

    print(f"{action} project '{project_name}' ({project_id})")
    print(f"  Sessions location : {sessions_location}")
    print(f"  Sessions available: {sessions_available}" + (f" ({session_count} files)" if sessions_available else ""))
    if git_location:
        print(f"  Git location      : {git_location}")
    print(f"  Status            : {'ready' if sessions_available else 'pending_processing'}")

    if sessions_available:
        print()
        print("Next steps:")
        print(f"  python scripts/discover_new_sessions.py")
        print(f"  python scripts/ingest_incremental.py --embed --project {project_id} -v")
    else:
        print()
        print(f"Warning: sessions directory not found at {sessions_location}")
        print("Update data/projects.json manually once sessions are available.")


if __name__ == "__main__":
    main()
