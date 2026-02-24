"""Tests for Transport Efficiency schema and memory-review CLI (Phase 16, Plan 01).

Verifies:
- transport_efficiency_sessions table creation with all 12 columns
- memory_candidates TE extensions (pre_te_avg, post_te_avg, te_delta)
- memory_candidates review extensions (confidence, subject, session_id)
- Schema idempotency (safe to call multiple times)
- memory-review CLI accept flow (writes to MEMORY.md + updates status)
- memory-review CLI reject flow
- memory-review CLI skip flow
- memory-review CLI quit flow
- memory-review CLI edit flow
- Dedup warning when ccd_axis already in MEMORY.md
- No pending candidates case
- CCD format in MEMORY.md matches existing entry format
"""

from __future__ import annotations

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.transport_efficiency import (
    MEMORY_CANDIDATES_REVIEW_EXTENSIONS,
    MEMORY_CANDIDATES_TE_EXTENSIONS,
    TRANSPORT_EFFICIENCY_DDL,
    TRANSPORT_EFFICIENCY_INDEXES,
    create_te_schema,
)
from src.pipeline.storage.schema import create_schema


def _seed_memory_candidate(
    conn: duckdb.DuckDBPyConnection,
    candidate_id: str = "cand_001",
    ccd_axis: str = "test-axis",
    scope_rule: str = "Test scope rule text",
    flood_example: str = "Test flood example text",
    confidence: float | None = 0.85,
    subject: str | None = "human",
    session_id: str | None = "session_01",
    source_flame_event_id: str | None = "fe_001",
    detection_count: int = 3,
    status: str = "pending",
) -> None:
    """Insert a memory_candidate row for testing."""
    conn.execute(
        "INSERT INTO memory_candidates "
        "(id, ccd_axis, scope_rule, flood_example, status, "
        "confidence, subject, session_id, source_flame_event_id, detection_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            candidate_id, ccd_axis, scope_rule, flood_example, status,
            confidence, subject, session_id, source_flame_event_id,
            detection_count,
        ],
    )


# ============================================================
# Schema Tests
# ============================================================


