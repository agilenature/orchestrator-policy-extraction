"""Tests for Phase 13 feedback loop data models, config, schema, and writer.

Covers:
- PolicyErrorEvent creation with all fields
- make_policy_error_event deterministic ID generation (same inputs = same ID)
- make_policy_error_event different IDs for different error_types
- PolicyErrorEvent is frozen (immutable)
- PolicyFeedbackConfig defaults
- PolicyFeedbackConfig wired into PipelineConfig
- policy_error_events table created by create_schema (in-memory DuckDB)
- write_policy_error_events writes and is idempotent (INSERT OR REPLACE)
- write_policy_error_events with empty list returns {"written": 0}
- ConstraintExtractor._make_constraint_id with source parameter
- ConstraintExtractor._make_constraint_id default source backward compat
- Backward compat explicit: old-format ID != new-format ID
"""

from __future__ import annotations

import hashlib

import duckdb
import pytest

from src.pipeline.constraint_extractor import ConstraintExtractor
from src.pipeline.feedback.models import PolicyErrorEvent, make_policy_error_event
from src.pipeline.models.config import PipelineConfig, PolicyFeedbackConfig
from src.pipeline.storage.schema import create_schema, drop_schema
from src.pipeline.storage.writer import write_policy_error_events


# --- PolicyErrorEvent model tests ---


def test_policy_error_event_creation():
    """PolicyErrorEvent can be created with all required fields."""
    event = PolicyErrorEvent(
        error_id="abc123def456gh78",
        session_id="s1",
        episode_id="ep1",
        error_type="suppressed",
        constraint_id="c1",
        recommendation_mode="Implement",
        recommendation_risk="low",
        detected_at="2026-02-20T00:00:00+00:00",
    )
    assert event.error_id == "abc123def456gh78"
    assert event.session_id == "s1"
    assert event.episode_id == "ep1"
    assert event.error_type == "suppressed"
    assert event.constraint_id == "c1"
    assert event.recommendation_mode == "Implement"
    assert event.recommendation_risk == "low"
    assert event.detected_at == "2026-02-20T00:00:00+00:00"


def test_policy_error_event_frozen():
    """PolicyErrorEvent is immutable (frozen=True)."""
    event = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    with pytest.raises(Exception):
        event.error_type = "surfaced_and_blocked"  # type: ignore[misc]


def test_make_policy_error_event_deterministic_id():
    """Same inputs produce the same error_id (deterministic)."""
    e1 = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    e2 = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    assert e1.error_id == e2.error_id
    assert len(e1.error_id) == 16


def test_make_policy_error_event_different_error_type_different_id():
    """Different error_type values produce different error_ids."""
    e1 = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    e2 = make_policy_error_event("s1", "ep1", "c1", "surfaced_and_blocked", "Implement", "low")
    assert e1.error_id != e2.error_id


def test_make_policy_error_event_detected_at_populated():
    """make_policy_error_event auto-populates detected_at."""
    event = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    assert event.detected_at  # non-empty
    assert "T" in event.detected_at  # ISO format


def test_make_policy_error_event_id_format():
    """error_id is a 16-char hex string derived from SHA-256."""
    event = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    expected_key = "s1:ep1:c1:suppressed"
    expected_id = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
    assert event.error_id == expected_id


# --- PolicyFeedbackConfig tests ---


def test_policy_feedback_config_defaults():
    """PolicyFeedbackConfig has correct default values."""
    cfg = PolicyFeedbackConfig()
    assert cfg.promote_after_sessions == 3
    assert cfg.error_rate_target == 0.05
    assert cfg.rolling_window_sessions == 100


def test_policy_feedback_config_in_pipeline_config():
    """PolicyFeedbackConfig is wired into PipelineConfig."""
    cfg = PipelineConfig()
    assert hasattr(cfg, "feedback")
    assert isinstance(cfg.feedback, PolicyFeedbackConfig)
    assert cfg.feedback.promote_after_sessions == 3
    assert cfg.feedback.error_rate_target == 0.05
    assert cfg.feedback.rolling_window_sessions == 100


def test_policy_feedback_config_custom_values():
    """PolicyFeedbackConfig accepts custom values."""
    cfg = PolicyFeedbackConfig(
        promote_after_sessions=5,
        error_rate_target=0.10,
        rolling_window_sessions=50,
    )
    assert cfg.promote_after_sessions == 5
    assert cfg.error_rate_target == 0.10
    assert cfg.rolling_window_sessions == 50


# --- DuckDB schema tests ---


