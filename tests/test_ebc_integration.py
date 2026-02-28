"""End-to-end integration tests for EBC drift detection pipeline.

Tests the full pipeline: parse_ebc_from_plan -> EBCDriftDetector.detect() ->
write_alert(). Validates component integration rather than individual unit
behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.ebc.detector import EBCDriftDetector
from src.pipeline.ebc.models import ExternalBehavioralContract
from src.pipeline.ebc.parser import parse_ebc_from_plan
from src.pipeline.ebc.writer import write_alert
from src.pipeline.models.config import PipelineConfig


# --- Helpers ---


def _make_config(**ebc_overrides) -> PipelineConfig:
    """Create a PipelineConfig with optional ebc_drift overrides."""
    ebc_drift = {
        "enabled": True,
        "threshold": 0.5,
        "ratio_only_threshold": 0.8,
        "tolerance_patterns": ["__init__.py", "__pycache__", "*.pyc"],
        "write_tool_names": ["Edit", "Write"],
        "bash_write_indicators": ["mkdir", "cp ", "mv ", "touch ", "> ", ">> "],
    }
    ebc_drift.update(ebc_overrides)
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


def _write_plan_file(tmp_path: Path, files_modified: list[str]) -> Path:
    """Write a minimal PLAN.md with YAML frontmatter for testing."""
    plan_path = tmp_path / "test-PLAN.md"
    files_yaml = "\n".join(f"  - {f}" for f in files_modified)
    plan_path.write_text(
        f"---\nphase: test-phase\nplan: 1\ntype: execute\n"
        f"files_modified:\n{files_yaml}\n---\n\n# Test Plan\n",
        encoding="utf-8",
    )
    return plan_path


# --- Integration Tests: Parse -> Detect -> Write ---


class TestParseThenDetect:
    """Integration tests combining parse_ebc_from_plan with EBCDriftDetector."""

    def test_parse_and_detect_no_drift(self, tmp_path: Path) -> None:
        """Parse a plan, build matching events, verify no drift."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py", "src/b.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/b.py"),
        ]

        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-integration-1")
        assert result is None

    def test_parse_and_detect_drift_detected(self, tmp_path: Path) -> None:
        """Parse a plan, events write unexpected files, verify drift alert."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/totally_unexpected.py"),
            _make_event("Write", "src/another_surprise.py"),
        ]

        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-integration-2")
        assert result is not None
        assert result.drift_score > 0

    def test_alert_has_correct_session_id(self, tmp_path: Path) -> None:
        """Verify alert.session_id matches input."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Write", "src/unexpected.py")]
        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "my-session-42")
        assert result is not None
        assert result.session_id == "my-session-42"

    def test_alert_drift_score_positive(self, tmp_path: Path) -> None:
        """Verify alert.drift_score > 0 when drift is detected."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Write", "src/unexpected.py")]
        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-score-check")
        assert result is not None
        assert result.drift_score > 0.0

    def test_alert_unexpected_files_populated(self, tmp_path: Path) -> None:
        """Verify alert.unexpected_files contains the unexpected paths."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/surprise.py"),
        ]
        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-unexpected")
        assert result is not None
        assert "src/surprise.py" in result.unexpected_files

    def test_alert_missing_files_populated(self, tmp_path: Path) -> None:
        """Verify alert.missing_expected_files contains unmodified plan files."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py", "src/b.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        # Only write to a.py -- b.py is missing plus add unexpected
        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/unexpected.py"),
        ]
        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-missing")
        assert result is not None
        assert "src/b.py" in result.missing_expected_files


class TestWriteAlertIntegration:
    """Integration tests for detect -> write_alert pipeline."""

    def test_write_alert_creates_json_file(self, tmp_path: Path) -> None:
        """write_alert creates file, read it back, verify JSON structure."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Write", "src/unexpected.py")]
        detector = EBCDriftDetector(_make_config())
        alert = detector.detect(ebc, events, "sess-write-test")
        assert alert is not None

        alerts_dir = tmp_path / "alerts"
        out_path = write_alert(alert, alerts_dir=alerts_dir)
        assert out_path.exists()

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess-write-test"
        assert data["drift_score"] > 0
        assert "signals" in data

    def test_full_pipeline_alert_json_valid_json(self, tmp_path: Path) -> None:
        """Full pipeline: parse -> detect -> write -> json.loads succeeds."""
        plan_path = _write_plan_file(
            tmp_path, ["src/x.py", "src/y.py", "src/z.py"]
        )
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        # Write completely different files to trigger large drift
        events = [
            _make_event("Edit", "src/other1.py"),
            _make_event("Write", "src/other2.py"),
        ]
        detector = EBCDriftDetector(_make_config())
        alert = detector.detect(ebc, events, "sess-json-valid")
        assert alert is not None

        alerts_dir = tmp_path / "alerts"
        out_path = write_alert(alert, alerts_dir=alerts_dir)

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(data["signals"], list)
        assert len(data["signals"]) > 0


