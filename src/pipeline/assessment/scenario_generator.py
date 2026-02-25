"""Scenario generator for Candidate Assessment System (Phase 17).

Generates calibrated pile problems from project_wisdom entries. Each scenario
produces two files (briefing + broken implementation), with L5-L7 scenarios
including a plausible-but-wrong CLAUDE.md handicap framing.

DDF-level-to-entity-type mapping:
- breakthrough -> L1-L2
- dead_end -> L2-L4
- scope_decision + dead_end composite -> L5-L7

Exports:
    ScenarioGenerator
    generate_scenario
"""

from __future__ import annotations

import logging
import subprocess
import textwrap
from pathlib import Path

import duckdb

from src.pipeline.assessment.models import ScenarioSpec

logger = logging.getLogger(__name__)

# Expected DDF level ranges per entity type
_ENTITY_TYPE_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "breakthrough": (1, 2),
    "dead_end": (2, 4),
    "scope_decision": (5, 7),
    "method_decision": (3, 5),
}

BROKEN_IMPL_TEMPLATE = textwrap.dedent('''\
    """Assessment scenario: {title}

    Run: python broken_impl.py
    """


    {seed_code}

    if __name__ == "__main__":
        main()
''')

_DEFAULT_SEED_TEMPLATE = textwrap.dedent('''\
    def main():
        """Entrypoint that demonstrates the failure symptom."""
        # This implementation contains the bug described in the scenario context.
        # The candidate must identify the root cause and fix it.
        raise RuntimeError(
            "Scenario symptom: {symptom}"
        )
''')

_HANDICAP_TEMPLATE = textwrap.dedent('''\
    # Project Analysis

    ## Known Issue

    The implementation file has a known issue related to **{wrong_component}**.

    ### Root Cause Analysis

    {wrong_framing}

    The most likely cause is **{wrong_cause}**.

    ### Suggested Fix

    {wrong_fix}

    ### Focus Area

    Concentrate your debugging on **{wrong_focus}**.
''')


