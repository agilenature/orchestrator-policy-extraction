"""TDD tests for EpisodePopulator.

Tests observation derivation from context events, action derivation from
start trigger events, outcome derivation from body events, provenance
building, and end-to-end episode population with schema validation.

Covers all 11+ test cases from the plan spec.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from src.pipeline.models.config import PipelineConfig, load_config
from src.pipeline.models.segments import EpisodeSegment
from src.pipeline.populator import EpisodePopulator
from src.pipeline.episode_validator import EpisodeValidator


# --- Helpers ---


def _make_config() -> PipelineConfig:
    """Load the real pipeline config for tests."""
    return load_config("data/config.yaml")


def _make_segment(
    *,
    segment_id: str = "seg-001",
    session_id: str = "sess-001",
    start_event_id: str = "evt-start",
    end_event_id: str = "evt-end",
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    start_trigger: str = "O_DIR",
    end_trigger: str = "X_PROPOSE",
    outcome: str = "success",
    events: list[str] | None = None,
    config_hash: str = "abc123",
) -> EpisodeSegment:
    """Create a test EpisodeSegment."""
    return EpisodeSegment(
        segment_id=segment_id,
        session_id=session_id,
        start_event_id=start_event_id,
        end_event_id=end_event_id,
        start_ts=start_ts or datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        end_ts=end_ts or datetime(2026, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
        start_trigger=start_trigger,
        end_trigger=end_trigger,
        outcome=outcome,
        events=events or ["evt-start", "evt-body1", "evt-body2", "evt-end"],
        event_count=len(events) if events else 4,
        config_hash=config_hash,
    )


def _make_event(
    *,
    event_id: str = "evt-001",
    ts: datetime | None = None,
    session_id: str = "sess-001",
    actor: str = "executor",
    event_type: str = "tool_use",
    text: str = "",
    files_touched: list[str] | None = None,
    primary_tag: str | None = None,
    source_system: str = "claude_jsonl",
    source_ref: str = "sess-001:uuid-001",
    links: dict | None = None,
    tool_name: str | None = None,
) -> dict:
    """Create a test event dict (as returned from DuckDB query)."""
    payload = {
        "common": {
            "text": text,
        }
    }
    if files_touched:
        payload["common"]["files_touched"] = files_touched
    if tool_name:
        payload["common"]["tool_name"] = tool_name

    event = {
        "event_id": event_id,
        "ts_utc": (ts or datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)).isoformat(),
        "session_id": session_id,
        "actor": actor,
        "event_type": event_type,
        "payload": json.dumps(payload),
        "links": json.dumps(links or {}),
        "source_system": source_system,
        "source_ref": source_ref,
        "primary_tag": primary_tag,
    }
    return event


# --- Test classes ---


class TestObservationDerivation:
    """Tests for observation derivation from context events."""

    def test_empty_context_events(self):
        """Empty context events -> unknown statuses, empty changed_files, 'Session start' summary."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement the auth feature",
        )

        result = populator.populate(segment, [start_event], [])
        obs = result["observation"]

        assert obs["repo_state"]["changed_files"] == []
        assert obs["quality_state"]["tests"]["status"] == "unknown"
        assert obs["quality_state"]["lint"]["status"] == "unknown"
        assert "Session start" in obs["context"]["recent_summary"]

    def test_context_with_test_pass(self):
        """Context with T_TEST pass event -> observation.quality_state.tests.status = 'pass'."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement the auth feature",
        )

        context_events = [
            _make_event(
                event_id="ctx-1",
                ts=datetime(2026, 1, 15, 9, 59, 0, tzinfo=timezone.utc),
                event_type="tool_result",
                text="All 15 tests passed",
                primary_tag="T_TEST",
            ),
        ]

        result = populator.populate(segment, [start_event], context_events)
        assert result["observation"]["quality_state"]["tests"]["status"] == "pass"

    def test_context_with_files_touched(self):
        """Context with files_touched -> observation.repo_state.changed_files populated."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Now add tests",
        )

        context_events = [
            _make_event(
                event_id="ctx-1",
                ts=datetime(2026, 1, 15, 9, 58, 0, tzinfo=timezone.utc),
                event_type="tool_result",
                text="Wrote file",
                files_touched=["src/auth.py", "src/models.py"],
            ),
            _make_event(
                event_id="ctx-2",
                ts=datetime(2026, 1, 15, 9, 59, 0, tzinfo=timezone.utc),
                event_type="tool_result",
                text="Wrote file",
                files_touched=["src/auth.py", "tests/test_auth.py"],
            ),
        ]

        result = populator.populate(segment, [start_event], context_events)
        changed_files = result["observation"]["repo_state"]["changed_files"]
        # Should be deduplicated and sorted
        assert "src/auth.py" in changed_files
        assert "src/models.py" in changed_files
        assert "tests/test_auth.py" in changed_files
        assert len(changed_files) == 3
        # diff_stat.files should match
        assert result["observation"]["repo_state"]["diff_stat"]["files"] == 3


