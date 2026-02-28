"""Tests for --plan and --inject-state CLI flags on the extract command.

Validates that the extract CLI accepts the new EBC-related options,
parses PLAN.md files into EBCs, and handles error cases gracefully.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from src.pipeline.cli.extract import main


@pytest.fixture
def cli_runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def minimal_jsonl(tmp_path: Path) -> Path:
    """Create a minimal valid JSONL file for testing."""
    jsonl_path = tmp_path / "test-session.jsonl"
    # Minimal event structure that the loader can parse
    jsonl_path.write_text(
        '{"type":"tool_use","timestamp":"2024-01-01T00:00:00Z",'
        '"session_id":"test-session-123","message":{"role":"assistant"}}\n',
        encoding="utf-8",
    )
    return jsonl_path


@pytest.fixture
def valid_plan_md(tmp_path: Path) -> Path:
    """Create a minimal valid PLAN.md with frontmatter."""
    plan_path = tmp_path / "PLAN.md"
    plan_path.write_text(
        "---\n"
        "phase: 99-test\n"
        "plan: 01\n"
        "type: execute\n"
        "files_modified:\n"
        "  - src/foo.py\n"
        "---\n"
        "\n# Test Plan\n",
        encoding="utf-8",
    )
    return plan_path


@pytest.fixture
def no_frontmatter_file(tmp_path: Path) -> Path:
    """Create a file without YAML frontmatter."""
    path = tmp_path / "NO_FRONTMATTER.md"
    path.write_text("# Just a markdown file\n\nNo frontmatter here.\n", encoding="utf-8")
    return path


class TestPlanFlagAcceptance:
    """Tests that --plan and --inject-state flags are recognized by Click."""

    def test_help_shows_plan_flag(self, cli_runner: CliRunner):
        """extract --help output contains --plan."""
        result = cli_runner.invoke(main, ["--help"])
        assert "--plan" in result.output

    def test_help_shows_inject_state_flag(self, cli_runner: CliRunner):
        """extract --help output contains --inject-state."""
        result = cli_runner.invoke(main, ["--help"])
        assert "--inject-state" in result.output

    def test_plan_flag_accepted(
        self, cli_runner: CliRunner, minimal_jsonl: Path, valid_plan_md: Path
    ):
        """CliRunner invokes extract with --plan without 'no such option' error."""
        result = cli_runner.invoke(
            main,
            [
                str(minimal_jsonl),
                "--db", ":memory:",
                "--plan", str(valid_plan_md),
            ],
        )
        # Should not fail with 'no such option' -- may fail for other reasons
        assert "no such option" not in (result.output or "").lower()

    def test_inject_state_flag_accepted(
        self, cli_runner: CliRunner, minimal_jsonl: Path, tmp_path: Path
    ):
        """CliRunner invokes with --inject-state without 'no such option' error."""
        state_path = tmp_path / "STATE.md"
        state_path.write_text("# State\n", encoding="utf-8")
        result = cli_runner.invoke(
            main,
            [
                str(minimal_jsonl),
                "--db", ":memory:",
                "--inject-state", str(state_path),
            ],
        )
        assert "no such option" not in (result.output or "").lower()


class TestPlanFlagBehavior:
    """Tests for --plan flag behavior: EBC parsing, output messages."""

    def test_plan_flag_with_valid_plan(
        self, cli_runner: CliRunner, minimal_jsonl: Path, valid_plan_md: Path
    ):
        """With a valid PLAN.md, verify 'EBC loaded' message in output."""
        result = cli_runner.invoke(
            main,
            [
                str(minimal_jsonl),
                "--db", ":memory:",
                "--plan", str(valid_plan_md),
            ],
        )
        assert "EBC loaded from:" in result.output
        assert "phase=99-test" in result.output

    def test_plan_flag_with_invalid_path(self, cli_runner: CliRunner, minimal_jsonl: Path):
        """With nonexistent plan path, verify warning in output."""
        result = cli_runner.invoke(
            main,
            [
                str(minimal_jsonl),
                "--db", ":memory:",
                "--plan", "/nonexistent/path/PLAN.md",
            ],
        )
        # Should warn about parse failure (parser returns None for nonexistent)
        assert "Warning: Could not parse EBC" in result.output

    def test_plan_flag_with_parse_failure(
        self, cli_runner: CliRunner, minimal_jsonl: Path, no_frontmatter_file: Path
    ):
        """Provide a file without frontmatter, verify warning printed."""
        result = cli_runner.invoke(
            main,
            [
                str(minimal_jsonl),
                "--db", ":memory:",
                "--plan", str(no_frontmatter_file),
            ],
        )
        assert "Warning: Could not parse EBC" in result.output

    def test_without_plan_flag_no_ebc_message(
        self, cli_runner: CliRunner, minimal_jsonl: Path
    ):
        """Without --plan, output should not contain 'EBC loaded'."""
        result = cli_runner.invoke(
            main,
            [str(minimal_jsonl), "--db", ":memory:"],
        )
        assert "EBC loaded" not in result.output
