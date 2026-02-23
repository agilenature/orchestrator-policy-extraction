"""Tests for the ReviewWriter.

Verifies append-only semantics, integrity constraint enforcement, and
that written rows are retrievable with all fields intact.
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.review.models import (
    IdentificationLayer,
    IdentificationReview,
    ReviewVerdict,
)
from src.pipeline.review.schema import create_review_schema
from src.pipeline.review.writer import ReviewWriter, ReviewWriterError


@pytest.fixture
def conn():
    """In-memory DuckDB connection with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    return c


def _make_review(**overrides) -> IdentificationReview:
    """Create a test IdentificationReview with sensible defaults."""
    defaults = dict(
        review_id="rev-001",
        identification_instance_id="inst-001",
        layer=IdentificationLayer.L2_TAGGING,
        point_id="L2-1",
        pipeline_component="EventTagger",
        trigger="Event tool_use requires classification",
        observation_state="actor=orchestrator, event_type=tool_use",
        action_taken="primary_tag=delegation (confidence=0.85)",
        downstream_impact="Primary tag drives episode population",
        provenance_pointer="sess:evt:events:line42",
        verdict=ReviewVerdict.ACCEPT,
        opinion=None,
        reviewed_at="2026-02-23T18:00:00+00:00",
        session_id=None,
    )
    defaults.update(overrides)
    return IdentificationReview(**defaults)


class TestReviewWriter:
    """Tests for ReviewWriter.write()."""

    def test_write_inserts_one_row(self, conn):
        """write() inserts one row to identification_reviews."""
        writer = ReviewWriter(conn)
        review = _make_review()
        writer.write(review)

        count = conn.execute(
            "SELECT COUNT(*) FROM identification_reviews"
        ).fetchone()[0]
        assert count == 1

    def test_duplicate_instance_id_raises_error(self, conn):
        """Writing same identification_instance_id twice raises ReviewWriterError."""
        writer = ReviewWriter(conn)
        review1 = _make_review(
            review_id="rev-001",
            identification_instance_id="inst-001",
        )
        review2 = _make_review(
            review_id="rev-002",
            identification_instance_id="inst-001",
        )
        writer.write(review1)

        with pytest.raises(ReviewWriterError, match="Append-only violation"):
            writer.write(review2)

    def test_duplicate_review_id_raises_error(self, conn):
        """Writing same review_id twice raises ReviewWriterError."""
        writer = ReviewWriter(conn)
        review1 = _make_review(
            review_id="rev-001",
            identification_instance_id="inst-001",
        )
        review2 = _make_review(
            review_id="rev-001",
            identification_instance_id="inst-002",
        )
        writer.write(review1)

        with pytest.raises(ReviewWriterError, match="Append-only violation"):
            writer.write(review2)

    def test_written_row_retrievable_with_all_fields(self, conn):
        """Written row is retrievable with all fields intact."""
        writer = ReviewWriter(conn)
        review = _make_review(
            review_id="rev-full",
            identification_instance_id="inst-full",
            layer=IdentificationLayer.L3_SEGMENTATION,
            point_id="L3-2",
            pipeline_component="Segmenter",
            trigger="Event evaluated as boundary",
            observation_state="end_event=evt_456",
            action_taken="end_trigger=X_RES",
            downstream_impact="Episode completeness affected",
            provenance_pointer="sess:evt:episode_segments:seg1",
            verdict=ReviewVerdict.REJECT,
            opinion="Incorrect boundary placement",
            reviewed_at="2026-02-23T19:00:00+00:00",
            session_id="session-xyz",
        )
        writer.write(review)

        row = conn.execute(
            "SELECT * FROM identification_reviews WHERE review_id = 'rev-full'"
        ).fetchone()

        assert row is not None
        # Unpack by column order
        (
            review_id, inst_id, layer, point_id, component,
            trigger_text, obs_state, action, impact, provenance,
            verdict, opinion, reviewed_at, session_id
        ) = row

        assert review_id == "rev-full"
        assert inst_id == "inst-full"
        assert layer == "L3"
        assert point_id == "L3-2"
        assert component == "Segmenter"
        assert trigger_text == "Event evaluated as boundary"
        assert obs_state == "end_event=evt_456"
        assert action == "end_trigger=X_RES"
        assert impact == "Episode completeness affected"
        assert provenance == "sess:evt:episode_segments:seg1"
        assert verdict == "reject"
        assert opinion == "Incorrect boundary placement"
        assert session_id == "session-xyz"

    def test_no_update_or_delete_methods(self):
        """ReviewWriter has no update() or delete() methods (API constraint)."""
        assert not hasattr(ReviewWriter, "update")
        assert not hasattr(ReviewWriter, "delete")

    def test_write_with_none_opinion(self, conn):
        """write() handles None opinion correctly."""
        writer = ReviewWriter(conn)
        review = _make_review(opinion=None)
        writer.write(review)

        row = conn.execute(
            "SELECT opinion FROM identification_reviews WHERE review_id = 'rev-001'"
        ).fetchone()
        assert row[0] is None
