"""Tests for AmnesiaDetector and AmnesiaEvent.

Covers:
- Amnesia events created for each VIOLATED result
- Amnesia_id is deterministic (same inputs = same ID)
- Amnesia_id is idempotent across multiple detect() calls
- Constraint metadata (type, severity) correctly populated
- No amnesia events for HONORED results
"""

from __future__ import annotations

import hashlib

import pytest

from src.pipeline.durability.amnesia import AmnesiaDetector, AmnesiaEvent
from src.pipeline.durability.evaluator import ConstraintEvalResult


@pytest.fixture()
def detector() -> AmnesiaDetector:
    """Default AmnesiaDetector instance."""
    return AmnesiaDetector()


def _make_eval_result(
    session_id: str = "s1",
    constraint_id: str = "c1",
    eval_state: str = "VIOLATED",
    evidence: list[dict] | None = None,
) -> ConstraintEvalResult:
    """Helper to build a ConstraintEvalResult."""
    return ConstraintEvalResult(
        session_id=session_id,
        constraint_id=constraint_id,
        eval_state=eval_state,
        evidence=evidence or [{"event_id": "e1", "matched_pattern": "test", "payload_excerpt": "test"}],
    )


def _make_constraint(
    constraint_id: str = "c1",
    constraint_type: str = "behavioral_constraint",
    severity: str = "forbidden",
) -> dict:
    """Helper to build a constraint dict for metadata lookup."""
    return {
        "constraint_id": constraint_id,
        "text": f"Test constraint {constraint_id}",
        "type": constraint_type,
        "severity": severity,
        "scope": {"paths": ["src/"]},
    }


class TestAmnesiaEventCreation:
    """Tests for amnesia event creation from VIOLATED results."""

    def test_creates_amnesia_for_violated(self, detector: AmnesiaDetector):
        """Amnesia event created for each VIOLATED result."""
        results = [
            _make_eval_result(session_id="s1", constraint_id="c1"),
            _make_eval_result(session_id="s1", constraint_id="c2"),
        ]
        constraints = [
            _make_constraint(constraint_id="c1"),
            _make_constraint(constraint_id="c2"),
        ]

        events = detector.detect(results, constraints)
        assert len(events) == 2

    def test_no_amnesia_for_honored(self, detector: AmnesiaDetector):
        """No amnesia events produced for HONORED results."""
        results = [
            _make_eval_result(eval_state="HONORED"),
        ]
        constraints = [_make_constraint()]

        events = detector.detect(results, constraints)
        assert len(events) == 0

    def test_mixed_results(self, detector: AmnesiaDetector):
        """Only VIOLATED results produce amnesia events."""
        results = [
            _make_eval_result(constraint_id="c1", eval_state="VIOLATED"),
            _make_eval_result(constraint_id="c2", eval_state="HONORED"),
            _make_eval_result(constraint_id="c3", eval_state="VIOLATED"),
        ]
        constraints = [
            _make_constraint(constraint_id="c1"),
            _make_constraint(constraint_id="c2"),
            _make_constraint(constraint_id="c3"),
        ]

        events = detector.detect(results, constraints)
        assert len(events) == 2
        ids = {e.constraint_id for e in events}
        assert ids == {"c1", "c3"}


