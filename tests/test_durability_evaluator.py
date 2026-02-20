"""Tests for SessionConstraintEvaluator with 3-state evaluation.

Covers:
- HONORED: scope overlaps, no detection hints match, status active
- VIOLATED: scope overlaps, detection_hints match event payload
- UNKNOWN excluded: scope doesn't overlap -> no result
- Temporal filter: constraint created_at after session_start_time -> excluded
- status_history filter: constraint was "candidate" at session time -> excluded
- O_ESC auto-violation: escalation_violations dict triggers VIOLATED
- Empty detection_hints with scope overlap -> HONORED
- Case-insensitive hint matching
- Evidence includes event_id, matched_pattern, payload_excerpt (truncated)
- Multiple constraints in single evaluation call
"""

from __future__ import annotations

import json

import pytest

from src.pipeline.durability.evaluator import (
    ConstraintEvalResult,
    SessionConstraintEvaluator,
)
from src.pipeline.models.config import PipelineConfig


@pytest.fixture()
def config() -> PipelineConfig:
    """Default pipeline config."""
    return PipelineConfig()


@pytest.fixture()
def evaluator(config: PipelineConfig) -> SessionConstraintEvaluator:
    """Default evaluator instance."""
    return SessionConstraintEvaluator(config)


def _make_constraint(
    constraint_id: str = "c1",
    scope_paths: list[str] | None = None,
    detection_hints: list[str] | None = None,
    status: str = "active",
    status_history: list[dict] | None = None,
    created_at: str = "2026-01-01T00:00:00+00:00",
    constraint_type: str = "behavioral_constraint",
    severity: str = "warning",
) -> dict:
    """Helper to build a constraint dict."""
    return {
        "constraint_id": constraint_id,
        "text": f"Test constraint {constraint_id}",
        "severity": severity,
        "scope": {"paths": scope_paths if scope_paths is not None else ["src/"]},
        "detection_hints": detection_hints if detection_hints is not None else [],
        "source_episode_id": "ep_test",
        "created_at": created_at,
        "status": status,
        "status_history": status_history
        if status_history is not None
        else [{"status": status, "changed_at": created_at}],
        "type": constraint_type,
        "supersedes": None,
        "examples": [],
    }


def _make_event(
    event_id: str = "evt1",
    payload: dict | None = None,
) -> dict:
    """Helper to build an event dict."""
    return {
        "event_id": event_id,
        "payload": payload if payload is not None else {"common": {"text": "no match here"}},
    }


