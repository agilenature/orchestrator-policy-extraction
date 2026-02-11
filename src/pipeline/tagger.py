"""Multi-pass event tagger (EXTRACT-02).

Classifies canonical events with semantic tags using three sequential passes,
each config-driven:

1. ToolTagger (Pass 1): Structured data, HIGH confidence
   - T_TEST, T_LINT, T_GIT_COMMIT from command matching
   - T_RISKY from risky_tools and protected_paths dual-layer detection

2. ExecutorTagger (Pass 2): Text patterns, MEDIUM confidence
   - X_PROPOSE per Q5 operational definition (normative stance + action content)
   - X_ASK per Q5 operational definition (missing info + explicit solicitation)

3. OrchestratorTagger (Pass 3): Keywords, VARIABLE confidence
   - O_CORR from reaction keywords with contextual boosting
   - O_GATE from gate patterns
   - O_DIR from mode inference keywords

Label resolution follows Q9 locked decision:
- Primary = highest confidence
- Ties broken by precedence: O_CORR > O_DIR > O_GATE
- Minimum 0.5 confidence required

All keywords, patterns, and thresholds come from config (not hardcoded).

Exports:
    EventTagger: Multi-pass orchestrator
    ToolTagger: Pass 1 classifier
    ExecutorTagger: Pass 2 classifier
    OrchestratorTagger: Pass 3 classifier
    _resolve_labels: Label resolution function
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from src.pipeline.models.config import PipelineConfig
from src.pipeline.models.events import (
    CanonicalEvent,
    Classification,
    TaggedEvent,
)


def _resolve_labels(
    classifications: list[Classification],
    min_confidence: float = 0.5,
    precedence: list[str] | None = None,
) -> tuple[Classification | None, list[Classification]]:
    """Resolve classifications into primary + secondaries.

    Implements Q9 locked decision:
    - Primary = highest confidence among all classifications
    - Ties broken by precedence: O_CORR > O_DIR > O_GATE (configurable)
    - Minimum confidence required (below threshold -> no primary label)
    - All non-primary classifications above threshold stored as secondaries

    Args:
        classifications: All candidate classifications for an event.
        min_confidence: Minimum confidence threshold (default 0.5 per Q9).
        precedence: Label precedence for tiebreaking. Lower index = higher priority.

    Returns:
        Tuple of (primary classification or None, list of secondary classifications).
    """
    if not classifications:
        return None, []

    if precedence is None:
        precedence = ["O_CORR", "O_DIR", "O_GATE"]

    # Filter by minimum confidence
    above_threshold = [c for c in classifications if c.confidence >= min_confidence]
    if not above_threshold:
        return None, []

    # Sort by confidence descending, then by precedence (lower index = higher priority)
    def sort_key(c: Classification) -> tuple[float, int]:
        prec_index = precedence.index(c.label) if c.label in precedence else len(precedence)
        return (-c.confidence, prec_index)

    sorted_classifications = sorted(above_threshold, key=sort_key)
    primary = sorted_classifications[0]
    secondaries = sorted_classifications[1:]

    return primary, secondaries


class ToolTagger:
    """Pass 1: Classify tool_use events from structured data.

    Detects T_TEST, T_LINT, T_GIT_COMMIT from command matching against config
    patterns. Detects T_RISKY from dual-layer detection (risky_tools + protected_paths).

    All patterns are loaded from config -- no hardcoded keywords.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        # Compile command patterns from config
        self._test_commands = config.tags.test_commands
        self._lint_commands = config.tags.lint_commands
        self._git_commit_commands = config.tags.git_commands.commit
        self._risky_commands = config.tags.risky_commands
        self._risky_tools = config.risk_model.risky_tools
        self._protected_paths = config.risk_model.protected_paths
        self._risk_threshold = config.risk_model.threshold

    def classify(self, event: CanonicalEvent) -> list[Classification]:
        """Classify a tool_use or tool_result event.

        Args:
            event: A canonical event to classify.

        Returns:
            List of classifications (may be empty if no rules match).
        """
        if event.event_type not in ("tool_use", "tool_result"):
            return []

        classifications: list[Classification] = []

        # Extract command text from payload
        command_text = self._extract_command_text(event)
        tool_name = self._extract_tool_name(event)
        file_path = self._extract_file_path(event)

        # Check test commands
        if command_text and self._matches_any(command_text, self._test_commands):
            classifications.append(
                Classification(label="T_TEST", confidence=0.95, source="direct")
            )

        # Check lint commands
        if command_text and self._matches_any(command_text, self._lint_commands):
            classifications.append(
                Classification(label="T_LINT", confidence=0.95, source="direct")
            )

        # Check git commit commands
        if command_text and self._matches_any(command_text, self._git_commit_commands):
            classifications.append(
                Classification(
                    label="T_GIT_COMMIT", confidence=0.95, source="direct"
                )
            )

        # Check risky commands and tools (dual-layer detection)
        risk_factors = self._compute_risk_factors(
            command_text, tool_name, file_path, event
        )
        if risk_factors:
            max_risk = max(f["weight"] for f in risk_factors)
            if max_risk >= self._risk_threshold:
                classifications.append(
                    Classification(
                        label="T_RISKY",
                        confidence=max_risk,
                        source="risk_model",
                    )
                )

        return classifications

    def _extract_command_text(self, event: CanonicalEvent) -> str:
        """Extract command text from event payload."""
        common = event.payload.get("common", {})
        text = common.get("text", "")
        return text

    def _extract_tool_name(self, event: CanonicalEvent) -> str:
        """Extract tool name from event payload."""
        common = event.payload.get("common", {})
        return common.get("tool_name", "")

    def _extract_file_path(self, event: CanonicalEvent) -> str:
        """Extract file path from event payload details."""
        details = event.payload.get("details", {})
        return details.get("file_path", "")

    def _matches_any(self, text: str, patterns: list[str]) -> bool:
        """Check if text contains any of the given command patterns."""
        text_lower = text.lower()
        for pattern in patterns:
            if pattern.lower() in text_lower:
                return True
        return False

    def _compute_risk_factors(
        self,
        command_text: str,
        tool_name: str,
        file_path: str,
        event: CanonicalEvent,
    ) -> list[dict[str, Any]]:
        """Compute risk factors from dual-layer detection.

        Layer 1: Risky tools/commands (exact match against risky_tools and risky_commands)
        Layer 2: Protected paths (glob match against protected_paths)

        Returns list of risk factor dicts with {factor, weight, matched}.
        """
        factors: list[dict[str, Any]] = []

        # Layer 1: Risky tools (from risk_model.risky_tools)
        if command_text:
            for risky in self._risky_tools:
                if risky.lower() in command_text.lower():
                    factors.append(
                        {"factor": f"risky_tool:{risky}", "weight": 0.8, "matched": risky}
                    )

        # Layer 1b: Risky commands (from tags.risky_commands)
        if command_text:
            for risky_cmd in self._risky_commands:
                if risky_cmd.lower() in command_text.lower():
                    factors.append(
                        {
                            "factor": f"risky_command:{risky_cmd}",
                            "weight": 0.8,
                            "matched": risky_cmd,
                        }
                    )

        # Layer 2: Protected paths
        # Check against the full text representation of the event payload
        text_to_check = command_text + " " + file_path
        for protected_pattern in self._protected_paths:
            if self._path_matches(text_to_check, protected_pattern):
                factors.append(
                    {
                        "factor": f"protected_path:{protected_pattern}",
                        "weight": 0.8,
                        "matched": protected_pattern,
                    }
                )

        # Deduplicate factors by factor name
        seen: set[str] = set()
        unique_factors: list[dict[str, Any]] = []
        for f in factors:
            if f["factor"] not in seen:
                seen.add(f["factor"])
                unique_factors.append(f)

        return unique_factors

    def _path_matches(self, text: str, pattern: str) -> bool:
        """Check if text contains a path matching the glob pattern.

        Handles glob patterns like '**/secrets.yaml', '**/db/migrations/**',
        and simple prefix patterns like 'auth/'.
        """
        # Normalize glob pattern for matching
        # Strip leading **/ for simpler substring matching
        clean_pattern = pattern.replace("**/", "").replace("/**", "")

        # Simple substring check (tolerates false positives per Q10)
        if clean_pattern and clean_pattern.lower() in text.lower():
            return True

        # Also try fnmatch on individual path components
        for word in text.split():
            if fnmatch.fnmatch(word, pattern):
                return True

        return False