class TestActionDerivation:
    """Tests for action derivation from start trigger event."""

    def test_implement_keyword(self):
        """Start event with 'implement' keyword -> mode = 'Implement'."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Please implement the login feature for the app",
        )

        result = populator.populate(segment, [start_event], [])
        assert result["orchestrator_action"]["mode"] == "Implement"

    def test_debug_keyword_is_triage(self):
        """Start event with 'debug this' keyword -> mode = 'Triage'."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Can you debug this failing test?",
        )

        result = populator.populate(segment, [start_event], [])
        assert result["orchestrator_action"]["mode"] == "Triage"

    def test_file_paths_extracted(self):
        """Start event with file paths in text -> scope.paths extracted."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement changes in src/pipeline/populator.py and tests/test_populator.py",
        )

        result = populator.populate(segment, [start_event], [])
        paths = result["orchestrator_action"]["scope"]["paths"]
        assert "src/pipeline/populator.py" in paths
        assert "tests/test_populator.py" in paths

    def test_goal_truncated_to_500(self):
        """Goal is truncated to 500 chars."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        long_text = "implement " + "x" * 600
        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text=long_text,
        )

        result = populator.populate(segment, [start_event], [])
        assert len(result["orchestrator_action"]["goal"]) <= 500

    def test_gate_extraction(self):
        """Start event with gate pattern -> gates list populated."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement the feature but run tests first and get approval before merging",
        )

        result = populator.populate(segment, [start_event], [])
        gate_types = [g["type"] for g in result["orchestrator_action"]["gates"]]
        assert "run_tests" in gate_types

    def test_mode_priority_ordering(self):
        """When multiple modes match, lowest priority number wins."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        # "investigate" -> Explore (priority 1), "implement" -> Implement (priority 3)
        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Investigate and implement the solution",
        )

        result = populator.populate(segment, [start_event], [])
        # Explore has priority 1, Implement has priority 3 -> Explore wins
        assert result["orchestrator_action"]["mode"] == "Explore"

    def test_no_keyword_defaults_to_implement(self):
        """When no mode keyword matches, default to 'Implement'."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Do the thing with the stuff",
        )

        result = populator.populate(segment, [start_event], [])
        assert result["orchestrator_action"]["mode"] == "Implement"


class TestOutcomeDerivation:
    """Tests for outcome derivation from body events."""

    def test_tool_calls_counted(self):
        """Body events with tool_use -> outcome.executor_effects.tool_calls_count > 0."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement something",
        )
        body_events = [
            _make_event(event_id="evt-body1", event_type="tool_use", text="Write file"),
            _make_event(event_id="evt-body2", event_type="tool_result", text="Success"),
        ]

        result = populator.populate(segment, [start_event] + body_events, [])
        assert result["outcome"]["executor_effects"]["tool_calls_count"] == 2

    def test_git_events_populated(self):
        """Body events with T_GIT_COMMIT -> outcome.executor_effects.git_events populated."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement the feature",
        )
        body_events = [
            _make_event(
                event_id="evt-body1",
                event_type="tool_result",
                text="Committed",
                primary_tag="T_GIT_COMMIT",
                links={"commit_hash": "abc123def"},
            ),
        ]

        result = populator.populate(segment, [start_event] + body_events, [])
        git_events = result["outcome"]["executor_effects"]["git_events"]
        assert len(git_events) >= 1
        assert git_events[0]["type"] == "commit"
        assert git_events[0]["ref"] == "abc123def"

    def test_files_touched_accumulated(self):
        """Body events with files_touched -> outcome.executor_effects.files_touched."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement something",
        )
        body_events = [
            _make_event(
                event_id="evt-body1",
                event_type="tool_use",
                text="Write file",
                files_touched=["src/a.py"],
            ),
            _make_event(
                event_id="evt-body2",
                event_type="tool_result",
                text="OK",
                files_touched=["src/a.py", "src/b.py"],
            ),
        ]

        result = populator.populate(segment, [start_event] + body_events, [])
        files = result["outcome"]["executor_effects"]["files_touched"]
        assert "src/a.py" in files
        assert "src/b.py" in files

    def test_test_status_from_body_events(self):
        """Segment with outcome 'success' and T_TEST -> tests_status = 'pass'."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment(outcome="success")

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement something",
        )
        body_events = [
            _make_event(
                event_id="evt-body1",
                event_type="tool_result",
                text="All tests passed",
                primary_tag="T_TEST",
            ),
        ]

        result = populator.populate(segment, [start_event] + body_events, [])
        assert result["outcome"]["quality"]["tests_status"] == "pass"

    def test_commands_capped_at_20(self):
        """Commands are capped at 20."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement something",
        )
        body_events = [
            _make_event(
                event_id=f"evt-body{i}",
                event_type="tool_use",
                text=f"command_{i}",
            )
            for i in range(30)
        ]

        result = populator.populate(segment, [start_event] + body_events, [])
        assert len(result["outcome"]["executor_effects"]["commands_ran"]) <= 20

    def test_reward_signals_computed(self):
        """Reward signals are computed from quality and diff."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment(outcome="success")

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement something",
        )
        body_events = [
            _make_event(
                event_id="evt-body1",
                event_type="tool_result",
                text="Tests passed",
                primary_tag="T_TEST",
                files_touched=["a.py", "b.py", "c.py"],
            ),
        ]

        result = populator.populate(segment, [start_event] + body_events, [])
        rewards = result["outcome"]["reward_signals"]["objective"]
        assert rewards["tests"] == 1.0  # pass -> 1.0
        assert rewards["lint"] == 0.5  # unknown -> 0.5
        assert rewards["diff_risk"] == pytest.approx(0.3, abs=0.1)  # 3 files * 0.1


class TestProvenance:
    """Tests for provenance building."""

    def test_provenance_deduplicates(self):
        """Multiple events with same source_ref -> provenance deduplicates."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        events = [
            _make_event(
                event_id="evt-start",
                actor="human_orchestrator",
                event_type="user_msg",
                text="Implement something",
                source_ref="sess-001:uuid-001",
            ),
            _make_event(
                event_id="evt-body1",
                event_type="tool_use",
                text="Write file",
                source_ref="sess-001:uuid-001",
            ),
            _make_event(
                event_id="evt-body2",
                event_type="tool_result",
                text="OK",
                source_ref="sess-001:uuid-002",
            ),
        ]

        result = populator.populate(segment, events, [])
        sources = result["provenance"]["sources"]
        refs = [s["ref"] for s in sources]
        # Should be deduplicated
        assert len(refs) == len(set(refs))

    def test_provenance_includes_git_refs(self):
        """Git commit hashes from links are included in provenance."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        events = [
            _make_event(
                event_id="evt-start",
                actor="human_orchestrator",
                event_type="user_msg",
                text="Implement something",
                source_ref="sess-001:uuid-001",
            ),
            _make_event(
                event_id="evt-body1",
                event_type="tool_result",
                text="Committed",
                primary_tag="T_GIT_COMMIT",
                links={"commit_hash": "deadbeef1234"},
                source_ref="sess-001:uuid-002",
            ),
        ]

        result = populator.populate(segment, events, [])
        sources = result["provenance"]["sources"]
        source_types = [s["type"] for s in sources]
        assert "git" in source_types
        git_refs = [s["ref"] for s in sources if s["type"] == "git"]
        assert "deadbeef1234" in git_refs


class TestEpisodeId:
    """Tests for deterministic episode ID generation."""

    def test_deterministic_id(self):
        """Episode ID is deterministic based on session_id + segment_id + config_hash."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment(
            session_id="sess-001", segment_id="seg-001", config_hash="abc123"
        )

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Do something",
        )

        result1 = populator.populate(segment, [start_event], [])
        result2 = populator.populate(segment, [start_event], [])
        assert result1["episode_id"] == result2["episode_id"]

        # Verify it's a 16-char hex string
        assert len(result1["episode_id"]) == 16
        assert all(c in "0123456789abcdef" for c in result1["episode_id"])


