"""Integration tests for Assessment Report pipeline (Phase 17, Plan 04).

End-to-end tests covering:
- Full chain: schema -> data -> report -> deposit -> verify
- simulation_review in memory-review queue
- Production IntelligenceProfile excludes assessment events
- 3-metric TE formula (no transport_speed)
- candidate_ratio stored in assessment_te_sessions
- CLI report command
"""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.assessment.models import AssessmentReport
from src.pipeline.assessment.reporter import AssessmentReporter, generate_report
from src.pipeline.assessment.schema import create_assessment_schema
from src.pipeline.ddf.schema import create_ddf_schema


def _setup_full_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply full schema including DDF + assessment + project_wisdom."""
    create_ddf_schema(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS project_wisdom ("
        "  wisdom_id VARCHAR PRIMARY KEY, entity_type VARCHAR, title VARCHAR,"
        "  description TEXT, scenario_seed TEXT, ddf_target_level INTEGER"
        ")"
    )
    create_assessment_schema(conn)
    # Add columns that rejection_detector queries
    for col_name in ("ccd_axis", "differential"):
        try:
            conn.execute(
                f"ALTER TABLE flame_events ADD COLUMN {col_name} VARCHAR"
            )
        except Exception:
            pass


def _insert_test_data(
    conn: duckdb.DuckDBPyConnection,
    session_id: str = "integ-session-001",
    scenario_id: str = "integ-scenario-001",
    candidate_id: str = "integ-candidate-001",
) -> None:
    """Insert a complete set of test data for integration testing."""
    # Flame events
    events = [
        (1, "human", "ground-truth-pointer"),
        (2, "human", "deposit-not-detect"),
        (4, "human", "deposit-not-detect"),
        (5, "human", "identity-firewall"),
        (6, "human", "identity-firewall"),
        (3, "ai", "deposit-not-detect"),
    ]
    for i, (level, subject, axis) in enumerate(events):
        conn.execute(
            "INSERT INTO flame_events ("
            "  flame_event_id, session_id, prompt_number, marker_level,"
            "  marker_type, subject, axis_identified, flood_confirmed,"
            "  quality_score, evidence_excerpt, assessment_session_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                f"integ-fe-{i:04d}",
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

    # Assessment TE row
    conn.execute(
        "INSERT INTO assessment_te_sessions ("
        "  te_id, session_id, scenario_id, candidate_id,"
        "  candidate_te, scenario_baseline_te, candidate_ratio,"
        "  raven_depth, crow_efficiency, trunk_quality,"
        "  fringe_drift_rate, scenario_ddf_level"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "integ-te-001",
            session_id,
            scenario_id,
            candidate_id,
            0.30,
            0.40,
            0.75,
            0.714,
            0.8,
            0.5,
            0.0,
            5,
        ],
    )


# ── Test 1: E2E schema to report deposit ──


def test_e2e_schema_to_report_deposit():
    """Full chain: schema -> insert test data -> generate report -> deposit -> verify."""
    conn = duckdb.connect(":memory:")
    _setup_full_schema(conn)
    _insert_test_data(conn)

    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "integ-session-001", "integ-scenario-001", "integ-candidate-001"
    )

    # Verify report
    assert report.flame_event_count == 5  # human only
    assert report.candidate_te == pytest.approx(0.30, rel=1e-2)
    assert report.raven_depth == pytest.approx(0.714, rel=1e-2)

    # Deposit
    mc_id = reporter.deposit_report(report)
    assert mc_id is not None

    # Verify in memory_candidates
    row = conn.execute(
        "SELECT source_type, fidelity, confidence, status "
        "FROM memory_candidates WHERE id = ?",
        [mc_id],
    ).fetchone()
    assert row is not None
    assert row[0] == "simulation_review"
    assert row[1] == 3
    assert row[2] == pytest.approx(0.85)
    assert row[3] == "pending"

    conn.close()


# ── Test 2: simulation_review in memory-review queue ──


def test_e2e_simulation_review_in_memory_review_queue():
    """After deposit, query pending memory_candidates, verify simulation_review appears."""
    conn = duckdb.connect(":memory:")
    _setup_full_schema(conn)
    _insert_test_data(conn)

    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "integ-session-001", "integ-scenario-001", "integ-candidate-001"
    )
    mc_id = reporter.deposit_report(report)

    # The memory-review CLI queries: WHERE status = 'pending'
    pending = conn.execute(
        "SELECT id, source_type FROM memory_candidates WHERE status = 'pending'"
    ).fetchall()

    ids = [r[0] for r in pending]
    assert mc_id in ids

    # Verify it's simulation_review type
    source_types = {r[0]: r[1] for r in pending}
    assert source_types[mc_id] == "simulation_review"

    conn.close()


# ── Test 3: Assessment events excluded from production profile ──


def test_e2e_assessment_events_excluded_from_production_profile():
    """Production + assessment events for same human, production query excludes assessment."""
    conn = duckdb.connect(":memory:")
    _setup_full_schema(conn)
    _insert_test_data(conn)

    # Insert a "production" event (no assessment_session_id)
    conn.execute(
        "INSERT INTO flame_events ("
        "  flame_event_id, session_id, prompt_number, marker_level,"
        "  marker_type, subject, axis_identified, flood_confirmed,"
        "  quality_score, evidence_excerpt, human_id"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "prod-fe-001",
            "prod-session-001",
            1,
            3,
            "tier2_stub",
            "human",
            "deposit-not-detect",
            False,
            0.8,
            "Production evidence",
            "david",
        ],
    )

    # Production IntelligenceProfile WHERE clause:
    # subject = 'human' AND human_id = ? AND (assessment_session_id IS NULL)
    production_events = conn.execute(
        "SELECT flame_event_id FROM flame_events "
        "WHERE subject = 'human' AND (assessment_session_id IS NULL)"
    ).fetchall()

    prod_ids = [r[0] for r in production_events]
    assert "prod-fe-001" in prod_ids
    # Assessment events should NOT be in production results
    for i in range(5):
        assert f"integ-fe-{i:04d}" not in prod_ids

    conn.close()


# ── Test 4: 3-metric TE formula ──


def test_e2e_3_metric_te_formula():
    """Assessment TE has no transport_speed."""
    conn = duckdb.connect(":memory:")
    _setup_full_schema(conn)
    _insert_test_data(conn)

    # Verify AssessmentReport model defaults
    report = AssessmentReport(
        report_id="test-te",
        session_id="s1",
        scenario_id="sc1",
        candidate_id="c1",
        raven_depth=0.857,
        crow_efficiency=0.8,
        trunk_quality=0.5,
    )
    # No transport_speed field exists on AssessmentReport
    assert not hasattr(report, "transport_speed")

    # Verify assessment_te_sessions has no transport_speed column
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'assessment_te_sessions'"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert "transport_speed" not in col_names
    assert "raven_depth" in col_names
    assert "crow_efficiency" in col_names
    assert "trunk_quality" in col_names

    conn.close()


# ── Test 5: candidate_ratio stored ──


def test_e2e_candidate_ratio_stored():
    """candidate_ratio in assessment_te_sessions."""
    conn = duckdb.connect(":memory:")
    _setup_full_schema(conn)
    _insert_test_data(conn)

    row = conn.execute(
        "SELECT candidate_ratio FROM assessment_te_sessions "
        "WHERE session_id = 'integ-session-001'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(0.75, rel=1e-2)

    conn.close()


# ── Test 6: CLI report command ──


def test_e2e_report_cli_command():
    """CliRunner on assess report, verify output sections + deposit confirmation."""
    # CLI opens its own connection, so use file-based DB
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_cli.db")
        conn = duckdb.connect(db_path)
        _setup_full_schema(conn)
        _insert_test_data(conn, session_id="cli-session-001")
        conn.close()

        from src.pipeline.cli.assess import assess_group

        runner = CliRunner()
        result = runner.invoke(
            assess_group,
            ["report", "cli-session-001", "--db", db_path],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "## Summary" in result.output
        assert "## TransportEfficiency" in result.output
        assert "## FlameEvent Timeline" in result.output
        assert "Terminal deposit" in result.output
        assert "simulation_review" in result.output