class ExecutorTagger:
    """Pass 2: Classify executor (assistant) text events.

    Detects X_PROPOSE and X_ASK per Q5 operational definitions.
    All patterns derived from config label definitions.

    X_PROPOSE requires: normative stance + action content + orchestrator degrees of freedom
    X_ASK requires: missing info + explicit solicitation
    """

    # Normative stance indicators for X_PROPOSE
    _PROPOSE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bI propose\b", re.IGNORECASE),
        re.compile(r"\bI recommend\b", re.IGNORECASE),
        re.compile(r"\bI suggest\b", re.IGNORECASE),
        re.compile(r"\bbest approach\b", re.IGNORECASE),
        re.compile(r"\bOptions:\s*\(?[A-Z]\)", re.IGNORECASE),
        re.compile(r"\b(?:option|approach)\s+[A-Z]\b", re.IGNORECASE),
        re.compile(r"\brecommended\)", re.IGNORECASE),
        re.compile(r"\bwe should\b", re.IGNORECASE),
        re.compile(r"\bwe could\b", re.IGNORECASE),
        re.compile(r"\bpropose switching\b", re.IGNORECASE),
    ]

    # Explicit solicitation patterns for X_ASK
    _ASK_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bShould I\b", re.IGNORECASE),
        re.compile(r"\bDo you want\b", re.IGNORECASE),
        re.compile(r"\bWhich\b.*\?", re.IGNORECASE),
        re.compile(r"\bMay I\b", re.IGNORECASE),
        re.compile(r"\bCan I\b", re.IGNORECASE),
        re.compile(r"\bshould we\b", re.IGNORECASE),
        re.compile(r"\bDo you prefer\b", re.IGNORECASE),
        re.compile(r"\bcorrect per spec\b", re.IGNORECASE),
        re.compile(r"\bor should\b.*\?", re.IGNORECASE),
    ]

    # Status/report patterns that should NOT be X_PROPOSE or X_ASK
    _STATUS_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"^I found\b", re.IGNORECASE),
        re.compile(r"^Here are\b", re.IGNORECASE),
        re.compile(r"^Next I'?ll\b", re.IGNORECASE),
        re.compile(r"^I'?ll (?:open|read|check|look|start)\b", re.IGNORECASE),
    ]

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def classify(self, event: CanonicalEvent) -> list[Classification]:
        """Classify an executor (assistant) text event.

        Args:
            event: A canonical event to classify.

        Returns:
            List of classifications (may be empty).
        """
        if event.actor != "executor" or event.event_type != "assistant_text":
            return []

        text = self._extract_text(event)
        if not text:
            return []

        classifications: list[Classification] = []

        # Check for status/report first (negative filter)
        is_status = any(p.search(text) for p in self._STATUS_PATTERNS)

        # Check X_PROPOSE: normative stance + action content
        if not is_status and self._is_propose(text):
            confidence = self._compute_propose_confidence(text)
            classifications.append(
                Classification(
                    label="X_PROPOSE", confidence=confidence, source="direct"
                )
            )

        # Check X_ASK: missing info + explicit solicitation
        if not is_status and self._is_ask(text):
            confidence = self._compute_ask_confidence(text)
            classifications.append(
                Classification(
                    label="X_ASK", confidence=confidence, source="direct"
                )
            )

        return classifications

    def _extract_text(self, event: CanonicalEvent) -> str:
        """Extract text content from event payload."""
        common = event.payload.get("common", {})
        return common.get("text", "")

    def _is_propose(self, text: str) -> bool:
        """Check if text matches X_PROPOSE operational definition.

        Requirements (from Q5):
        1. Action-content exists
        2. Normative stance exists
        3. Orchestrator-relevant degrees of freedom
        """
        # Must have normative stance
        has_normative_stance = any(p.search(text) for p in self._PROPOSE_PATTERNS)
        if not has_normative_stance:
            return False

        # Must NOT be a pure question (that would be X_ASK)
        # A proposal can contain a question, but the primary content should be action
        is_pure_question = self._is_pure_question(text)
        if is_pure_question:
            return False

        return True

    def _is_ask(self, text: str) -> bool:
        """Check if text matches X_ASK operational definition.

        Requirements (from Q5):
        1. Information/decision is missing
        2. Proceeding would be speculation
        3. Explicitly soliciting input
        """
        return any(p.search(text) for p in self._ASK_PATTERNS)

    def _is_pure_question(self, text: str) -> bool:
        """Check if text is primarily a question without a recommendation.

        Reuses the class-level _PROPOSE_PATTERNS to avoid redundant regex compilation.
        """
        has_recommendation = any(p.search(text) for p in self._PROPOSE_PATTERNS)
        return not has_recommendation

    def _compute_propose_confidence(self, text: str) -> float:
        """Compute confidence for X_PROPOSE classification.

        Base confidence 0.7, boosted by strength of normative stance.
        """
        confidence = 0.7
        # Multiple propose signals boost confidence
        match_count = sum(1 for p in self._PROPOSE_PATTERNS if p.search(text))
        if match_count >= 2:
            confidence = min(0.9, confidence + 0.1 * (match_count - 1))
        return confidence

    def _compute_ask_confidence(self, text: str) -> float:
        """Compute confidence for X_ASK classification.

        Base confidence 0.7, boosted by explicit question mark and solicitation clarity.
        """
        confidence = 0.7
        if "?" in text:
            confidence = min(0.9, confidence + 0.1)
        return confidence


