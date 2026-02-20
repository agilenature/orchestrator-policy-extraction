"""Integration tests for the full decision durability pipeline.

Verifies end-to-end flow: events -> scope extraction -> constraint evaluation
-> amnesia detection -> durability scoring -> ShadowReporter metrics.

Tests use in-memory DuckDB databases with schema created fresh per test.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb
import pytest

from src.pipeline.durability.amnesia import AmnesiaDetector
from src.pipeline.durability.evaluator import SessionConstraintEvaluator
from src.pipeline.durability.index import DurabilityIndex
from src.pipeline.durability.scope_extractor import extract_session_scope
from src.pipeline.models.config import PipelineConfig
from src.pipeline.shadow.reporter import ShadowReporter
from src.pipeline.storage.schema import create_schema
from src.pipeline.storage.writer import write_amnesia_events, write_constraint_evals


# --- Fixtures ---


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema created."""
    c = duckdb.connect(":memory:")
    create_schema(c)
    yield c
    c.close()


@pytest.fixture
def config():
    """Default pipeline config."""
    return PipelineConfig()


@pytest.fixture
def constraints():
    """Test constraints with varying scope, detection_hints, and type."""
    return [
        {
            "constraint_id": "c-src",
            "text": "Never use eval() in source code",
            "severity": "forbidden",
            "type": "behavioral_constraint",
            "scope": {"paths": ["src/"]},
            "status": "active",
            "status_history": [
                {"status": "active", "changed_at": "2020-01-01T00:00:00+00:00"}
            ],
            "detection_hints": ["eval("],
            "created_at": "2020-01-01T00:00:00+00:00",
            "examples": [],
        },
        {
            "constraint_id": "c-global",
            "text": "Always include error handling",
            "severity": "requires_approval",
            "type": "behavioral_constraint",
            "scope": {"paths": []},  # repo-wide
            "status": "active",
            "status_history": [
                {"status": "active", "changed_at": "2020-01-01T00:00:00+00:00"}
            ],
            "detection_hints": [],  # no detection hints -> always HONORED
            "created_at": "2020-01-01T00:00:00+00:00",
            "examples": [],
        },
        {
            "constraint_id": "c-tests",
            "text": "Never skip tests",
            "severity": "forbidden",
            "type": "architectural_decision",
            "scope": {"paths": ["tests/"]},
            "status": "active",
            "status_history": [
                {"status": "active", "changed_at": "2020-01-01T00:00:00+00:00"}
            ],
            "detection_hints": ["pytest.mark.skip", "--no-tests"],
            "created_at": "2020-01-01T00:00:00+00:00",
            "examples": [],
        },
    ]


def _make_event(event_id, session_id, text="", file_path=None):
    """Create a minimal event dict for testing."""
    payload = {"common": {"text": text}}
    if file_path:
        payload["details"] = {"file_path": file_path}
    return {
        "event_id": event_id,
        "ts_utc": datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        "session_id": session_id,
        "actor": "assistant",
        "event_type": "tool_use",
        "payload": payload,
    }


# --- Full evaluation flow tests ---


