"""Tests for the governance CLI commands (govern ingest, govern check-stability).

Uses click.testing.CliRunner to invoke commands. Uses tmp_path for file
isolation to avoid mutating the real constraints file or DuckDB database.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli


@pytest.fixture
def runner() -> CliRunner:
    """Click CliRunner for testing."""
    return CliRunner()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Copy the real config.yaml to tmp_path for test isolation."""
    src = Path("data/config.yaml")
    dst = tmp_path / "config.yaml"
    shutil.copy(src, dst)
    return dst


@pytest.fixture
def premortem_fixture(tmp_path: Path) -> Path:
    """Small pre-mortem fixture with 2 stories and 3 assumptions."""
    content = """# Test Pre-Mortem

## Failure Stories

### Story 1: Bad Library Choice
We tried using pybreaker but it uses consecutive failure counting.

### Story 2: Wrong Upload Pattern
The single-step upload assumption was incorrect.

## Key Assumptions

- Actual scan result counts must be verified by machine-checkable queries
- Constraint violations must never be silently overridden
- All uploads must be gated on completion verification
"""
    p = tmp_path / "test_premortem.md"
    p.write_text(content)
    return p


@pytest.fixture
def empty_fixture(tmp_path: Path) -> Path:
    """Markdown fixture with no governance sections."""
    content = """# Just a Title

Some text with no governance sections at all.
"""
    p = tmp_path / "empty.md"
    p.write_text(content)
    return p


def _make_stability_config(tmp_path: Path, stability_checks: list) -> Path:
    """Create a config YAML with specified stability checks.

    Copies real config.yaml and overrides the governance section.
    """
    src = Path("data/config.yaml")
    with open(src) as f:
        config = yaml.safe_load(f)

    config["governance"] = {
        "bulk_ingest_threshold": 5,
        "stability_checks": stability_checks,
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config))
    return config_path


# --- Help tests ---


class TestGovernHelp:
    """Tests for govern help output."""

    def test_govern_help_shows_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["govern", "--help"])
        assert result.exit_code == 0
        assert "ingest" in result.output
        assert "check-stability" in result.output

    def test_main_help_shows_govern(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "govern" in result.output


# --- Ingest tests ---


class TestGovernIngest:
    """Tests for govern ingest command."""

    def test_ingest_dry_run(
        self,
        runner: CliRunner,
        premortem_fixture: Path,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        constraints_path = tmp_path / "c.json"
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "ingest",
                str(premortem_fixture),
                "--dry-run",
                "--db",
                db_path,
                "--constraints",
                str(constraints_path),
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "DRY RUN" in result.output
        assert "Constraints:" in result.output
        assert "Wisdom:" in result.output
        # Dry run should not create constraints file
        assert not constraints_path.exists()

    def test_ingest_writes(
        self,
        runner: CliRunner,
        premortem_fixture: Path,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        constraints_path = tmp_path / "c.json"
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "ingest",
                str(premortem_fixture),
                "--db",
                db_path,
                "--constraints",
                str(constraints_path),
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "3 added" in result.output  # 3 constraints
        assert "2 added" in result.output  # 2 wisdom
        # Constraints file should now exist
        assert constraints_path.exists()

    def test_ingest_empty_doc_exits_2(
        self,
        runner: CliRunner,
        empty_fixture: Path,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "ingest",
                str(empty_fixture),
                "--db",
                db_path,
                "--constraints",
                str(tmp_path / "c.json"),
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 2
        assert "No entities extracted" in result.output

    def test_ingest_with_source_id(
        self,
        runner: CliRunner,
        premortem_fixture: Path,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "ingest",
                str(premortem_fixture),
                "--source-id",
                "custom-doc-id",
                "--db",
                db_path,
                "--constraints",
                str(tmp_path / "c.json"),
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"

        # Verify the wisdom entities have the custom source_id
        from src.pipeline.wisdom.store import WisdomStore

        store = WisdomStore(db_path=Path(db_path))
        entities = store.list()
        for entity in entities:
            assert entity.source_document == "custom-doc-id"


# --- Check-stability tests ---


class TestGovernCheckStability:
    """Tests for govern check-stability command."""

    def test_no_stability_checks_configured(
        self,
        runner: CliRunner,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        # Real config already has empty stability_checks
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "check-stability",
                "--db",
                db_path,
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0
        assert "No stability checks configured" in result.output

    def test_passing_check(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        config_path = _make_stability_config(
            tmp_path,
            [{"id": "echo-check", "command": ["echo", "ok"], "description": "test"}],
        )
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "check-stability",
                "--db",
                db_path,
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "PASS" in result.output

    def test_failing_check(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        config_path = _make_stability_config(
            tmp_path,
            [{"id": "fail-check", "command": ["false"]}],
        )
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "check-stability",
                "--db",
                db_path,
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 2
        assert "FAIL" in result.output

    def test_json_output(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        config_path = _make_stability_config(
            tmp_path,
            [{"id": "echo-check", "command": ["echo", "ok"]}],
        )
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "check-stability",
                "--output",
                "json",
                "--db",
                db_path,
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert "outcomes" in data
        assert "all_passed" in data
        assert data["all_passed"] is True
        assert "missing_validation_flagged" in data
        assert "episodes_validated" in data