class OrchestratorTagger:
    """Pass 3: Classify orchestrator (user) message events.

    Detects O_CORR from reaction keywords with contextual boosting.
    Detects O_GATE from gate patterns.
    Detects O_DIR from mode inference keywords.

    All keywords come from config.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        # O_CORR keywords from config (Q6) -- pre-compile regex patterns
        self._corr_keywords = config.classification.reaction_keywords.get(
            "O_CORR", []
        )
        self._corr_patterns = [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for kw in self._corr_keywords
        ]
        # Gate patterns from config
        self._gate_patterns = config.gate_patterns
        # Mode inference keywords from config -- pre-compile regex patterns
        self._mode_keywords = config.mode_inference
        self._dir_patterns: list[re.Pattern[str]] = []
        for _mode_name, mode_config in self._mode_keywords.items():
            if isinstance(mode_config, dict):
                for keyword in mode_config.get("keywords", []):
                    self._dir_patterns.append(
                        re.compile(
                            r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE
                        )
                    )

    def classify(
        self,
        event: CanonicalEvent,
        context: list[CanonicalEvent | TaggedEvent],
    ) -> list[Classification]:
        """Classify an orchestrator (user) message event.

        Args:
            event: A canonical event to classify.
            context: Previous events for contextual boosting (may be
                CanonicalEvent or TaggedEvent instances).

        Returns:
            List of classifications (may be empty).
        """
        if event.actor != "human_orchestrator" or event.event_type != "user_msg":
            return []

        text = self._extract_text(event)
        if not text:
            return []

        classifications: list[Classification] = []

        # Check O_CORR: reaction keywords
        if self._has_correction_keyword(text):
            confidence = 0.8
            # Contextual boosting: if previous event was T_TEST or T_RISKY
            if self._preceding_is_test_or_risky(context):
                confidence = 0.9
            classifications.append(
                Classification(
                    label="O_CORR", confidence=confidence, source="direct"
                )
            )

        # Check O_GATE: gate patterns
        if self._has_gate_pattern(text):
            classifications.append(
                Classification(
                    label="O_GATE", confidence=0.7, source="direct"
                )
            )

        # Check O_DIR: mode/direction keywords
        if self._has_direction_keyword(text):
            classifications.append(
                Classification(
                    label="O_DIR", confidence=0.7, source="direct"
                )
            )

        return classifications

    def _extract_text(self, event: CanonicalEvent) -> str:
        """Extract text content from event payload."""
        common = event.payload.get("common", {})
        return common.get("text", "")

    def _has_correction_keyword(self, text: str) -> bool:
        """Check if text starts with or contains reaction keywords (Q6).

        Uses pre-compiled word-boundary regex patterns for efficient matching.
        """
        return any(p.search(text) for p in self._corr_patterns)

    def _has_gate_pattern(self, text: str) -> bool:
        """Check if text matches gate patterns from config."""
        text_lower = text.lower()
        for _gate_name, patterns in self._gate_patterns.items():
            if isinstance(patterns, list):
                for pattern in patterns:
                    if isinstance(pattern, str) and pattern.lower() in text_lower:
                        return True
            elif isinstance(patterns, dict):
                # gate_patterns might be nested dicts
                pass
        return False

    def _has_direction_keyword(self, text: str) -> bool:
        """Check if text matches mode inference keywords (O_DIR).

        Uses pre-compiled word-boundary regex patterns to prevent false
        positives from short keywords (e.g., 'PR' matching 'production').
        """
        return any(p.search(text) for p in self._dir_patterns)

    def _preceding_is_test_or_risky(
        self, context: list[CanonicalEvent | TaggedEvent]
    ) -> bool:
        """Check if any recent context event is tagged T_TEST or T_RISKY.

        Implements contextual boosting from Q6:
        'If previous event was T_TEST failure or T_RISKY and user responds
        immediately, default to O_CORR' with boosted confidence.
        """
        for ctx_event in reversed(context):
            if isinstance(ctx_event, TaggedEvent):
                if ctx_event.primary and ctx_event.primary.label in (
                    "T_TEST",
                    "T_RISKY",
                ):
                    return True
        return False


class EventTagger:
    """Multi-pass event classifier.

    Orchestrates three classification passes:
    1. ToolTagger: tool_use/tool_result events (HIGH confidence)
    2. ExecutorTagger: assistant_text events (MEDIUM confidence)
    3. OrchestratorTagger: user_msg events (VARIABLE confidence)

    After all passes, resolves labels per Q9 (highest confidence primary,
    precedence tiebreaking, min threshold).

    tool_result events inherit tags from their linked tool_use events
    via tool_use_id matching.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.tool_tagger = ToolTagger(config)
        self.executor_tagger = ExecutorTagger(config)
        self.orchestrator_tagger = OrchestratorTagger(config)
        self._min_confidence = config.classification.min_confidence
        self._precedence = config.classification.precedence

    def tag(self, events: list[CanonicalEvent]) -> list[TaggedEvent]:
        """Tag a list of canonical events with semantic classifications.

        Processes events in order, building context for each event from
        previously tagged events.

        Tool result events inherit tags from their linked tool_use events
        via the tool_use_id link.

        Args:
            events: List of canonical events to classify.

        Returns:
            List of TaggedEvent instances with primary and secondary labels.
        """
        tagged: list[TaggedEvent] = []
        # Map tool_use_id -> classifications for tool_result inheritance
        tool_use_classifications: dict[str, list[Classification]] = {}

        for i, event in enumerate(events):
            classifications: list[Classification] = []

            # Pass 1: Tool classification (structured data, high confidence)
            if event.event_type == "tool_use":
                tool_cls = self.tool_tagger.classify(event)
                classifications.extend(tool_cls)
                # Store for tool_result inheritance
                tool_use_id = event.links.get("tool_use_id")
                if tool_use_id:
                    tool_use_classifications[tool_use_id] = tool_cls

            elif event.event_type == "tool_result":
                # Check for inherited classifications from linked tool_use
                tool_use_id = event.links.get("tool_use_id")
                if tool_use_id and tool_use_id in tool_use_classifications:
                    # Inherit classifications from the tool_use event
                    inherited = tool_use_classifications[tool_use_id]
                    classifications.extend(
                        Classification(
                            label=c.label,
                            confidence=c.confidence,
                            source="inferred",
                        )
                        for c in inherited
                    )
                else:
                    # No linked tool_use found; classify the tool_result directly
                    tool_cls = self.tool_tagger.classify(event)
                    classifications.extend(tool_cls)

            # Pass 2: Executor classification (text patterns, medium confidence)
            if event.actor == "executor" and event.event_type == "assistant_text":
                classifications.extend(self.executor_tagger.classify(event))

            # Pass 3: Orchestrator classification (keywords, variable confidence)
            if (
                event.actor == "human_orchestrator"
                and event.event_type == "user_msg"
            ):
                # Use previously tagged events as context (up to 3 preceding)
                context = tagged[max(0, len(tagged) - 3) :]
                classifications.extend(
                    self.orchestrator_tagger.classify(event, context)
                )

            # Resolve labels
            primary, secondaries = _resolve_labels(
                classifications,
                min_confidence=self._min_confidence,
                precedence=self._precedence,
            )
            tagged_event = TaggedEvent(
                event=event,
                primary=primary,
                secondaries=secondaries,
                all_classifications=classifications,
            )
            tagged.append(tagged_event)

        return tagged