class TestAmnesiaIdDeterminism:
    """Tests for deterministic amnesia_id generation."""

    def test_amnesia_id_is_deterministic(self, detector: AmnesiaDetector):
        """Same session_id + constraint_id = same amnesia_id."""
        results = [_make_eval_result(session_id="s1", constraint_id="c1")]
        constraints = [_make_constraint(constraint_id="c1")]

        events1 = detector.detect(results, constraints)
        events2 = detector.detect(results, constraints)

        assert events1[0].amnesia_id == events2[0].amnesia_id

    def test_amnesia_id_matches_sha256_formula(self, detector: AmnesiaDetector):
        """amnesia_id = SHA-256(session_id + constraint_id)[:16]."""
        results = [_make_eval_result(session_id="sess_abc", constraint_id="const_xyz")]
        constraints = [_make_constraint(constraint_id="const_xyz")]

        events = detector.detect(results, constraints)

        expected_id = hashlib.sha256(
            ("sess_abc" + "const_xyz").encode()
        ).hexdigest()[:16]
        assert events[0].amnesia_id == expected_id

    def test_different_inputs_different_ids(self, detector: AmnesiaDetector):
        """Different session/constraint combos produce different IDs."""
        r1 = [_make_eval_result(session_id="s1", constraint_id="c1")]
        r2 = [_make_eval_result(session_id="s2", constraint_id="c1")]
        constraints = [_make_constraint(constraint_id="c1")]

        events1 = detector.detect(r1, constraints)
        events2 = detector.detect(r2, constraints)

        assert events1[0].amnesia_id != events2[0].amnesia_id

    def test_idempotent_across_calls(self, detector: AmnesiaDetector):
        """Multiple detect() calls with same inputs produce same IDs."""
        results = [
            _make_eval_result(session_id="s1", constraint_id="c1"),
            _make_eval_result(session_id="s1", constraint_id="c2"),
        ]
        constraints = [
            _make_constraint(constraint_id="c1"),
            _make_constraint(constraint_id="c2"),
        ]

        events_a = detector.detect(results, constraints)
        events_b = detector.detect(results, constraints)

        for a, b in zip(events_a, events_b):
            assert a.amnesia_id == b.amnesia_id


class TestConstraintMetadata:
    """Tests for constraint metadata population in amnesia events."""

    def test_type_populated(self, detector: AmnesiaDetector):
        """Constraint type is populated from constraint dict."""
        results = [_make_eval_result(constraint_id="c1")]
        constraints = [
            _make_constraint(
                constraint_id="c1", constraint_type="architectural_decision"
            )
        ]

        events = detector.detect(results, constraints)
        assert events[0].constraint_type == "architectural_decision"

    def test_severity_populated(self, detector: AmnesiaDetector):
        """Constraint severity is populated from constraint dict."""
        results = [_make_eval_result(constraint_id="c1")]
        constraints = [
            _make_constraint(constraint_id="c1", severity="requires_approval")
        ]

        events = detector.detect(results, constraints)
        assert events[0].severity == "requires_approval"

    def test_metadata_none_for_unknown_constraint(self, detector: AmnesiaDetector):
        """Metadata is None when constraint not found in lookup."""
        results = [_make_eval_result(constraint_id="c_missing")]
        constraints = []  # No constraints to look up

        events = detector.detect(results, constraints)
        assert len(events) == 1
        assert events[0].constraint_type is None
        assert events[0].severity is None

    def test_evidence_carried_through(self, detector: AmnesiaDetector):
        """Evidence from eval result is carried through to amnesia event."""
        evidence = [
            {
                "event_id": "evt_bad",
                "matched_pattern": "eval(",
                "payload_excerpt": "result = eval(expression)",
            }
        ]
        results = [_make_eval_result(constraint_id="c1", evidence=evidence)]
        constraints = [_make_constraint(constraint_id="c1")]

        events = detector.detect(results, constraints)
        assert events[0].evidence == evidence


class TestAmnesiaEventModel:
    """Tests for AmnesiaEvent Pydantic model."""

    def test_frozen_immutable(self):
        """AmnesiaEvent is immutable (frozen)."""
        event = AmnesiaEvent(
            amnesia_id="abc123",
            session_id="s1",
            constraint_id="c1",
            detected_at="2026-01-15T00:00:00+00:00",
        )
        with pytest.raises(Exception):
            event.session_id = "s2"

    def test_detected_at_populated(self, detector: AmnesiaDetector):
        """detected_at is populated with UTC timestamp."""
        results = [_make_eval_result()]
        constraints = [_make_constraint()]

        events = detector.detect(results, constraints)
        assert events[0].detected_at != ""
        assert "T" in events[0].detected_at  # ISO format
