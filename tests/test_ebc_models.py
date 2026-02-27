"""Tests for EBC Pydantic models.

Covers construction, field defaults, expected_write_paths property,
frozen immutability, and serialization.
"""

from __future__ import annotations

import json

import pytest

from src.pipeline.ebc.models import (
    DriftSignal,
    EBCArtifact,
    EBCDriftAlert,
    EBCKeyLink,
    ExternalBehavioralContract,
)


class TestEBCArtifact:
    """Tests for EBCArtifact model."""

    def test_minimal_construction(self) -> None:
        a = EBCArtifact(path="src/foo.py")
        assert a.path == "src/foo.py"
        assert a.provides == ""
        assert a.exports == []
        assert a.contains == ""

    def test_full_construction(self) -> None:
        a = EBCArtifact(
            path="src/bar.py",
            provides="Bar class",
            exports=["Bar", "BarConfig"],
            contains="implementation",
        )
        assert a.path == "src/bar.py"
        assert a.provides == "Bar class"
        assert a.exports == ["Bar", "BarConfig"]
        assert a.contains == "implementation"

    def test_frozen_rejects_mutation(self) -> None:
        a = EBCArtifact(path="src/foo.py")
        with pytest.raises(Exception):  # ValidationError for frozen
            a.path = "changed"  # type: ignore[misc]


class TestEBCKeyLink:
    """Tests for EBCKeyLink model with alias support."""

    def test_construction_with_aliases(self) -> None:
        """Test using 'from' and 'to' aliases (as in YAML frontmatter)."""
        kl = EBCKeyLink(**{"from": "src/a.py", "to": "src/b.py", "via": "import"})
        assert kl.from_path == "src/a.py"
        assert kl.to_target == "src/b.py"
        assert kl.via == "import"

    def test_construction_with_field_names(self) -> None:
        """Test using from_path and to_target field names directly."""
        kl = EBCKeyLink(from_path="src/a.py", to_target="src/b.py", pattern="regex")
        assert kl.from_path == "src/a.py"
        assert kl.to_target == "src/b.py"
        assert kl.pattern == "regex"

    def test_frozen_rejects_mutation(self) -> None:
        kl = EBCKeyLink(from_path="src/a.py", to_target="src/b.py")
        with pytest.raises(Exception):
            kl.from_path = "changed"  # type: ignore[misc]


class TestExternalBehavioralContract:
    """Tests for ExternalBehavioralContract model."""

    def test_expected_write_paths_combines_files_and_artifacts(self) -> None:
        ebc = ExternalBehavioralContract(
            phase="test-phase",
            plan=1,
            files_modified=["src/a.py", "src/b.py"],
            artifacts=[
                EBCArtifact(path="src/c.py"),
                EBCArtifact(path="src/d.py"),
            ],
        )
        assert ebc.expected_write_paths == {
            "src/a.py", "src/b.py", "src/c.py", "src/d.py",
        }

    def test_expected_write_paths_deduplicates(self) -> None:
        """Same path in files_modified and artifacts should deduplicate."""
        ebc = ExternalBehavioralContract(
            phase="test-phase",
            plan=1,
            files_modified=["src/a.py", "src/b.py"],
            artifacts=[EBCArtifact(path="src/a.py")],
        )
        assert ebc.expected_write_paths == {"src/a.py", "src/b.py"}

    def test_expected_write_paths_empty(self) -> None:
        ebc = ExternalBehavioralContract(phase="test-phase", plan=1)
        assert ebc.expected_write_paths == set()

    def test_defaults(self) -> None:
        ebc = ExternalBehavioralContract(phase="test-phase", plan=1)
        assert ebc.plan_type == "execute"
        assert ebc.wave == 1
        assert ebc.depends_on == []
        assert ebc.files_modified == []
        assert ebc.autonomous is True
        assert ebc.truths == []
        assert ebc.artifacts == []
        assert ebc.key_links == []

    def test_frozen_rejects_mutation(self) -> None:
        ebc = ExternalBehavioralContract(phase="test-phase", plan=1)
        with pytest.raises(Exception):
            ebc.phase = "changed"  # type: ignore[misc]


class TestDriftSignal:
    """Tests for DriftSignal model."""

    def test_construction(self) -> None:
        ds = DriftSignal(
            signal_type="unexpected_file",
            detail="src/surprise.py",
            weight=1.0,
        )
        assert ds.signal_type == "unexpected_file"
        assert ds.detail == "src/surprise.py"
        assert ds.weight == 1.0

    def test_frozen_rejects_mutation(self) -> None:
        ds = DriftSignal(signal_type="unexpected_file", detail="x", weight=1.0)
        with pytest.raises(Exception):
            ds.weight = 0.5  # type: ignore[misc]


class TestEBCDriftAlert:
    """Tests for EBCDriftAlert model."""

    def test_construction(self) -> None:
        alert = EBCDriftAlert(
            session_id="sess-123",
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
            missing_expected_files=[],
        )
        assert alert.session_id == "sess-123"
        assert alert.drift_score == 0.75
        assert len(alert.signals) == 1
        assert alert.unexpected_files == ["src/surprise.py"]

    def test_serialization_roundtrip(self) -> None:
        alert = EBCDriftAlert(
            session_id="sess-456",
            drift_score=0.5,
            signals=[
                DriftSignal(
                    signal_type="missing_expected_file",
                    detail="src/expected.py",
                    weight=0.3,
                ),
            ],
            ebc_phase="p1",
            ebc_plan="2",
        )
        json_str = alert.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "sess-456"
        assert parsed["drift_score"] == 0.5
        assert parsed["signals"][0]["signal_type"] == "missing_expected_file"
        assert parsed["ebc_phase"] == "p1"
        assert parsed["ebc_plan"] == "2"

    def test_defaults(self) -> None:
        alert = EBCDriftAlert(
            session_id="s",
            drift_score=0.0,
            signals=[],
            ebc_phase="p",
            ebc_plan="1",
        )
        assert alert.unexpected_files == []
        assert alert.missing_expected_files == []
