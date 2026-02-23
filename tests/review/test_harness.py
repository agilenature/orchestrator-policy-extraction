"""Tests for the HarnessRunner and HarnessReport.

Tests the orchestrating harness that runs all structural invariants
and produces a structured report.
"""

from __future__ import annotations

import duckdb
import pytest

from src.pipeline.review.harness import HarnessReport, HarnessRunner
from src.pipeline.review.invariants import InvariantResult
from src.pipeline.review.schema import create_review_schema


@pytest.fixture
def conn():
    """In-memory DuckDB with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    yield c
    c.close()


@pytest.fixture
def memory_md(tmp_path):
    """Create a minimal MEMORY.md."""
    md = tmp_path / "MEMORY.md"
    md.write_text("# Memory\n\nNo entries.\n")
    return str(md)


class TestHarnessRunnerRun:
    """Tests for HarnessRunner.run()."""

    def test_returns_report_with_five_results(self, conn, memory_md):
        """HarnessRunner.run() returns HarnessReport with 5 results."""
        runner = HarnessRunner(conn, memory_md)
        report = runner.run()

        assert isinstance(report, HarnessReport)
        assert len(report.results) == 5

    def test_all_invariant_names_present(self, conn, memory_md):
        """All five invariant names appear in the report."""
        runner = HarnessRunner(conn, memory_md)
        report = runner.run()

        names = {r.invariant_name for r in report.results}
        expected = {
            "at_most_once_verdict",
            "layer_coverage_monotonic",
            "specification_closure",
            "delta_retrieval",
            "nversion_consistency",
        }
        assert names == expected

    def test_all_pass_on_empty_db(self, conn, memory_md):
        """All invariants pass when database is empty."""
        runner = HarnessRunner(conn, memory_md)
        report = runner.run()

        assert report.all_passed is True

    def test_exits_cleanly_on_zero_data(self, conn, memory_md):
        """No crashes on zero-data state."""
        runner = HarnessRunner(conn, memory_md)
        # Should not raise
        report = runner.run()

        assert report.run_at != ""
        assert isinstance(report.results, list)

    def test_writes_coverage_snapshot(self, conn, memory_md):
        """HarnessRunner writes layer_coverage_snapshots after run."""
        # Seed a review so there is a layer to snapshot
        conn.execute(
            """
            INSERT INTO identification_reviews (
                review_id, identification_instance_id, layer, point_id,
                pipeline_component, trigger_text, observation_state,
                action_taken, downstream_impact, provenance_pointer,
                verdict
            ) VALUES ('rev-1', 'inst-1', 'L1', 'L1-1', 'Comp',
                      'trigger', 'obs', 'action', 'impact', 'prov', 'accept')
            """
        )

        runner = HarnessRunner(conn, memory_md)
        runner.run()

        count = conn.execute(
            "SELECT COUNT(*) FROM layer_coverage_snapshots"
        ).fetchone()[0]
        assert count >= 1

        snap = conn.execute(
            "SELECT layer, reviewed_count FROM layer_coverage_snapshots"
        ).fetchone()
        assert snap[0] == "L1"
        assert snap[1] == 1


class TestHarnessReport:
    """Tests for HarnessReport dataclass."""

    def test_all_passed_true_when_all_pass(self):
        """all_passed is True when all invariants pass."""
        report = HarnessReport(
            results=[
                InvariantResult("inv1", True, [], "2026-02-23"),
                InvariantResult("inv2", True, [], "2026-02-23"),
            ],
            run_at="2026-02-23T00:00:00Z",
        )

        assert report.all_passed is True

    def test_all_passed_false_when_one_fails(self):
        """all_passed is False when any invariant fails."""
        report = HarnessReport(
            results=[
                InvariantResult("inv1", True, [], "2026-02-23"),
                InvariantResult("inv2", False, [{"detail": "bad"}], "2026-02-23"),
            ],
            run_at="2026-02-23T00:00:00Z",
        )

        assert report.all_passed is False

    def test_summary_contains_all_invariant_names(self):
        """summary() contains all invariant names."""
        report = HarnessReport(
            results=[
                InvariantResult("at_most_once", True, [], "2026-02-23"),
                InvariantResult("spec_closure", False, [{"d": "x"}], "2026-02-23"),
            ],
            run_at="2026-02-23T00:00:00Z",
        )

        summary = report.summary()

        assert "at_most_once" in summary
        assert "spec_closure" in summary
        assert "PASS" in summary
        assert "FAIL" in summary

    def test_summary_shows_pass_for_passing(self):
        """summary() shows PASS for passing invariants."""
        report = HarnessReport(
            results=[
                InvariantResult("inv1", True, [], "2026-02-23"),
            ],
            run_at="2026-02-23T00:00:00Z",
        )

        assert "PASS" in report.summary()

    def test_summary_shows_violation_count_for_failing(self):
        """summary() shows violation count for failing invariants."""
        report = HarnessReport(
            results=[
                InvariantResult(
                    "inv1", False,
                    [{"d": "a"}, {"d": "b"}],
                    "2026-02-23",
                ),
            ],
            run_at="2026-02-23T00:00:00Z",
        )

        summary = report.summary()
        assert "FAIL (2 violations)" in summary
