"""Gold-standard export/import workflow for human-verified episode labels.

Exports episodes for human review (with template label files) and imports
validated labels for quality metrics computation.

Exports:
    export_for_review: Export episodes + template labels for human review
    import_labels: Import and validate human-verified label files
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import jsonschema
from jsonschema import validators
from loguru import logger


def export_for_review(
    conn: duckdb.DuckDBPyConnection,
    output_dir: Path,
    sample_size: int = 100,
) -> int:
    """Export episodes for human review with stratified sampling.

    Creates two subdirectories under output_dir:
    - episodes/{episode_id}.json -- full episode data
    - labels/{episode_id}.json -- template label with blank fields

    Stratified sampling ensures minimum 5 examples per mode and per
    reaction_label where available, filling remaining slots with random
    selection up to sample_size.

    Args:
        conn: DuckDB connection with populated episodes table.
        output_dir: Root directory for exported files.
        sample_size: Maximum number of episodes to export.

    Returns:
        Count of exported episodes.
    """
    # Query all episodes
    rows = conn.execute("""
        SELECT
            episode_id, session_id, mode, risk,
            reaction_label, reaction_confidence, outcome_type,
            observation, orchestrator_action, outcome, provenance
        FROM episodes
    """).fetchall()

    columns = [
        "episode_id", "session_id", "mode", "risk",
        "reaction_label", "reaction_confidence", "outcome_type",
        "observation", "orchestrator_action", "outcome", "provenance",
    ]

    all_episodes = []
    for row in rows:
        ep = dict(zip(columns, row))
        # Parse JSON columns
        for json_col in ("orchestrator_action", "outcome", "provenance"):
            val = ep.get(json_col)
            if isinstance(val, str):
                try:
                    ep[json_col] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        # Convert observation STRUCT to dict if needed
        obs = ep.get("observation")
        if obs is not None and not isinstance(obs, dict):
            ep["observation"] = _struct_to_dict(obs)
        all_episodes.append(ep)

    if not all_episodes:
        logger.warning("No episodes found to export")
        return 0

    # Stratified sampling
    selected = _stratified_sample(all_episodes, sample_size)

    # Create output directories
    episodes_dir = output_dir / "episodes"
    labels_dir = output_dir / "labels"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    # Write files
    for ep in selected:
        eid = ep["episode_id"]

        # Write episode data
        ep_path = episodes_dir / f"{eid}.json"
        with open(ep_path, "w") as f:
            json.dump(_serialize_episode(ep), f, indent=2, default=str)
            f.write("\n")

        # Write template label
        label_path = labels_dir / f"{eid}.json"
        label_template = {
            "episode_id": eid,
            "verified_mode": "",
            "verified_reaction_label": "",
            "verified_reaction_confidence": None,
            "constraint_should_extract": None,
            "notes": "",
            "reviewer": "",
        }
        with open(label_path, "w") as f:
            json.dump(label_template, f, indent=2)
            f.write("\n")

    logger.info("Exported {} episodes for review to {}", len(selected), output_dir)
    return len(selected)


def import_labels(
    label_dir: Path,
    schema_path: Path,
) -> tuple[list[dict], list[str]]:
    """Import and validate human-verified label files.

    Reads all .json files from label_dir, validates each against the
    gold-standard-label JSON Schema, and returns valid labels.

    Labels with blank verified_mode or verified_reaction_label are skipped
    (considered incomplete). Malformed or invalid files produce error messages.

    Args:
        label_dir: Directory containing label .json files.
        schema_path: Path to gold-standard-label.schema.json.

    Returns:
        Tuple of (valid_labels, error_messages).
    """
    valid_labels: list[dict] = []
    errors: list[str] = []

    # Load schema validator
    validator = _load_label_validator(schema_path)

    if not label_dir.exists():
        errors.append(f"Label directory does not exist: {label_dir}")
        return valid_labels, errors

    label_files = sorted(label_dir.glob("*.json"))
    if not label_files:
        errors.append(f"No .json files found in {label_dir}")
        return valid_labels, errors

    for label_file in label_files:
        try:
            with open(label_file) as f:
                label = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"{label_file.name}: failed to read: {e}")
            continue

        # Skip incomplete labels (blank required fields)
        verified_mode = label.get("verified_mode", "")
        verified_reaction = label.get("verified_reaction_label", "")
        if not verified_mode or not verified_reaction:
            logger.debug("Skipping incomplete label: {}", label_file.name)
            continue

        # Validate against schema
        if validator is not None:
            validation_errors = list(validator.iter_errors(label))
            if validation_errors:
                msg = "; ".join(e.message for e in validation_errors)
                errors.append(f"{label_file.name}: schema validation failed: {msg}")
                continue

        valid_labels.append(label)

    logger.info(
        "Imported {} valid labels from {} ({} errors, {} skipped)",
        len(valid_labels),
        label_dir,
        len(errors),
        len(label_files) - len(valid_labels) - len(errors),
    )
    return valid_labels, errors


# --- Private helpers ---


def _stratified_sample(
    episodes: list[dict],
    sample_size: int,
    min_per_stratum: int = 5,
) -> list[dict]:
    """Stratified sampling ensuring coverage across modes and reaction labels.

    Ensures minimum min_per_stratum examples per mode and per reaction_label
    where available, then fills remaining slots with random selection.
    """
    if len(episodes) <= sample_size:
        return list(episodes)

    selected_ids: set[str] = set()
    selected: list[dict] = []

    def _add(ep: dict) -> None:
        eid = ep["episode_id"]
        if eid not in selected_ids:
            selected_ids.add(eid)
            selected.append(ep)

    # Group by mode
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for ep in episodes:
        mode = ep.get("mode") or "unknown"
        by_mode[mode].append(ep)

    # Group by reaction_label
    by_reaction: dict[str, list[dict]] = defaultdict(list)
    for ep in episodes:
        rl = ep.get("reaction_label") or "unknown"
        by_reaction[rl].append(ep)

    # Ensure minimum coverage per mode
    for mode, mode_eps in by_mode.items():
        take = min(min_per_stratum, len(mode_eps))
        for ep in random.sample(mode_eps, take):
            _add(ep)
            if len(selected) >= sample_size:
                return selected

    # Ensure minimum coverage per reaction_label
    for rl, rl_eps in by_reaction.items():
        take = min(min_per_stratum, len(rl_eps))
        for ep in random.sample(rl_eps, take):
            _add(ep)
            if len(selected) >= sample_size:
                return selected

    # Fill remaining with random selection
    remaining = [ep for ep in episodes if ep["episode_id"] not in selected_ids]
    random.shuffle(remaining)
    for ep in remaining:
        _add(ep)
        if len(selected) >= sample_size:
            break

    return selected


def _struct_to_dict(obj: Any) -> Any:
    """Convert DuckDB STRUCT result to a plain dict recursively."""
    if isinstance(obj, dict):
        return {k: _struct_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_struct_to_dict(item) for item in obj]
    return obj


def _serialize_episode(ep: dict) -> dict:
    """Prepare episode dict for JSON serialization."""
    result = {}
    for k, v in ep.items():
        if isinstance(v, (dict, list, str, int, float, bool)) or v is None:
            result[k] = v
        else:
            result[k] = str(v)
    return result


def _load_label_validator(schema_path: Path):
    """Load JSON Schema validator for gold-standard labels.

    Returns None if schema file is missing (validation will be skipped).
    """
    if not schema_path.exists():
        logger.warning(
            "Gold-standard label schema not found at {}, validation disabled",
            schema_path,
        )
        return None
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        validator_cls = validators.validator_for(schema)
        return validator_cls(schema, format_checker=jsonschema.FormatChecker())
    except Exception as e:
        logger.warning(
            "Failed to load label schema from {}: {}, validation disabled",
            schema_path,
            e,
        )
        return None
