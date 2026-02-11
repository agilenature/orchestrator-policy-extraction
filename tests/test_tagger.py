"""TDD tests for the multi-pass event tagger (EXTRACT-02).

Tests all classification rules from locked decisions:
- ToolTagger: T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY detection from tool_use events
- ExecutorTagger: X_PROPOSE, X_ASK detection per Q5 operational definitions
- OrchestratorTagger: O_CORR keyword detection, contextual boosting, O_GATE, O_DIR
- Label resolution: confidence-based primary selection, precedence tiebreaking, min threshold
- Risk scoring: dual-layer detection, max threshold, weighted average scoring
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.pipeline.models.config import PipelineConfig, load_config
from src.pipeline.models.events import CanonicalEvent, Classification, TaggedEvent
from src.pipeline.tagger import (
    EventTagger,
    ExecutorTagger,
    OrchestratorTagger,
    ToolTagger,
    _resolve_labels,
)
from tests.conftest import make_event, make_tagged_event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> PipelineConfig:
    """Load config from data/config.yaml."""
    return load_config("data/config.yaml")


@pytest.fixture
def tool_tagger(config: PipelineConfig) -> ToolTagger:
    return ToolTagger(config)


@pytest.fixture
def executor_tagger(config: PipelineConfig) -> ExecutorTagger:
    return ExecutorTagger(config)


@pytest.fixture
def orchestrator_tagger(config: PipelineConfig) -> OrchestratorTagger:
    return OrchestratorTagger(config)


@pytest.fixture
def event_tagger(config: PipelineConfig) -> EventTagger:
    return EventTagger(config)


# ---------------------------------------------------------------------------
# TestToolTagger: Pass 1 - structured data, HIGH confidence
# ---------------------------------------------------------------------------


class TestToolTagger:
    """Tests for ToolTagger: T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY detection."""

    def test_pytest_is_t_test(self, tool_tagger: ToolTagger):
        """tool_use("Bash", {"command": "pytest tests/"}) -> T_TEST, confidence 0.95"""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "pytest tests/"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_TEST" in labels
        t_test = next(c for c in classifications if c.label == "T_TEST")
        assert t_test.confidence == pytest.approx(0.95)

    def test_npm_test_is_t_test(self, tool_tagger: ToolTagger):
        """Bash command 'npm test' matches test_commands."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "npm test"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_TEST" in labels

    def test_ruff_is_t_lint(self, tool_tagger: ToolTagger):
        """tool_use("Bash", {"command": "ruff check src/"}) -> T_LINT, confidence 0.95"""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "ruff check src/"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_LINT" in labels
        t_lint = next(c for c in classifications if c.label == "T_LINT")
        assert t_lint.confidence == pytest.approx(0.95)

    def test_eslint_is_t_lint(self, tool_tagger: ToolTagger):
        """Bash command 'eslint src/' matches lint_commands."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "eslint src/"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_LINT" in labels

    def test_git_commit_is_t_git_commit(self, tool_tagger: ToolTagger):
        """tool_use("Bash", {"command": "git commit -m 'fix'"}) -> T_GIT_COMMIT, confidence 0.95"""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "git commit -m 'fix'"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_GIT_COMMIT" in labels
        t_gc = next(c for c in classifications if c.label == "T_GIT_COMMIT")
        assert t_gc.confidence == pytest.approx(0.95)

    def test_rm_rf_is_t_risky(self, tool_tagger: ToolTagger):
        """tool_use("Bash", {"command": "rm -rf /tmp/data"}) -> T_RISKY, confidence >= 0.7"""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "rm -rf /tmp/data"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_RISKY" in labels
        t_risky = next(c for c in classifications if c.label == "T_RISKY")
        assert t_risky.confidence >= 0.7

    def test_protected_path_is_t_risky(self, tool_tagger: ToolTagger):
        """tool_use("Edit", {"file_path": "db/migrations/001.py"}) -> T_RISKY (protected path)"""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={
                "common": {"tool_name": "Edit", "text": "db/migrations/001.py"},
                "details": {"file_path": "db/migrations/001.py"},
            },
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_RISKY" in labels

    def test_env_file_is_t_risky(self, tool_tagger: ToolTagger):
        """Editing .env file triggers protected path detection."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={
                "common": {"tool_name": "Edit", "text": ".env"},
                "details": {"file_path": ".env"},
            },
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_RISKY" in labels

    def test_tool_result_inherits_from_tool_use(self, event_tagger: EventTagger):
        """tool_result inherits tag from its linked tool_use via tool_use_id."""
        ts = datetime(2026, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
        tool_use_event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "pytest tests/"}},
            links={"tool_use_id": "toolu_abc123"},
            ts_utc=ts,
            event_id="ev-tool-use-1",
        )
        tool_result_event = make_event(
            actor="tool",
            event_type="tool_result",
            payload={"common": {"text": "3 passed"}},
            links={"tool_use_id": "toolu_abc123"},
            ts_utc=ts + timedelta(seconds=1),
            event_id="ev-tool-result-1",
        )
        tagged = event_tagger.tag([tool_use_event, tool_result_event])
        assert tagged[0].primary is not None
        assert tagged[0].primary.label == "T_TEST"
        # tool_result should inherit T_TEST from linked tool_use
        assert tagged[1].primary is not None
        assert tagged[1].primary.label == "T_TEST"

    def test_safe_command_no_tag(self, tool_tagger: ToolTagger):
        """A safe Bash command like 'ls -la' should not get T_TEST, T_LINT, T_GIT_COMMIT, or T_RISKY."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "ls -la"}},
        )
        classifications = tool_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "T_TEST" not in labels
        assert "T_LINT" not in labels
        assert "T_GIT_COMMIT" not in labels
        assert "T_RISKY" not in labels

    def test_non_tool_event_no_classifications(self, tool_tagger: ToolTagger):
        """ToolTagger should produce no classifications for non-tool events."""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "Hello world"}},
        )
        classifications = tool_tagger.classify(event)
        assert len(classifications) == 0


# ---------------------------------------------------------------------------
# TestExecutorTagger: Pass 2 - text patterns, MEDIUM confidence
# ---------------------------------------------------------------------------


class TestExecutorTagger:
    """Tests for ExecutorTagger: X_PROPOSE and X_ASK per Q5 operational definitions."""

    # --- X_PROPOSE canonical examples ---

    def test_propose_with_explicit_proposal(self, executor_tagger: ExecutorTagger):
        """'I propose we fix this by editing config.yaml...' -> X_PROPOSE"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {
                    "text": "I propose we fix this by editing config.yaml and adding a regression test."
                }
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_PROPOSE" in labels
        x_prop = next(c for c in classifications if c.label == "X_PROPOSE")
        assert 0.7 <= x_prop.confidence <= 0.9

    def test_propose_with_options_recommend(self, executor_tagger: ExecutorTagger):
        """'Options: (A)... I recommend A.' -> X_PROPOSE"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {
                    "text": "Options: (A) reuse existing adapter (recommended), (B) add new dependency, (C) rewrite module. I recommend A."
                }
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_PROPOSE" in labels

    def test_propose_with_mode_switch(self, executor_tagger: ExecutorTagger):
        """'Given the failing tests, I propose switching to Triage mode...' -> X_PROPOSE"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {
                    "text": "Given the failing tests, I propose switching to Triage mode and reproducing with pytest -k ...."
                }
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_PROPOSE" in labels

    # --- X_PROPOSE non-examples (should NOT be X_PROPOSE) ---

    def test_status_report_not_propose(self, executor_tagger: ExecutorTagger):
        """'I found 3 references in src/.' -> NOT X_PROPOSE (status only)"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "I found 3 references in src/."}},
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_PROPOSE" not in labels

    def test_routine_continuation_not_propose(self, executor_tagger: ExecutorTagger):
        """'Next I'll open file X.' -> NOT X_PROPOSE (routine continuation)"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "Next I'll open file X."}},
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_PROPOSE" not in labels

    def test_question_not_propose(self, executor_tagger: ExecutorTagger):
        """'Which framework should I use?' -> NOT X_PROPOSE (it's X_ASK)"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "Which framework should I use?"}},
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_PROPOSE" not in labels

    # --- X_ASK canonical examples ---

    def test_ask_react_or_vue(self, executor_tagger: ExecutorTagger):
        """'Should I use React or Vue?' -> X_ASK"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "Should I use React or Vue?"}},
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_ASK" in labels
        x_ask = next(c for c in classifications if c.label == "X_ASK")
        assert 0.7 <= x_ask.confidence <= 0.9

    def test_ask_backward_compatibility(self, executor_tagger: ExecutorTagger):
        """'Do you want backward compatibility with v1 clients?' -> X_ASK"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {
                    "text": "Do you want backward compatibility with v1 clients?"
                }
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_ASK" in labels

    def test_ask_permission_protected_path(self, executor_tagger: ExecutorTagger):
        """'This touches db/migrations/. May I proceed...' -> X_ASK"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {
                    "text": "This touches db/migrations/. May I proceed, or should we require approval?"
                }
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_ASK" in labels

    def test_ask_which_behavior(self, executor_tagger: ExecutorTagger):
        """'Which of these two behaviors is correct per spec?' -> X_ASK"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {
                    "text": "Which of these two behaviors is correct per spec?"
                }
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_ASK" in labels

    # --- X_ASK non-examples ---

    def test_here_are_results_not_ask(self, executor_tagger: ExecutorTagger):
        """'Here are the results from the scan.' -> NOT X_ASK (status)"""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {"text": "Here are the results from the scan."}
            },
        )
        classifications = executor_tagger.classify(event)
        labels = [c.label for c in classifications]
        assert "X_ASK" not in labels

    # --- Non-executor events should get no X_ tags ---

    def test_user_msg_no_executor_tags(self, executor_tagger: ExecutorTagger):
        """User messages should not get X_PROPOSE or X_ASK."""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "I propose we use React."}},
        )
        classifications = executor_tagger.classify(event)
        assert len(classifications) == 0


# ---------------------------------------------------------------------------
# TestOrchestratorTagger: Pass 3 - keywords, VARIABLE confidence
# ---------------------------------------------------------------------------


class TestOrchestratorTagger:
    """Tests for OrchestratorTagger: O_CORR, O_GATE, O_DIR detection."""

    # --- O_CORR keyword detection ---

    def test_no_dont_is_o_corr(self, orchestrator_tagger: OrchestratorTagger):
        """'No, don't do that.' -> O_CORR"""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "No, don't do that."}},
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        labels = [c.label for c in classifications]
        assert "O_CORR" in labels
        o_corr = next(c for c in classifications if c.label == "O_CORR")
        assert o_corr.confidence == pytest.approx(0.8)

    def test_wrong_approach_is_o_corr(self, orchestrator_tagger: OrchestratorTagger):
        """'Wrong approach, use the other method.' -> O_CORR"""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={
                "common": {"text": "Wrong approach, use the other method."}
            },
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        labels = [c.label for c in classifications]
        assert "O_CORR" in labels

    def test_stop_is_o_corr(self, orchestrator_tagger: OrchestratorTagger):
        """'Stop' as first word -> O_CORR"""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "Stop what you're doing."}},
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        labels = [c.label for c in classifications]
        assert "O_CORR" in labels

    # --- O_CORR contextual boosting ---

    def test_o_corr_boosted_after_t_test_failure(
        self, orchestrator_tagger: OrchestratorTagger
    ):
        """After T_TEST failure, 'Fix the failing test.' -> O_CORR with boosted confidence (0.9)"""
        # Create a context event that is a T_TEST failure
        preceding_event = make_event(
            actor="tool",
            event_type="tool_result",
            payload={"common": {"text": "FAILED tests/test_foo.py", "error_message": "1 failed"}},
            event_id="ev-preceding-test",
        )
        preceding_tagged = make_tagged_event(preceding_event, "T_TEST", 0.95)

        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "Fix the failing test."}},
        )
        classifications = orchestrator_tagger.classify(
            event, context=[preceding_tagged]
        )
        labels = [c.label for c in classifications]
        assert "O_CORR" in labels
        o_corr = next(c for c in classifications if c.label == "O_CORR")
        assert o_corr.confidence == pytest.approx(0.9)

    def test_o_corr_boosted_after_t_risky(
        self, orchestrator_tagger: OrchestratorTagger
    ):
        """After T_RISKY, user responds with correction -> O_CORR with boosted confidence."""
        preceding_event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "rm -rf /"}},
            event_id="ev-preceding-risky",
        )
        preceding_tagged = make_tagged_event(preceding_event, "T_RISKY", 0.9)

        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "No, stop that immediately."}},
        )
        classifications = orchestrator_tagger.classify(
            event, context=[preceding_tagged]
        )
        labels = [c.label for c in classifications]
        assert "O_CORR" in labels
        o_corr = next(c for c in classifications if c.label == "O_CORR")
        assert o_corr.confidence == pytest.approx(0.9)

    # --- O_GATE detection ---

    def test_run_tests_first_is_o_gate(self, orchestrator_tagger: OrchestratorTagger):
        """'Run tests before committing.' -> O_GATE"""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "Run tests before committing."}},
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        labels = [c.label for c in classifications]
        assert "O_GATE" in labels
        o_gate = next(c for c in classifications if c.label == "O_GATE")
        assert o_gate.confidence == pytest.approx(0.7)

    def test_ask_first_is_o_gate(self, orchestrator_tagger: OrchestratorTagger):
        """'Ask first before making any changes.' -> O_GATE (matches 'ask first' gate pattern)"""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={
                "common": {"text": "Ask first before making any changes."}
            },
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        labels = [c.label for c in classifications]
        assert "O_GATE" in labels

    # --- O_DIR detection ---

    def test_investigate_is_o_dir(self, orchestrator_tagger: OrchestratorTagger):
        """'Investigate the auth module.' -> O_DIR"""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "Investigate the auth module."}},
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        labels = [c.label for c in classifications]
        assert "O_DIR" in labels
        o_dir = next(c for c in classifications if c.label == "O_DIR")
        assert o_dir.confidence == pytest.approx(0.7)

    # --- Non-orchestrator events ---

    def test_executor_msg_no_orchestrator_tags(
        self, orchestrator_tagger: OrchestratorTagger
    ):
        """Executor messages should not get O_ tags."""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={"common": {"text": "No, that's wrong."}},
        )
        classifications = orchestrator_tagger.classify(event, context=[])
        assert len(classifications) == 0