class TestFullEvaluationFlow:
    """End-to-end integration tests for the evaluation pipeline."""

    def test_scope_to_eval_to_amnesia_to_score(self, conn, config, constraints):
        """Full flow: extract scope -> evaluate -> detect amnesia -> compute score."""
        # Session 1: Touches src/ files, has eval() in payload -> violates c-src
        events_s1 = [
            _make_event("e1", "sess-1", "Writing eval() function", "src/utils.py"),
            _make_event("e2", "sess-1", "More work", "src/main.py"),
        ]

        # Session 2: Touches src/ files, no eval() -> honors c-src
        events_s2 = [
            _make_event("e3", "sess-2", "Clean code", "src/utils.py"),
            _make_event("e4", "sess-2", "More clean code", "src/main.py"),
        ]

        # Session 3: Touches src/ files, has eval() -> violates c-src
        events_s3 = [
            _make_event("e5", "sess-3", "Using eval(expr)", "src/parser.py"),
        ]

        evaluator = SessionConstraintEvaluator(config)
        detector = AmnesiaDetector()
        all_amnesia = []

        for session_id, events in [("sess-1", events_s1), ("sess-2", events_s2), ("sess-3", events_s3)]:
            scope = extract_session_scope(events)
            start_time = str(events[0]["ts_utc"])

            results = evaluator.evaluate(
                session_id=session_id,
                session_scope_paths=scope,
                session_start_time=start_time,
                events=events,
                constraints=constraints,
            )

            write_constraint_evals(conn, results)

            amnesia = detector.detect(results, constraints)
            if amnesia:
                write_amnesia_events(conn, amnesia)
                all_amnesia.extend(amnesia)

        # Verify c-src was violated in sess-1 and sess-3, honored in sess-2
        c_src_evals = conn.execute(
            "SELECT session_id, eval_state FROM session_constraint_eval "
            "WHERE constraint_id = 'c-src' ORDER BY session_id"
        ).fetchall()
        assert len(c_src_evals) == 3
        assert c_src_evals[0] == ("sess-1", "VIOLATED")
        assert c_src_evals[1] == ("sess-2", "HONORED")
        assert c_src_evals[2] == ("sess-3", "VIOLATED")

        # c-global (repo-wide, no hints) should be HONORED in all sessions
        c_global_evals = conn.execute(
            "SELECT eval_state FROM session_constraint_eval "
            "WHERE constraint_id = 'c-global'"
        ).fetchall()
        assert all(row[0] == "HONORED" for row in c_global_evals)

        # c-tests scope (tests/) doesn't overlap src/ -> excluded (no rows)
        c_tests_evals = conn.execute(
            "SELECT COUNT(*) FROM session_constraint_eval "
            "WHERE constraint_id = 'c-tests'"
        ).fetchone()[0]
        assert c_tests_evals == 0

        # Verify amnesia events: 2 (sess-1 and sess-3 violated c-src)
        assert len(all_amnesia) == 2
        amnesia_ids = {ae.amnesia_id for ae in all_amnesia}
        assert len(amnesia_ids) == 2  # deterministic and unique

        # Compute durability scores
        index = DurabilityIndex(conn)
        score = index.compute_score("c-src")
        assert score["sessions_active"] == 3
        assert score["sessions_honored"] == 1
        assert score["sessions_violated"] == 2
        # durability_score = 1/3 = 0.333...
        assert abs(score["durability_score"] - (1 / 3)) < 0.001
        assert not score["insufficient_data"]

        # c-global: 3 sessions, all honored -> score = 1.0
        score_global = index.compute_score("c-global")
        assert score_global["durability_score"] == 1.0

    def test_constraints_with_non_overlapping_scope_excluded(self, config, constraints):
        """Constraints whose scope doesn't overlap session scope are excluded."""
        # Events only touch docs/ - no constraint matches docs/
        events = [
            _make_event("e1", "sess-x", "Editing docs", "docs/readme.md"),
        ]

        evaluator = SessionConstraintEvaluator(config)
        scope = extract_session_scope(events)
        results = evaluator.evaluate(
            session_id="sess-x",
            session_scope_paths=scope,
            session_start_time=str(events[0]["ts_utc"]),
            events=events,
            constraints=constraints,
        )

        # c-src (src/) -> excluded (no overlap)
        # c-global (empty=[]) -> repo-wide -> included, HONORED (no hints)
        # c-tests (tests/) -> excluded (no overlap)
        assert len(results) == 1
        assert results[0].constraint_id == "c-global"
        assert results[0].eval_state == "HONORED"

    def test_detection_hints_produce_violated(self, config, constraints):
        """Matching detection hints produce VIOLATED with evidence."""
        events = [
            _make_event("e1", "sess-v", "Using eval(x) here", "src/bad.py"),
        ]

        evaluator = SessionConstraintEvaluator(config)
        scope = extract_session_scope(events)
        results = evaluator.evaluate(
            session_id="sess-v",
            session_scope_paths=scope,
            session_start_time=str(events[0]["ts_utc"]),
            events=events,
            constraints=constraints,
        )

        violated = [r for r in results if r.eval_state == "VIOLATED"]
        assert len(violated) == 1
        assert violated[0].constraint_id == "c-src"
        assert len(violated[0].evidence) > 0
        assert violated[0].evidence[0]["matched_pattern"] == "eval("

    def test_amnesia_events_have_deterministic_ids(self, config, constraints):
        """Amnesia event IDs are deterministic SHA-256(session+constraint)[:16]."""
        import hashlib

        events = [
            _make_event("e1", "sess-d", "eval()", "src/x.py"),
        ]

        evaluator = SessionConstraintEvaluator(config)
        scope = extract_session_scope(events)
        results = evaluator.evaluate(
            session_id="sess-d",
            session_scope_paths=scope,
            session_start_time=str(events[0]["ts_utc"]),
            events=events,
            constraints=constraints,
        )

        detector = AmnesiaDetector()
        amnesia = detector.detect(results, constraints)

        for ae in amnesia:
            expected_id = hashlib.sha256(
                (ae.session_id + ae.constraint_id).encode()
            ).hexdigest()[:16]
            assert ae.amnesia_id == expected_id


# --- ShadowReporter integration tests ---


