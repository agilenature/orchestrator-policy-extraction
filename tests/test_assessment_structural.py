"""Tests for structural integrity integration in assessment pipeline (Phase 18, Plan 05).

Covers:
- AssessmentReport model structural field defaults and population
- Reporter structural_events query + graceful fallback
- Markdown formatting with Structural Integrity section
- Deposit text inclusion of structural data
- Scenario generator floating_cable_context in handicap
- End-to-end structural assessment chain
"""

from __future__ import annotations

import duckdb
import pytest
from pydantic import ValidationError

from src.pipeline.assessment.models import AssessmentReport
from src.pipeline.assessment.reporter import AssessmentReporter
from src.pipeline.assessment.schema import create_assessment_schema
from src.pipeline.assessment.scenario_generator import ScenarioGenerator
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.structural.schema import create_structural_schema


def _add_rejection_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Add columns the rejection detector queries but aren't in base DDL."""
    for col_name, col_def in [
        ("ccd_axis", "VARCHAR"),
        ("differential", "VARCHAR"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE flame_events ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass


def _make_report(**overrides) -> AssessmentReport:
    """Helper to create an AssessmentReport with reasonable defaults."""
    defaults = dict(
        report_id="rpt-001",
        session_id="sess-001",
        scenario_id="sc-1",
        candidate_id="cand-1",
    )
    defaults.update(overrides)
    return AssessmentReport(**defaults)


@pytest.fixture
def conn_structural():
    """In-memory DuckDB with full schema including structural_events."""
    conn = duckdb.connect(":memory:")
    create_ddf_schema(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS project_wisdom ("
        "  wisdom_id VARCHAR PRIMARY KEY, entity_type VARCHAR, title VARCHAR,"
        "  description TEXT, scenario_seed TEXT, ddf_target_level INTEGER"
        ")"
    )
    create_assessment_schema(conn)
    create_structural_schema(conn)
    _add_rejection_columns(conn)
    yield conn
    conn.close()


def _insert_flame_events(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> None:
    """Insert minimal flame_events for a session."""
    test_events = [
        (1, "human", "ground-truth-pointer"),
        (3, "human", "deposit-not-detect"),
        (5, "human", "identity-firewall"),
        (2, "ai", "deposit-not-detect"),
    ]
    for i, (level, subject, axis) in enumerate(test_events):
        conn.execute(
            "INSERT INTO flame_events ("
            "  flame_event_id, session_id, prompt_number, marker_level,"
            "  marker_type, subject, axis_identified, flood_confirmed,"
            "  quality_score, evidence_excerpt, assessment_session_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                f"fe-struct-{i:04d}",
                session_id,
                i * 10,
                level,
                f"tier{min(level, 2)}_stub",
                subject,
                axis,
                level >= 6,
                0.7,
                f"Evidence for L{level}",
                session_id,
            ],
        )


def _insert_te_session(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    scenario_id: str = "scenario-struct-001",
    candidate_id: str = "candidate-struct-001",
) -> None:
    """Insert assessment_te_sessions row for a session."""
    conn.execute(
        "INSERT INTO assessment_te_sessions ("
        "  te_id, session_id, scenario_id, candidate_id,"
        "  candidate_te, scenario_baseline_te, candidate_ratio,"
        "  raven_depth, crow_efficiency, trunk_quality,"
        "  fringe_drift_rate, scenario_ddf_level"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            f"te-struct-{session_id}",
            session_id,
            scenario_id,
            candidate_id,
            0.35,
            0.40,
            0.875,
            0.857,
            0.8,
            0.5,
            0.0,
            5,
        ],
    )


def _insert_structural_events(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    events: list[tuple[str, str, bool]],
) -> None:
    """Insert structural_events rows.

    events: list of (subject, signal_type, signal_passed)
    """
    for i, (subject, signal_type, signal_passed) in enumerate(events):
        conn.execute(
            "INSERT INTO structural_events ("
            "  event_id, session_id, assessment_session_id,"
            "  prompt_number, subject, signal_type, signal_passed"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                f"se-{session_id}-{i:04d}",
                session_id,
                session_id,
                i * 5,
                subject,
                signal_type,
                signal_passed,
            ],
        )


# =========================================================================
# 1. AssessmentReport model tests
# =========================================================================


class TestAssessmentReportStructuralDefaults:
    """Tests for structural field defaults on AssessmentReport."""

    def test_assessment_report_structural_defaults(self):
        """Minimal AssessmentReport has structural fields at defaults."""
        r = _make_report()
        assert r.structural_integrity_score is None
        assert r.structural_event_count == 0
        assert r.floating_cable_count == 0

    def test_assessment_report_with_structural_data(self):
        """AssessmentReport accepts explicit structural field values."""
        r = _make_report(
            structural_integrity_score=0.75,
            structural_event_count=8,
            floating_cable_count=2,
        )
        assert r.structural_integrity_score == 0.75
        assert r.structural_event_count == 8
        assert r.floating_cable_count == 2

    def test_assessment_report_frozen_structural(self):
        """Structural fields are frozen (cannot be mutated)."""
        r = _make_report(structural_integrity_score=0.8)
        with pytest.raises(ValidationError):
            r.structural_integrity_score = 0.9


# =========================================================================
# 2. Reporter structural integration tests
# =========================================================================


class TestReporterStructuralIntegration:
    """Tests for structural_events query in generate_report()."""

    def test_generate_report_no_structural_events(self, conn_structural):
        """Session with flame_events but no structural_events gets defaults."""
        session_id = "sess-no-struct"
        _insert_flame_events(conn_structural, session_id)
        _insert_te_session(conn_structural, session_id)

        reporter = AssessmentReporter(conn_structural)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )
        # compute_structural_integrity returns defaults when no events
        # integrity_score is the neutral fallback formula:
        # 0.30*0.5 + 0.40*0.5 + 0.20*0.5 + 0.10*0.0 = 0.45
        assert report.structural_integrity_score is not None
        assert report.structural_event_count == 0
        assert report.floating_cable_count == 0

    def test_generate_report_with_structural_events(self, conn_structural):
        """Session with structural_events populates structural fields."""
        session_id = "sess-with-struct"
        _insert_flame_events(conn_structural, session_id)
        _insert_te_session(conn_structural, session_id)
        _insert_structural_events(
            conn_structural,
            session_id,
            [
                ("human", "gravity_check", True),
                ("human", "gravity_check", True),
                ("human", "main_cable", True),
                ("human", "main_cable", False),
                ("human", "dependency_sequencing", False),
            ],
        )

        reporter = AssessmentReporter(conn_structural)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )
        assert report.structural_integrity_score is not None
        assert report.structural_event_count > 0

    def test_generate_report_floating_cables(self, conn_structural):
        """AI main_cable failures counted as floating cables."""
        session_id = "sess-float-cables"
        _insert_flame_events(conn_structural, session_id)
        _insert_te_session(conn_structural, session_id)
        _insert_structural_events(
            conn_structural,
            session_id,
            [
                ("ai", "main_cable", False),
                ("ai", "main_cable", False),
                ("ai", "main_cable", True),
                ("human", "gravity_check", True),
            ],
        )

        reporter = AssessmentReporter(conn_structural)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )
        assert report.floating_cable_count == 2

    def test_format_report_structural_section(self, conn_structural):
        """Markdown output contains Structural Integrity section."""
        session_id = "sess-md-struct"
        _insert_flame_events(conn_structural, session_id)
        _insert_te_session(conn_structural, session_id)
        _insert_structural_events(
            conn_structural,
            session_id,
            [
                ("human", "gravity_check", True),
                ("human", "main_cable", True),
            ],
        )

        reporter = AssessmentReporter(conn_structural)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )
        markdown = reporter.format_report_markdown(report)

        assert "## Structural Integrity" in markdown
        assert "Integrity Score:" in markdown
        assert "Floating Cables" in markdown

    def test_deposit_report_includes_structural(self, conn_structural):
        """Deposited scope_rule text includes structural data."""
        session_id = "sess-deposit-struct"
        _insert_flame_events(conn_structural, session_id)
        _insert_te_session(conn_structural, session_id)
        _insert_structural_events(
            conn_structural,
            session_id,
            [
                ("human", "gravity_check", True),
                ("ai", "main_cable", False),
            ],
        )

        reporter = AssessmentReporter(conn_structural)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )
        mc_id = reporter.deposit_report(report)
        assert mc_id is not None

        row = conn_structural.execute(
            "SELECT scope_rule, flood_example FROM memory_candidates WHERE id = ?",
            [mc_id],
        ).fetchone()
        assert row is not None
        assert "Structural integrity:" in row[0]
        assert "Floating cables:" in row[0]
        assert "structural integrity" in row[1]