# ---------------------------------------------------------------------------
# TestLabelResolution: Q9 locked decision
# ---------------------------------------------------------------------------


class TestLabelResolution:
    """Tests for label resolution: confidence-based selection, precedence tiebreaking, min threshold."""

    def test_highest_confidence_wins(self):
        """Primary = highest confidence among all classifications."""
        classifications = [
            Classification(label="O_DIR", confidence=0.7, source="direct"),
            Classification(label="O_CORR", confidence=0.8, source="direct"),
        ]
        primary, secondaries = _resolve_labels(classifications, min_confidence=0.5, precedence=["O_CORR", "O_DIR", "O_GATE"])
        assert primary is not None
        assert primary.label == "O_CORR"
        assert len(secondaries) == 1
        assert secondaries[0].label == "O_DIR"

    def test_precedence_breaks_ties(self):
        """When confidence tied, precedence O_CORR > O_DIR > O_GATE."""
        classifications = [
            Classification(label="O_DIR", confidence=0.8, source="direct"),
            Classification(label="O_CORR", confidence=0.8, source="direct"),
        ]
        primary, secondaries = _resolve_labels(classifications, min_confidence=0.5, precedence=["O_CORR", "O_DIR", "O_GATE"])
        assert primary is not None
        assert primary.label == "O_CORR"

    def test_o_dir_beats_o_gate_on_tie(self):
        """O_DIR > O_GATE when tied."""
        classifications = [
            Classification(label="O_GATE", confidence=0.7, source="direct"),
            Classification(label="O_DIR", confidence=0.7, source="direct"),
        ]
        primary, secondaries = _resolve_labels(classifications, min_confidence=0.5, precedence=["O_CORR", "O_DIR", "O_GATE"])
        assert primary is not None
        assert primary.label == "O_DIR"

    def test_below_min_confidence_no_primary(self):
        """Minimum 0.5 confidence required; below threshold -> no primary."""
        classifications = [
            Classification(label="O_CORR", confidence=0.4, source="direct"),
        ]
        primary, secondaries = _resolve_labels(classifications, min_confidence=0.5, precedence=["O_CORR", "O_DIR", "O_GATE"])
        assert primary is None
        assert len(secondaries) == 0  # below threshold, not even secondary

    def test_empty_classifications(self):
        """No classifications -> no primary, empty secondaries."""
        primary, secondaries = _resolve_labels([], min_confidence=0.5, precedence=["O_CORR", "O_DIR", "O_GATE"])
        assert primary is None
        assert len(secondaries) == 0

    def test_all_non_primary_are_secondaries(self):
        """All classifications above threshold but not primary go to secondaries."""
        classifications = [
            Classification(label="T_TEST", confidence=0.95, source="direct"),
            Classification(label="T_RISKY", confidence=0.8, source="risk_model"),
            Classification(label="O_DIR", confidence=0.7, source="direct"),
        ]
        primary, secondaries = _resolve_labels(classifications, min_confidence=0.5, precedence=["O_CORR", "O_DIR", "O_GATE"])
        assert primary is not None
        assert primary.label == "T_TEST"
        assert len(secondaries) == 2


