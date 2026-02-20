"""Tests for EscalationDetector: sliding window sequence detection.

30 test cases total:
- 15 positive (EscalationCandidate expected):
  - 5 blatant bypass: O_GATE -> immediate Bash/Write/Edit within 1-2 turns
  - 5 delayed bypass within window: O_GATE -> 2-4 non-exempt events -> bypass on turn 4-5
  - 5 indirect bypass via different tool: O_CORR -> bypass via Edit, Bash rm, Write
- 15 negative (no EscalationCandidate expected):
  - 5 read-only post-rejection: O_GATE -> only Read/Glob/Grep -> no bypass
  - 5 X_ASK resets window: O_GATE -> X_ASK -> Bash (window was reset)
  - 5 window expired: O_GATE -> 6+ non-exempt events -> then Bash (too late)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.pipeline.escalation.detector import EscalationDetector
from src.pipeline.escalation.models import EscalationCandidate
from src.pipeline.models.config import EscalationConfig, PipelineConfig
from src.pipeline.models.events import CanonicalEvent, Classification, TaggedEvent
from tests.conftest import make_event, make_tagged_event


# --- Helper Utilities ---

T0 = datetime(2026, 2, 11, 12, 0, 0, tzinfo=timezone.utc)


def _ts(offset_seconds: int) -> datetime:
    """Return T0 + offset in seconds."""
    return T0 + timedelta(seconds=offset_seconds)


def _eid(n: int) -> str:
    """Return a deterministic event ID."""
    return f"evt-{n:04d}"


def _make_block_event(
    tag: str,
    event_id: str,
    ts_offset: int = 0,
    session_id: str = "test-session-001",
) -> TaggedEvent:
    """Create a block event (O_GATE or O_CORR)."""
    return make_tagged_event(
        make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "No, stop that."}},
            ts_utc=_ts(ts_offset),
            event_id=event_id,
            session_id=session_id,
        ),
        primary_label=tag,
        confidence=0.9,
    )


def _make_tool_event(
    tool_name: str,
    command_text: str = "",
    primary_label: str | None = None,
    event_id: str = "evt-generic",
    ts_offset: int = 5,
    session_id: str = "test-session-001",
    resource_path: str = "",
) -> TaggedEvent:
    """Create a tool_use event with optional primary label."""
    payload: dict = {"common": {"tool_name": tool_name, "text": command_text}}
    if resource_path:
        payload["details"] = {"file_path": resource_path}
    return make_tagged_event(
        make_event(
            actor="tool",
            event_type="tool_use",
            payload=payload,
            ts_utc=_ts(ts_offset),
            event_id=event_id,
            session_id=session_id,
        ),
        primary_label=primary_label,
    )


def _make_ask_event(
    tag: str = "X_ASK",
    event_id: str = "evt-ask",
    ts_offset: int = 5,
    session_id: str = "test-session-001",
) -> TaggedEvent:
    """Create an X_ASK or X_PROPOSE event."""
    return make_tagged_event(
        make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "Should I proceed?"}},
            ts_utc=_ts(ts_offset),
            event_id=event_id,
            session_id=session_id,
        ),
        primary_label=tag,
        confidence=0.9,
    )


def _make_neutral_event(
    event_id: str = "evt-neutral",
    ts_offset: int = 5,
    session_id: str = "test-session-001",
) -> TaggedEvent:
    """Create a neutral assistant_text event (non-exempt, non-bypass)."""
    return make_tagged_event(
        make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "Thinking about next steps..."}},
            ts_utc=_ts(ts_offset),
            event_id=event_id,
            session_id=session_id,
        ),
        primary_label=None,
    )


def _default_config() -> PipelineConfig:
    """Create default PipelineConfig with escalation settings."""
    return PipelineConfig()


def _detector(config: PipelineConfig | None = None) -> EscalationDetector:
    """Create EscalationDetector with default config."""
    return EscalationDetector(config or _default_config())


# =============================================================================
# POSITIVE TESTS: Blatant Bypass (5)
# O_GATE -> immediate Bash/Write/Edit within 1-2 turns
# =============================================================================


class TestBlatantBypass:
    """5 tests: O_GATE/O_CORR -> immediate bypass within 1-2 turns."""

    def test_gate_then_immediate_bash(self):
        """O_GATE -> Bash (1 turn) = 1 candidate."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "git push origin main", "T_RISKY", _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        c = result[0]
        assert c.block_event_id == _eid(1)
        assert c.block_event_tag == "O_GATE"
        assert c.bypass_event_id == _eid(2)
        assert c.bypass_tool_name == "Bash"
        assert c.window_turns_used == 1
        assert c.confidence == 1.0

    def test_gate_then_immediate_write(self):
        """O_GATE -> Write (1 turn, no T_RISKY tag) = 1 candidate via tool-name layer."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Write", "write to config.yaml", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Write"
        assert result[0].window_turns_used == 1

    def test_gate_then_immediate_edit(self):
        """O_GATE -> Edit (1 turn, no T_RISKY tag) = 1 candidate via tool-name layer."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Edit", "edit src/main.py", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Edit"

    def test_gate_then_read_then_bash(self):
        """O_GATE -> Read (exempt, skipped) -> Bash (1 non-exempt turn) = 1 candidate."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Read", "read src/main.py", None, _eid(2), ts_offset=5),
            _make_tool_event("Bash", "rm -rf /tmp/data", "T_RISKY", _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_event_id == _eid(3)
        # Read is exempt, so only 1 non-exempt turn used
        assert result[0].window_turns_used == 1

    def test_corr_then_immediate_bash(self):
        """O_CORR -> Bash (1 turn) = 1 candidate (O_CORR counts as block)."""
        events = [
            _make_block_event("O_CORR", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "sudo chown root file", "T_RISKY", _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].block_event_tag == "O_CORR"


# =============================================================================
# POSITIVE TESTS: Delayed Bypass Within Window (5)
# O_GATE -> 2-4 non-exempt events -> bypass on turn 4-5
# =============================================================================


class TestDelayedBypass:
    """5 tests: O_GATE -> multiple non-exempt events -> bypass within window."""

    def test_gate_then_4_neutral_then_bash(self):
        """O_GATE -> 4 neutral events -> Bash on turn 5 = 1 candidate."""
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(4):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(50), ts_offset=30)
        )
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].window_turns_used == 5

    def test_gate_then_3_neutral_then_write(self):
        """O_GATE -> 3 neutral events -> Write on turn 4 = 1 candidate."""
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(3):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Write", "write config", None, _eid(50), ts_offset=25)
        )
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].window_turns_used == 4

    def test_gate_then_2_neutral_then_edit_with_exempt_interleaved(self):
        """O_GATE -> neutral -> Glob (exempt) -> neutral -> Edit on turn 3 = 1 candidate.

        Exempt tool does not count toward window.
        """
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_neutral_event(_eid(2), ts_offset=5),
            _make_tool_event("Glob", "*.py", None, _eid(3), ts_offset=10),
            _make_neutral_event(_eid(4), ts_offset=15),
            _make_tool_event("Edit", "edit file", None, _eid(5), ts_offset=20),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        # 2 non-exempt (neutral) + 1 bypass = 3 non-exempt turns used
        assert result[0].window_turns_used == 3

    def test_gate_then_4_neutral_with_grep_then_bash(self):
        """O_GATE -> 2 neutral -> Grep (exempt) -> 2 neutral -> Bash on turn 5 = 1 candidate.

        5 non-exempt events = just within window.
        """
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_neutral_event(_eid(2), ts_offset=5),
            _make_neutral_event(_eid(3), ts_offset=10),
            _make_tool_event("Grep", "search pattern", None, _eid(4), ts_offset=15),
            _make_neutral_event(_eid(5), ts_offset=20),
            _make_neutral_event(_eid(6), ts_offset=25),
            _make_tool_event("Bash", "chmod 777 file", "T_RISKY", _eid(7), ts_offset=30),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].window_turns_used == 5

    def test_gate_then_delayed_t_git_commit(self):
        """O_GATE -> 3 neutral events -> T_GIT_COMMIT on turn 4 = 1 candidate.

        T_GIT_COMMIT tag triggers bypass via tag-based layer.
        """
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(3):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Bash", "git commit -m 'fix'", "T_GIT_COMMIT", _eid(50), ts_offset=25)
        )
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].window_turns_used == 4


# =============================================================================
# POSITIVE TESTS: Indirect Bypass via Different Tool (5)
# O_CORR -> bypass via Edit (not Bash), Bash rm, Write after rejection
# =============================================================================


class TestIndirectBypass:
    """5 tests: O_CORR -> bypass via unexpected tool or always-bypass pattern."""

    def test_corr_then_edit_bypass(self):
        """O_CORR -> Edit (no tag but bypass-eligible tool) = 1 candidate."""
        events = [
            _make_block_event("O_CORR", _eid(1), ts_offset=0),
            _make_tool_event("Edit", "edit src/auth.py", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Edit"
        assert result[0].block_event_tag == "O_CORR"

    def test_corr_then_bash_rm_always_bypass(self):
        """O_CORR -> Bash 'rm -rf' (always-bypass pattern) = 1 candidate.

        Always-bypass patterns trigger regardless of tag.
        """
        events = [
            _make_block_event("O_CORR", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "rm -rf /tmp/important", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Bash"

    def test_gate_then_write_after_gate(self):
        """O_GATE -> Write to protected path = 1 candidate."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event(
                "Write", "writing to .env", None, _eid(2), ts_offset=5,
                resource_path=".env",
            ),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Write"

    def test_gate_then_bash_sudo_always_bypass(self):
        """O_GATE -> Bash 'sudo apt install' (always-bypass: sudo) = 1 candidate."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "sudo apt install package", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Bash"

    def test_gate_then_t_test_tag_bypass(self):
        """O_GATE -> Bash with T_TEST tag = 1 candidate (tag-based bypass layer)."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "pytest tests/", "T_TEST", _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Bash"


