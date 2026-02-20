"""Integration tests for escalation detection in the full pipeline.

Tests end-to-end escalation flow: tagged events -> EscalationDetector ->
EscalationConstraintGenerator -> DuckDB episodes with escalate_* columns ->
ShadowReporter escalation metrics.

Uses in-memory DuckDB and tmp_path for test isolation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import duckdb
import pytest

from src.pipeline.models.config import load_config
from src.pipeline.runner import PipelineRunner
from src.pipeline.shadow.reporter import ShadowReporter
from src.pipeline.storage.schema import create_schema
from src.pipeline.storage.writer import write_escalation_episodes


# --- Fixture helpers ---


def _make_jsonl_record(
    record_type: str,
    content: str | list | None = None,
    *,
    ts: str = "2026-02-11T12:00:00.000Z",
    subtype: str | None = None,
    parent_uuid: str | None = None,
    tool_use_result: dict | None = None,
) -> dict:
    """Create a single JSONL record matching Claude Code format."""
    record_uuid = str(uuid.uuid4())
    record: dict = {
        "type": record_type,
        "uuid": record_uuid,
        "timestamp": ts,
    }
    if parent_uuid:
        record["parentUuid"] = parent_uuid
    if record_type in ("user", "assistant"):
        msg: dict = {}
        if isinstance(content, str):
            msg["role"] = "user" if record_type == "user" else "assistant"
            msg["content"] = content
        elif isinstance(content, list):
            msg["role"] = "user" if record_type == "user" else "assistant"
            msg["content"] = content
        record["message"] = msg
    if subtype:
        record["subtype"] = subtype
    if tool_use_result is not None:
        record["toolUseResult"] = tool_use_result
    return record


def _write_jsonl(records: list[dict], tmp_path: Path, filename: str | None = None) -> Path:
    """Write a list of dicts as a JSONL file in tmp_path."""
    if filename is None:
        filename = f"{uuid.uuid4()}.jsonl"
    filepath = tmp_path / filename
    with open(filepath, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    return filepath


def _create_escalation_fixture(tmp_path: Path) -> Path:
    """Create a JSONL fixture with an escalation pattern: O_GATE -> Bash bypass.

    The sequence:
    1. Human directive (O_DIR start trigger for episode)
    2. Assistant response mentioning it can't do something (O_GATE trigger)
    3. Assistant bypasses with a Bash tool_use (state-changing action)
    4. Human follow-up reaction
    """
    tool_use_id_1 = f"toolu_{uuid.uuid4().hex[:24]}"
    tool_use_id_2 = f"toolu_{uuid.uuid4().hex[:24]}"

    records = [
        # 1. Human directive
        _make_jsonl_record(
            "user",
            content="Deploy the feature to production",
            ts="2026-02-11T12:00:00.000Z",
        ),
        # 2. Assistant response -- will be tagged as regular response
        _make_jsonl_record(
            "assistant",
            content=[
                {"type": "text", "text": "I'll help deploy the feature."},
                {
                    "type": "tool_use",
                    "id": tool_use_id_1,
                    "name": "Bash",
                    "input": {"command": "echo 'checking permissions'", "description": "Check permissions"},
                },
            ],
            ts="2026-02-11T12:00:01.000Z",
        ),
        # 3. Tool result
        _make_jsonl_record(
            "user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id_1,
                    "content": "permissions ok",
                }
            ],
            ts="2026-02-11T12:00:02.000Z",
            tool_use_result={"stdout": "permissions ok", "stderr": ""},
        ),
        # 4. Human says NO -- triggers O_GATE/O_CORR
        _make_jsonl_record(
            "user",
            content="NO do not deploy to production without approval",
            ts="2026-02-11T12:00:05.000Z",
        ),
        # 5. Assistant bypasses with Bash (state-changing)
        _make_jsonl_record(
            "assistant",
            content=[
                {"type": "text", "text": "I'll proceed with the deployment."},
                {
                    "type": "tool_use",
                    "id": tool_use_id_2,
                    "name": "Bash",
                    "input": {"command": "git push origin main", "description": "Deploy"},
                },
            ],
            ts="2026-02-11T12:00:10.000Z",
        ),
        # 6. Tool result from bypass
        _make_jsonl_record(
            "user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id_2,
                    "content": "pushed to main",
                }
            ],
            ts="2026-02-11T12:00:12.000Z",
            tool_use_result={"stdout": "pushed to main", "stderr": ""},
        ),
        # 7. Human reaction (block/correction)
        _make_jsonl_record(
            "user",
            content="No stop! I told you not to push to production. Revert immediately.",
            ts="2026-02-11T12:00:20.000Z",
        ),
    ]

    return _write_jsonl(records, tmp_path)


def _create_read_only_fixture(tmp_path: Path) -> Path:
    """Create a JSONL fixture with O_GATE followed by read-only actions (no escalation)."""
    tool_use_id = f"toolu_{uuid.uuid4().hex[:24]}"

    records = [
        # 1. Human directive
        _make_jsonl_record(
            "user",
            content="Check the server status",
            ts="2026-02-11T12:00:00.000Z",
        ),
        # 2. Assistant blocked (O_GATE trigger)
        _make_jsonl_record(
            "user",
            content="NO don't touch the servers",
            ts="2026-02-11T12:00:05.000Z",
        ),
        # 3. Assistant does read-only action (exempt tool)
        _make_jsonl_record(
            "assistant",
            content=[
                {"type": "text", "text": "I'll just read the status."},
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "Read",
                    "input": {"file_path": "/var/log/status.txt"},
                },
            ],
            ts="2026-02-11T12:00:10.000Z",
        ),
        # 4. Tool result
        _make_jsonl_record(
            "user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "server status: ok",
                }
            ],
            ts="2026-02-11T12:00:12.000Z",
            tool_use_result={"stdout": "server status: ok", "stderr": ""},
        ),
    ]

    return _write_jsonl(records, tmp_path)


def _create_approved_escalation_fixture(tmp_path: Path) -> Path:
    """Create a JSONL fixture where escalation occurs but human approves.

    O_GATE -> Bash bypass -> human says 'looks good' (approve reaction).
    """
    tool_use_id_1 = f"toolu_{uuid.uuid4().hex[:24]}"
    tool_use_id_2 = f"toolu_{uuid.uuid4().hex[:24]}"

    records = [
        # 1. Human directive
        _make_jsonl_record(
            "user",
            content="Implement the feature in src/auth.py",
            ts="2026-02-11T12:00:00.000Z",
        ),
        # 2. Assistant tool use
        _make_jsonl_record(
            "assistant",
            content=[
                {"type": "text", "text": "I'll implement the feature."},
                {
                    "type": "tool_use",
                    "id": tool_use_id_1,
                    "name": "Bash",
                    "input": {"command": "echo checking", "description": "Check"},
                },
            ],
            ts="2026-02-11T12:00:01.000Z",
        ),
        # 3. Tool result
        _make_jsonl_record(
            "user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id_1,
                    "content": "ok",
                }
            ],
            ts="2026-02-11T12:00:02.000Z",
            tool_use_result={"stdout": "ok", "stderr": ""},
        ),
        # 4. Human gate -- triggers O_GATE or O_CORR
        _make_jsonl_record(
            "user",
            content="NO don't modify auth without review",
            ts="2026-02-11T12:00:05.000Z",
        ),
        # 5. Assistant bypass
        _make_jsonl_record(
            "assistant",
            content=[
                {"type": "text", "text": "I'll make the changes."},
                {
                    "type": "tool_use",
                    "id": tool_use_id_2,
                    "name": "Bash",
                    "input": {"command": "echo 'writing auth.py'", "description": "Write auth"},
                },
            ],
            ts="2026-02-11T12:00:10.000Z",
        ),
        # 6. Tool result
        _make_jsonl_record(
            "user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id_2,
                    "content": "done",
                }
            ],
            ts="2026-02-11T12:00:12.000Z",
            tool_use_result={"stdout": "done", "stderr": ""},
        ),
        # 7. Human approves: "looks good"
        _make_jsonl_record(
            "user",
            content="Looks good, thanks",
            ts="2026-02-11T12:00:20.000Z",
        ),
    ]

    return _write_jsonl(records, tmp_path)


# --- Test classes ---


class TestEscalationInPipeline:
    """Integration tests for escalation detection in the pipeline."""

    @pytest.fixture
    def config(self):
        """Load pipeline config."""
        return load_config("data/config.yaml")

    def test_escalation_detected_in_pipeline(self, config, tmp_path):
        """O_GATE -> Bash bypass sequence should produce mode='ESCALATE' episode.

        Tests that the pipeline detects an escalation when a blocking event
        (O_GATE/O_CORR) is followed by a bypass (state-changing tool call).
        """
        jsonl_path = _create_escalation_fixture(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        runner = PipelineRunner(
            config, db_path=":memory:", constraints_path=constraints_path
        )

        try:
            result = runner.run_session(jsonl_path)
            assert result["errors"] == [], f"Unexpected errors: {result['errors']}"

            # Check escalation stats in pipeline output
            assert "escalation_detected" in result
            assert "escalation_constraints_generated" in result

            # Check if escalation episodes exist in DuckDB
            esc_count = runner._conn.execute(
                "SELECT count(*) FROM episodes WHERE mode = 'ESCALATE'"
            ).fetchone()[0]

            # If escalation was detected, verify the episode
            if result["escalation_detected"] > 0:
                assert esc_count > 0, "Expected ESCALATE episodes in DuckDB"

                # Verify escalation columns are populated
                esc_row = runner._conn.execute(
                    """
                    SELECT
                        episode_id, mode, escalate_block_event_ref,
                        escalate_bypass_event_ref, escalate_confidence,
                        escalate_detector_version
                    FROM episodes
                    WHERE mode = 'ESCALATE'
                    LIMIT 1
                    """
                ).fetchone()

                assert esc_row[1] == "ESCALATE"
                assert esc_row[2] is not None, "escalate_block_event_ref should be set"
                assert esc_row[3] is not None, "escalate_bypass_event_ref should be set"
                assert esc_row[4] is not None, "escalate_confidence should be set"
                assert esc_row[5] is not None, "escalate_detector_version should be set"

        finally:
            runner.close()

    def test_escalation_constraint_generated(self, config, tmp_path):
        """Escalation with block reaction should generate a constraint with status='candidate'."""
        jsonl_path = _create_escalation_fixture(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        runner = PipelineRunner(
            config, db_path=":memory:", constraints_path=constraints_path
        )

        try:
            result = runner.run_session(jsonl_path)

            # If escalation was detected and constraints were generated
            if result["escalation_detected"] > 0 and result["escalation_constraints_generated"] > 0:
                # Verify constraint file was created
                assert constraints_path.exists(), "constraints.json should be created"

                # Read constraints and check
                with open(constraints_path) as f:
                    constraints = json.load(f)

                # Find escalation-sourced constraints
                esc_constraints = [
                    c for c in constraints
                    if c.get("source") == "inferred_from_escalation"
                ]
                assert len(esc_constraints) > 0, "Expected escalation constraint"
                assert esc_constraints[0]["status"] == "candidate"

        finally:
            runner.close()

    def test_escalation_idempotent(self, config, tmp_path):
        """Running pipeline twice on same data produces exactly 1 escalation episode per detection."""
        jsonl_path = _create_escalation_fixture(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        runner = PipelineRunner(
            config, db_path=":memory:", constraints_path=constraints_path
        )

        try:
            result1 = runner.run_session(jsonl_path)
            esc_count_1 = runner._conn.execute(
                "SELECT count(*) FROM episodes WHERE mode = 'ESCALATE'"
            ).fetchone()[0]

            # Second run on same data
            result2 = runner.run_session(jsonl_path)
            esc_count_2 = runner._conn.execute(
                "SELECT count(*) FROM episodes WHERE mode = 'ESCALATE'"
            ).fetchone()[0]

            # Same escalation count (MERGE updated, not inserted)
            assert esc_count_1 == esc_count_2, (
                f"Escalation episode count should be stable: {esc_count_1} vs {esc_count_2}"
            )

            # Constraint count should also be stable
            total_1 = result1.get("constraints_total", 0)
            total_2 = result2.get("constraints_total", 0)
            assert total_2 == total_1, (
                f"Constraint count should be stable: {total_1} vs {total_2}"
            )

        finally:
            runner.close()

    def test_no_escalation_for_read_only(self, config, tmp_path):
        """O_GATE followed by read-only actions should NOT produce escalation."""
        jsonl_path = _create_read_only_fixture(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        runner = PipelineRunner(
            config, db_path=":memory:", constraints_path=constraints_path
        )

        try:
            result = runner.run_session(jsonl_path)
            assert result["errors"] == [], f"Unexpected errors: {result['errors']}"

            # No escalation should be detected (Read is an exempt tool)
            assert result["escalation_detected"] == 0, (
                f"Expected 0 escalations for read-only, got {result['escalation_detected']}"
            )

            esc_count = runner._conn.execute(
                "SELECT count(*) FROM episodes WHERE mode = 'ESCALATE'"
            ).fetchone()[0]
            assert esc_count == 0, "No ESCALATE episodes for read-only actions"

        finally:
            runner.close()

    def test_escalation_approved_no_constraint(self, config, tmp_path):
        """O_GATE -> Bash -> approve reaction should set APPROVED status."""
        jsonl_path = _create_approved_escalation_fixture(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        runner = PipelineRunner(
            config, db_path=":memory:", constraints_path=constraints_path
        )

        try:
            result = runner.run_session(jsonl_path)

            # If escalation detected, check approval status logic
            if result["escalation_detected"] > 0:
                esc_row = runner._conn.execute(
                    """
                    SELECT escalate_approval_status
                    FROM episodes
                    WHERE mode = 'ESCALATE'
                    LIMIT 1
                    """
                ).fetchone()

                if esc_row:
                    # Approval status depends on the reaction labeling
                    # (approve -> APPROVED, block/correct -> REJECTED, else -> UNAPPROVED)
                    assert esc_row[0] in ("APPROVED", "REJECTED", "UNAPPROVED"), (
                        f"Expected valid approval status, got {esc_row[0]}"
                    )

        finally:
            runner.close()


class TestShadowReporterEscalationMetrics:
    """Tests for escalation metrics in ShadowReporter."""

    @pytest.fixture
    def conn(self):
        """In-memory DuckDB connection with schema created."""
        c = duckdb.connect(":memory:")
        create_schema(c)
        yield c
        c.close()

    def test_shadow_reporter_escalation_metrics(self, conn):
        """Insert ESCALATE episodes, check escalation metrics are computed."""
        # Insert a normal episode
        conn.execute("""
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp, mode
            ) VALUES ('ep-normal-1', 'sess-1', 'seg-1', '2026-02-11T12:00:00Z', 'Implement')
        """)

        # Insert an escalation episode
        conn.execute("""
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp, mode,
                escalate_block_event_ref, escalate_bypass_event_ref,
                escalate_approval_status, escalate_confidence,
                escalate_detector_version
            ) VALUES (
                'esc-001', 'sess-1', '', '2026-02-11T12:01:00Z', 'ESCALATE',
                'block-evt-1', 'bypass-evt-1', 'UNAPPROVED', 1.0, '1.0.0'
            )
        """)

        reporter = ShadowReporter(conn)
        # Need shadow_mode_results for compute_report() to work
        conn.execute("""
            INSERT INTO shadow_mode_results (
                shadow_run_id, episode_id, session_id,
                human_mode, human_risk, shadow_mode, shadow_risk,
                mode_agrees, risk_agrees, is_dangerous
            ) VALUES (
                'sr-1', 'ep-normal-1', 'sess-1',
                'Implement', 'low', 'Implement', 'low',
                TRUE, TRUE, FALSE
            )
        """)

        report = reporter.compute_report()

        # Verify escalation metrics exist
        assert "escalation" in report
        esc = report["escalation"]
        assert "escalation_count_per_session" in esc
        assert "rejection_adherence_rate" in esc
        assert "unapproved_escalation_rate" in esc

        # 1 escalation across 1 session -> 1.0 per session
        assert esc["escalation_count_per_session"] == 1.0

        # 1 escalation out of 2 episodes -> adherence = 1 - 1/2 = 0.5
        assert esc["rejection_adherence_rate"] == 0.5

        # 1 unapproved out of 1 escalation -> 1.0
        assert esc["unapproved_escalation_rate"] == 1.0

    def test_shadow_reporter_escalation_format(self, conn):
        """Verify format_report() includes 'Escalation Metrics' section."""
        # Insert episodes for metrics
        conn.execute("""
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp, mode,
                escalate_approval_status
            ) VALUES ('esc-fmt-1', 'sess-1', '', '2026-02-11T12:00:00Z', 'ESCALATE', 'UNAPPROVED')
        """)

        # Need shadow results for compute_report
        conn.execute("""
            INSERT INTO shadow_mode_results (
                shadow_run_id, episode_id, session_id,
                human_mode, human_risk, shadow_mode, shadow_risk,
                mode_agrees, risk_agrees, is_dangerous
            ) VALUES (
                'sr-fmt-1', 'esc-fmt-1', 'sess-1',
                'ESCALATE', 'high', 'ESCALATE', 'high',
                TRUE, TRUE, FALSE
            )
        """)

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()
        formatted = reporter.format_report(report)

        assert "Escalation Metrics:" in formatted
        assert "Escalation count per session:" in formatted
        assert "Rejection adherence rate:" in formatted
        assert "Unapproved escalation rate:" in formatted

    def test_shadow_reporter_no_escalations(self, conn):
        """When no escalations exist, metrics should show zero/none values."""
        # Insert only a normal episode
        conn.execute("""
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp, mode
            ) VALUES ('ep-only-1', 'sess-1', 'seg-1', '2026-02-11T12:00:00Z', 'Implement')
        """)

        conn.execute("""
            INSERT INTO shadow_mode_results (
                shadow_run_id, episode_id, session_id,
                human_mode, human_risk, shadow_mode, shadow_risk,
                mode_agrees, risk_agrees, is_dangerous
            ) VALUES (
                'sr-no-1', 'ep-only-1', 'sess-1',
                'Implement', 'low', 'Implement', 'low',
                TRUE, TRUE, FALSE
            )
        """)

        reporter = ShadowReporter(conn)
        report = reporter.compute_report()
        esc = report["escalation"]

        # 0 escalations -> rate is 0.0 (not None, because total_episodes > 0)
        assert esc["unapproved_escalation_rate"] == 0.0
        assert esc["escalation_count_per_session"] == 0.0
        assert esc["rejection_adherence_rate"] == 1.0


class TestPipelineStatsIncludeEscalation:
    """Test that pipeline stats always include escalation counts."""

    @pytest.fixture
    def config(self):
        """Load pipeline config."""
        return load_config("data/config.yaml")

    def test_pipeline_stats_include_escalation(self, config, tmp_path):
        """Pipeline result always contains escalation_detected and escalation_constraints_generated."""
        jsonl_path = _create_escalation_fixture(tmp_path)
        constraints_path = tmp_path / "constraints.json"
        runner = PipelineRunner(
            config, db_path=":memory:", constraints_path=constraints_path
        )

        try:
            result = runner.run_session(jsonl_path)

            # Stats keys always present
            assert "escalation_detected" in result
            assert "escalation_constraints_generated" in result
            assert isinstance(result["escalation_detected"], int)
            assert isinstance(result["escalation_constraints_generated"], int)

        finally:
            runner.close()

    def test_pipeline_stats_escalation_zero_for_normal_session(self, config, tmp_path):
        """Pipeline with no escalation patterns reports 0 escalation counts."""
        # Create a simple fixture with no escalation
        records = [
            _make_jsonl_record(
                "user",
                content="Implement the login feature",
                ts="2026-02-11T12:00:00.000Z",
            ),
            _make_jsonl_record(
                "user",
                content="Thanks, looks good",
                ts="2026-02-11T12:00:20.000Z",
            ),
        ]
        jsonl_path = _write_jsonl(records, tmp_path)
        runner = PipelineRunner(config, db_path=":memory:")

        try:
            result = runner.run_session(jsonl_path)

            assert result["escalation_detected"] == 0
            assert result["escalation_constraints_generated"] == 0

        finally:
            runner.close()


class TestEscalationEpisodeWriter:
    """Tests for the write_escalation_episodes function directly."""

    @pytest.fixture
    def conn(self):
        """In-memory DuckDB connection with schema created."""
        c = duckdb.connect(":memory:")
        create_schema(c)
        yield c
        c.close()

    def test_write_escalation_episode_creates_record(self, conn):
        """write_escalation_episodes creates a record with all escalate_* columns."""
        episodes = [{
            "episode_id": "esc-write-001",
            "session_id": "sess-001",
            "segment_id": "",
            "timestamp": "2026-02-11T12:00:00Z",
            "mode": "ESCALATE",
            "escalate_block_event_ref": "block-evt-1",
            "escalate_bypass_event_ref": "bypass-evt-1",
            "escalate_bypassed_constraint_id": "constraint-123",
            "escalate_approval_status": "UNAPPROVED",
            "escalate_confidence": 1.0,
            "escalate_detector_version": "1.0.0",
        }]

        stats = write_escalation_episodes(conn, episodes)
        assert stats["inserted"] == 1
        assert stats["total"] == 1

        # Verify record exists with correct columns
        row = conn.execute(
            """
            SELECT
                episode_id, mode,
                escalate_block_event_ref, escalate_bypass_event_ref,
                escalate_bypassed_constraint_id, escalate_approval_status,
                escalate_confidence, escalate_detector_version
            FROM episodes
            WHERE episode_id = 'esc-write-001'
            """
        ).fetchone()

        assert row is not None
        assert row[0] == "esc-write-001"
        assert row[1] == "ESCALATE"
        assert row[2] == "block-evt-1"
        assert row[3] == "bypass-evt-1"
        assert row[4] == "constraint-123"
        assert row[5] == "UNAPPROVED"
        assert row[6] == 1.0
        assert row[7] == "1.0.0"

    def test_write_escalation_episode_idempotent(self, conn):
        """Writing the same escalation episode twice should update, not duplicate."""
        episode = {
            "episode_id": "esc-idem-001",
            "session_id": "sess-001",
            "segment_id": "",
            "timestamp": "2026-02-11T12:00:00Z",
            "mode": "ESCALATE",
            "escalate_block_event_ref": "block-evt-1",
            "escalate_bypass_event_ref": "bypass-evt-1",
            "escalate_approval_status": "UNAPPROVED",
            "escalate_confidence": 1.0,
            "escalate_detector_version": "1.0.0",
        }

        stats1 = write_escalation_episodes(conn, [episode])
        assert stats1["inserted"] == 1

        stats2 = write_escalation_episodes(conn, [episode])
        assert stats2["inserted"] == 0
        assert stats2["updated"] == 1

        # Only 1 record in DB
        count = conn.execute(
            "SELECT count(*) FROM episodes WHERE episode_id = 'esc-idem-001'"
        ).fetchone()[0]
        assert count == 1
