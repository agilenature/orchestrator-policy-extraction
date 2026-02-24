"""Tests for AssessmentReporter (Phase 17, Plan 04).

Covers:
- Report generation: all fields, level distribution, axis quality, flood rate,
  spiral evidence, AI contribution, percentile
- Markdown formatting with required sections
- Terminal deposit: source_type, fidelity, confidence, idempotency
- Auto-calibration: insufficient data, too_easy proposal, no auto-update
- Production profile exclusion via assessment_session_id IS NULL filter
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.assessment.models import AssessmentReport
from src.pipeline.assessment.reporter import AssessmentReporter
from src.pipeline.assessment.schema import create_assessment_schema
from src.pipeline.ddf.schema import create_ddf_schema


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


@pytest.fixture
def conn_with_assessment_data():
    """In-memory DuckDB with full schema and assessment test data."""
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

    session_id = "test-session-001"
    # Insert flame_events with both human and AI events
    test_events = [
        (1, "human", "ground-truth-pointer"),
        (2, "human", "deposit-not-detect"),
        (3, "human", "deposit-not-detect"),
        (5, "human", "identity-firewall"),
        (6, "human", "identity-firewall"),
        (2, "ai", "deposit-not-detect"),
        (3, "ai", "ground-truth-pointer"),
    ]
    for i, (level, subject, axis) in enumerate(test_events):
        conn.execute(
            "INSERT INTO flame_events ("
            "  flame_event_id, session_id, prompt_number, marker_level,"
            "  marker_type, subject, axis_identified, flood_confirmed,"
            "  quality_score, evidence_excerpt, assessment_session_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                f"fe-{i:04d}",
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

    # Insert assessment_te_sessions row
    conn.execute(
        "INSERT INTO assessment_te_sessions ("
        "  te_id, session_id, scenario_id, candidate_id,"
        "  candidate_te, scenario_baseline_te, candidate_ratio,"
        "  raven_depth, crow_efficiency, trunk_quality,"
        "  fringe_drift_rate, scenario_ddf_level"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "te-001",
            session_id,
            "scenario-001",
            "candidate-001",
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

    yield conn
    conn.close()


# ── Test 1: All fields present ──


def test_generate_report_all_fields_present(conn_with_assessment_data):
    """Generated report has all required fields populated."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    assert report.flame_event_count > 0
    assert len(report.level_distribution) > 0
    assert report.candidate_te is not None
    assert report.ai_flame_event_count > 0
    assert report.session_id == "test-session-001"
    assert report.scenario_id == "scenario-001"
    assert report.candidate_id == "candidate-001"


# ── Test 2: Level distribution ──


def test_generate_report_level_distribution(conn_with_assessment_data):
    """Level distribution correctly counts per level for human events."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    # Human events: L1, L2, L3, L5, L6
    assert report.level_distribution == {
        "L1": 1,
        "L2": 1,
        "L3": 1,
        "L5": 1,
        "L6": 1,
    }


# ── Test 3: Axis quality scores ──


def test_generate_report_axis_quality_scores(conn_with_assessment_data):
    """Axis quality scores computed for unique axes."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    assert len(report.axis_quality_scores) > 0
    assert "ground-truth-pointer" in report.axis_quality_scores
    assert "deposit-not-detect" in report.axis_quality_scores
    assert "identity-firewall" in report.axis_quality_scores


# ── Test 4: Flood rate ──


def test_generate_report_flood_rate(conn_with_assessment_data):
    """Flood rate is ratio of flood_confirmed=True to total human events."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    # 1 event with flood_confirmed=True (L6), 5 human events total
    assert report.flood_rate == pytest.approx(1 / 5, rel=1e-3)


# ── Test 5: Spiral evidence ──


def test_generate_report_spiral_evidence(conn_with_assessment_data):
    """Ascending levels (1,2,3,5,6) detect spiral."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    # Human events sorted by prompt_number: L1, L2, L3, L5, L6
    # That's a 5-step ascending run
    assert len(report.spiral_evidence) > 0
    assert "5 steps" in report.spiral_evidence[0]


# ── Test 6: AI contribution ──


def test_generate_report_ai_contribution(conn_with_assessment_data):
    """AI avg marker level computed from AI events."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    assert report.ai_flame_event_count == 2
    # AI events: L2, L3 -> avg = 2.5
    assert report.ai_avg_marker_level == pytest.approx(2.5, rel=1e-3)


# ── Test 7: Percentile None when insufficient baselines ──


def test_generate_report_percentile_none_when_insufficient_baselines(
    conn_with_assessment_data,
):
    """No baselines -> percentile_rank None."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    # No assessment_baselines rows -> percentile should be None
    assert report.percentile_rank is None


