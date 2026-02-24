"""Tests for Candidate Assessment System models (Phase 17, Plan 01).

Covers:
- ScenarioSpec frozen immutability and ID generation
- ScenarioSpec ddf_target_level validation (1-7)
- AssessmentSession JSONL path derivation
- AssessmentSession status literal validation
- AssessmentReport ID generation and defaults
- AssessmentReport source_type validation
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.pipeline.assessment.models import (
    AssessmentReport,
    AssessmentSession,
    ScenarioSpec,
)


def _make_scenario(**overrides) -> ScenarioSpec:
    """Helper to create a ScenarioSpec with reasonable defaults."""
    defaults = dict(
        scenario_id="abc123",
        wisdom_id="w1",
        ddf_target_level=3,
        entity_type="breakthrough",
        title="Test Scenario",
        scenario_context="Some context",
        broken_impl_filename="broken.py",
        broken_impl_content="def broken(): pass",
    )
    defaults.update(overrides)
    return ScenarioSpec(**defaults)


def _make_session(**overrides) -> AssessmentSession:
    """Helper to create an AssessmentSession with reasonable defaults."""
    defaults = dict(
        session_id="sess-001",
        scenario_id="sc-1",
        candidate_id="cand-1",
        assessment_dir="/tmp/ope_assess_abc123/",
    )
    defaults.update(overrides)
    return AssessmentSession(**defaults)


def _make_report(**overrides) -> AssessmentReport:
    """Helper to create an AssessmentReport with reasonable defaults."""
    defaults = dict(
        report_id="rpt-001",
        session_id="sess-001",
        scenario_id="sc-1",
        candidate_id="cand-1",
    )
    defaults.update(overrides)
    return AssessmentReport(**defaults)


# ── Test 1: ScenarioSpec frozen ──


def test_scenario_spec_frozen():
    """Verify ScenarioSpec is immutable after creation."""
    s = _make_scenario()
    with pytest.raises(ValidationError):
        s.wisdom_id = "changed"


# ── Test 2: ScenarioSpec.make_id deterministic ──


def test_scenario_spec_make_id_deterministic():
    """Same inputs produce same ID; different inputs produce different IDs."""
    id1 = ScenarioSpec.make_id("w1", 3)
    id2 = ScenarioSpec.make_id("w1", 3)
    id3 = ScenarioSpec.make_id("w1", 4)

    assert id1 == id2, "Same inputs must produce same ID"
    assert id1 != id3, "Different inputs must produce different IDs"
    assert len(id1) == 16, "ID must be 16 hex characters"


# ── Test 3: ScenarioSpec ddf_target_level validation ──


def test_scenario_spec_ddf_level_validation():
    """ddf_target_level 0 and 8 must raise ValueError."""
    with pytest.raises(ValidationError, match="ddf_target_level must be 1-7"):
        _make_scenario(ddf_target_level=0)

    with pytest.raises(ValidationError, match="ddf_target_level must be 1-7"):
        _make_scenario(ddf_target_level=8)

    # Valid boundary values
    s1 = _make_scenario(ddf_target_level=1)
    assert s1.ddf_target_level == 1

    s7 = _make_scenario(ddf_target_level=7)
    assert s7.ddf_target_level == 7


# ── Test 4: AssessmentSession.derive_jsonl_path ──


def test_assessment_session_derive_jsonl_path():
    """/tmp/ope_assess_abc123/ produces expected JSONL path with dash encoding."""
    path = AssessmentSession.derive_jsonl_path(
        "/tmp/ope_assess_abc123/", "sess-001"
    )
    # All slashes replaced with dashes, including leading
    assert "-tmp-ope_assess_abc123" in path
    assert path.endswith("sess-001.jsonl")
    assert ".claude/projects/" in path

    # Verify trailing slash stripping
    path2 = AssessmentSession.derive_jsonl_path(
        "/tmp/ope_assess_abc123", "sess-001"
    )
    assert path == path2


# ── Test 5: AssessmentSession status literal ──


def test_assessment_session_status_literal():
    """Only valid statuses accepted."""
    # Valid statuses
    for status in ("setup", "running", "completed", "failed"):
        s = _make_session(status=status)
        assert s.status == status

    # Invalid status
    with pytest.raises(ValidationError):
        _make_session(status="invalid_status")


# ── Test 6: AssessmentReport.make_id deterministic ──


def test_assessment_report_make_id_deterministic():
    """Same session_id produces same report_id."""
    id1 = AssessmentReport.make_id("sess-001")
    id2 = AssessmentReport.make_id("sess-001")
    id3 = AssessmentReport.make_id("sess-002")

    assert id1 == id2, "Same session_id must produce same report_id"
    assert id1 != id3, "Different session_ids must produce different report_ids"
    assert len(id1) == 16, "ID must be 16 hex characters"


# ── Test 7: AssessmentReport defaults ──


def test_assessment_report_defaults():
    """Verify default source_type, fidelity, and confidence values."""
    r = _make_report()
    assert r.source_type == "simulation_review"
    assert r.fidelity == 3
    assert r.confidence == 0.85
    assert r.flame_event_count == 0
    assert r.ai_flame_event_count == 0
    assert r.rejections_detected == 0
    assert r.level_distribution == {}
    assert r.axis_quality_scores == {}
    assert r.spiral_evidence == []


# ── Test 8: AssessmentReport source_type validation ──


def test_assessment_report_source_type_validation():
    """Invalid source_type raises ValueError."""
    with pytest.raises(ValidationError, match="source_type"):
        _make_report(source_type="invalid_type")
