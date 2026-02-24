"""Premise-Assertion Gate (PAG) PreToolUse hook script.

This script is invoked by Claude Code via the PreToolUse hook protocol.
It receives JSON on stdin and outputs JSON on stdout.

The hook intercepts write-class tool calls (Edit, Write, Bash) and:
1. Reads recent assistant text from the JSONL transcript
2. Parses PREMISE blocks from the text
3. Stages parsed premises to premise_staging.jsonl
4. Checks for warnings (UNVALIDATED on high-risk, stained premises,
   foil instantiation, Ad Ignorantiam, frontier warnings,
   cross-axis verification)
5. Emits additionalContext warnings as appropriate
6. Always exits 0 (allow) -- Phase 14.1 does NOT block

The hook NEVER writes to data/ope.db. All writes go to
data/premise_staging.jsonl. Read-only DuckDB access for staining
and foil checks, wrapped in try/except (fail-open).

Usage:
    echo '{"tool_name": "Edit", "transcript_path": "/path/to.jsonl", ...}' | python premise_gate.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.parser import parse_premise_blocks
from src.pipeline.premise.staging import append_to_staging
from src.pipeline.premise.transcript import (
    count_validation_calls_since_last_user,
    read_recent_assistant_text,
)

logger = logging.getLogger(__name__)

# Write-class tools that require PREMISE declarations
WRITE_CLASS = frozenset({"Edit", "Write", "Bash"})

# High-risk file paths where UNVALIDATED premises warrant a warning
HIGH_RISK_PATHS = (
    "src/pipeline/storage/schema.py",
    "data/constraints.json",
    ".claude/settings.json",
    "src/pipeline/models/",
)


def _is_high_risk_path(tool_input: dict, cwd: str) -> bool:
    """Check if the tool_input targets a high-risk file path.

    Args:
        tool_input: The tool_input dict from hook stdin.
        cwd: Current working directory.

    Returns:
        True if the tool targets a high-risk path.
    """
    # Extract path from tool_input (different fields for different tools)
    target_path = (
        tool_input.get("file_path", "")
        or tool_input.get("path", "")
        or tool_input.get("command", "")
    )

    if not target_path:
        return False

    for risk_path in HIGH_RISK_PATHS:
        if risk_path in target_path:
            return True

    return False


def _check_stained_premises(
    premises: list, session_id: str, cwd: str
) -> list[str]:
    """Check if any parsed premises match stained premises in the registry.

    Uses a READ-ONLY DuckDB connection. Wrapped in try/except (fail-open).

    Args:
        premises: List of ParsedPremise objects.
        session_id: Current session ID.
        cwd: Current working directory.

    Returns:
        List of warning messages for stained premises.
    """
    warnings: list[str] = []

    db_path = Path("data/ope.db")
    if not db_path.exists():
        return warnings

    try:
        import duckdb

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            # Check if premise_registry table exists
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'premise_registry'"
            ).fetchall()
            if not tables:
                return warnings

            for premise in premises:
                # Check if the claim matches any stained premise
                rows = conn.execute(
                    "SELECT premise_id, claim FROM premise_registry "
                    "WHERE json_extract_string(staining_record, '$.stained') = 'true' "
                    "AND claim = ? "
                    "LIMIT 1",
                    [premise.claim],
                ).fetchall()

                if rows:
                    warnings.append(
                        f"PROJECTION_WARNING: Premise claim matches stained premise "
                        f"{rows[0][0]}. Previous instance was invalidated. "
                        f"Re-validate before proceeding."
                    )
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Stained premise check failed (fail-open): %s", e)

    return warnings


def _check_foil_instantiation(
    premises: list, session_id: str, cwd: str
) -> list[str]:
    """Check for historical foil matches with foil_path_outcomes.

    For each parsed premise with a non-null foil field, searches the registry
    for historical premises whose claim matches the foil text. If matches exist
    and have non-null foil_path_outcomes, emits PROJECTION_WARNING: FOIL_INSTANTIATED.

    Args:
        premises: List of ParsedPremise objects.
        session_id: Current session ID.
        cwd: Current working directory.

    Returns:
        List of warning messages for foil instantiation.
    """
    warnings: list[str] = []

    db_path = Path("data/ope.db")
    if not db_path.exists():
        return warnings

    try:
        import duckdb

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'premise_registry'"
            ).fetchall()
            if not tables:
                return warnings

            from src.pipeline.premise.registry import PremiseRegistry

            registry = PremiseRegistry(conn)

            for premise in premises:
                if not premise.foil:
                    continue

                matches = registry.find_by_foil(
                    premise.foil,
                    project_scope=cwd,
                    exclude_session=session_id,
                    limit=5,
                )

                for match in matches:
                    if match.foil_path_outcomes:
                        warnings.append(
                            f"PROJECTION_WARNING: FOIL_INSTANTIATED - "
                            f"Historical premise {match.premise_id} has foil "
                            f"path outcomes for foil '{premise.foil}'. "
                            f"Review divergence before proceeding."
                        )
                        break  # One warning per premise is sufficient
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Foil instantiation check failed (fail-open): %s", e)

    return warnings


def _check_ad_ignorantiam(
    premises: list, validation_calls: int
) -> list[str]:
    """Check for Ad Ignorantiam (RQR=0) on non-UNVALIDATED premises.

    Fires when validation_calls_before_claim == 0 AND the premise's
    validated_by does NOT start with "UNVALIDATED" (case-insensitive).

    Args:
        premises: List of ParsedPremise objects.
        validation_calls: Count of validation calls before claim.

    Returns:
        List of warning messages for Ad Ignorantiam.
    """
    if validation_calls > 0:
        return []

    warnings: list[str] = []
    for premise in premises:
        if not premise.is_unvalidated:
            warnings.append(
                f"AD_IGNORANTIAM: Premise claims validation "
                f"('{premise.validated_by[:60]}...') but "
                f"validation_calls_before_claim=0 (RQR=0). "
                f"No Read/Grep/Glob/WebFetch calls found since last user message."
            )

    return warnings


def _extract_axes_from_premises(premises: list, conn) -> list[str]:
    """Extract CCD axis names mentioned across all premises.

    Matches premise claim and scope text against known CCD axes
    from the memory_candidates table.

    Args:
        premises: List of ParsedPremise objects.
        conn: DuckDB connection (read-only).

    Returns:
        List of matching CCD axis names.
    """
    try:
        axes_rows = conn.execute(
            "SELECT DISTINCT ccd_axis FROM memory_candidates"
        ).fetchall()
    except Exception:
        return []

    known_axes = [row[0] for row in axes_rows]
    if not known_axes:
        return []

    found: set[str] = set()
    for premise in premises:
        claim = premise.claim if hasattr(premise, "claim") else str(premise)
        scope = premise.scope if hasattr(premise, "scope") else ""
        text = (claim + " " + (scope or "")).lower()
        for axis in known_axes:
            if axis.lower() in text:
                found.add(axis)

    return list(found)


def _extract_axes_from_single_premise(premise, conn) -> list[str]:
    """Extract CCD axis names from a single premise.

    Args:
        premise: A ParsedPremise object.
        conn: DuckDB connection (read-only).

    Returns:
        List of matching CCD axis names.
    """
    try:
        axes_rows = conn.execute(
            "SELECT DISTINCT ccd_axis FROM memory_candidates"
        ).fetchall()
    except Exception:
        return []

    known_axes = [row[0] for row in axes_rows]
    found: set[str] = set()
    claim = premise.claim if hasattr(premise, "claim") else str(premise)
    scope = premise.scope if hasattr(premise, "scope") else ""
    text = (claim + " " + (scope or "")).lower()
    for axis in known_axes:
        if axis.lower() in text:
            found.add(axis)

    return list(found)


def _check_frontier_warning(
    premises: list, session_id: str, cwd: str
) -> list[str]:
    """Check for Frontier Warnings: axis pairs with no recorded edge.

    Uses READ-ONLY DuckDB. Wrapped in try/except (fail-open).

    Args:
        premises: List of ParsedPremise objects.
        session_id: Current session ID.
        cwd: Current working directory.

    Returns:
        List of FRONTIER_WARNING strings.
    """
    warnings: list[str] = []

    db_path = Path("data/ope.db")
    if not db_path.exists():
        return warnings

    try:
        import duckdb

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'axis_edges'"
            ).fetchall()
            if not tables:
                return warnings

            from src.pipeline.ddf.topology.frontier import FrontierChecker

            checker = FrontierChecker(conn)
            active_axes = _extract_axes_from_premises(premises, conn)
            if len(active_axes) >= 2:
                warnings = checker.check_frontier(active_axes)
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Frontier warning check failed (fail-open): %s", e)

    return warnings


def _check_cross_axis(
    premises: list, session_id: str, cwd: str
) -> list[str]:
    """Check premise claims against recorded cross-axis edges.

    Uses READ-ONLY DuckDB. Wrapped in try/except (fail-open).

    Args:
        premises: List of ParsedPremise objects.
        session_id: Current session ID.
        cwd: Current working directory.

    Returns:
        List of CROSS_AXIS_WARNING strings.
    """
    warnings: list[str] = []

    db_path = Path("data/ope.db")
    if not db_path.exists():
        return warnings

    try:
        import duckdb

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'axis_edges'"
            ).fetchall()
            if not tables:
                return warnings

            from src.pipeline.ddf.topology.verifier import CrossAxisVerifier

            verifier = CrossAxisVerifier(conn)
            for premise in premises:
                active_axes = _extract_axes_from_single_premise(premise, conn)
                if len(active_axes) >= 2:
                    pair_warnings = verifier.verify_premise(
                        premise_axes=active_axes,
                        premise_claim=(
                            premise.claim
                            if hasattr(premise, "claim")
                            else str(premise)
                        ),
                    )
                    warnings.extend(pair_warnings)
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cross-axis check failed (fail-open): %s", e)

    return warnings


def main() -> None:
    """PAG PreToolUse hook entry point.

    Reads JSON from stdin, processes PREMISE blocks, stages records,
    checks for warnings, and emits response on stdout.

    Always exits 0 (allow). Phase 14.1 does NOT block tool calls.
    """
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "")
    tool_input = hook_input.get("tool_input", {})
    cwd = hook_input.get("cwd", "")

    # Gate check: only activate for write-class tools
    if tool_name not in WRITE_CLASS:
        sys.exit(0)

    # Read transcript for recent assistant text
    texts = read_recent_assistant_text(transcript_path)

    # Parse PREMISE blocks from assistant text
    all_premises = []
    for text in texts:
        all_premises.extend(parse_premise_blocks(text))

    # Handle no PREMISE found: fail-open
    if not all_premises:
        logger.debug(
            "No PREMISE blocks found for write-class tool %s (fail-open)",
            tool_name,
        )
        sys.exit(0)

    # Count validation calls for Ad Ignorantiam detection
    validation_calls = count_validation_calls_since_last_user(transcript_path)

    # Build staging records
    now_iso = datetime.now(timezone.utc).isoformat()
    tool_use_id = tool_input.get("id", "") or f"{tool_name}_{now_iso}"

    records: list[dict] = []
    for premise in all_premises:
        premise_id = PremiseRecord.make_id(premise.claim, session_id, tool_use_id)
        record = {
            "premise_id": premise_id,
            "claim": premise.claim,
            "validated_by": premise.validated_by,
            "validation_context": None,
            "foil": premise.foil,
            "distinguishing_prop": premise.distinguishing_prop,
            "staleness_counter": 0,
            "staining_record": None,
            "ground_truth_pointer": None,
            "project_scope": cwd,
            "session_id": session_id,
            "tool_use_id": tool_use_id,
            "foil_path_outcomes": None,
            "divergence_patterns": None,
            "parent_episode_links": None,
            "derivation_depth": 0,
            "validation_calls_before_claim": validation_calls,
            "derivation_chain": (
                [{"derives_from": ref["derives_from"]} for ref in premise.derivation_chain]
                if premise.derivation_chain
                else None
            ),
            "scope": premise.scope,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        records.append(record)

    # Write to staging (never to ope.db)
    append_to_staging(records)

    # Check for warnings
    additional_context: list[str] = []

    # 1. UNVALIDATED on high-risk file
    if _is_high_risk_path(tool_input, cwd):
        for premise in all_premises:
            if premise.is_unvalidated:
                additional_context.append(
                    f"WARNING: UNVALIDATED premise on high-risk file. "
                    f"Claim: '{premise.claim[:80]}'. "
                    f"Validate before mutating critical paths."
                )

    # 2. Stained premise check
    stained_warnings = _check_stained_premises(all_premises, session_id, cwd)
    additional_context.extend(stained_warnings)

    # 3. Foil instantiation check
    foil_warnings = _check_foil_instantiation(all_premises, session_id, cwd)
    additional_context.extend(foil_warnings)

    # 4. Ad Ignorantiam detection (RQR=0)
    ad_warnings = _check_ad_ignorantiam(all_premises, validation_calls)
    additional_context.extend(ad_warnings)

    # 5. Phase 16.1: Frontier Warning check
    frontier_warnings = _check_frontier_warning(all_premises, session_id, cwd)
    additional_context.extend(frontier_warnings)

    # 6. Phase 16.1: Cross-axis verification check
    cross_axis_warnings = _check_cross_axis(all_premises, session_id, cwd)
    additional_context.extend(cross_axis_warnings)

    # Emit response
    if additional_context:
        response = {
            "hookSpecificOutput": {
                "additionalContext": "\n".join(additional_context)
            }
        }
        json.dump(response, sys.stdout)

    sys.exit(0)


if __name__ == "__main__":
    main()