# ── Test 8: Percentile computed when sufficient ──


def test_generate_report_percentile_computed_when_sufficient(
    conn_with_assessment_data,
):
    """Insert baselines with n_assessments=10, verify percentile computed."""
    conn = conn_with_assessment_data
    conn.execute(
        "INSERT INTO assessment_baselines "
        "(scenario_id, n_assessments, mean_ratio, stddev_ratio) "
        "VALUES (?, ?, ?, ?)",
        ["scenario-001", 10, 0.8, 0.2],
    )
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    assert report.percentile_rank is not None
    assert 0.0 <= report.percentile_rank <= 1.0


# ── Test 9: Markdown sections ──


def test_format_report_markdown_contains_sections(conn_with_assessment_data):
    """Markdown report contains required sections."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    markdown = reporter.format_report_markdown(report)
    assert "## Summary" in markdown
    assert "## TransportEfficiency" in markdown
    assert "## FlameEvent Timeline" in markdown
    assert "## DDF Level Distribution" in markdown
    assert "## Axis Quality Scores" in markdown
    assert "## Spiral Evidence" in markdown
    assert "## AI Contribution Profile" in markdown
    assert "## Rejection Analysis" in markdown
    assert "## Fringe Drift" in markdown
    assert "## Population Comparison" in markdown
    assert "transport_speed excluded" in markdown


# ── Test 10: Terminal deposit creates memory candidate ──


def test_deposit_report_creates_memory_candidate(conn_with_assessment_data):
    """After deposit: source_type='simulation_review', fidelity=3, confidence=0.85."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    mc_id = reporter.deposit_report(report)
    assert mc_id is not None

    row = conn.execute(
        "SELECT id, source_type, fidelity, confidence, status, "
        "ccd_axis, scope_rule, flood_example, pipeline_component "
        "FROM memory_candidates WHERE id = ?",
        [mc_id],
    ).fetchone()
    assert row is not None
    assert row[1] == "simulation_review"
    assert row[2] == 3
    assert row[3] == pytest.approx(0.85)
    assert row[4] == "pending"
    # CCD fields are non-empty
    assert len(row[5].strip()) > 0  # ccd_axis
    assert len(row[6].strip()) > 0  # scope_rule
    assert len(row[7].strip()) > 0  # flood_example
    assert row[8] == "assessment_reporter"


# ── Test 11: Deposit idempotent ──