# ---------------------------------------------------------------------------
# TestRiskScoring: Q10, Q11, Q12 locked decisions
# ---------------------------------------------------------------------------


class TestRiskScoring:
    """Tests for risk scoring: dual-layer detection, threshold, combination modes."""

    def test_risky_tool_detected(self, tool_tagger: ToolTagger):
        """risky_tools match (rm -rf) -> T_RISKY with risk_score."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "rm -rf /tmp/old"}},
        )
        classifications = tool_tagger.classify(event)
        risky = [c for c in classifications if c.label == "T_RISKY"]
        assert len(risky) > 0
        assert risky[0].confidence >= 0.7

    def test_protected_path_detected(self, tool_tagger: ToolTagger):
        """Protected path match (secrets.yaml) -> T_RISKY."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={
                "common": {"tool_name": "Edit", "text": "config/secrets.yaml"},
                "details": {"file_path": "config/secrets.yaml"},
            },
        )
        classifications = tool_tagger.classify(event)
        risky = [c for c in classifications if c.label == "T_RISKY"]
        assert len(risky) > 0

    def test_safe_tool_no_risk(self, tool_tagger: ToolTagger):
        """A safe tool operation should not be T_RISKY."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "echo hello"}},
        )
        classifications = tool_tagger.classify(event)
        risky = [c for c in classifications if c.label == "T_RISKY"]
        assert len(risky) == 0

    def test_sudo_is_risky(self, tool_tagger: ToolTagger):
        """sudo command triggers T_RISKY."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "sudo apt install foo"}},
        )
        classifications = tool_tagger.classify(event)
        risky = [c for c in classifications if c.label == "T_RISKY"]
        assert len(risky) > 0


