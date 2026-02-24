"""Tests for DDF Detection Substrate schema and models (Phase 15).

Covers:
- flame_events table creation with correct columns
- ai_flame_events view filtering
- axis_hypotheses and constraint_metrics tables
- memory_candidates extension columns
- FlameEvent model ID generation and validation
- O_AXS classification label acceptance
- DDFConfig defaults and YAML loading
- Schema idempotency
- CHECK constraint enforcement on flame_events.subject
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.models import (
    AxisHypothesis,
    ConstraintMetric,
    FlameEvent,
    IntelligenceProfile,
)
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.models.config import DDFConfig, OAxsConfig, load_config
from src.pipeline.models.events import Classification
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


# ── Test 1: flame_events table exists with correct columns ──


def test_create_ddf_schema_creates_flame_events(conn):
    """Verify flame_events exists with all expected columns.

    The base DDL defines 16 columns; Phase 17 adds assessment_session_id
    via ALTER TABLE in create_assessment_schema (called by the schema chain).
    """
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'flame_events' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]

    # Base 16 columns from Phase 15 DDL
    expected_base = [
        "flame_event_id",
        "session_id",
        "human_id",
        "prompt_number",
        "marker_level",
        "marker_type",
        "evidence_excerpt",
        "quality_score",
        "axis_identified",
        "flood_confirmed",
        "subject",
        "detection_source",
        "deposited_to_candidates",
        "source_episode_id",
        "session_event_ref",
        "created_at",
    ]
    for col in expected_base:
        assert col in col_names, f"Missing base column: {col}"

    # Phase 17 extension column
    assert "assessment_session_id" in col_names
    assert len(col_names) == 17


# ── Test 2: ai_flame_events view filters subject='ai' ──


def test_create_ddf_schema_creates_ai_flame_events_view(conn):
    """Verify ai_flame_events view returns only subject='ai' rows."""
    # Insert one human and one AI flame event
    conn.execute(
        "INSERT INTO flame_events (flame_event_id, session_id, marker_level, "
        "marker_type, subject) VALUES ('h1', 's1', 3, 'trunk_id', 'human')"
    )
    conn.execute(
        "INSERT INTO flame_events (flame_event_id, session_id, marker_level, "
        "marker_type, subject) VALUES ('a1', 's1', 2, 'concept_intro', 'ai')"
    )

    # View should return only the AI row
    rows = conn.execute("SELECT * FROM ai_flame_events").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "a1"  # flame_event_id


# ── Test 3: axis_hypotheses table exists ──


def test_create_ddf_schema_creates_axis_hypotheses(conn):
    """Verify axis_hypotheses table exists with expected columns."""
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'axis_hypotheses' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert "hypothesis_id" in col_names
    assert "hypothesized_axis" in col_names
    assert "confidence" in col_names
    assert "marker_type" in col_names


# ── Test 4: constraint_metrics table exists ──


def test_create_ddf_schema_creates_constraint_metrics(conn):
    """Verify constraint_metrics table exists with expected columns."""
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'constraint_metrics' ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert "constraint_id" in col_names
    assert "radius" in col_names
    assert "firing_count" in col_names
    assert "is_stagnant" in col_names


# ── Test 5: memory_candidates extension columns ──


def test_memory_candidates_extension_columns(conn):
    """Verify source_flame_event_id, fidelity, detection_count columns added."""
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'memory_candidates'"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert "source_flame_event_id" in col_names
    assert "fidelity" in col_names
    assert "detection_count" in col_names


# ── Test 6: FlameEvent.make_id deterministic ──


def test_flame_event_model_make_id():
    """Verify FlameEvent.make_id produces deterministic IDs."""
    id1 = FlameEvent.make_id("sess1", 42, "trunk_id")
    id2 = FlameEvent.make_id("sess1", 42, "trunk_id")
    id3 = FlameEvent.make_id("sess1", 43, "trunk_id")

    assert id1 == id2, "Same inputs must produce same ID"
    assert id1 != id3, "Different inputs must produce different IDs"
    assert len(id1) == 16, "ID must be 16 hex characters"


# ── Test 7: FlameEvent model validation ──


def test_flame_event_model_validation():
    """Verify marker_level 0-7 range and subject enum validation."""
    # Valid creation
    fe = FlameEvent(
        flame_event_id="test1",
        session_id="s1",
        marker_level=0,
        marker_type="trunk_id",
        subject="human",
    )
    assert fe.marker_level == 0
    assert fe.subject == "human"

    # Max valid level
    fe7 = FlameEvent(
        flame_event_id="test2",
        session_id="s1",
        marker_level=7,
        marker_type="flood",
        subject="ai",
    )
    assert fe7.marker_level == 7
    assert fe7.subject == "ai"

    # Invalid marker level
    with pytest.raises(ValueError, match="marker_level must be between 0 and 7"):
        FlameEvent(
            flame_event_id="test3",
            session_id="s1",
            marker_level=8,
            marker_type="invalid",
        )

    # Invalid marker level (negative)
    with pytest.raises(ValueError, match="marker_level must be between 0 and 7"):
        FlameEvent(
            flame_event_id="test4",
            session_id="s1",
            marker_level=-1,
            marker_type="invalid",
        )


# ── Test 8: O_AXS valid classification label ──


def test_o_axs_valid_label():
    """Verify Classification accepts O_AXS label with axis_shift_detector source."""
    c = Classification(
        label="O_AXS",
        confidence=0.8,
        source="axis_shift_detector",
    )
    assert c.label == "O_AXS"
    assert c.source == "axis_shift_detector"

    # Also verify ddf_tier1 and ddf_tier2 sources work
    c1 = Classification(label="O_AXS", confidence=0.7, source="ddf_tier1")
    assert c1.source == "ddf_tier1"

    c2 = Classification(label="O_AXS", confidence=0.6, source="ddf_tier2")
    assert c2.source == "ddf_tier2"


# ── Test 9: DDFConfig defaults ──


def test_ddf_config_defaults():
    """Verify DDFConfig loads with correct default values."""
    cfg = DDFConfig()
    assert cfg.o_axs.granularity_drop_ratio == 0.5
    assert cfg.o_axs.prior_prompts_window == 4
    assert cfg.o_axs.novel_concept_min_occurrences == 2
    assert cfg.o_axs.novel_concept_message_window == 3
    assert cfg.false_integration_confidence_threshold == 0.6
    assert cfg.epistemological_default == "principled"
    assert cfg.stagnation_min_firing_count == 10


# ── Test 10: DDFConfig from YAML ──


def test_ddf_config_from_yaml():
    """Verify load_config() includes ddf.o_axs.granularity_drop_ratio = 0.5."""
    cfg = load_config()
    assert hasattr(cfg, "ddf")
    assert cfg.ddf.o_axs.granularity_drop_ratio == 0.5
    assert cfg.ddf.false_integration_confidence_threshold == 0.6
    assert cfg.ddf.epistemological_default == "principled"
    assert cfg.ddf.stagnation_min_firing_count == 10


# ── Test 11: Schema idempotency ──


def test_create_ddf_schema_idempotent():
    """Calling create_ddf_schema twice must not raise errors."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    # Second call to create_ddf_schema (first is inside create_schema)
    create_ddf_schema(c)
    # Verify tables still exist
    tables = c.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "flame_events" in table_names
    c.close()


# ── Test 12: CHECK constraint on subject column ──


def test_flame_events_subject_check_constraint(conn):
    """INSERT with invalid subject must raise an error."""
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            "INSERT INTO flame_events (flame_event_id, session_id, marker_level, "
            "marker_type, subject) VALUES ('bad1', 's1', 3, 'test', 'invalid')"
        )