class TestSchemaValidation:
    """Tests that populated episodes pass EpisodeValidator."""

    def test_populated_episode_passes_validation(self):
        """Populated episode from test fixtures passes EpisodeValidator."""
        config = _make_config()
        populator = EpisodePopulator(config)
        validator = EpisodeValidator()

        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement the login feature in src/auth.py",
        )
        body_events = [
            _make_event(
                event_id="evt-body1",
                event_type="tool_use",
                text="Writing to src/auth.py",
                files_touched=["src/auth.py"],
            ),
            _make_event(
                event_id="evt-body2",
                event_type="tool_result",
                text="File written successfully",
                files_touched=["src/auth.py"],
            ),
        ]

        context_events = [
            _make_event(
                event_id="ctx-1",
                ts=datetime(2026, 1, 15, 9, 59, 0, tzinfo=timezone.utc),
                event_type="tool_result",
                text="All tests passed",
                primary_tag="T_TEST",
            ),
        ]

        result = populator.populate(
            segment, [start_event] + body_events, context_events
        )

        is_valid, errors = validator.validate(result)
        assert is_valid, f"Episode failed validation: {errors}"

    def test_minimal_episode_passes_validation(self):
        """Even a minimal episode (no context, no body events) passes validation."""
        config = _make_config()
        populator = EpisodePopulator(config)
        validator = EpisodeValidator()

        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Do something",
        )

        result = populator.populate(segment, [start_event], [])

        is_valid, errors = validator.validate(result)
        assert is_valid, f"Minimal episode failed validation: {errors}"