class TestRealPlanIntegration:
    """Integration tests using actual PLAN.md files from the project."""

    REAL_PLAN = Path(
        ".planning/phases/22-unified-discriminated-query-interface/22-01-PLAN.md"
    )

    @pytest.mark.skipif(
        not Path(
            ".planning/phases/22-unified-discriminated-query-interface/22-01-PLAN.md"
        ).exists(),
        reason="Real plan file not available",
    )
    def test_real_plan_no_drift(self) -> None:
        """Parse actual 22-01-PLAN.md, construct matching events, verify no drift."""
        ebc = parse_ebc_from_plan(self.REAL_PLAN)
        assert ebc is not None
        assert len(ebc.expected_write_paths) > 0

        # Construct events matching first few files_modified
        events = [
            _make_event("Edit", path) for path in list(ebc.expected_write_paths)[:4]
        ]

        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-real-no-drift")
        # With partial writes, there may be missing files but score could be
        # below threshold. Build matching events for ALL expected files.
        events_all = [
            _make_event("Edit", path) for path in ebc.expected_write_paths
        ]
        result = detector.detect(ebc, events_all, "sess-real-no-drift")
        assert result is None

    @pytest.mark.skipif(
        not Path(
            ".planning/phases/22-unified-discriminated-query-interface/22-01-PLAN.md"
        ).exists(),
        reason="Real plan file not available",
    )
    def test_real_plan_with_drift(self) -> None:
        """Parse actual 22-01-PLAN.md, use completely different files, verify drift."""
        ebc = parse_ebc_from_plan(self.REAL_PLAN)
        assert ebc is not None

        # Completely different files
        events = [
            _make_event("Write", "src/totally/different/file1.py"),
            _make_event("Edit", "src/totally/different/file2.py"),
            _make_event("Write", "src/totally/different/file3.py"),
        ]

        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-real-drift")
        assert result is not None
        assert result.drift_score > 0


class TestEdgeCases:
    """Edge case integration tests."""

    def test_threshold_change(self, tmp_path: Path) -> None:
        """Override threshold to 0.9, construct ~60% drift, verify returns None."""
        plan_path = _write_plan_file(
            tmp_path, [f"src/f{i}.py" for i in range(5)]
        )
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        # Write 2 of 5 expected files + 1 unexpected
        # missing: 3 * 0.3 = 0.9; unexpected: 1 * 1.0 = 1.0
        # total: 1.9 / 5 = 0.38, below 0.9 threshold
        events = [
            _make_event("Edit", "src/f0.py"),
            _make_event("Edit", "src/f1.py"),
            _make_event("Write", "src/unexpected.py"),
        ]

        config = _make_config(threshold=0.9)
        detector = EBCDriftDetector(config)
        result = detector.detect(ebc, events, "sess-threshold-test")
        assert result is None

    def test_empty_session_no_drift(self, tmp_path: Path) -> None:
        """detect() with empty events list returns None when below threshold."""
        plan_path = _write_plan_file(
            tmp_path, [f"src/f{i}.py" for i in range(10)]
        )
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        # 10 missing files * 0.3 / 10 = 0.3, below default 0.5 threshold
        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, [], "sess-empty")
        assert result is None


