"""Tests for EBC Drift Detector.

Covers detection logic, write path extraction, tolerance patterns,
drift scoring, and signal generation.
"""

from __future__ import annotations

import pytest

from src.pipeline.ebc.detector import EBCDriftDetector
from src.pipeline.ebc.models import EBCArtifact, ExternalBehavioralContract
from src.pipeline.models.config import PipelineConfig


# --- Helpers ---

def _make_config(**overrides) -> PipelineConfig:
    """Create a PipelineConfig with optional ebc_drift overrides."""
    ebc_drift = {
        "enabled": True,
        "threshold": 0.5,
        "ratio_only_threshold": 0.8,
        "tolerance_patterns": ["__init__.py", "__pycache__", "*.pyc"],
        "write_tool_names": ["Edit", "Write"],
        "bash_write_indicators": ["mkdir", "cp ", "mv ", "touch ", "> ", ">> "],
    }
    ebc_drift.update(overrides)
    return PipelineConfig(ebc_drift=ebc_drift)


def _make_event(tool_name: str, file_path: str = "", text: str = "") -> dict:
    """Create a mock session event dict matching read_events() structure."""
    payload: dict = {
        "common": {
            "tool_name": tool_name,
            "text": text,
        },
    }
    if file_path:
        payload["details"] = {"file_path": file_path}
    return {
        "event_id": f"evt-{tool_name}-{file_path}",
        "ts_utc": "2026-01-01T00:00:00Z",
        "session_id": "test-session",
        "actor": "assistant",
        "event_type": "tool_use",
        "primary_tag": None,
        "payload": payload,
    }


def _make_ebc(files_modified: list[str], artifacts: list[str] | None = None) -> ExternalBehavioralContract:
    """Create a minimal EBC with given expected files."""
    artifact_objs = []
    if artifacts:
        artifact_objs = [EBCArtifact(path=p) for p in artifacts]
    return ExternalBehavioralContract(
        phase="test-phase",
        plan=1,
        files_modified=files_modified,
        artifacts=artifact_objs,
    )


# --- Tests ---

class TestDetectNoDrift:
    """Tests where no drift is detected."""

    def test_no_drift_when_all_files_match(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py", "src/b.py"])
        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/b.py"),
        ]
        result = detector.detect(ebc, events, "sess-1")
        assert result is None

    def test_no_drift_when_below_threshold(self) -> None:
        """Small drift that doesn't exceed the 0.5 threshold."""
        config = _make_config(threshold=0.5)
        detector = EBCDriftDetector(config)
        # 10 expected files, 1 missing = 0.3/10 = 0.03 drift
        ebc = _make_ebc([f"src/f{i}.py" for i in range(10)])
        events = [_make_event("Edit", f"src/f{i}.py") for i in range(9)]
        result = detector.detect(ebc, events, "sess-1")
        assert result is None

    def test_empty_ebc_returns_none(self) -> None:
        """No contract to violate = no drift."""
        config = _make_config()
        detector = EBCDriftDetector(config)
        ebc = _make_ebc([])
        events = [_make_event("Edit", "src/surprise.py")]
        result = detector.detect(ebc, events, "sess-1")
        assert result is None


class TestDetectDrift:
    """Tests where drift is detected."""

    def test_unexpected_files_trigger_alert(self) -> None:
        config = _make_config(threshold=0.3)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py"])
        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/unexpected.py"),
        ]
        result = detector.detect(ebc, events, "sess-1")
        assert result is not None
        assert result.drift_score > 0
        assert "src/unexpected.py" in result.unexpected_files

    def test_missing_files_contribute_weight_0_3(self) -> None:
        """Missing expected files have 0.3 weight each."""
        config = _make_config(threshold=0.1)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py", "src/b.py"])
        # No writes at all -> 2 missing * 0.3 = 0.6 / 2 = 0.3
        events = []
        result = detector.detect(ebc, events, "sess-1")
        assert result is not None
        assert len(result.missing_expected_files) == 2
        assert abs(result.drift_score - 0.3) < 0.01

    def test_drift_score_exceeds_threshold(self) -> None:
        config = _make_config(threshold=0.5)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py"])
        # 1 unexpected (weight 1.0) + 1 missing (weight 0.3) = 1.3 / 1 = 1.0 (capped)
        events = [_make_event("Edit", "src/unexpected.py")]
        result = detector.detect(ebc, events, "sess-1")
        assert result is not None
        assert result.drift_score == 1.0

    def test_drift_score_capped_at_1(self) -> None:
        config = _make_config(threshold=0.1)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py"])
        # 5 unexpected files (weight 5.0) / 1 expected -> capped at 1.0
        events = [_make_event("Edit", f"src/u{i}.py") for i in range(5)]
        result = detector.detect(ebc, events, "sess-1")
        assert result is not None
        assert result.drift_score == 1.0

    def test_alert_has_correct_metadata(self) -> None:
        config = _make_config(threshold=0.1)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py"])
        events = [_make_event("Write", "src/unexpected.py")]
        result = detector.detect(ebc, events, "sess-42")
        assert result is not None
        assert result.session_id == "sess-42"
        assert result.ebc_phase == "test-phase"
        assert result.ebc_plan == "1"
        assert "src/unexpected.py" in result.unexpected_files
        assert "src/a.py" in result.missing_expected_files


class TestTolerancePatterns:
    """Tests for tolerance pattern filtering."""

    def test_init_py_filtered(self) -> None:
        config = _make_config(threshold=0.1)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py"])
        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/pipeline/__init__.py"),
        ]
        result = detector.detect(ebc, events, "sess-1")
        assert result is None

    def test_pyc_files_filtered(self) -> None:
        config = _make_config(threshold=0.1)
        detector = EBCDriftDetector(config)
        ebc = _make_ebc(["src/a.py"])
        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/cache.pyc"),
        ]
        result = detector.detect(ebc, events, "sess-1")
        assert result is None


class TestExtractWritePaths:
    """Tests for write path extraction from events."""

    def test_edit_tool_extracted(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        events = [_make_event("Edit", "src/a.py")]
        paths = detector._extract_write_paths(events)
        assert paths == {"src/a.py"}

    def test_write_tool_extracted(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        events = [_make_event("Write", "src/b.py")]
        paths = detector._extract_write_paths(events)
        assert paths == {"src/b.py"}

    def test_read_tool_ignored(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        events = [
            _make_event("Read", "src/a.py"),
            _make_event("Glob", ""),
            _make_event("Grep", ""),
        ]
        paths = detector._extract_write_paths(events)
        assert paths == set()

    def test_extracts_file_path_from_details(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        event = {
            "event_id": "evt-1",
            "payload": {
                "common": {"tool_name": "Edit"},
                "details": {"file_path": "src/deep/nested/file.py"},
            },
        }
        paths = detector._extract_write_paths([event])
        assert "src/deep/nested/file.py" in paths

    def test_missing_payload_gracefully_handled(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        events = [{"event_id": "evt-1"}]
        paths = detector._extract_write_paths(events)
        assert paths == set()

    def test_missing_details_gracefully_handled(self) -> None:
        config = _make_config()
        detector = EBCDriftDetector(config)
        events = [{"event_id": "evt-1", "payload": {"common": {"tool_name": "Edit"}}}]
        paths = detector._extract_write_paths(events)
        assert paths == set()
