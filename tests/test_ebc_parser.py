"""Tests for EBC PLAN.md frontmatter parser.

Covers valid parsing, must_haves extraction, edge cases, and
integration with a real PLAN.md file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.ebc.models import EBCArtifact, EBCKeyLink
from src.pipeline.ebc.parser import parse_ebc_from_plan


# --- Fixtures ---

VALID_FRONTMATTER = """\
---
phase: test-phase
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - src/foo.py
  - src/bar.py
autonomous: true

must_haves:
  truths:
    - "foo works correctly"
    - "bar handles errors"
  artifacts:
    - path: "src/foo.py"
      provides: "Foo class"
      exports: ["Foo"]
    - path: "tests/test_foo.py"
      provides: "Tests for Foo"
  key_links:
    - from: "src/foo.py"
      to: "src/bar.py"
      via: "import Bar"
      pattern: "from src.bar import"
---

<objective>
Test objective.
</objective>
"""

MINIMAL_FRONTMATTER = """\
---
phase: minimal-phase
plan: 2
---

Content here.
"""


class TestParseValidPlan:
    """Tests for successful PLAN.md parsing."""

    def test_parse_valid_returns_ebc(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(VALID_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert ebc.phase == "test-phase"
        assert ebc.plan == 1

    def test_parse_extracts_files_modified(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(VALID_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert ebc.files_modified == ["src/foo.py", "src/bar.py"]

    def test_parse_extracts_truths(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(VALID_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert len(ebc.truths) == 2
        assert "foo works correctly" in ebc.truths

    def test_parse_extracts_artifacts(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(VALID_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert len(ebc.artifacts) == 2
        assert isinstance(ebc.artifacts[0], EBCArtifact)
        assert ebc.artifacts[0].path == "src/foo.py"
        assert ebc.artifacts[0].exports == ["Foo"]

    def test_parse_extracts_key_links(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(VALID_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert len(ebc.key_links) == 1
        assert isinstance(ebc.key_links[0], EBCKeyLink)
        assert ebc.key_links[0].from_path == "src/foo.py"
        assert ebc.key_links[0].to_target == "src/bar.py"

    def test_parse_renames_type_to_plan_type(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(VALID_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert ebc.plan_type == "execute"

    def test_parse_handles_missing_must_haves(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text(MINIMAL_FRONTMATTER)
        ebc = parse_ebc_from_plan(plan_file)
        assert ebc is not None
        assert ebc.truths == []
        assert ebc.artifacts == []
        assert ebc.key_links == []


class TestParseInvalidPlan:
    """Tests for parser returning None on invalid input."""

    def test_nonexistent_file(self) -> None:
        result = parse_ebc_from_plan("/nonexistent/path/PLAN.md")
        assert result is None

    def test_no_frontmatter_markers(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text("Just some text without frontmatter.")
        result = parse_ebc_from_plan(plan_file)
        assert result is None

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text("---\n: invalid: yaml: [\n---\nContent\n")
        result = parse_ebc_from_plan(plan_file)
        assert result is None

    def test_only_one_marker(self, tmp_path: Path) -> None:
        """File with only opening --- but no closing ---."""
        plan_file = tmp_path / "PLAN.md"
        plan_file.write_text("---\nphase: test\nplan: 1\n")
        result = parse_ebc_from_plan(plan_file)
        assert result is None


class TestParseRealPlan:
    """Integration test using a real PLAN.md from the project."""

    @pytest.mark.skipif(
        not Path(
            ".planning/phases/22-unified-discriminated-query-interface/22-01-PLAN.md"
        ).exists(),
        reason="Real PLAN.md not available",
    )
    def test_parse_real_plan(self) -> None:
        plan_path = Path(
            ".planning/phases/22-unified-discriminated-query-interface/22-01-PLAN.md"
        )
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None
        assert ebc.phase == "22-unified-discriminated-query-interface"
        assert ebc.plan == 1
        assert len(ebc.files_modified) > 0
        assert len(ebc.artifacts) > 0
        assert len(ebc.truths) > 0