class TestHonored:
    """Tests for HONORED evaluation state."""

    def test_honored_when_scope_overlaps_no_hints_match(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Constraint HONORED when scope overlaps and no hints match."""
        constraint = _make_constraint(
            scope_paths=["src/"], detection_hints=["eval("]
        )
        events = [_make_event(payload={"common": {"text": "normal code"}})]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 1
        assert results[0].eval_state == "HONORED"
        assert results[0].constraint_id == "c1"
        assert results[0].session_id == "s1"

    def test_honored_when_empty_detection_hints(
        self, evaluator: SessionConstraintEvaluator
    ):
        """HONORED when detection_hints is empty and scope overlaps."""
        constraint = _make_constraint(
            scope_paths=["src/"], detection_hints=[]
        )
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 1
        assert results[0].eval_state == "HONORED"


class TestViolated:
    """Tests for VIOLATED evaluation state."""

    def test_violated_when_detection_hints_match(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Constraint VIOLATED when detection hints match event payload."""
        constraint = _make_constraint(
            scope_paths=["src/"], detection_hints=["eval("]
        )
        events = [
            _make_event(
                event_id="evt_bad",
                payload={"common": {"text": "result = eval(expression)"}},
            )
        ]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/runner.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 1
        assert results[0].eval_state == "VIOLATED"
        assert len(results[0].evidence) > 0
        assert results[0].evidence[0]["event_id"] == "evt_bad"
        assert results[0].evidence[0]["matched_pattern"] == "eval("

    def test_case_insensitive_hint_matching(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Detection hints match case-insensitively."""
        constraint = _make_constraint(
            scope_paths=["src/"], detection_hints=["EVAL("]
        )
        events = [
            _make_event(
                payload={"common": {"text": "result = eval(expr)"}},
            )
        ]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/runner.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 1
        assert results[0].eval_state == "VIOLATED"

    def test_evidence_includes_required_fields(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Evidence includes event_id, matched_pattern, and payload_excerpt."""
        constraint = _make_constraint(
            scope_paths=["src/"], detection_hints=["rm -rf"]
        )
        events = [
            _make_event(
                event_id="evt_rm",
                payload={"common": {"text": "rm -rf /tmp/build"}},
            )
        ]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/runner.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        evidence = results[0].evidence[0]
        assert "event_id" in evidence
        assert "matched_pattern" in evidence
        assert "payload_excerpt" in evidence
        assert evidence["event_id"] == "evt_rm"
        assert evidence["matched_pattern"] == "rm -rf"

    def test_evidence_payload_excerpt_truncated(self):
        """Evidence payload_excerpt is truncated to max_chars."""
        config = PipelineConfig()
        config.durability.evidence_excerpt_max_chars = 50
        evaluator = SessionConstraintEvaluator(config)

        long_text = "x" * 1000
        constraint = _make_constraint(
            scope_paths=["src/"], detection_hints=["xxx"]
        )
        events = [
            _make_event(
                payload={"common": {"text": long_text}},
            )
        ]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/runner.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        assert results[0].eval_state == "VIOLATED"
        excerpt = results[0].evidence[0]["payload_excerpt"]
        assert len(excerpt) <= 50


class TestUnknownExcluded:
    """Tests for UNKNOWN (excluded) constraint evaluation."""

    def test_excluded_when_scope_no_overlap(
        self, evaluator: SessionConstraintEvaluator
    ):
        """No result produced when constraint scope doesn't overlap session."""
        constraint = _make_constraint(
            scope_paths=["docs/"],  # Session touches src/, no overlap
        )
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 0


class TestTemporalFilter:
    """Tests for temporal filtering of constraints."""

    def test_excluded_when_created_after_session(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Constraint excluded if created_at is after session_start_time."""
        constraint = _make_constraint(
            created_at="2026-02-01T00:00:00+00:00",
            status_history=[
                {"status": "active", "changed_at": "2026-02-01T00:00:00+00:00"}
            ],
        )
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",  # Before created_at
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 0

    def test_excluded_when_status_was_candidate(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Constraint excluded if status was 'candidate' at session time."""
        constraint = _make_constraint(
            status="active",
            status_history=[
                {"status": "candidate", "changed_at": "2026-01-01T00:00:00+00:00"},
                {"status": "active", "changed_at": "2026-02-01T00:00:00+00:00"},
            ],
        )
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",  # Status was candidate
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 0

    def test_included_when_status_is_active_at_time(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Constraint included when status was 'active' at session time."""
        constraint = _make_constraint(
            status="retired",
            status_history=[
                {"status": "active", "changed_at": "2026-01-01T00:00:00+00:00"},
                {"status": "retired", "changed_at": "2026-03-01T00:00:00+00:00"},
            ],
        )
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-02-15T00:00:00+00:00",  # Status was active
            events=events,
            constraints=[constraint],
        )

        assert len(results) == 1
        assert results[0].eval_state == "HONORED"


class TestEscalationViolation:
    """Tests for O_ESC auto-violation."""

    def test_oesc_auto_violation(
        self, evaluator: SessionConstraintEvaluator
    ):
        """O_ESC escalation_violations dict triggers VIOLATED."""
        constraint = _make_constraint(constraint_id="c_esc")
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
            escalation_violations={"c_esc": "s1"},
        )

        assert len(results) == 1
        assert results[0].eval_state == "VIOLATED"
        assert results[0].evidence[0]["matched_pattern"] == "O_ESC bypass"

    def test_oesc_takes_precedence_over_honored(
        self, evaluator: SessionConstraintEvaluator
    ):
        """O_ESC violation takes precedence even with no hint matches."""
        constraint = _make_constraint(
            constraint_id="c_esc",
            detection_hints=[],  # No hints to match
        )
        events = [_make_event()]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[constraint],
            escalation_violations={"c_esc": "s1"},
        )

        assert results[0].eval_state == "VIOLATED"


class TestMultipleConstraints:
    """Tests for evaluating multiple constraints."""

    def test_evaluates_multiple_constraints(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Evaluate multiple constraints in single call."""
        c1 = _make_constraint(
            constraint_id="c_honored",
            scope_paths=["src/"],
            detection_hints=["eval("],
        )
        c2 = _make_constraint(
            constraint_id="c_violated",
            scope_paths=["src/"],
            detection_hints=["rm -rf"],
        )
        c3 = _make_constraint(
            constraint_id="c_excluded",
            scope_paths=["docs/"],  # No overlap
        )

        events = [
            _make_event(
                event_id="evt1",
                payload={"common": {"text": "rm -rf /tmp/old_build"}},
            )
        ]

        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=events,
            constraints=[c1, c2, c3],
        )

        # c1: HONORED (eval( doesn't match "rm -rf /tmp/old_build")
        # c2: VIOLATED (rm -rf matches)
        # c3: excluded (no scope overlap)
        assert len(results) == 2
        result_map = {r.constraint_id: r.eval_state for r in results}
        assert result_map["c_honored"] == "HONORED"
        assert result_map["c_violated"] == "VIOLATED"
        assert "c_excluded" not in result_map

    def test_handles_empty_constraints_list(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Empty constraints list returns empty results."""
        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/pipeline/config.py"],
            session_start_time="2026-01-15T00:00:00+00:00",
            events=[_make_event()],
            constraints=[],
        )
        assert results == []

    def test_handles_invalid_session_start_time(
        self, evaluator: SessionConstraintEvaluator
    ):
        """Invalid session_start_time returns empty results."""
        results = evaluator.evaluate(
            session_id="s1",
            session_scope_paths=["src/"],
            session_start_time="not-a-datetime",
            events=[_make_event()],
            constraints=[_make_constraint()],
        )
        assert results == []


class TestConstraintEvalResultModel:
    """Tests for ConstraintEvalResult Pydantic model."""

    def test_frozen_immutable(self):
        """ConstraintEvalResult is immutable (frozen)."""
        result = ConstraintEvalResult(
            session_id="s1",
            constraint_id="c1",
            eval_state="HONORED",
        )
        with pytest.raises(Exception):
            result.eval_state = "VIOLATED"

    def test_defaults(self):
        """ConstraintEvalResult has correct defaults."""
        result = ConstraintEvalResult(
            session_id="s1",
            constraint_id="c1",
            eval_state="HONORED",
        )
        assert result.evidence == []
        assert result.scope_matched is True