@pytest.fixture()
def db_conn():
    """In-memory DuckDB connection with schema created."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn
    conn.close()


def test_policy_error_events_table_exists(db_conn):
    """policy_error_events table is created by create_schema."""
    result = db_conn.execute(
        "SELECT * FROM policy_error_events"
    ).fetchall()
    assert result == []


def test_policy_error_events_table_columns(db_conn):
    """policy_error_events table has all expected columns."""
    columns = db_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'policy_error_events' "
        "ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in columns]
    assert "error_id" in col_names
    assert "session_id" in col_names
    assert "episode_id" in col_names
    assert "error_type" in col_names
    assert "constraint_id" in col_names
    assert "recommendation_mode" in col_names
    assert "recommendation_risk" in col_names
    assert "detected_at" in col_names


def test_policy_error_events_check_constraint(db_conn):
    """error_type CHECK constraint rejects invalid values."""
    with pytest.raises(duckdb.ConstraintException):
        db_conn.execute(
            "INSERT INTO policy_error_events "
            "(error_id, session_id, error_type) "
            "VALUES ('e1', 's1', 'invalid_type')"
        )


def test_policy_error_events_valid_types(db_conn):
    """error_type CHECK constraint accepts valid values."""
    db_conn.execute(
        "INSERT INTO policy_error_events "
        "(error_id, session_id, error_type) "
        "VALUES ('e1', 's1', 'suppressed')"
    )
    db_conn.execute(
        "INSERT INTO policy_error_events "
        "(error_id, session_id, error_type) "
        "VALUES ('e2', 's1', 'surfaced_and_blocked')"
    )
    count = db_conn.execute(
        "SELECT count(*) FROM policy_error_events"
    ).fetchone()[0]
    assert count == 2


def test_drop_schema_includes_policy_error_events(db_conn):
    """drop_schema removes policy_error_events table."""
    drop_schema(db_conn)
    with pytest.raises(duckdb.CatalogException):
        db_conn.execute("SELECT * FROM policy_error_events")


# --- Writer tests ---


def test_write_policy_error_events_empty(db_conn):
    """write_policy_error_events with empty list returns written=0."""
    result = write_policy_error_events(db_conn, [])
    assert result == {"written": 0}


def test_write_policy_error_events_single(db_conn):
    """write_policy_error_events persists a single event."""
    event = make_policy_error_event(
        "s1", "ep1", "c1", "suppressed", "Implement", "low"
    )
    result = write_policy_error_events(db_conn, [event])
    assert result == {"written": 1}

    rows = db_conn.execute(
        "SELECT error_id, session_id, episode_id, error_type, "
        "constraint_id, recommendation_mode, recommendation_risk "
        "FROM policy_error_events"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == event.error_id
    assert rows[0][1] == "s1"
    assert rows[0][2] == "ep1"
    assert rows[0][3] == "suppressed"
    assert rows[0][4] == "c1"
    assert rows[0][5] == "Implement"
    assert rows[0][6] == "low"


def test_write_policy_error_events_idempotent(db_conn):
    """write_policy_error_events is idempotent (INSERT OR REPLACE)."""
    event = make_policy_error_event(
        "s1", "ep1", "c1", "suppressed", "Implement", "low"
    )
    write_policy_error_events(db_conn, [event])
    write_policy_error_events(db_conn, [event])  # Second write

    count = db_conn.execute(
        "SELECT count(*) FROM policy_error_events"
    ).fetchone()[0]
    assert count == 1  # No duplicate


def test_write_policy_error_events_multiple(db_conn):
    """write_policy_error_events handles multiple events."""
    e1 = make_policy_error_event("s1", "ep1", "c1", "suppressed", "Implement", "low")
    e2 = make_policy_error_event("s2", "ep2", "c2", "surfaced_and_blocked", "Ask", "high")
    result = write_policy_error_events(db_conn, [e1, e2])
    assert result == {"written": 2}

    count = db_conn.execute(
        "SELECT count(*) FROM policy_error_events"
    ).fetchone()[0]
    assert count == 2


# --- ConstraintExtractor._make_constraint_id tests ---


@pytest.fixture()
def extractor():
    """Default ConstraintExtractor."""
    return ConstraintExtractor(PipelineConfig())


def test_make_constraint_id_with_source(extractor):
    """_make_constraint_id with explicit source produces expected ID."""
    id1 = extractor._make_constraint_id("test text", ["a.py"], source="human_correction")
    id2 = extractor._make_constraint_id("test text", ["a.py"], source="feedback_loop")
    assert id1 != id2
    assert len(id1) == 16
    assert len(id2) == 16


def test_make_constraint_id_default_source(extractor):
    """_make_constraint_id default source is 'human_correction'."""
    id_default = extractor._make_constraint_id("test text", ["a.py"])
    id_explicit = extractor._make_constraint_id("test text", ["a.py"], source="human_correction")
    assert id_default == id_explicit


def test_make_constraint_id_deterministic_with_source(extractor):
    """Same inputs with same source produce same ID."""
    id1 = extractor._make_constraint_id("test text", ["a.py", "b.py"], source="feedback_loop")
    id2 = extractor._make_constraint_id("test text", ["b.py", "a.py"], source="feedback_loop")
    assert id1 == id2  # scope_paths are sorted


def test_make_constraint_id_backward_compat_explicit(extractor):
    """Old-format IDs (without source) differ from new-format IDs (with source).

    This confirms the forward-only ID break is intentional: old constraints
    keep their old IDs in constraints.json, new extractions produce
    new-format IDs with the source appended.
    """
    text = "do not use eval."
    scope_paths = ["src/api/handler.py"]
    scope_key = "|".join(sorted(scope_paths))

    # Old format: key = text.lower().strip() + ":" + scope_key (no source)
    old_key = f"{text.lower().strip()}:{scope_key}"
    old_id = hashlib.sha256(old_key.encode()).hexdigest()[:16]

    # New format: key = text.lower().strip() + ":" + scope_key + ":" + source
    new_id = extractor._make_constraint_id(text, scope_paths, source="human_correction")

    assert old_id != new_id, (
        "Old-format ID should differ from new-format ID "
        "(forward-only break confirmed)"
    )


def test_make_constraint_id_pipe_separator_preserved(extractor):
    """ConstraintExtractor keeps '|' separator for scope paths (locked decision)."""
    text = "test constraint."
    scope_paths = ["a.py", "b.py"]
    scope_key = "|".join(sorted(scope_paths))
    expected_key = f"{text.lower().strip()}:{scope_key}:human_correction"
    expected_id = hashlib.sha256(expected_key.encode()).hexdigest()[:16]

    actual_id = extractor._make_constraint_id(text, scope_paths)
    assert actual_id == expected_id
