"""Tests for GenusEdgeWriter, append_genus_staging, and ingest_genus_staging.

Tests:
- GenusEdgeWriter.build_genus_edge produces valid EdgeRecord
- GenusEdgeWriter.build_genus_shift_event produces valid FlameEvent
- append_genus_staging writes to JSONL file
- ingest_genus_staging roundtrip: staging -> DuckDB axis_edges + flame_events
- ingest_genus_staging with empty file returns zeros
- ingest_genus_staging clears staging after success
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.premise.genus_writer import (
    GenusEdgeWriter,
    append_genus_staging,
    ingest_genus_staging,
)
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """Create an in-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    create_ddf_schema(c)
    yield c
    c.close()


@pytest.fixture
def writer():
    """Create a GenusEdgeWriter instance."""
    return GenusEdgeWriter()


def _staging_path(tmp_path: Path) -> str:
    """Return a unique staging path within tmp_path."""
    return str(tmp_path / "genus_staging.jsonl")


class TestBuildGenusEdge:
    """Tests for GenusEdgeWriter.build_genus_edge."""

    def test_produces_valid_edge_record(self, writer):
        """build_genus_edge should return an EdgeRecord with correct fields."""
        edge = writer.build_genus_edge(
            genus_name="corpus-relative identity retrieval",
            premise_claim="per-file search fails across repos",
            session_id="sess-1",
            instances=["A7 per-file searchability", "shared-aspect collision"],
        )

        assert edge.relationship_text == "genus_of"
        assert edge.abstraction_level == 3
        assert edge.axis_a == "corpus-relative identity retrieval"
        assert edge.axis_b == "per-file search fails across repos"
        assert edge.status == "candidate"
        assert edge.trunk_quality == 1.0
        assert edge.created_session_id == "sess-1"
        assert edge.evidence["instances"] == [
            "A7 per-file searchability",
            "shared-aspect collision",
        ]
        assert edge.evidence["source"] == "genus_check_gate"

    def test_edge_id_is_deterministic(self, writer):
        """Same inputs should produce the same edge_id."""
        edge1 = writer.build_genus_edge("genus-A", "claim-X", "sess-1")
        edge2 = writer.build_genus_edge("genus-A", "claim-X", "sess-2")
        assert edge1.edge_id == edge2.edge_id  # ID based on axis_a|axis_b|rel

    def test_axis_b_truncated_to_100(self, writer):
        """Premise claim longer than 100 chars should be truncated for axis_b."""
        long_claim = "x" * 200
        edge = writer.build_genus_edge("genus-A", long_claim, "sess-1")
        assert len(edge.axis_b) == 100

    def test_activation_condition_write_class(self, writer):
        """Activation condition should target write_class goal type."""
        edge = writer.build_genus_edge("genus-A", "claim", "sess-1")
        assert edge.activation_condition.goal_type == ["write_class"]
        assert edge.activation_condition.min_axes_simultaneously_active == 1


class TestBuildGenusShiftEvent:
    """Tests for GenusEdgeWriter.build_genus_shift_event."""

    def test_produces_valid_flame_event(self, writer):
        """build_genus_shift_event should return a FlameEvent with correct fields."""
        fe = writer.build_genus_shift_event(
            genus_name="corpus-relative identity retrieval",
            session_id="sess-1",
            evidence_excerpt="per-file search fails",
        )

        assert fe.marker_type == "genus_shift"
        assert fe.subject == "ai"
        assert fe.marker_level == 2
        assert fe.detection_source == "stub"
        assert fe.axis_identified == "corpus-relative identity retrieval"
        assert fe.deposited_to_candidates is False
        assert fe.evidence_excerpt == "per-file search fails"

    def test_defaults_evidence_to_genus_name(self, writer):
        """When no evidence_excerpt provided, should default to genus_name."""
        fe = writer.build_genus_shift_event("genus-A", "sess-1")
        assert fe.evidence_excerpt == "genus-A"


