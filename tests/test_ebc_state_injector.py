"""Tests for STATE.md sentinel-based injection of EBC drift warnings.

Validates that inject_alert_into_state() correctly handles:
- Appending when no sentinels or Performance Metrics exist
- Replacing content between existing sentinels
- Inserting before Performance Metrics section
- Preserving non-sentinel content
- Edge cases (empty alerts, nonexistent files, double injection)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.ebc.state_injector import (
    SENTINEL_END,
    SENTINEL_START,
    inject_alert_into_state,
)


SAMPLE_ALERT = (
    "> **WARNING:** Session `test-123` drifted from EBC\n"
    "> - Phase: 23, Plan: 02\n"
    "> - Alert artifact: `data/alerts/test-123-ebc-drift.json`\n"
    "> - Recovery: Run `/project:autonomous-loop-mode-switch` for options"
)

SECOND_ALERT = (
    "> **WARNING:** Session `test-456` drifted from EBC\n"
    "> - Phase: 23, Plan: 03"
)


class TestInjectionNoSentinels:
    """Tests for injection into files without existing sentinel blocks."""

    def test_injection_no_sentinels_appends_at_end(self, tmp_path: Path):
        """File without sentinels or Performance Metrics: content appended at end."""
        state = tmp_path / "STATE.md"
        state.write_text("# Project State\n\nSome content here.\n", encoding="utf-8")

        result = inject_alert_into_state(state, SAMPLE_ALERT)

        assert result is True
        content = state.read_text(encoding="utf-8")
        assert SENTINEL_START in content
        assert SENTINEL_END in content
        assert "## EBC Drift Alerts" in content
        assert SAMPLE_ALERT in content
        # Sentinel block should be at the end
        assert content.index("Some content here.") < content.index(SENTINEL_START)

    def test_injection_before_performance_metrics(self, tmp_path: Path):
        """File with '## Performance Metrics': content inserted before it."""
        state = tmp_path / "STATE.md"
        state.write_text(
            "# Project State\n\n## Performance Metrics\n\nVelocity: fast\n",
            encoding="utf-8",
        )

        result = inject_alert_into_state(state, SAMPLE_ALERT)

        assert result is True
        content = state.read_text(encoding="utf-8")
        assert SENTINEL_START in content
        # Sentinel block should be BEFORE Performance Metrics
        assert content.index(SENTINEL_END) < content.index("## Performance Metrics")

    def test_returns_false_for_nonexistent_file(self, tmp_path: Path):
        """Returns False when file doesn't exist."""
        state = tmp_path / "NONEXISTENT.md"
        result = inject_alert_into_state(state, SAMPLE_ALERT)
        assert result is False


class TestInjectionWithExistingSentinels:
    """Tests for injection into files with existing sentinel blocks."""

    def test_injection_with_existing_sentinels_replaces(self, tmp_path: Path):
        """File with existing sentinels: content between replaced."""
        state = tmp_path / "STATE.md"
        state.write_text(
            f"# State\n\n{SENTINEL_START}\n## EBC Drift Alerts\n\nOld alert\n{SENTINEL_END}\n\n## Footer\n",
            encoding="utf-8",
        )

        result = inject_alert_into_state(state, SAMPLE_ALERT)

        assert result is True
        content = state.read_text(encoding="utf-8")
        assert "Old alert" not in content
        assert SAMPLE_ALERT in content
        assert "## Footer" in content

    def test_double_injection_single_block(self, tmp_path: Path):
        """Inject twice: only one sentinel block in result."""
        state = tmp_path / "STATE.md"
        state.write_text("# State\n", encoding="utf-8")

        inject_alert_into_state(state, SAMPLE_ALERT)
        inject_alert_into_state(state, SECOND_ALERT)

        content = state.read_text(encoding="utf-8")
        assert content.count(SENTINEL_START) == 1
        assert content.count(SENTINEL_END) == 1
        # Second alert should be present, first should be replaced
        assert SECOND_ALERT in content
        assert "test-123" not in content

    def test_content_between_sentinels_fully_replaced(self, tmp_path: Path):
        """Second injection with different content replaces, not appends."""
        state = tmp_path / "STATE.md"
        state.write_text("# State\n", encoding="utf-8")

        inject_alert_into_state(state, SAMPLE_ALERT)
        content_after_first = state.read_text(encoding="utf-8")
        assert "test-123" in content_after_first

        inject_alert_into_state(state, SECOND_ALERT)
        content_after_second = state.read_text(encoding="utf-8")
        assert "test-456" in content_after_second
        assert "test-123" not in content_after_second


class TestInjectionContentPreservation:
    """Tests for content integrity during injection."""

    def test_injection_preserves_other_content(self, tmp_path: Path):
        """All non-sentinel content preserved."""
        original_content = (
            "# Project State\n\n"
            "## Current Position\n\n"
            "Phase: 23\n\n"
            "## Decisions\n\n"
            "| ID | Decision |\n"
            "|----|---------|\n"
            "| 1  | Use EBC  |\n"
        )
        state = tmp_path / "STATE.md"
        state.write_text(original_content, encoding="utf-8")

        inject_alert_into_state(state, SAMPLE_ALERT)

        content = state.read_text(encoding="utf-8")
        assert "## Current Position" in content
        assert "Phase: 23" in content
        assert "## Decisions" in content
        assert "| Use EBC  |" in content

    def test_injection_with_empty_alert_block(self, tmp_path: Path):
        """Empty alert_block still creates valid section with sentinels."""
        state = tmp_path / "STATE.md"
        state.write_text("# State\n", encoding="utf-8")

        result = inject_alert_into_state(state, "")

        assert result is True
        content = state.read_text(encoding="utf-8")
        assert SENTINEL_START in content
        assert SENTINEL_END in content
        assert "## EBC Drift Alerts" in content

    def test_sentinels_are_html_comments(self, tmp_path: Path):
        """Sentinels start with <!-- (valid HTML comments)."""
        assert SENTINEL_START.startswith("<!--")
        assert SENTINEL_START.endswith("-->")
        assert SENTINEL_END.startswith("<!--")
        assert SENTINEL_END.endswith("-->")


class TestRealisticStateMd:
    """Tests using realistic STATE.md content."""

    def test_realistic_state_md_snippet(self, tmp_path: Path):
        """Use a realistic STATE.md structure as fixture text."""
        realistic_content = (
            "# Project State\n\n"
            "## Project Reference\n\n"
            "See: .planning/PROJECT.md\n\n"
            "## Current Position\n\n"
            "Phase: 23 (Autonomous Loop Mode-Switch Detection)\n"
            "Plan: 1 of 3 complete\n"
            "Status: In progress\n\n"
            "Progress: [###########.....] 33%\n\n"
            "## Performance Metrics\n\n"
            "**Velocity:**\n"
            "- Total plans completed: 94\n"
        )
        state = tmp_path / "STATE.md"
        state.write_text(realistic_content, encoding="utf-8")

        result = inject_alert_into_state(state, SAMPLE_ALERT)

        assert result is True
        content = state.read_text(encoding="utf-8")
        # Alert should be between Progress and Performance Metrics
        assert content.index(SENTINEL_END) < content.index("## Performance Metrics")
        assert content.index("Progress:") < content.index(SENTINEL_START)
        # All original content preserved
        assert "Phase: 23" in content
        assert "Total plans completed: 94" in content