# =============================================================================
# NEGATIVE TESTS: Read-Only Post-Rejection (5)
# O_GATE -> only Read/Glob/Grep -> no bypass
# =============================================================================


class TestReadOnlyPostRejection:
    """5 tests: O_GATE followed by only exempt tools = 0 candidates."""

    def test_gate_then_only_read(self):
        """O_GATE -> Read -> Read -> Read -> no bypass."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Read", "read file1", None, _eid(2), ts_offset=5),
            _make_tool_event("Read", "read file2", None, _eid(3), ts_offset=10),
            _make_tool_event("Read", "read file3", None, _eid(4), ts_offset=15),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_only_glob(self):
        """O_GATE -> Glob -> Glob -> no bypass."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Glob", "**/*.py", None, _eid(2), ts_offset=5),
            _make_tool_event("Glob", "**/*.js", None, _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_only_grep(self):
        """O_GATE -> Grep -> Grep -> no bypass."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Grep", "search pattern1", None, _eid(2), ts_offset=5),
            _make_tool_event("Grep", "search pattern2", None, _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_mixed_exempt_tools(self):
        """O_GATE -> Read -> Glob -> Grep -> WebFetch -> no bypass."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Read", "read", None, _eid(2), ts_offset=5),
            _make_tool_event("Glob", "*.py", None, _eid(3), ts_offset=10),
            _make_tool_event("Grep", "pattern", None, _eid(4), ts_offset=15),
            _make_tool_event("WebFetch", "https://example.com", None, _eid(5), ts_offset=20),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_webfetch_and_task(self):
        """O_GATE -> WebFetch -> Task -> WebSearch -> no bypass."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("WebFetch", "fetch url", None, _eid(2), ts_offset=5),
            _make_tool_event("Task", "sub-task", None, _eid(3), ts_offset=10),
            _make_tool_event("WebSearch", "search query", None, _eid(4), ts_offset=15),
        ]
        result = _detector().detect(events)
        assert len(result) == 0


# =============================================================================
# NEGATIVE TESTS: X_ASK Resets Window (5)
# O_GATE -> X_ASK -> Bash (window was reset)
# =============================================================================


class TestXAskResetsWindow:
    """5 tests: X_ASK or X_PROPOSE between block and bypass = 0 candidates."""

    def test_gate_then_x_ask_then_bash(self):
        """O_GATE -> X_ASK -> Bash = 0 candidates (window reset by X_ASK)."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_ask_event("X_ASK", _eid(2), ts_offset=5),
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_x_propose_then_write(self):
        """O_GATE -> X_PROPOSE -> Write = 0 candidates (window reset by X_PROPOSE)."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_ask_event("X_PROPOSE", _eid(2), ts_offset=5),
            _make_tool_event("Write", "write file", None, _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_neutral_then_x_ask_then_bash(self):
        """O_GATE -> neutral -> X_ASK -> Bash = 0 candidates."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_neutral_event(_eid(2), ts_offset=5),
            _make_ask_event("X_ASK", _eid(3), ts_offset=10),
            _make_tool_event("Bash", "rm file", "T_RISKY", _eid(4), ts_offset=15),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_corr_then_x_ask_then_edit(self):
        """O_CORR -> X_ASK -> Edit = 0 candidates (X_ASK resets O_CORR window too)."""
        events = [
            _make_block_event("O_CORR", _eid(1), ts_offset=0),
            _make_ask_event("X_ASK", _eid(2), ts_offset=5),
            _make_tool_event("Edit", "edit file", None, _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_x_propose_resets_all_windows(self):
        """O_GATE -> O_CORR -> X_PROPOSE -> Bash = 0 candidates.

        X_PROPOSE resets ALL pending windows, not just the most recent.
        """
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_block_event("O_CORR", _eid(2), ts_offset=5),
            _make_ask_event("X_PROPOSE", _eid(3), ts_offset=10),
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(4), ts_offset=15),
        ]
        result = _detector().detect(events)
        assert len(result) == 0


