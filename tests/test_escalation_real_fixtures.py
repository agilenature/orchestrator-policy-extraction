"""Tests for EscalationDetector using real session fixtures from data/ope.db.

Loads JSONL fixture files extracted from the objectivism project's DuckDB
database and verifies the EscalationDetector produces correct results on
real event patterns (not just synthetic ones).

Fixtures:
    tests/fixtures/escalation/session_01695e90_ocorr_trisky.jsonl
    tests/fixtures/escalation/session_0326bf5e_ocorr_trisky.jsonl
    tests/fixtures/escalation/session_1cf6d12f_ocorr_tgitcommit.jsonl
    tests/fixtures/escalation/session_1cf6d12f_ocorr_trisky.jsonl
    tests/fixtures/escalation/session_0e3cf9a0_window_expired.jsonl
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.pipeline.escalation.detector import EscalationDetector
from src.pipeline.models.config import EscalationConfig, PipelineConfig
from src.pipeline.models.events import CanonicalEvent, Classification, TaggedEvent

FIXTURE_DIR = Path("tests/fixtures/escalation")


def load_fixture(filename: str) -> list[TaggedEvent]:
    """Load a JSONL fixture file and construct TaggedEvent objects.

    Reads tests/fixtures/escalation/{filename}, skipping comment lines
    (starting with '#'). Parses each JSON line into a CanonicalEvent
    wrapped in a TaggedEvent.

    Args:
        filename: Name of the JSONL file in the fixture directory.

    Returns:
        List of TaggedEvent objects in timestamp order.
    """
    filepath = FIXTURE_DIR / filename
    tagged_events: list[TaggedEvent] = []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            d = json.loads(line)
            ts = datetime.fromisoformat(d["ts_utc"])

            event = CanonicalEvent(
                event_id=d["event_id"],
                ts_utc=ts,
                session_id=d["session_id"],
                actor=d["actor"],
                event_type=d["event_type"],
                payload=d["payload"],
                links=d["links"],
                source_system=d["source_system"],
                source_ref=d["source_ref"],
                risk_score=d["risk_score"],
                risk_factors=d["risk_factors"],
            )

            primary = None
            if d["primary_tag"]:
                primary = Classification(
                    label=d["primary_tag"],
                    confidence=d["primary_tag_confidence"],
                    source="direct",
                )

            tagged = TaggedEvent(event=event, primary=primary)
            tagged_events.append(tagged)

    return tagged_events


# =============================================================================
# POSITIVE TESTS: Real session escalation detections
# =============================================================================


class TestSession01695e90:
    """Session 01695e90: O_CORR -> T_RISKY via 4 Read calls (exempt).

    6 non-exempt events between O_CORR and T_RISKY (assistant_text,
    tool_results from exempt Read calls, another assistant_text, then
    T_RISKY tool_result). Requires window_turns >= 6.
    """

    def test_default_window_no_detection(self):
        """Default window_turns=5 is too small for 6 non-exempt events."""
        events = load_fixture("session_01695e90_ocorr_trisky.jsonl")
        config = PipelineConfig()
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) == 0

    def test_window_10_detects_escalation(self):
        """window_turns=10 detects the O_CORR -> T_RISKY escalation."""
        events = load_fixture("session_01695e90_ocorr_trisky.jsonl")
        config = PipelineConfig(escalation=EscalationConfig(window_turns=10))
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.block_event_tag == "O_CORR"
        assert c.block_event_id == "cd8a4ddb45e9ec7e"
        assert c.session_id.startswith("01695e90")
        assert c.window_turns_used == 6


class TestSession0326bf5e:
    """Session 0326bf5e: O_CORR -> T_RISKY with exactly 5 non-exempt events.

    Intervening events are Read calls (exempt) plus assistant_text and
    tool_results (non-exempt). T_RISKY tool_result is the 5th non-exempt
    event, fitting exactly within default window_turns=5.
    """

    def test_default_window_detects_escalation(self):
        """Default window_turns=5 detects this escalation (exactly 5 non-exempt)."""
        events = load_fixture("session_0326bf5e_ocorr_trisky.jsonl")
        config = PipelineConfig()
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.block_event_tag == "O_CORR"
        assert c.block_event_id.startswith("f25edf2c")
        assert c.window_turns_used == 5


class TestSession1cf6d12fTgitcommit:
    """Session 1cf6d12f: O_CORR -> Edit (bypass) -> T_GIT_COMMIT.

    The detector catches Edit first (bypass-eligible tool at non-exempt turn 6)
    before reaching T_GIT_COMMIT. Requires window_turns >= 6.
    """

    def test_default_window_no_detection(self):
        """Default window_turns=5 is too small for 6 non-exempt events to Edit."""
        events = load_fixture("session_1cf6d12f_ocorr_tgitcommit.jsonl")
        config = PipelineConfig()
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) == 0

    def test_window_10_detects_edit_bypass(self):
        """window_turns=10 detects escalation. Bypass is Edit (tool-name layer)."""
        events = load_fixture("session_1cf6d12f_ocorr_tgitcommit.jsonl")
        config = PipelineConfig(escalation=EscalationConfig(window_turns=10))
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.block_event_tag == "O_CORR"
        assert c.block_event_id.startswith("840d0c5a")
        # Detector catches Edit first (bypass-eligible tool), not T_GIT_COMMIT
        assert c.bypass_tool_name == "Edit"
        assert c.window_turns_used == 6


class TestSession1cf6d12fTrisky:
    """Session 1cf6d12f: O_CORR -> T_RISKY with 18+ non-exempt events.

    Many intervening Bash, TaskOutput, TaskStop calls (all non-exempt).
    The first Bash call is a bypass-eligible tool at non-exempt turn 6.
    With window_turns=5 it cannot be detected; with window_turns=20 the
    first Bash is caught at turn 6.
    """

    def test_default_window_no_detection(self):
        """Default window_turns=5 is too small for any bypass within window."""
        events = load_fixture("session_1cf6d12f_ocorr_trisky.jsonl")
        config = PipelineConfig()
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) == 0

    def test_window_20_detects_first_bash_bypass(self):
        """window_turns=20 detects escalation. First Bash is bypass at turn 6."""
        events = load_fixture("session_1cf6d12f_ocorr_trisky.jsonl")
        config = PipelineConfig(escalation=EscalationConfig(window_turns=20))
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.block_event_tag == "O_CORR"
        assert c.block_event_id.startswith("9f8886ac")
        assert c.bypass_tool_name == "Bash"
        assert c.window_turns_used == 6


# =============================================================================
# NEGATIVE TEST: Window expired before bypass
# =============================================================================


class TestSession0e3cf9a0WindowExpired:
    """Session 0e3cf9a0: O_CORR -> T_RISKY with ~14 non-exempt events.

    Negative case: with default window_turns=5, the window expires long
    before any bypass-eligible event. With window_turns=20, a Bash call
    at non-exempt turn 7 triggers detection.
    """

    def test_default_window_no_detection(self):
        """Default window_turns=5 produces 0 candidates (window expired)."""
        events = load_fixture("session_0e3cf9a0_window_expired.jsonl")
        config = PipelineConfig()
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) == 0

    def test_large_window_detects_escalation(self):
        """window_turns=20 detects escalation (Bash bypass at turn 7)."""
        events = load_fixture("session_0e3cf9a0_window_expired.jsonl")
        config = PipelineConfig(escalation=EscalationConfig(window_turns=20))
        detector = EscalationDetector(config)
        candidates = detector.detect(events)
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.block_event_tag == "O_CORR"
        assert c.bypass_tool_name == "Bash"


# =============================================================================
# PARAMETRIZED SUMMARY: All positive fixtures detected with sufficient window
# =============================================================================


@pytest.mark.parametrize(
    "filename,window_turns,expected_block_prefix",
    [
        ("session_01695e90_ocorr_trisky.jsonl", 10, "cd8a4ddb"),
        ("session_0326bf5e_ocorr_trisky.jsonl", 5, "f25edf2c"),
        ("session_1cf6d12f_ocorr_tgitcommit.jsonl", 10, "840d0c5a"),
        ("session_1cf6d12f_ocorr_trisky.jsonl", 20, "9f8886ac"),
    ],
    ids=[
        "session_01695e90_trisky",
        "session_0326bf5e_trisky",
        "session_1cf6d12f_tgitcommit",
        "session_1cf6d12f_trisky",
    ],
)
def test_all_positive_fixtures_detected(
    filename: str,
    window_turns: int,
    expected_block_prefix: str,
) -> None:
    """Each positive fixture produces at least 1 EscalationCandidate with sufficient window."""
    events = load_fixture(filename)
    config = PipelineConfig(escalation=EscalationConfig(window_turns=window_turns))
    detector = EscalationDetector(config)
    candidates = detector.detect(events)
    assert len(candidates) >= 1, f"Expected detection in {filename} with window_turns={window_turns}"
    assert candidates[0].block_event_id.startswith(expected_block_prefix)