class ScenarioGenerator:
    """Generates assessment scenarios from project_wisdom entries.

    Each scenario consists of:
    1. A scenario_context.md briefing file
    2. A broken implementation file that fails when executed
    3. (L5-L7 only) A plausible-but-wrong CLAUDE.md handicap framing

    Args:
        conn: DuckDB connection with project_wisdom table.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def generate_scenario(self, wisdom_id: str) -> ScenarioSpec:
        """Generate a ScenarioSpec from a project_wisdom entry.

        Queries the wisdom entry, validates annotation, builds scenario
        context, broken implementation, and optional handicap framing.

        Args:
            wisdom_id: The wisdom_id to generate a scenario from.

        Returns:
            ScenarioSpec with all fields populated.

        Raises:
            ValueError: If wisdom_id not found or ddf_target_level is NULL.
        """
        row = self._conn.execute(
            "SELECT wisdom_id, entity_type, title, description, "
            "scenario_seed, ddf_target_level "
            "FROM project_wisdom WHERE wisdom_id = ?",
            [wisdom_id],
        ).fetchone()

        if row is None:
            raise ValueError(f"Wisdom entry not found: {wisdom_id}")

        w_id, entity_type, title, description, scenario_seed, ddf_target_level = row

        if ddf_target_level is None:
            raise ValueError(
                f"Wisdom entry {wisdom_id} has no ddf_target_level annotation. "
                "Run 'annotate-scenarios' first."
            )

        # Warn if entity_type doesn't match expected DDF level range
        self._check_level_entity_match(entity_type, ddf_target_level, wisdom_id)

        scenario_id = ScenarioSpec.make_id(w_id, ddf_target_level)

        # Build scenario context (strip solution hints from description)
        scenario_context = self._build_scenario_context(title, description)

        # Build broken implementation
        broken_impl_content = self._build_broken_impl(
            title, description, scenario_seed
        )

        # Build handicap CLAUDE.md (only for L5-L7)
        handicap_claude_md = None
        if ddf_target_level >= 5:
            handicap_claude_md = self._build_handicap(
                title, description, entity_type
            )

        return ScenarioSpec(
            scenario_id=scenario_id,
            wisdom_id=w_id,
            ddf_target_level=ddf_target_level,
            entity_type=entity_type,
            title=title,
            scenario_context=scenario_context,
            broken_impl_filename="broken_impl.py",
            broken_impl_content=broken_impl_content,
            handicap_claude_md=handicap_claude_md,
            scenario_seed=scenario_seed,
        )

    def generate_scenario_files(
        self, spec: ScenarioSpec, output_dir: Path
    ) -> tuple[Path, Path, Path | None]:
        """Write scenario files to the output directory.

        Args:
            spec: ScenarioSpec with content to write.
            output_dir: Directory to write files into.

        Returns:
            Tuple of (context_path, impl_path, claude_md_path or None).
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        context_path = output_dir / "scenario_context.md"
        context_path.write_text(spec.scenario_context, encoding="utf-8")

        impl_path = output_dir / spec.broken_impl_filename
        impl_path.write_text(spec.broken_impl_content, encoding="utf-8")

        claude_md_path = None
        if spec.handicap_claude_md:
            claude_dir = output_dir / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            claude_md_path = claude_dir / "CLAUDE.md"
            claude_md_path.write_text(
                spec.handicap_claude_md, encoding="utf-8"
            )

        return context_path, impl_path, claude_md_path

    def validate_broken_impl(
        self, spec: ScenarioSpec, output_dir: Path
    ) -> bool:
        """Validate that the broken implementation fails when executed.

        Args:
            spec: ScenarioSpec containing the broken implementation.
            output_dir: Directory where the implementation file was written.

        Returns:
            True if exit code != 0 (correctly fails).
            False if exit code == 0 (unexpectedly succeeds).
        """
        impl_path = output_dir / spec.broken_impl_filename
        if not impl_path.exists():
            logger.warning("Broken impl file not found: %s", impl_path)
            return False

        try:
            result = subprocess.run(
                ["python", str(impl_path)],
                capture_output=True,
                timeout=30,
            )
            return result.returncode != 0
        except subprocess.TimeoutExpired:
            logger.warning("Broken impl timed out (30s): %s", impl_path)
            return True  # Timeout is still a failure (non-zero exit)

    def _check_level_entity_match(
        self, entity_type: str, level: int, wisdom_id: str
    ) -> None:
        """Warn if entity_type doesn't match expected DDF level range."""
        expected_range = _ENTITY_TYPE_LEVEL_RANGES.get(entity_type)
        if expected_range is None:
            logger.warning(
                "Unknown entity_type '%s' for wisdom %s",
                entity_type, wisdom_id,
            )
            return
        lo, hi = expected_range
        if not lo <= level <= hi:
            logger.warning(
                "Wisdom %s: entity_type '%s' typically maps to L%d-L%d, "
                "but ddf_target_level is %d",
                wisdom_id, entity_type, lo, hi, level,
            )

    def _build_scenario_context(self, title: str, description: str) -> str:
        """Build the scenario context markdown from title and description.

        Strips solution hints (lines containing 'solution:', 'fix:', 'answer:')
        from the description to avoid giving away the answer.
        """
        # Strip solution hints from description
        cleaned_lines = []
        for line in description.split("\n"):
            lower = line.lower().strip()
            if any(
                lower.startswith(hint)
                for hint in ("solution:", "fix:", "answer:", "resolution:")
            ):
                continue
            cleaned_lines.append(line)
        cleaned_description = "\n".join(cleaned_lines).strip()

        return (
            f"# Assessment Scenario: {title}\n\n"
            f"## Context\n\n{cleaned_description}\n\n"
            f"## Task\n\n"
            f"Your task is to diagnose and fix the issue in the "
            f"provided implementation file.\n"
        )

    def _build_broken_impl(
        self, title: str, description: str, scenario_seed: str | None
    ) -> str:
        """Build broken Python implementation content.

        If scenario_seed exists, uses it as the basis. Otherwise generates
        a minimal Python file that raises an exception demonstrating the symptom.
        """
        if scenario_seed:
            seed_code = scenario_seed
        else:
            # Extract a symptom hint from the description (first sentence)
            symptom = description.split(".")[0][:100] if description else title
            seed_code = _DEFAULT_SEED_TEMPLATE.format(symptom=symptom)

        return BROKEN_IMPL_TEMPLATE.format(
            title=title,
            seed_code=seed_code,
        )

    def _build_handicap(
        self,
        title: str,
        description: str,
        entity_type: str,
        floating_cable_context: str | None = None,
    ) -> str:
        """Build plausible-but-wrong CLAUDE.md handicap for L5-L7 scenarios.

        Creates a surface-level analysis that points to the wrong root cause,
        designed to test whether the candidate can resist the framing.

        Args:
            title: Scenario title.
            description: Scenario description.
            entity_type: Entity type from project_wisdom.
            floating_cable_context: Optional floating-cable awareness text.
                When provided, appends an AI Analysis Notes section.

        Returns:
            Handicap markdown string.
        """
        # Generate plausible-but-wrong analysis components
        wrong_component = "configuration handling"
        wrong_cause = "incorrect parameter ordering in the initialization sequence"
        wrong_framing = (
            f"The {title.lower()} issue appears to be a straightforward "
            f"configuration problem. Initial analysis suggests the "
            f"implementation fails due to a surface-level setup error."
        )
        wrong_fix = (
            f"Review the initialization parameters and ensure they match "
            f"the expected order. This is likely a simple ordering issue."
        )
        wrong_focus = "initialization and configuration code paths"

        handicap = _HANDICAP_TEMPLATE.format(
            wrong_component=wrong_component,
            wrong_framing=wrong_framing,
            wrong_cause=wrong_cause,
            wrong_fix=wrong_fix,
            wrong_focus=wrong_focus,
        )

        if floating_cable_context:
            handicap += textwrap.dedent(f"""\

            ### AI Analysis Notes

            {floating_cable_context}
            """)

        return handicap


def generate_scenario(
    conn: duckdb.DuckDBPyConnection, wisdom_id: str
) -> ScenarioSpec:
    """Convenience function to generate a scenario from a wisdom entry.

    Args:
        conn: DuckDB connection with project_wisdom table.
        wisdom_id: The wisdom_id to generate a scenario from.

    Returns:
        ScenarioSpec with all fields populated.
    """
    return ScenarioGenerator(conn).generate_scenario(wisdom_id)
