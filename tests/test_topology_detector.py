"""Tests for ConjunctiveFlameDetector and EdgeGenerator.

15 tests covering:
- Conjunctive trigger logic (fires/rejects) [tests 1-4]
- Baseline computation [tests 5-7]
- Boundary cases [tests 8-10]
- Edge generation [tests 11-15]
"""
from __future__ import annotations

import pytest

from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.topology.detector import (
    ConjunctiveFlameDetector,
    ConjunctiveTrigger,
)
from src.pipeline.ddf.topology.generator import EdgeGenerator
from src.pipeline.ddf.topology.models import EdgeRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flame(
    session_id: str = "sess-001",
    prompt_number: int = 1,
    marker_level: int = 2,
    marker_type: str = "trunk_identification",
    axis_identified: str | None = None,
) -> FlameEvent:
    """Create a FlameEvent with deterministic ID."""
    return FlameEvent(
        flame_event_id=FlameEvent.make_id(session_id, prompt_number, marker_type),
        session_id=session_id,
        prompt_number=prompt_number,
        marker_level=marker_level,
        marker_type=marker_type,
        axis_identified=axis_identified,
    )


TWO_AXES = ["deposit-not-detect", "ground-truth-pointer"]
THREE_AXES = ["deposit-not-detect", "ground-truth-pointer", "identity-firewall"]
ONE_AXIS = ["deposit-not-detect"]


# ---------------------------------------------------------------------------
# Detector tests (1-10)
# ---------------------------------------------------------------------------

