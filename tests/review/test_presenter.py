"""Tests for the identification review presenter.

Verifies that present() correctly formats IdentificationPoint instances
with all five decision-boundary externalization fields visible in output.
"""

from __future__ import annotations

from src.pipeline.review.models import IdentificationLayer, IdentificationPoint
from src.pipeline.review.presenter import present, _wrap


def _make_point(**overrides) -> IdentificationPoint:
    """Create a test IdentificationPoint with sensible defaults."""
    defaults = dict(
        instance_id="test-instance-001",
        layer=IdentificationLayer.L2_TAGGING,
        point_id="L2-1",
        point_label="Primary label",
        pipeline_component="EventTagger",
        trigger="Event tool_use from actor=orchestrator requires classification",
        observation_state="actor=orchestrator, event_type=tool_use",
        action_taken="primary_tag=delegation (confidence=0.85)",
        downstream_impact="Primary tag drives episode population mode/risk inference",
        provenance_pointer="sess_abc:evt_123:events:line42",
    )
    defaults.update(overrides)
    return IdentificationPoint(**defaults)


class TestPresent:
    """Tests for present() display formatting."""

    def test_returns_string_with_all_five_field_labels(self):
        """present() returns string containing all five field labels."""
        point = _make_point()
        output = present(point)

        assert "IDENTIFICATION POINT:" in output
        assert "RAW DATA:" in output
        assert "DECISION MADE:" in output
        assert "DOWNSTREAM IMPACT:" in output
        assert "PROVENANCE:" in output

    def test_layer_value_appears_in_output(self):
        """Layer value (e.g. 'L2') appears in the identification point line."""
        point = _make_point(layer=IdentificationLayer.L3_SEGMENTATION)
        output = present(point)

        assert "[L3]" in output

    def test_point_label_appears_in_output(self):
        """Point label appears in the identification point line."""
        point = _make_point(point_label="Risk assessment")
        output = present(point)

        assert "Risk assessment" in output

    def test_pipeline_component_appears_in_output(self):
        """Pipeline component appears in the footer line."""
        point = _make_point(pipeline_component="ReactionLabeler")
        output = present(point)

        assert "[Pipeline component: ReactionLabeler]" in output

    def test_observation_state_in_raw_data(self):
        """observation_state value appears in the RAW DATA field."""
        point = _make_point(observation_state="actor=orchestrator, event_type=tool_use")
        output = present(point)

        assert "actor=orchestrator, event_type=tool_use" in output

    def test_action_taken_in_decision_made(self):
        """action_taken value appears in the DECISION MADE field."""
        point = _make_point(action_taken="primary_tag=delegation")
        output = present(point)

        assert "primary_tag=delegation" in output

    def test_provenance_in_output(self):
        """provenance_pointer value appears in the PROVENANCE field."""
        point = _make_point(provenance_pointer="sess:evt:table:key")
        output = present(point)

        assert "sess:evt:table:key" in output


class TestWrap:
    """Tests for _wrap() text wrapping."""

    def test_short_text_unchanged(self):
        """Text shorter than width is returned unchanged."""
        result = _wrap("short text", width=80)
        assert result == "short text"

    def test_long_text_wrapped_at_width(self):
        """Text longer than width is wrapped into multiple lines."""
        long_text = "word " * 30  # ~150 chars
        result = _wrap(long_text, width=80)

        # Result should contain a newline (was wrapped)
        assert "\n" in result
        # First line content should be <= 80 chars
        lines = result.split("\n")
        assert len(lines[0].rstrip()) <= 80

    def test_empty_text(self):
        """Empty string is returned as-is."""
        result = _wrap("", width=80)
        assert result == ""

    def test_exact_width_text_unchanged(self):
        """Text exactly at width is returned unchanged."""
        text = "x" * 80
        result = _wrap(text, width=80)
        assert result == text