def test_deposit_report_idempotent(conn_with_assessment_data):
    """Calling deposit_report twice does not error."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    id1 = reporter.deposit_report(report)
    id2 = reporter.deposit_report(report)
    assert id1 == id2

    # Exactly one row
    count = conn.execute(
        "SELECT COUNT(*) FROM memory_candidates WHERE id = ?", [id1]
    ).fetchone()[0]
    assert count == 1


# ── Test 12: Source type correct ──


def test_deposit_report_source_type_correct(conn_with_assessment_data):
    """source_type='simulation_review' (not 'production')."""
    conn = conn_with_assessment_data
    reporter = AssessmentReporter(conn)
    report = reporter.generate_report(
        "test-session-001", "scenario-001", "candidate-001"
    )
    mc_id = reporter.deposit_report(report)

    source_type = conn.execute(
        "SELECT source_type FROM memory_candidates WHERE id = ?", [mc_id]
    ).fetchone()[0]
    assert source_type == "simulation_review"
    assert source_type != "production"


# ── Test 13: Auto-calibration insufficient data ──


def test_auto_calibration_insufficient_data(conn_with_assessment_data):
    """n_assessments < 10 -> None."""
    conn = conn_with_assessment_data
    # Insert baseline with only 5 assessments
    conn.execute(
        "INSERT INTO assessment_baselines "
        "(scenario_id, n_assessments, mean_ratio, stddev_ratio) "
        "VALUES (?, ?, ?, ?)",
        ["scenario-001", 5, 0.8, 0.2],
    )
    reporter = AssessmentReporter(conn)
    result = reporter.check_auto_calibration("scenario-001")
    assert result is None


# ── Test 14: Auto-calibration too easy deposits proposal ──


def test_auto_calibration_too_easy_deposits_proposal(
    conn_with_assessment_data,
):
    """3 ratios > 1.3, proposal deposited."""
    conn = conn_with_assessment_data

    # Insert baseline with 10+ assessments
    conn.execute(
        "INSERT INTO assessment_baselines "
        "(scenario_id, n_assessments, mean_ratio, stddev_ratio) "
        "VALUES (?, ?, ?, ?)",
        ["scenario-001", 12, 1.4, 0.1],
    )

    # Insert 3 sessions with ratios > 1.3
    for i in range(3):
        conn.execute(
            "DELETE FROM assessment_te_sessions WHERE te_id = ?",
            [f"te-auto-{i}"],
        )
        conn.execute(
            "INSERT INTO assessment_te_sessions ("
            "  te_id, session_id, scenario_id, candidate_id,"
            "  candidate_te, scenario_baseline_te, candidate_ratio,"
            "  raven_depth, crow_efficiency, trunk_quality,"
            "  fringe_drift_rate, scenario_ddf_level"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                f"te-auto-{i}",
                f"sess-auto-{i}",
                "scenario-001",
                f"candidate-auto-{i}",
                0.6,
                0.4,
                1.5,  # > 1.3
                0.8,
                0.8,
                0.5,
                0.0,
                5,
            ],
        )

    reporter = AssessmentReporter(conn)
    cal_id = reporter.check_auto_calibration("scenario-001")
    assert cal_id is not None

    # Verify proposal deposited to memory_candidates
    row = conn.execute(
        "SELECT source_type, status FROM memory_candidates WHERE id = ?",
        [cal_id],
    ).fetchone()
    assert row is not None
    assert row[0] == "simulation_review"
    assert row[1] == "pending"


# ── Test 15: Auto-calibration does NOT update ddf_target_level ──


def test_auto_calibration_does_not_auto_update_ddf_level(
    conn_with_assessment_data,
):
    """project_wisdom.ddf_target_level UNCHANGED after proposal."""
    conn = conn_with_assessment_data

    # Insert wisdom entry with ddf_target_level
    conn.execute(
        "INSERT INTO project_wisdom "
        "(wisdom_id, entity_type, title, description, ddf_target_level) "
        "VALUES (?, ?, ?, ?, ?)",
        ["wisdom-001", "constraint", "Test wisdom", "Description", 5],
    )

    # Insert baseline + 3 too-easy sessions
    conn.execute(
        "INSERT INTO assessment_baselines "
        "(scenario_id, n_assessments, mean_ratio, stddev_ratio) "
        "VALUES (?, ?, ?, ?)",
        ["scenario-001", 12, 1.4, 0.1],
    )
    for i in range(3):
        conn.execute(
            "DELETE FROM assessment_te_sessions WHERE te_id = ?",
            [f"te-cal-{i}"],
        )
        conn.execute(
            "INSERT INTO assessment_te_sessions ("
            "  te_id, session_id, scenario_id, candidate_id,"
            "  candidate_te, scenario_baseline_te, candidate_ratio,"
            "  raven_depth, crow_efficiency, trunk_quality,"
            "  fringe_drift_rate, scenario_ddf_level"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                f"te-cal-{i}",
                f"sess-cal-{i}",
                "scenario-001",
                f"candidate-cal-{i}",
                0.6,
                0.4,
                1.5,
                0.8,
                0.8,
                0.5,
                0.0,
                5,
            ],
        )

    reporter = AssessmentReporter(conn)
    cal_id = reporter.check_auto_calibration("scenario-001")
    assert cal_id is not None

    # ddf_target_level must be UNCHANGED
    level = conn.execute(
        "SELECT ddf_target_level FROM project_wisdom WHERE wisdom_id = ?",
        ["wisdom-001"],
    ).fetchone()[0]
    assert level == 5


# ── Test 16: Production profile excludes assessment events ──


def test_production_profile_excludes_assessment_events(
    conn_with_assessment_data,
):
    """Events with assessment_session_id IS NOT NULL excluded from production WHERE clause."""
    conn = conn_with_assessment_data

    # Verify the production profile filter pattern excludes assessment events
    # The production IntelligenceProfile uses: AND (assessment_session_id IS NULL)
    production_count = conn.execute(
        "SELECT COUNT(*) FROM flame_events "
        "WHERE subject = 'human' AND (assessment_session_id IS NULL)"
    ).fetchone()[0]
    assert production_count == 0  # All events have assessment_session_id set

    total_count = conn.execute(
        "SELECT COUNT(*) FROM flame_events WHERE subject = 'human'"
    ).fetchone()[0]
    assert total_count == 5  # 5 human events exist but excluded from production
