"""Tests for Phase 18 structural integrity schema, models, writer, and config."""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.ddf.structural.models import (
    StructuralEvent,
    StructuralIntegrityResult,
)
from src.pipeline.ddf.structural.schema import create_structural_schema
from src.pipeline.ddf.structural.writer import write_structural_events
from src.pipeline.ddf.models import IntelligenceProfile
from src.pipeline.models.config import DDFConfig, StructuralConfig
from src.pipeline.storage.schema import create_schema


@pytest.fixture
def conn():
    """In-memory DuckDB connection with full schema."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


@pytest.fixture
def structural_conn():
    """In-memory DuckDB connection with only structural schema."""
    c = duckdb.connect(":memory:")
    create_structural_schema(c)
    yield c
    c.close()


def _make_event(
    session_id: str = "sess-001",
    prompt_number: int = 1,
    signal_type: str = "gravity_check",
    subject: str = "human",
    signal_passed: bool = True,
    **kwargs,
) -> StructuralEvent:
    """Helper to create a valid StructuralEvent with sensible defaults."""
    event_id = StructuralEvent.make_id(session_id, prompt_number, signal_type)
    defaults = dict(
        event_id=event_id,
        session_id=session_id,
        prompt_number=prompt_number,
        subject=subject,
        signal_type=signal_type,
        signal_passed=signal_passed,
    )
    defaults.update(kwargs)
    return StructuralEvent(**defaults)


# -- Schema tests --


def test_create_structural_schema_creates_table(structural_conn):
    """Verify structural_events table exists after create_structural_schema."""
    tables = structural_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'structural_events'"
    ).fetchall()
    assert len(tables) == 1
    assert tables[0][0] == "structural_events"


def test_create_structural_schema_idempotent(structural_conn):
    """Call create_structural_schema twice, verify no error."""
    # Already called once in fixture
    create_structural_schema(structural_conn)

    tables = structural_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'structural_events'"
    ).fetchall()
    assert len(tables) == 1


def test_structural_events_check_constraints(structural_conn):
    """Insert with invalid signal_type must raise; valid must succeed."""
    # Invalid signal_type
    with pytest.raises(duckdb.ConstraintException):
        structural_conn.execute(
            "INSERT INTO structural_events "
            "(event_id, session_id, prompt_number, subject, signal_type, "
            "signal_passed) "
            "VALUES ('e1', 's1', 1, 'human', 'invalid_type', true)"
        )

    # Invalid subject
    with pytest.raises(duckdb.ConstraintException):
        structural_conn.execute(
            "INSERT INTO structural_events "
            "(event_id, session_id, prompt_number, subject, signal_type, "
            "signal_passed) "
            "VALUES ('e2', 's1', 1, 'robot', 'gravity_check', true)"
        )

    # Valid insert
    structural_conn.execute(
        "INSERT INTO structural_events "
        "(event_id, session_id, prompt_number, subject, signal_type, "
        "signal_passed) "
        "VALUES ('e3', 's1', 1, 'human', 'gravity_check', true)"
    )
    count = structural_conn.execute(
        "SELECT COUNT(*) FROM structural_events"
    ).fetchone()[0]
    assert count == 1


def test_structural_events_varchar_array(structural_conn):
    """Insert with Python list for contributing_flame_event_ids, read back."""
    structural_conn.execute(
        "INSERT INTO structural_events "
        "(event_id, session_id, prompt_number, subject, signal_type, "
        "signal_passed, contributing_flame_event_ids) "
        "VALUES ('e1', 's1', 1, 'human', 'main_cable', true, "
        "['fe-001', 'fe-002'])"
    )
    row = structural_conn.execute(
        "SELECT contributing_flame_event_ids FROM structural_events "
        "WHERE event_id = 'e1'"
    ).fetchone()
    assert row is not None
    result = row[0]
    assert isinstance(result, list)
    assert result == ["fe-001", "fe-002"]


# -- Model tests --


def test_structural_event_make_id_deterministic():
    """Same inputs produce same 16-char hex ID."""
    id1 = StructuralEvent.make_id("sess-001", 1, "gravity_check")
    id2 = StructuralEvent.make_id("sess-001", 1, "gravity_check")
    assert id1 == id2
    assert len(id1) == 16
    # Verify it's valid hex
    int(id1, 16)


def test_structural_event_make_id_different_inputs():
    """Different inputs produce different IDs."""
    id1 = StructuralEvent.make_id("sess-001", 1, "gravity_check")
    id2 = StructuralEvent.make_id("sess-001", 2, "gravity_check")
    id3 = StructuralEvent.make_id("sess-001", 1, "main_cable")
    assert id1 != id2
    assert id1 != id3


def test_structural_event_frozen():
    """Assignment to field on frozen model raises error."""
    event = _make_event()
    with pytest.raises(Exception):
        event.session_id = "other-session"


def test_structural_event_signal_type_validation():
    """Invalid signal_type raises ValidationError."""
    with pytest.raises(Exception):
        StructuralEvent(
            event_id="bad",
            session_id="s1",
            prompt_number=1,
            subject="human",
            signal_type="invalid_signal",
            signal_passed=True,
        )


# -- Writer tests --


def test_write_structural_events_basic(structural_conn):
    """Write 2 events, verify 2 rows in table."""
    events = [
        _make_event(prompt_number=1, signal_type="gravity_check"),
        _make_event(prompt_number=2, signal_type="main_cable"),
    ]
    written = write_structural_events(structural_conn, events)
    assert written == 2

    count = structural_conn.execute(
        "SELECT COUNT(*) FROM structural_events"
    ).fetchone()[0]
    assert count == 2


def test_write_structural_events_idempotent(structural_conn):
    """Write same events twice, still 2 rows (INSERT OR REPLACE)."""
    events = [
        _make_event(prompt_number=1, signal_type="gravity_check"),
        _make_event(prompt_number=2, signal_type="main_cable"),
    ]
    write_structural_events(structural_conn, events)
    write_structural_events(structural_conn, events)

    count = structural_conn.execute(
        "SELECT COUNT(*) FROM structural_events"
    ).fetchone()[0]
    assert count == 2


# -- Config tests --


def test_structural_config_defaults():
    """StructuralConfig() has gravity_window=3 and weights sum to ~1.0."""
    config = StructuralConfig()
    assert config.gravity_window == 3
    total = (
        config.gravity_weight
        + config.main_cable_weight
        + config.dependency_weight
        + config.spiral_weight
    )
    assert abs(total - 1.0) < 1e-9


def test_ddf_config_has_structural():
    """DDFConfig().structural.gravity_window == 3."""
    config = DDFConfig()
    assert config.structural.gravity_window == 3
    assert config.structural.main_cable_weight == 0.40


# -- IntelligenceProfile compatibility test --


def test_intelligence_profile_backward_compatible():
    """IntelligenceProfile works without and with integrity_score."""
    # Without new fields (backward compatible)
    ip1 = IntelligenceProfile(human_id="test-human")
    assert ip1.integrity_score is None
    assert ip1.structural_event_count is None

    # With new fields
    ip2 = IntelligenceProfile(
        human_id="test-human",
        integrity_score=0.75,
        structural_event_count=12,
    )
    assert ip2.integrity_score == 0.75
    assert ip2.structural_event_count == 12