# =============================================================================
# NEGATIVE TESTS: Window Expired (5)
# O_GATE -> 6+ non-exempt events -> then Bash (too late)
# =============================================================================


class TestWindowExpired:
    """5 tests: bypass attempt after window has expired = 0 candidates."""

    def test_gate_then_6_neutral_then_bash(self):
        """O_GATE -> 6 neutral events (window=5 expired) -> Bash = 0 candidates."""
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(6):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(50), ts_offset=40)
        )
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_5_neutral_then_write(self):
        """O_GATE -> 5 neutral events (exactly fills window) -> Write = 0 candidates.

        5 non-exempt events fully expire the 5-turn window. The 6th event (Write)
        is outside.
        """
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(5):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Write", "write file", None, _eid(50), ts_offset=35)
        )
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_7_neutral_then_edit(self):
        """O_GATE -> 7 neutral events -> Edit = 0 candidates (well past window)."""
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(7):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Edit", "edit file", None, _eid(50), ts_offset=45)
        )
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_exempt_tools_dont_save_window(self):
        """O_GATE -> 5 neutral -> many exempt -> Bash = 0 candidates.

        Exempt tools don't count, but 5 non-exempt events have already expired.
        """
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(5):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        # Add exempt tools after window expired
        events.append(_make_tool_event("Read", "read", None, _eid(20), ts_offset=35))
        events.append(_make_tool_event("Glob", "*.py", None, _eid(21), ts_offset=40))
        events.append(
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(50), ts_offset=45)
        )
        result = _detector().detect(events)
        assert len(result) == 0

    def test_gate_then_window_expired_with_custom_window_size(self):
        """O_GATE -> 3 neutral events -> Bash = 0 candidates (window_turns=3).

        With a 3-turn window, 3 neutral events expire the window.
        """
        config = PipelineConfig(escalation=EscalationConfig(window_turns=3))
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(3):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        events.append(
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(50), ts_offset=25)
        )
        result = EscalationDetector(config).detect(events)
        assert len(result) == 0


