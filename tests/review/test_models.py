"""Tests for identification review data models.

Verifies:
- IdentificationPoint with all required fields serializes to dict cleanly
- ReviewVerdict enum values are 'accept' and 'reject'
- IdentificationLayer enum has all 8 expected values
"""

from __future__ import annotations

import pytest

from src.pipeline.review.models import (
    IdentificationLayer,
    IdentificationPoint,
    IdentificationReview,
    ReviewVerdict,
)


class TestIdentificationLayer:
    """IdentificationLayer enum has all 8 pipeline layers."""

    def test_has_eight_layers(self):
        assert len(IdentificationLayer) == 8

    def test_layer_values(self):
        expected = {"L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"}
        actual = {layer.value for layer in IdentificationLayer}
        assert actual == expected

    def test_layer_names(self):
        expected_names = {
            "L1_EVENT_FILTER",
            "L2_TAGGING",
            "L3_SEGMENTATION",
            "L4_EPISODE_POPULATION",
            "L5_CONSTRAINT_EXTRACTION",
            "L6_CONSTRAINT_EVALUATION",
            "L7_ESCALATION_DETECTION",
            "L8_POLICY_FEEDBACK",
        }
        actual_names = {layer.name for layer in IdentificationLayer}
        assert actual_names == expected_names

    def test_is_string_enum(self):
        """Layer values are strings, usable in SQL."""
        for layer in IdentificationLayer:
            assert isinstance(layer.value, str)


class TestReviewVerdict:
    """ReviewVerdict enum has exactly accept and reject."""

    def test_has_two_values(self):
        assert len(ReviewVerdict) == 2

    def test_accept_value(self):
        assert ReviewVerdict.ACCEPT.value == "accept"

    def test_reject_value(self):
        assert ReviewVerdict.REJECT.value == "reject"


class TestIdentificationPoint:
    """IdentificationPoint serialization and field validation."""

    @pytest.fixture
    def valid_point(self) -> IdentificationPoint:
        return IdentificationPoint(
            layer=IdentificationLayer.L2_TAGGING,
            point_id="L2-1",
            point_label="Primary label",
            pipeline_component="EventTagger",
            trigger="Event assistant_text requires classification",
            observation_state="actor=executor, event_type=assistant_text",
            action_taken="primary_tag=X_ASK (confidence=0.80)",
            downstream_impact="Primary tag drives episode population",
            provenance_pointer="sess1:evt1:events:ref1",
            source_session_id="sess1",
            source_event_id="evt1",
        )

    def test_serializes_to_dict(self, valid_point: IdentificationPoint):
        d = valid_point.model_dump()
        assert isinstance(d, dict)
        assert d["layer"] == "L2"
        assert d["point_id"] == "L2-1"
        assert d["pipeline_component"] == "EventTagger"

    def test_instance_id_auto_generated(self, valid_point: IdentificationPoint):
        assert valid_point.instance_id
        assert isinstance(valid_point.instance_id, str)
        assert len(valid_point.instance_id) > 0

    def test_five_externalization_properties(self, valid_point: IdentificationPoint):
        """All five decision-boundary externalization properties present."""
        assert valid_point.trigger
        assert valid_point.observation_state
        assert valid_point.action_taken
        assert valid_point.downstream_impact
        assert valid_point.provenance_pointer

    def test_optional_fields_default_none(self):
        point = IdentificationPoint(
            layer=IdentificationLayer.L1_EVENT_FILTER,
            point_id="L1-1",
            point_label="Record meaningfulness",
            pipeline_component="EventFilter",
            trigger="test",
            observation_state="test",
            action_taken="test",
            downstream_impact="test",
            provenance_pointer="test",
        )
        assert point.source_session_id is None
        assert point.source_event_id is None
        assert point.source_episode_id is None

    def test_custom_instance_id(self):
        point = IdentificationPoint(
            instance_id="events:evt123:L2-1",
            layer=IdentificationLayer.L2_TAGGING,
            point_id="L2-1",
            point_label="Primary label",
            pipeline_component="EventTagger",
            trigger="test",
            observation_state="test",
            action_taken="test",
            downstream_impact="test",
            provenance_pointer="test",
        )
        assert point.instance_id == "events:evt123:L2-1"


class TestIdentificationReview:
    """IdentificationReview serialization and field validation."""

    def test_serializes_to_dict(self):
        review = IdentificationReview(
            identification_instance_id="events:evt1:L2-1",
            layer=IdentificationLayer.L2_TAGGING,
            point_id="L2-1",
            pipeline_component="EventTagger",
            trigger="test trigger",
            observation_state="test obs",
            action_taken="test action",
            downstream_impact="test impact",
            provenance_pointer="sess1:evt1:events:ref1",
            verdict=ReviewVerdict.ACCEPT,
            reviewed_at="2026-02-23T12:00:00Z",
        )
        d = review.model_dump()
        assert d["verdict"] == "accept"
        assert d["reviewed_at"] == "2026-02-23T12:00:00Z"
        assert d["opinion"] is None

    def test_review_id_auto_generated(self):
        review = IdentificationReview(
            identification_instance_id="test",
            layer=IdentificationLayer.L1_EVENT_FILTER,
            point_id="L1-1",
            pipeline_component="EventFilter",
            trigger="t",
            observation_state="o",
            action_taken="a",
            downstream_impact="d",
            provenance_pointer="p",
            verdict=ReviewVerdict.REJECT,
            opinion="Wrong actor assignment",
            reviewed_at="2026-02-23T12:00:00Z",
        )
        assert review.review_id
        assert isinstance(review.review_id, str)

    def test_reject_with_opinion(self):
        review = IdentificationReview(
            identification_instance_id="test",
            layer=IdentificationLayer.L3_SEGMENTATION,
            point_id="L3-1",
            pipeline_component="Segmenter",
            trigger="t",
            observation_state="o",
            action_taken="a",
            downstream_impact="d",
            provenance_pointer="p",
            verdict=ReviewVerdict.REJECT,
            opinion="False positive boundary -- X_ASK is mid-episode",
            reviewed_at="2026-02-23T12:00:00Z",
        )
        assert review.verdict == ReviewVerdict.REJECT
        assert review.opinion is not None