# =========================================================================
# 3. Scenario generator handicap tests
# =========================================================================


class TestScenarioGeneratorHandicap:
    """Tests for floating_cable_context in _build_handicap()."""

    def test_build_handicap_no_floating_context(self):
        """Default handicap does not contain AI Analysis Notes."""
        conn = duckdb.connect(":memory:")
        gen = ScenarioGenerator(conn)
        result = gen._build_handicap("Test Title", "Test desc", "scope_decision")
        assert "AI Analysis Notes" not in result
        conn.close()

    def test_build_handicap_with_floating_context(self):
        """Handicap with floating_cable_context contains AI Analysis Notes."""
        conn = duckdb.connect(":memory:")
        gen = ScenarioGenerator(conn)
        context_text = "The AI's principle about X appears ungrounded."
        result = gen._build_handicap(
            "Test Title",
            "Test desc",
            "scope_decision",
            floating_cable_context=context_text,
        )
        assert "### AI Analysis Notes" in result
        assert context_text in result
        conn.close()


# =========================================================================
# 4. End-to-end structural assessment tests
# =========================================================================


class TestStructuralAssessmentEndToEnd:
    """End-to-end tests for the structural assessment chain."""

    def test_structural_assessment_end_to_end(self, conn_structural):
        """Full chain: insert data, generate report, verify fields, deposit."""
        session_id = "sess-e2e-struct"
        _insert_flame_events(conn_structural, session_id)
        _insert_te_session(conn_structural, session_id)
        _insert_structural_events(
            conn_structural,
            session_id,
            [
                ("human", "gravity_check", True),
                ("human", "gravity_check", False),
                ("human", "main_cable", True),
                ("human", "dependency_sequencing", True),
                ("ai", "main_cable", False),
                ("ai", "main_cable", False),
            ],
        )

        reporter = AssessmentReporter(conn_structural)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )

        # Structural fields populated
        assert report.structural_integrity_score is not None
        assert report.structural_event_count > 0
        assert report.floating_cable_count == 2

        # Deposit includes structural data
        mc_id = reporter.deposit_report(report)
        assert mc_id is not None

        row = conn_structural.execute(
            "SELECT scope_rule FROM memory_candidates WHERE id = ?",
            [mc_id],
        ).fetchone()
        assert "Structural integrity:" in row[0]
        assert "Floating cables: 2" in row[0]

    def test_structural_assessment_no_structural_table(self):
        """generate_report() gracefully falls back when structural_events absent."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS project_wisdom ("
            "  wisdom_id VARCHAR PRIMARY KEY, entity_type VARCHAR, title VARCHAR,"
            "  description TEXT, scenario_seed TEXT, ddf_target_level INTEGER"
            ")"
        )
        create_assessment_schema(conn)
        _add_rejection_columns(conn)

        # Drop structural_events to simulate missing table
        conn.execute("DROP TABLE IF EXISTS structural_events")

        session_id = "sess-no-table"
        _insert_flame_events(conn, session_id)
        _insert_te_session(conn, session_id)

        reporter = AssessmentReporter(conn)
        report = reporter.generate_report(
            session_id, "scenario-struct-001", "candidate-struct-001"
        )

        # Falls back to defaults when structural_events table is absent
        assert report.structural_integrity_score is None
        assert report.structural_event_count == 0
        assert report.floating_cable_count == 0

        conn.close()