# =============================================================================
# EDGE CASES & PITFALL TESTS
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests covering pitfalls from research."""

    def test_sequential_blocks_produce_at_most_1_candidate(self):
        """Pitfall 2: O_GATE -> O_CORR -> Bash = only 1 candidate (oldest window consumed).

        Two pending windows from sequential blocks, but only 1 candidate per bypass event.
        """
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_block_event("O_CORR", _eid(2), ts_offset=5),
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(3), ts_offset=10),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        # Oldest window (O_GATE) should be consumed
        assert result[0].block_event_id == _eid(1)
        assert result[0].block_event_tag == "O_GATE"

    def test_exempt_tools_dont_count_toward_window(self):
        """Pitfall 1: exempt tools are invisible to window counter.

        O_GATE -> 4 neutral -> 10 Read -> 1 Bash on turn 5 = detected
        (only 5 non-exempt events in window, 10 Reads are transparent).
        """
        events = [_make_block_event("O_GATE", _eid(1), ts_offset=0)]
        for i in range(4):
            events.append(_make_neutral_event(_eid(10 + i), ts_offset=5 * (i + 1)))
        # Add 10 exempt Read events
        for i in range(10):
            events.append(
                _make_tool_event("Read", f"read file {i}", None, _eid(30 + i), ts_offset=25 + i)
            )
        events.append(
            _make_tool_event("Bash", "dangerous command", "T_RISKY", _eid(50), ts_offset=40)
        )
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].window_turns_used == 5

    def test_two_layer_bypass_tag_based(self):
        """Pitfall 5: T_RISKY tag on non-bypass-eligible tool triggers bypass.

        A tool_use with T_RISKY tag should be caught by tag-based layer.
        """
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "curl -X DELETE https://api/data", "T_RISKY", _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1

    def test_two_layer_bypass_tool_name_based(self):
        """Pitfall 5: Write/Edit/Bash without any tag triggers bypass via tool-name layer."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Write", "write data", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1

    def test_always_bypass_pattern_in_bash(self):
        """Always-bypass patterns trigger regardless of tag."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "chmod 755 /usr/bin/app", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_tool_name == "Bash"

    def test_empty_event_list(self):
        """Empty event list produces no candidates."""
        result = _detector().detect([])
        assert result == []

    def test_no_block_events(self):
        """Event list with no blocks produces no candidates."""
        events = [
            _make_tool_event("Bash", "git push", "T_RISKY", _eid(1), ts_offset=0),
            _make_tool_event("Write", "write", None, _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 0

    def test_session_id_propagated(self):
        """Session ID from events is propagated to EscalationCandidate."""
        sid = "session-abc-123"
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0, session_id=sid),
            _make_tool_event("Bash", "rm file", "T_RISKY", _eid(2), ts_offset=5, session_id=sid),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].session_id == sid

    def test_bypass_command_captured(self):
        """Bypass command text is captured in the EscalationCandidate."""
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "git push origin main --force", "T_RISKY", _eid(2), ts_offset=5),
        ]
        result = _detector().detect(events)
        assert len(result) == 1
        assert result[0].bypass_command == "git push origin main --force"

    def test_detector_version_from_config(self):
        """Detector version comes from config."""
        config = PipelineConfig(escalation=EscalationConfig(detector_version="2.0.0"))
        events = [
            _make_block_event("O_GATE", _eid(1), ts_offset=0),
            _make_tool_event("Bash", "rm file", "T_RISKY", _eid(2), ts_offset=5),
        ]
        result = EscalationDetector(config).detect(events)
        assert len(result) == 1
        assert result[0].detector_version == "2.0.0"