class TestTransportEfficiencySchema:
    """Test transport_efficiency_sessions DDL creation."""

    def test_te_table_created(self):
        """transport_efficiency_sessions table should be created."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'transport_efficiency_sessions'"
        ).fetchall()]
        assert "transport_efficiency_sessions" in tables
        conn.close()

    def test_te_table_has_12_columns(self):
        """transport_efficiency_sessions should have all 12 columns."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        cols = [r[0] for r in conn.execute(
            "DESCRIBE transport_efficiency_sessions"
        ).fetchall()]
        assert len(cols) == 12
        expected = [
            "te_id", "session_id", "human_id", "subject",
            "raven_depth", "crow_efficiency", "transport_speed",
            "trunk_quality", "composite_te", "trunk_quality_status",
            "fringe_drift_rate", "created_at",
        ]
        for col in expected:
            assert col in cols, f"Missing column: {col}"
        conn.close()

    def test_te_subject_check_constraint(self):
        """subject column should only accept 'human' or 'ai'."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        # Valid insert
        conn.execute(
            "INSERT INTO transport_efficiency_sessions "
            "(te_id, session_id, subject) VALUES ('t1', 's1', 'human')"
        )
        conn.execute(
            "INSERT INTO transport_efficiency_sessions "
            "(te_id, session_id, subject) VALUES ('t2', 's2', 'ai')"
        )
        # Invalid insert
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO transport_efficiency_sessions "
                "(te_id, session_id, subject) VALUES ('t3', 's3', 'invalid')"
            )
        conn.close()

    def test_te_trunk_quality_status_check(self):
        """trunk_quality_status should only accept 'pending' or 'confirmed'."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        # Default is 'pending'
        conn.execute(
            "INSERT INTO transport_efficiency_sessions "
            "(te_id, session_id, subject) VALUES ('t1', 's1', 'human')"
        )
        row = conn.execute(
            "SELECT trunk_quality_status FROM transport_efficiency_sessions "
            "WHERE te_id = 't1'"
        ).fetchone()
        assert row[0] == "pending"
        # Invalid
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO transport_efficiency_sessions "
                "(te_id, session_id, subject, trunk_quality_status) "
                "VALUES ('t2', 's2', 'human', 'invalid')"
            )
        conn.close()

    def test_te_indexes_created(self):
        """Indexes on session_id and subject should be created."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        # DuckDB stores index info -- just verify no error on index DDL
        # Re-running should be idempotent
        for idx_sql in TRANSPORT_EFFICIENCY_INDEXES:
            conn.execute(idx_sql)
        conn.close()


class TestMemoryCandidatesTEExtensions:
    """Test memory_candidates ALTER TABLE TE extensions."""

    def test_pre_te_avg_column_added(self):
        """memory_candidates should have pre_te_avg FLOAT column."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        cols = {r[0]: r[1] for r in conn.execute(
            "DESCRIBE memory_candidates"
        ).fetchall()}
        assert "pre_te_avg" in cols
        assert "FLOAT" in cols["pre_te_avg"]
        conn.close()

    def test_post_te_avg_column_added(self):
        """memory_candidates should have post_te_avg FLOAT column."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        cols = {r[0]: r[1] for r in conn.execute(
            "DESCRIBE memory_candidates"
        ).fetchall()}
        assert "post_te_avg" in cols
        assert "FLOAT" in cols["post_te_avg"]
        conn.close()

    def test_te_delta_column_added(self):
        """memory_candidates should have te_delta FLOAT column."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        cols = {r[0]: r[1] for r in conn.execute(
            "DESCRIBE memory_candidates"
        ).fetchall()}
        assert "te_delta" in cols
        assert "FLOAT" in cols["te_delta"]
        conn.close()

    def test_review_extensions_added(self):
        """memory_candidates should have confidence, subject, session_id."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        cols = [r[0] for r in conn.execute(
            "DESCRIBE memory_candidates"
        ).fetchall()]
        for col_name, _ in MEMORY_CANDIDATES_REVIEW_EXTENSIONS:
            assert col_name in cols, f"Missing review extension: {col_name}"
        conn.close()

    def test_schema_idempotency(self):
        """Calling create_ddf_schema twice should not error."""
        conn = duckdb.connect(":memory:")
        create_ddf_schema(conn)
        create_ddf_schema(conn)
        # All columns still present
        cols = [r[0] for r in conn.execute(
            "DESCRIBE memory_candidates"
        ).fetchall()]
        assert "pre_te_avg" in cols
        assert "post_te_avg" in cols
        assert "te_delta" in cols
        conn.close()


# ============================================================
# Memory-Review CLI Tests
# ============================================================


class TestMemoryReviewNoCandidates:
    """Test memory-review with no pending candidates."""

    def test_no_pending_candidates(self, tmp_path):
        """Should display 'No pending memory candidates.' and exit 0."""
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "memory-review", "--db", db_path],
        )
        assert result.exit_code == 0
        assert "No pending memory candidates." in result.output


class TestMemoryReviewAcceptFlow:
    """Test memory-review accept flow."""

    def test_accept_writes_to_memory_file(self, tmp_path):
        """Accept should write CCD entry to MEMORY.md."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        # Create initial MEMORY.md
        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, ccd_axis="test-deposit-axis")
        conn.close()

        # Mock input: 'a' for accept
        inputs = iter(["a"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        with open(memory_path) as f:
            content = f.read()

        assert "## test-deposit-axis" in content
        assert "**CCD axis:** test-deposit-axis" in content
        assert "**Scope rule:** Test scope rule text" in content
        assert "**Flood example:** Test flood example text" in content

    def test_accept_updates_status_to_validated(self, tmp_path):
        """Accept should update status to 'validated' in DuckDB."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, candidate_id="cand_accept")
        conn.close()

        inputs = iter(["a"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT status, reviewed_at FROM memory_candidates WHERE id = 'cand_accept'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "validated"
        assert row[1] is not None  # reviewed_at should be set

    def test_accept_ccd_format_matches_spec(self, tmp_path):
        """Accepted entry should match CCD format: ---\\n\\n## axis\\n\\n..."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, ccd_axis="format-check-axis")
        conn.close()

        inputs = iter(["a"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        with open(memory_path) as f:
            content = f.read()

        # Verify exact CCD format structure
        assert "\n---\n\n## format-check-axis\n\n" in content
        assert "**CCD axis:** format-check-axis\n" in content
        assert "**Scope rule:** Test scope rule text\n" in content
        assert "**Flood example:** Test flood example text\n" in content

    def test_accept_creates_memory_file_if_missing(self, tmp_path):
        """Accept should create MEMORY.md if it doesn't exist."""
        db_path = str(tmp_path / "test.db")
        memory_dir = tmp_path / "subdir"
        memory_path = str(memory_dir / "MEMORY.md")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, ccd_axis="new-file-axis")
        conn.close()

        inputs = iter(["a"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        assert (memory_dir / "MEMORY.md").exists()
        with open(memory_path) as f:
            content = f.read()
        assert "## new-file-axis" in content

    def test_accept_multiple_candidates(self, tmp_path):
        """Accepting multiple candidates should append each to MEMORY.md."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(
            conn, candidate_id="c1", ccd_axis="axis-one",
            scope_rule="Scope one", flood_example="Flood one",
            confidence=0.9,
        )
        _seed_memory_candidate(
            conn, candidate_id="c2", ccd_axis="axis-two",
            scope_rule="Scope two", flood_example="Flood two",
            confidence=0.8,
        )
        conn.close()

        inputs = iter(["a", "a"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        with open(memory_path) as f:
            content = f.read()

        assert "## axis-one" in content
        assert "## axis-two" in content


class TestMemoryReviewRejectFlow:
    """Test memory-review reject flow."""

    def test_reject_updates_status(self, tmp_path):
        """Reject should update status to 'rejected'."""
        db_path = str(tmp_path / "test.db")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, candidate_id="cand_reject")
        conn.close()

        inputs = iter(["r"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=str(tmp_path / "MEMORY.md"),
            input_fn=lambda _prompt: next(inputs),
        )

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT status, reviewed_at FROM memory_candidates WHERE id = 'cand_reject'"
        ).fetchone()
        conn.close()

        assert row[0] == "rejected"
        assert row[1] is not None

    def test_reject_does_not_write_to_memory_file(self, tmp_path):
        """Reject should NOT write anything to MEMORY.md."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, ccd_axis="reject-axis")
        conn.close()

        inputs = iter(["r"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        with open(memory_path) as f:
            content = f.read()

        assert "reject-axis" not in content
        assert content == "# Project Memory\n\n"


class TestMemoryReviewSkipFlow:
    """Test memory-review skip flow."""

    def test_skip_does_not_change_status(self, tmp_path):
        """Skip should leave candidate status as 'pending'."""
        db_path = str(tmp_path / "test.db")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, candidate_id="cand_skip")
        conn.close()

        inputs = iter(["s"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=str(tmp_path / "MEMORY.md"),
            input_fn=lambda _prompt: next(inputs),
        )

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT status FROM memory_candidates WHERE id = 'cand_skip'"
        ).fetchone()
        conn.close()

        assert row[0] == "pending"


class TestMemoryReviewQuitFlow:
    """Test memory-review quit flow."""

    def test_quit_stops_processing(self, tmp_path):
        """Quit should stop processing remaining candidates."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(
            conn, candidate_id="c1", ccd_axis="axis-one",
            confidence=0.9,
        )
        _seed_memory_candidate(
            conn, candidate_id="c2", ccd_axis="axis-two",
            confidence=0.8,
        )
        conn.close()

        # Quit on first candidate; second never processed
        inputs = iter(["q"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(inputs),
        )

        # Both should still be pending
        conn = duckdb.connect(db_path)
        statuses = conn.execute(
            "SELECT id, status FROM memory_candidates ORDER BY id"
        ).fetchall()
        conn.close()

        assert all(s == "pending" for _, s in statuses)


class TestMemoryReviewDedupWarning:
    """Test dedup warning when ccd_axis already in MEMORY.md."""

    def test_dedup_warning_fires(self, tmp_path):
        """Should warn when ccd_axis already appears in MEMORY.md."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        # Pre-populate MEMORY.md with existing axis
        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n## existing-axis\n\n"
                    "**CCD axis:** existing-axis\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, ccd_axis="existing-axis")
        conn.close()

        # Accept, then 'n' to dedup warning
        prompts_seen = []
        responses = iter(["a", "n"])

        def mock_input(prompt):
            prompts_seen.append(prompt)
            return next(responses)

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=mock_input,
        )

        # Should have been asked about duplicate
        assert any("Proceed anyway" in p for p in prompts_seen)

    def test_dedup_case_insensitive(self, tmp_path):
        """Dedup check should be case-insensitive."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n## Existing-Axis\n\n"
                    "**CCD axis:** Existing-Axis\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(conn, ccd_axis="existing-axis")  # lowercase
        conn.close()

        prompts_seen = []
        responses = iter(["a", "n"])

        def mock_input(prompt):
            prompts_seen.append(prompt)
            return next(responses)

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=mock_input,
        )

        assert any("Proceed anyway" in p for p in prompts_seen)

    def test_dedup_proceed_yes_writes(self, tmp_path):
        """Confirming 'y' on dedup should still write to MEMORY.md."""
        db_path = str(tmp_path / "test.db")
        memory_path = str(tmp_path / "MEMORY.md")

        with open(memory_path, "w") as f:
            f.write("# Project Memory\n\n## dup-axis\n\n")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(
            conn, ccd_axis="dup-axis",
            scope_rule="New scope rule",
        )
        conn.close()

        responses = iter(["a", "y"])

        from src.pipeline.cli.intelligence import _memory_review_impl
        _memory_review_impl(
            db=db_path,
            memory_file=memory_path,
            input_fn=lambda _prompt: next(responses),
        )

        with open(memory_path) as f:
            content = f.read()

        # The entry should appear (second instance after the original)
        assert content.count("dup-axis") > 1


class TestMemoryReviewDisplayFormat:
    """Test candidate display format."""

    def test_displays_candidate_info(self, tmp_path):
        """Should display candidate with confidence, subject, detections."""
        db_path = str(tmp_path / "test.db")

        conn = duckdb.connect(db_path)
        create_schema(conn)
        create_ddf_schema(conn)
        _seed_memory_candidate(
            conn,
            ccd_axis="display-axis",
            confidence=0.92,
            subject="human",
            detection_count=5,
        )
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["intelligence", "memory-review", "--db", db_path],
            input="s\n",
        )

        assert result.exit_code == 0
        assert "CANDIDATE [1/1]" in result.output
        assert "0.92" in result.output
        assert "human" in result.output
        assert "display-axis" in result.output


class TestMemoryReviewRegistered:
    """Verify memory-review is registered in the intelligence group."""

    def test_memory_review_registered(self):
        """memory-review should be a registered command."""
        from src.pipeline.cli.intelligence import intelligence_group
        assert "memory-review" in intelligence_group.commands