class TestRiskComputation:
    """Tests for risk computation from mode and scope."""

    def test_explore_is_low_risk(self):
        """Explore mode -> low risk."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Investigate the codebase structure",
        )

        result = populator.populate(segment, [start_event], [])
        assert result["orchestrator_action"]["risk"] == "low"

    def test_implement_protected_path_is_high(self):
        """Implement mode with protected path in scope -> high risk."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text="Implement changes to auth/login.py and db/migrations/0001.sql",
        )

        result = populator.populate(segment, [start_event], [])
        assert result["orchestrator_action"]["risk"] in ("high", "critical")


class TestAllModes:
    """Tests that all 7 modes can be inferred correctly."""

    @pytest.mark.parametrize(
        "text,expected_mode",
        [
            ("Investigate the error logs", "Explore"),
            ("Plan the refactoring approach and propose options", "Plan"),
            ("Implement the new login feature", "Implement"),
            ("Run tests to verify the fix", "Verify"),
            ("Commit and push the changes to PR", "Integrate"),
            ("Debug the failing test case", "Triage"),
            ("Refactor the auth module for clarity", "Refactor"),
        ],
    )
    def test_mode_inference(self, text: str, expected_mode: str):
        """All 7 modes are correctly inferred from keywords."""
        config = _make_config()
        populator = EpisodePopulator(config)
        segment = _make_segment()

        start_event = _make_event(
            event_id="evt-start",
            actor="human_orchestrator",
            event_type="user_msg",
            text=text,
        )

        result = populator.populate(segment, [start_event], [])
        assert result["orchestrator_action"]["mode"] == expected_mode
