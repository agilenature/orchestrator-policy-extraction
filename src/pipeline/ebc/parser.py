"""PLAN.md frontmatter parser producing ExternalBehavioralContract.

Reads a PLAN.md file, extracts YAML frontmatter between --- markers,
and constructs an ExternalBehavioralContract from the parsed data.

Exports:
    parse_ebc_from_plan: Parse a PLAN.md file into an EBC (or None on failure)
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from src.pipeline.ebc.models import ExternalBehavioralContract


def parse_ebc_from_plan(plan_path: str | Path) -> ExternalBehavioralContract | None:
    """Parse a PLAN.md file and return an ExternalBehavioralContract.

    Extracts YAML frontmatter from the file, processes must_haves into
    truths/artifacts/key_links, and constructs the contract model.

    Args:
        plan_path: Path to a PLAN.md file with YAML frontmatter.

    Returns:
        ExternalBehavioralContract if parsing succeeds, None otherwise.
        Returns None for: nonexistent files, missing frontmatter markers,
        invalid YAML, missing required fields.
    """
    plan_path = Path(plan_path)

    if not plan_path.exists():
        return None

    text = plan_path.read_text(encoding="utf-8")

    # Must start with ---
    if not text.startswith("---"):
        return None

    # Split on --- with maxsplit=2: expect ["", frontmatter, rest]
    parts = text.split("---", maxsplit=2)
    if len(parts) < 3:
        return None

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None

    if not isinstance(frontmatter, dict):
        return None

    # Extract must_haves into top-level fields
    must_haves = frontmatter.pop("must_haves", None)
    if isinstance(must_haves, dict):
        truths = must_haves.get("truths")
        if truths is not None:
            frontmatter["truths"] = truths
        artifacts = must_haves.get("artifacts")
        if artifacts is not None:
            frontmatter["artifacts"] = artifacts
        key_links = must_haves.get("key_links")
        if key_links is not None:
            frontmatter["key_links"] = key_links

    # Rename 'type' to 'plan_type' to avoid BaseModel conflict
    if "type" in frontmatter:
        frontmatter["plan_type"] = frontmatter.pop("type")

    # Construct the contract
    try:
        return ExternalBehavioralContract(**frontmatter)
    except (ValidationError, TypeError):
        return None
