"""Constraint migration -- adds type, status_history, supersedes fields.

Migrates existing constraints in data/constraints.json to include the
Phase 10 decision-durability fields:
  - type: behavioral_constraint (default) or architectural_decision
  - status_history: chronological status change log for point-in-time lookups
  - supersedes: ID of a prior constraint this one supersedes (null default)

Idempotent: skips constraints that already have all three fields populated.

Exports:
    migrate_constraints
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from jsonschema import validators
from loguru import logger


def migrate_constraints(
    path: Path = Path("data/constraints.json"),
    schema_path: Path = Path("data/schemas/constraint.schema.json"),
) -> int:
    """Migrate existing constraints to include type, status_history, supersedes.

    For each constraint:
      - Missing type: set to "behavioral_constraint"
      - Missing status_history: bootstrap from status + created_at
      - Missing supersedes: set to None

    Validates each migrated constraint against the schema.

    Args:
        path: Path to the constraints JSON file.
        schema_path: Path to the constraint JSON Schema file.

    Returns:
        Count of constraints that were migrated (had missing fields).
    """
    if not path.exists():
        logger.warning("Constraints file not found at {}, nothing to migrate", path)
        return 0

    with open(path) as f:
        constraints = json.load(f)

    if not isinstance(constraints, list):
        logger.warning("Constraints file {} does not contain a JSON array", path)
        return 0

    # Load schema for validation
    validator = _load_validator(schema_path)

    migrated_count = 0

    for constraint in constraints:
        changed = False

        # Add type if missing
        if "type" not in constraint:
            constraint["type"] = "behavioral_constraint"
            changed = True

        # Add status_history if missing
        if "status_history" not in constraint:
            status_history = _bootstrap_status_history(constraint)
            constraint["status_history"] = status_history
            changed = True

        # Add supersedes if missing
        if "supersedes" not in constraint:
            constraint["supersedes"] = None
            changed = True

        if changed:
            migrated_count += 1

        # Validate against schema
        if validator is not None:
            errors = list(validator.iter_errors(constraint))
            if errors:
                logger.warning(
                    "Constraint {} failed post-migration validation: {}",
                    constraint.get("constraint_id", "unknown"),
                    errors[0].message,
                )

    # Write back
    with open(path, "w") as f:
        json.dump(constraints, f, indent=2)
        f.write("\n")

    logger.info(
        "Migrated {}/{} constraints in {}",
        migrated_count,
        len(constraints),
        path,
    )
    return migrated_count


def _bootstrap_status_history(constraint: dict) -> list[dict]:
    """Bootstrap a status_history from existing constraint fields.

    Uses status + created_at to create the initial history entry.
    Falls back to examples[0] episode timestamp if created_at is missing.

    Args:
        constraint: Constraint dict to bootstrap from.

    Returns:
        List with a single status_history entry, or empty list if
        no timestamp could be determined.
    """
    status = constraint.get("status", "active")
    changed_at = constraint.get("created_at")

    if not changed_at:
        # Try to approximate from earliest example's episode context
        examples = constraint.get("examples", [])
        if examples:
            # We don't have episode timestamps directly in examples,
            # so we can't reliably approximate. Log and return empty.
            logger.warning(
                "Constraint {} has no created_at; status_history bootstrapped empty",
                constraint.get("constraint_id", "unknown"),
            )
            return []
        else:
            logger.warning(
                "Constraint {} has no created_at and no examples; "
                "status_history bootstrapped empty",
                constraint.get("constraint_id", "unknown"),
            )
            return []

    return [{"status": status, "changed_at": changed_at}]


def _load_validator(schema_path: Path):
    """Load JSON Schema validator for constraints.

    Returns None if schema file is missing (validation will be skipped).
    """
    if not schema_path.exists():
        logger.warning(
            "Constraint schema not found at {}, validation disabled",
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
            "Failed to load constraint schema: {}, validation disabled", e
        )
        return None


if __name__ == "__main__":
    count = migrate_constraints()
    print(f"Migrated {count} constraints")