# ---------------------------------------------------------------------------
# TestEventTagger: Full pipeline integration
# ---------------------------------------------------------------------------


class TestEventTagger:
    """Tests for EventTagger: multi-pass orchestration and full tagging pipeline."""

    def test_tags_tool_use_events(self, event_tagger: EventTagger):
        """EventTagger routes tool_use events to ToolTagger."""
        event = make_event(
            actor="tool",
            event_type="tool_use",
            payload={"common": {"tool_name": "Bash", "text": "pytest tests/"}},
        )
        tagged = event_tagger.tag([event])
        assert len(tagged) == 1
        assert tagged[0].primary is not None
        assert tagged[0].primary.label == "T_TEST"

    def test_tags_assistant_text_events(self, event_tagger: EventTagger):
        """EventTagger routes assistant_text events to ExecutorTagger."""
        event = make_event(
            actor="executor",
            event_type="assistant_text",
            payload={
                "common": {"text": "Should I use React or Vue?"}
            },
        )
        tagged = event_tagger.tag([event])
        assert len(tagged) == 1
        assert tagged[0].primary is not None
        assert tagged[0].primary.label == "X_ASK"

    def test_tags_user_msg_events(self, event_tagger: EventTagger):
        """EventTagger routes user_msg events to OrchestratorTagger."""
        event = make_event(
            actor="human_orchestrator",
            event_type="user_msg",
            payload={"common": {"text": "No, don't do that."}},
        )
        tagged = event_tagger.tag([event])
        assert len(tagged) == 1
        assert tagged[0].primary is not None
        assert tagged[0].primary.label == "O_CORR"

    def test_unclassified_event_no_primary(self, event_tagger: EventTagger):
        """An event that matches no rules gets no primary label."""
        event = make_event(
            actor="system",
            event_type="system_event",
            payload={"common": {"text": "turn_duration"}},
        )
        tagged = event_tagger.tag([event])
        assert len(tagged) == 1
        assert tagged[0].primary is None

    def test_multi_event_sequence(self, event_tagger: EventTagger):
        """Multiple events tagged correctly in sequence."""
        ts = datetime(2026, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_event(
                actor="human_orchestrator",
                event_type="user_msg",
                payload={"common": {"text": "Investigate the auth module."}},
                ts_utc=ts,
                event_id="ev-1",
            ),
            make_event(
                actor="executor",
                event_type="assistant_text",
                payload={
                    "common": {
                        "text": "I propose we fix this by editing config.yaml and adding a regression test."
                    }
                },
                ts_utc=ts + timedelta(seconds=5),
                event_id="ev-2",
            ),
            make_event(
                actor="tool",
                event_type="tool_use",
                payload={"common": {"tool_name": "Bash", "text": "pytest tests/"}},
                ts_utc=ts + timedelta(seconds=10),
                event_id="ev-3",
            ),
        ]
        tagged = event_tagger.tag(events)
        assert len(tagged) == 3
        assert tagged[0].primary.label == "O_DIR"
        assert tagged[1].primary.label == "X_PROPOSE"
        assert tagged[2].primary.label == "T_TEST"