class TestShadowReporterIntegration:
    """Tests for ShadowReporter with amnesia and durability metrics."""

    def _populate_shadow_results(self, conn):
        """Insert minimal shadow_mode_results for reporter to work."""
        conn.execute(
            "INSERT INTO shadow_mode_results "
            "(shadow_run_id, episode_id, session_id, human_mode, human_risk, "
            "shadow_mode, shadow_risk, mode_agrees, risk_agrees, scope_overlap, "
            "is_dangerous) "
            "VALUES ('sr1', 'ep1', 'sess-1', 'DIR', 'low', 'DIR', 'low', "
            "TRUE, TRUE, 1.0, FALSE)"
        )

    def test_report_includes_amnesia_metrics(self, conn):
        """ShadowReporter.compute_report() includes amnesia metrics."""
        self._populate_shadow_results(conn)

        # Insert evaluation data
        for i in range(3):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) "
                "VALUES (?, 'c001', ?)",
                [f"sess-{i}", "HONORED" if i < 2 else "VIOLATED"],
            )

        # Insert amnesia event for the violated one
        conn.execute(
            "INSERT INTO amnesia_events "
            "(amnesia_id, session_id, constraint_id, constraint_type, severity) "
            "VALUES ('a001', 'sess-2', 'c001', 'behavioral_constraint', 'forbidden')"
        )

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()

        assert "amnesia" in report
        amnesia = report["amnesia"]
        assert "amnesia_rate" in amnesia
        assert "avg_durability_score" in amnesia

        # 3 audited sessions, 1 with amnesia -> rate = 1/3
        assert abs(amnesia["amnesia_rate"] - (1 / 3)) < 0.001

        # 3 sessions, 2 honored, 1 violated -> durability = 2/3
        assert abs(amnesia["avg_durability_score"] - (2 / 3)) < 0.001

    def test_format_report_includes_durability_section(self, conn):
        """ShadowReporter.format_report() includes Decision Durability section."""
        self._populate_shadow_results(conn)

        # Insert eval data for 3+ sessions
        for i in range(4):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()
        text = reporter.format_report(report)

        assert "Decision Durability Metrics:" in text
        assert "Amnesia rate:" in text
        assert "Avg durability score:" in text

    def test_format_report_amnesia_pass(self, conn):
        """Amnesia rate 0.0% shows PASS gate."""
        self._populate_shadow_results(conn)

        # All sessions honored, no amnesia events
        for i in range(3):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()
        text = reporter.format_report(report)

        assert "0.0%" in text
        assert "PASS" in text

    def test_format_report_amnesia_fail(self, conn):
        """Amnesia rate > 0% shows FAIL gate."""
        self._populate_shadow_results(conn)

        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state) VALUES ('sess-0', 'c001', 'VIOLATED')"
        )
        conn.execute(
            "INSERT INTO amnesia_events "
            "(amnesia_id, session_id, constraint_id) "
            "VALUES ('a001', 'sess-0', 'c001')"
        )

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()
        text = reporter.format_report(report)

        assert "FAIL" in text
        assert "100.0%" in text  # 1/1 sessions have amnesia

    def test_format_report_no_eval_data(self, conn):
        """Report shows N/A when no evaluation data exists."""
        self._populate_shadow_results(conn)

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()
        text = reporter.format_report(report)

        assert "Amnesia rate: N/A" in text
        assert "Avg durability score: N/A" in text


# --- Minimum sessions threshold tests ---


class TestMinimumSessionsThreshold:
    """Tests for the minimum sessions threshold in durability scoring."""

    def test_insufficient_data_below_threshold(self, conn):
        """DurabilityIndex returns null score with insufficient_data=True for < 3 sessions."""
        # Insert eval results for only 2 sessions
        for i in range(2):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )

        index = DurabilityIndex(conn)
        score = index.compute_score("c001")
        assert score["durability_score"] is None
        assert score["insufficient_data"] is True

    def test_sufficient_data_at_threshold(self, conn):
        """DurabilityIndex computes score at exactly 3 sessions."""
        for i in range(3):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) VALUES (?, 'c001', ?)",
                [f"sess-{i}", "HONORED" if i < 2 else "VIOLATED"],
            )

        index = DurabilityIndex(conn)
        score = index.compute_score("c001")
        assert score["durability_score"] is not None
        assert not score["insufficient_data"]
        assert abs(score["durability_score"] - (2 / 3)) < 0.001

    def test_reporter_avg_durability_excludes_insufficient(self, conn):
        """Reporter avg_durability_score only includes constraints with >= 3 sessions."""
        # Insert minimal shadow data for reporter
        conn.execute(
            "INSERT INTO shadow_mode_results "
            "(shadow_run_id, episode_id, session_id, human_mode, human_risk, "
            "shadow_mode, shadow_risk, mode_agrees, risk_agrees, scope_overlap, "
            "is_dangerous) "
            "VALUES ('sr1', 'ep1', 'sess-1', 'DIR', 'low', 'DIR', 'low', "
            "TRUE, TRUE, 1.0, FALSE)"
        )

        # c001: 3 sessions (above threshold), 3 honored -> score = 1.0
        for i in range(3):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) VALUES (?, 'c001', 'HONORED')",
                [f"sess-{i}"],
            )

        # c002: only 2 sessions (below threshold) -> excluded from avg
        for i in range(2):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state) VALUES (?, 'c002', 'VIOLATED')",
                [f"sess-{i}"],
            )

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()

        # avg_durability should only count c001 (1.0), not c002
        assert report["amnesia"]["avg_durability_score"] == 1.0