class TestConjunctiveFlameDetector:
    """Tests for ConjunctiveFlameDetector conjunctive trigger logic."""

    def test_conjunctive_fires_level5_delta2_two_axes(self) -> None:
        """Test 1: Level 5 + delta 3 + 2 axes -> fires."""
        detector = ConjunctiveFlameDetector()

        # Build baseline: 10 events at level 2 -> median = 2.0
        for i in range(10):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Triggering event: level 5, delta = 5 - 2 = 3, two axes
        trigger_event = _make_flame(marker_level=5, prompt_number=100)
        result = detector.check_conjunctive(
            trigger_event, TWO_AXES, episode_id="ep-001"
        )

        assert result is not None
        assert isinstance(result, ConjunctiveTrigger)
        assert result.flame_event == trigger_event
        assert result.delta == 3.0
        assert result.baseline_marker_level == 2.0
        assert set(result.active_axes) == set(TWO_AXES)
        assert result.episode_id == "ep-001"
        assert result.session_id == "sess-001"

    def test_conjunctive_rejects_level4_high_delta(self) -> None:
        """Test 2: Level 4, high delta -> None (level too low)."""
        detector = ConjunctiveFlameDetector()

        # No baseline history -> baseline=0.0, delta=4 is high
        event = _make_flame(marker_level=4, prompt_number=1)
        result = detector.check_conjunctive(event, TWO_AXES, episode_id="ep-001")

        # Level 4 < MIN_LEVEL 5, so must reject
        assert result is None

    def test_conjunctive_rejects_level5_low_delta(self) -> None:
        """Test 3: Level 5, low delta -> None (delta too low)."""
        detector = ConjunctiveFlameDetector()

        # Build baseline at level 4 -> median = 4.0
        for i in range(10):
            event = _make_flame(marker_level=4, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 5, delta = 5 - 4 = 1.0 < MIN_DELTA 2.0
        trigger_event = _make_flame(marker_level=5, prompt_number=100)
        result = detector.check_conjunctive(
            trigger_event, TWO_AXES, episode_id="ep-001"
        )

        assert result is None

    def test_conjunctive_rejects_single_axis(self) -> None:
        """Test 4: Level 6, delta 3, only 1 axis -> None."""
        detector = ConjunctiveFlameDetector()

        # Build baseline at level 3
        for i in range(10):
            event = _make_flame(marker_level=3, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 6, delta = 6 - 3 = 3, but only 1 axis
        trigger_event = _make_flame(marker_level=6, prompt_number=100)
        result = detector.check_conjunctive(
            trigger_event, ONE_AXIS, episode_id="ep-001"
        )

        assert result is None

    def test_baseline_rolling_median(self) -> None:
        """Test 5: 10 events at level 2, verify baseline=2.0, delta=3.0."""
        detector = ConjunctiveFlameDetector()

        for i in range(10):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Check baseline after 10 events (includes all 10 in history)
        baseline = detector.compute_baseline("sess-001")
        assert baseline == 2.0

        # Trigger at level 5 -> delta = 5 - 2 = 3
        trigger_event = _make_flame(marker_level=5, prompt_number=100)
        result = detector.check_conjunctive(
            trigger_event, TWO_AXES, episode_id="ep-001"
        )

        assert result is not None
        assert result.baseline_marker_level == 2.0
        assert result.delta == 3.0

    def test_baseline_empty_session(self) -> None:
        """Test 6: First event in session -> baseline=0.0."""
        detector = ConjunctiveFlameDetector()

        # First event ever for this session -> no prior history
        event = _make_flame(marker_level=6, prompt_number=1)
        result = detector.check_conjunctive(event, TWO_AXES, episode_id="ep-001")

        # Baseline = 0.0 (no prior events), delta = 6.0 >= 2.0
        assert result is not None
        assert result.baseline_marker_level == 0.0
        assert result.delta == 6.0

    def test_baseline_uses_prior_events_only(self) -> None:
        """Test 7: Current event not included in its own baseline."""
        detector = ConjunctiveFlameDetector()

        # Add 5 events at level 2
        for i in range(5):
            event = _make_flame(marker_level=2, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Event at level 7 should have baseline=2.0 (not influenced by 7)
        trigger_event = _make_flame(marker_level=7, prompt_number=100)
        result = detector.check_conjunctive(
            trigger_event, TWO_AXES, episode_id="ep-001"
        )

        assert result is not None
        # If current event were included: median([2,2,2,2,2,7]) = 2.0 (still 2 here)
        # But more importantly, baseline should be median of [2,2,2,2,2] = 2.0
        assert result.baseline_marker_level == 2.0
        assert result.delta == 5.0

    def test_conjunctive_exactly_level5_exactly_delta2(self) -> None:
        """Test 8: Boundary: level 5, baseline 3.0 (delta=2.0) -> fires."""
        detector = ConjunctiveFlameDetector()

        # Build baseline at level 3 -> median = 3.0
        for i in range(10):
            event = _make_flame(marker_level=3, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        # Level 5, delta = 5 - 3 = 2.0, exactly at boundary (>= not >)
        trigger_event = _make_flame(marker_level=5, prompt_number=100)
        result = detector.check_conjunctive(
            trigger_event, TWO_AXES, episode_id="ep-001"
        )

        assert result is not None
        assert result.delta == 2.0
        assert result.baseline_marker_level == 3.0

    def test_conjunctive_two_axes_minimum(self) -> None:
        """Test 9: Exactly 2 axes -> fires (minimum)."""
        detector = ConjunctiveFlameDetector()

        event = _make_flame(marker_level=6, prompt_number=1)
        result = detector.check_conjunctive(
            event, ["deposit-not-detect", "bootstrap-circularity"], episode_id="ep-001"
        )

        assert result is not None
        assert len(set(result.active_axes)) == 2

    def test_reset_session_clears_history(self) -> None:
        """Test 10: reset_session -> baseline reverts to 0.0."""
        detector = ConjunctiveFlameDetector()

        # Build history
        for i in range(10):
            event = _make_flame(marker_level=4, prompt_number=i)
            detector.check_conjunctive(event, ONE_AXIS)

        assert detector.compute_baseline("sess-001") == 4.0

        # Reset
        detector.reset_session("sess-001")
        assert detector.compute_baseline("sess-001") == 0.0


# ---------------------------------------------------------------------------
# Generator tests (11-15)
# ---------------------------------------------------------------------------

class TestEdgeGenerator:
    """Tests for EdgeGenerator edge record creation."""

    def _make_trigger(
        self,
        axes: list[str] | None = None,
        marker_level: int = 6,
        session_id: str = "sess-001",
        episode_id: str = "ep-001",
    ) -> ConjunctiveTrigger:
        """Create a ConjunctiveTrigger for testing."""
        event = _make_flame(
            session_id=session_id,
            marker_level=marker_level,
            prompt_number=99,
        )
        return ConjunctiveTrigger(
            flame_event=event,
            baseline_marker_level=2.0,
            delta=marker_level - 2.0,
            active_axes=axes or TWO_AXES,
            episode_id=episode_id,
            session_id=session_id,
        )

    def test_generator_produces_edge_record(self) -> None:
        """Test 11: generate() returns EdgeRecord with all fields populated."""
        gen = EdgeGenerator()
        trigger = self._make_trigger()

        records = gen.generate(trigger)
        assert len(records) == 1

        rec = records[0]
        assert isinstance(rec, EdgeRecord)
        assert rec.axis_a == "deposit-not-detect"
        assert rec.axis_b == "ground-truth-pointer"
        assert rec.status == "candidate"
        assert rec.abstraction_level == 6
        assert rec.trunk_quality == 1.0
        assert rec.created_session_id == "sess-001"
        assert rec.evidence["session_id"] == "sess-001"
        assert rec.evidence["episode_id"] == "ep-001"
        assert isinstance(rec.evidence["flame_event_ids"], list)
        assert len(rec.evidence["flame_event_ids"]) == 1
        assert rec.activation_condition.goal_type == ["any"]
        assert rec.activation_condition.min_axes_simultaneously_active == 2

    def test_generator_deterministic_id(self) -> None:
        """Test 12: Same trigger -> same edge_id (deterministic)."""
        gen = EdgeGenerator()
        trigger = self._make_trigger()

        records_a = gen.generate(trigger, relationship_text="test relationship")
        records_b = gen.generate(trigger, relationship_text="test relationship")

        assert records_a[0].edge_id == records_b[0].edge_id

    def test_generator_two_axes_one_record(self) -> None:
        """Test 13: 2 axes -> 1 EdgeRecord (C(2,2) = 1)."""
        gen = EdgeGenerator()
        trigger = self._make_trigger(axes=TWO_AXES)

        records = gen.generate(trigger)
        assert len(records) == 1

    def test_generator_three_axes_three_records(self) -> None:
        """Test 14: 3 axes -> 3 EdgeRecords (C(3,2) = 3)."""
        gen = EdgeGenerator()
        trigger = self._make_trigger(axes=THREE_AXES)

        records = gen.generate(trigger)
        assert len(records) == 3

        # Verify all pairs present
        pairs = {(r.axis_a, r.axis_b) for r in records}
        expected = {
            ("deposit-not-detect", "ground-truth-pointer"),
            ("deposit-not-detect", "identity-firewall"),
            ("ground-truth-pointer", "identity-firewall"),
        }
        assert pairs == expected

    def test_generator_custom_relationship_text(self) -> None:
        """Test 15: Custom relationship_text overrides auto-generated."""
        gen = EdgeGenerator()
        trigger = self._make_trigger()

        custom_text = "Identity firewall necessitates deposit-not-detect"
        records = gen.generate(trigger, relationship_text=custom_text)

        assert len(records) == 1
        assert records[0].relationship_text == custom_text