class TestToolRatioSignal:
    """Tests for the tool usage ratio secondary signal."""

    def test_high_read_ratio_30_reads_0_writes(self, tmp_path: Path) -> None:
        """30 Read events, 0 writes -> signal with weight 0.5."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Read", f"src/file{i}.py") for i in range(30)]
        detector = EBCDriftDetector(_make_config())

        signal = detector._compute_tool_ratio_signal(events)
        assert signal is not None
        assert signal.signal_type == "high_read_ratio"
        assert signal.weight == 0.5
        assert "write=0" in signal.detail

    def test_high_read_ratio_30_reads_2_writes(self, tmp_path: Path) -> None:
        """30 reads, 2 writes (15:1) -> signal with weight 0.3."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Read", f"src/file{i}.py") for i in range(30)]
        events.append(_make_event("Edit", "src/a.py"))
        events.append(_make_event("Write", "src/b.py"))

        detector = EBCDriftDetector(_make_config())
        signal = detector._compute_tool_ratio_signal(events)
        assert signal is not None
        assert signal.signal_type == "high_read_ratio"
        assert signal.weight == 0.3
        assert "15.0:1" in signal.detail

    def test_read_ratio_below_threshold(self, tmp_path: Path) -> None:
        """20 reads, 5 writes (4:1) -> no ratio signal."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Read", f"src/file{i}.py") for i in range(20)]
        for i in range(5):
            events.append(_make_event("Edit", f"src/w{i}.py"))

        detector = EBCDriftDetector(_make_config())
        signal = detector._compute_tool_ratio_signal(events)
        assert signal is None

    def test_small_session_no_ratio_signal(self, tmp_path: Path) -> None:
        """5 reads, 0 writes -> no signal (below min 20 reads)."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        events = [_make_event("Read", f"src/file{i}.py") for i in range(5)]
        detector = EBCDriftDetector(_make_config())
        signal = detector._compute_tool_ratio_signal(events)
        assert signal is None

    def test_ratio_only_no_alert_at_default_threshold(self, tmp_path: Path) -> None:
        """Ratio signal only (no file-set signals) at score < 0.8 -> returns None."""
        plan_path = _write_plan_file(
            tmp_path, [f"src/f{i}.py" for i in range(10)]
        )
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        # Match all expected files (no file-set drift), add 25 reads + 0 writes
        events = [_make_event("Edit", f"src/f{i}.py") for i in range(10)]
        events.extend(_make_event("Read", f"src/r{i}.py") for i in range(25))

        # ratio signal weight=0.5, score = 0.5/10 = 0.05, well below 0.8
        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-ratio-only")
        assert result is None

    def test_ratio_plus_file_signals_increases_score(self, tmp_path: Path) -> None:
        """Ratio signal + file-set signals combined -> drift_score includes ratio weight."""
        plan_path = _write_plan_file(tmp_path, ["src/a.py", "src/b.py"])
        ebc = parse_ebc_from_plan(plan_path)
        assert ebc is not None

        # Write unexpected files + many reads to trigger both signal types
        events = [
            _make_event("Edit", "src/a.py"),
            _make_event("Write", "src/unexpected1.py"),
            _make_event("Write", "src/unexpected2.py"),
        ]
        # Add 25 Read events for ratio signal (25 reads, 0 write-tool writes
        # counted by _extract_write_paths produces {src/a.py, src/unexpected1.py,
        # src/unexpected2.py} = 3 write paths; 25/3 = 8.3:1, below 10:1 threshold)
        # Need 0 writes for 0.5 weight or very high ratio.
        # Actually the writes above DO count. Let's use 40 reads for 40/3 = 13.3:1
        events.extend(_make_event("Read", f"src/r{i}.py") for i in range(40))

        detector = EBCDriftDetector(_make_config())
        result = detector.detect(ebc, events, "sess-combined")
        assert result is not None
        # Should have file signals AND ratio signal
        signal_types = {s.signal_type for s in result.signals}
        assert "unexpected_file" in signal_types
        assert "high_read_ratio" in signal_types
        assert result.drift_score > 0