class TestAppendGenusStaging:
    """Tests for append_genus_staging."""

    def test_writes_records_to_jsonl(self, tmp_path):
        """append_genus_staging should write records as JSONL lines."""
        path = _staging_path(tmp_path)
        records = [
            {"edge": {"axis_a": "genus-A"}, "flame_event": {"marker_type": "genus_shift"}},
            {"edge": {"axis_a": "genus-B"}, "flame_event": {"marker_type": "genus_shift"}},
        ]

        count = append_genus_staging(records, path)

        assert count == 2
        lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["edge"]["axis_a"] == "genus-A"

    def test_empty_records_returns_zero(self, tmp_path):
        """append_genus_staging with empty list should return 0."""
        path = _staging_path(tmp_path)
        count = append_genus_staging([], path)
        assert count == 0


class TestIngestGenusStaging:
    """Tests for ingest_genus_staging roundtrip."""

    def test_roundtrip_staging_to_duckdb(self, conn, writer, tmp_path):
        """Full roundtrip: build -> serialize -> stage -> ingest -> verify in DB."""
        path = _staging_path(tmp_path)

        # Build edge and flame event
        edge = writer.build_genus_edge(
            genus_name="corpus-relative identity retrieval",
            premise_claim="per-file search fails",
            session_id="sess-roundtrip",
            instances=["A7", "ObjLib"],
        )
        fe = writer.build_genus_shift_event(
            genus_name="corpus-relative identity retrieval",
            session_id="sess-roundtrip",
        )

        # Serialize to staging format
        edge_dict = json.loads(edge.model_dump_json())
        fe_dict = json.loads(fe.model_dump_json())
        staging_record = {
            "edge": edge_dict,
            "flame_event": fe_dict,
            "session_id": "sess-roundtrip",
            "created_at": "2026-02-28T00:00:00Z",
        }
        append_genus_staging([staging_record], path)

        # Ingest
        stats = ingest_genus_staging(conn, path)

        assert stats["edges_written"] == 1
        assert stats["events_written"] == 1
        assert stats["errors"] == 0

        # Verify edge in axis_edges
        rows = conn.execute(
            "SELECT edge_id, axis_a, relationship_text, abstraction_level, status "
            "FROM axis_edges WHERE axis_a = ?",
            ["corpus-relative identity retrieval"],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "genus_of"
        assert rows[0][3] == 3
        assert rows[0][4] == "candidate"

        # Verify flame_event in flame_events
        fe_rows = conn.execute(
            "SELECT flame_event_id, marker_type, subject, marker_level "
            "FROM flame_events WHERE marker_type = 'genus_shift'",
        ).fetchall()
        assert len(fe_rows) == 1
        assert fe_rows[0][1] == "genus_shift"
        assert fe_rows[0][2] == "ai"
        assert fe_rows[0][3] == 2

    def test_empty_staging_returns_zeros(self, conn, tmp_path):
        """Ingest with no staging file should return all zeros."""
        path = _staging_path(tmp_path)
        stats = ingest_genus_staging(conn, path)
        assert stats == {"edges_written": 0, "events_written": 0, "errors": 0}

    def test_clears_staging_after_success(self, conn, writer, tmp_path):
        """Staging file should be emptied after successful ingestion."""
        path = _staging_path(tmp_path)

        edge = writer.build_genus_edge("genus-A", "claim", "sess-1")
        fe = writer.build_genus_shift_event("genus-A", "sess-1")

        edge_dict = json.loads(edge.model_dump_json())
        fe_dict = json.loads(fe.model_dump_json())
        append_genus_staging([{
            "edge": edge_dict,
            "flame_event": fe_dict,
            "session_id": "sess-1",
            "created_at": "2026-02-28T00:00:00Z",
        }], path)

        ingest_genus_staging(conn, path)

        staging_file = Path(path)
        assert staging_file.exists()
        assert staging_file.read_text().strip() == ""

    def test_corrupt_line_counted_as_error(self, conn, tmp_path):
        """Corrupt JSONL line should increment errors counter."""
        path = _staging_path(tmp_path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write("not valid json\n")

        stats = ingest_genus_staging(conn, path)
        assert stats["errors"] == 1
        assert stats["edges_written"] == 0
