"""Tests for EBC alert writer.

Covers file creation, JSON validity, expected keys, directory creation,
and overwrite behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.ebc.models import DriftSignal, EBCDriftAlert
from src.pipeline.ebc.writer import write_alert


def _make_alert(session_id: str = "test-session") -> EBCDriftAlert:
    """Create a sample EBCDriftAlert for testing."""
    return EBCDriftAlert(
        session_id=session_id,
        drift_score=0.75,
        signals=[
            DriftSignal(
                signal_type="unexpected_file",
                detail="src/surprise.py",
                weight=1.0,
            ),
        ],
        ebc_phase="test-phase",
        ebc_plan="1",
        unexpected_files=["src/surprise.py"],
        missing_expected_files=["src/expected.py"],
    )


class TestWriteAlert:
    """Tests for write_alert function."""

    def test_creates_file_at_expected_path(self, tmp_path: Path) -> None:
        alert = _make_alert()
        result = write_alert(alert, alerts_dir=tmp_path)
        assert result == tmp_path / "test-session-ebc-drift.json"
        assert result.exists()

    def test_file_contains_valid_json(self, tmp_path: Path) -> None:
        alert = _make_alert()
        result = write_alert(alert, alerts_dir=tmp_path)
        content = result.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert isinstance(parsed, dict)

    def test_json_has_expected_keys(self, tmp_path: Path) -> None:
        alert = _make_alert()
        result = write_alert(alert, alerts_dir=tmp_path)
        parsed = json.loads(result.read_text())
        assert "session_id" in parsed
        assert "drift_score" in parsed
        assert "signals" in parsed
        assert "ebc_phase" in parsed
        assert "ebc_plan" in parsed
        assert parsed["session_id"] == "test-session"
        assert parsed["drift_score"] == 0.75

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        nested_dir = tmp_path / "nested" / "alerts"
        alert = _make_alert()
        result = write_alert(alert, alerts_dir=nested_dir)
        assert result.exists()
        assert nested_dir.exists()

    def test_overwrites_existing_alert(self, tmp_path: Path) -> None:
        alert1 = _make_alert()
        write_alert(alert1, alerts_dir=tmp_path)

        # Write a second alert with same session_id but different score
        alert2 = EBCDriftAlert(
            session_id="test-session",
            drift_score=0.99,
            signals=[],
            ebc_phase="p2",
            ebc_plan="2",
        )
        result = write_alert(alert2, alerts_dir=tmp_path)
        parsed = json.loads(result.read_text())
        assert parsed["drift_score"] == 0.99
        assert parsed["ebc_phase"] == "p2"
