"""EBC Drift Detector: compares behavioral contract against session activity.

Extracts actual write-class tool operations from session events, compares
them against the expected write paths declared in the EBC, and produces
a drift alert when the divergence exceeds the configured threshold.

Only Edit/Write tool operations are counted as writes (matching the
exempt_tools pattern from EscalationDetector). Read/Glob/Grep operations
are explicitly excluded.

Exports:
    EBCDriftDetector: Detector class with detect() method
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from src.pipeline.ebc.models import (
    DriftSignal,
    EBCDriftAlert,
    ExternalBehavioralContract,
)
from src.pipeline.models.config import PipelineConfig


class EBCDriftDetector:
    """Compares an EBC contract against actual session behavior.

    Scans session events for write-class tool operations (Edit, Write),
    compares the set of actually-written files against the EBC's
    expected_write_paths, and returns an EBCDriftAlert if the drift
    score exceeds the configured threshold.

    Args:
        config: PipelineConfig with ebc_drift settings.
    """

    # Read-class tools that are always excluded from write detection
    _READ_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task"})

    # Minimum read events required before computing read/write ratio
    _MIN_READ_EVENTS_FOR_RATIO = 20

    # Read/write ratio above which a high_read_ratio signal fires
    _HIGH_RATIO_THRESHOLD = 10.0

    def __init__(self, config: PipelineConfig) -> None:
        ebc_cfg = config.ebc_drift
        self._threshold = ebc_cfg.threshold
        self._ratio_only_threshold = ebc_cfg.ratio_only_threshold
        self._tolerance_patterns = ebc_cfg.tolerance_patterns
        self._write_tool_names = frozenset(ebc_cfg.write_tool_names)
        self._bash_write_indicators = frozenset(ebc_cfg.bash_write_indicators)

    def detect(
        self,
        ebc: ExternalBehavioralContract,
        session_events: list[dict[str, Any]],
        session_id: str,
    ) -> EBCDriftAlert | None:
        """Detect drift between EBC contract and actual session behavior.

        Args:
            ebc: The behavioral contract to compare against.
            session_events: List of event dicts from read_events().
            session_id: Session identifier for the alert.

        Returns:
            EBCDriftAlert if drift exceeds threshold, None otherwise.
            Returns None if EBC has no expected_write_paths (no contract).
        """
        expected = ebc.expected_write_paths
        if not expected:
            return None

        actual = self._extract_write_paths(session_events)

        # Normalize paths: strip leading ./
        expected_normalized = {p.lstrip("./") for p in expected}
        actual_normalized = {p.lstrip("./") for p in actual}

        # Compute raw sets
        raw_unexpected = actual_normalized - expected_normalized
        missing = expected_normalized - actual_normalized

        # Filter tolerance patterns from unexpected set
        unexpected = set()
        for f in raw_unexpected:
            if not self._matches_tolerance(f):
                unexpected.add(f)

        # Build signals
        signals: list[DriftSignal] = []

        for f in sorted(unexpected):
            signals.append(
                DriftSignal(
                    signal_type="unexpected_file",
                    detail=f,
                    weight=1.0,
                )
            )

        for f in sorted(missing):
            signals.append(
                DriftSignal(
                    signal_type="missing_expected_file",
                    detail=f,
                    weight=0.3,
                )
            )

        # Add secondary behavioral signal: tool usage ratio
        ratio_signal = self._compute_tool_ratio_signal(session_events)
        if ratio_signal is not None:
            signals.append(ratio_signal)

        if not signals:
            return None

        # Compute drift score: weighted sum / max(expected count, 1), capped at 1.0
        raw_score = sum(s.weight for s in signals) / max(len(expected_normalized), 1)
        drift_score = min(raw_score, 1.0)

        # Ratio-only signals use a higher threshold (less likely to alert alone)
        has_file_signals = any(s.signal_type != "high_read_ratio" for s in signals)
        if not has_file_signals and drift_score < self._ratio_only_threshold:
            return None

        if drift_score < self._threshold:
            return None

        return EBCDriftAlert(
            session_id=session_id,
            drift_score=round(drift_score, 4),
            signals=signals,
            ebc_phase=ebc.phase,
            ebc_plan=str(ebc.plan),
            unexpected_files=sorted(unexpected),
            missing_expected_files=sorted(missing),
        )

    def _extract_write_paths(self, session_events: list[dict[str, Any]]) -> set[str]:
        """Extract file paths from write-class tool operations.

        Scans session events for Edit/Write tool invocations and extracts
        the file_path from the payload details dict.

        Args:
            session_events: List of event dicts from read_events().

        Returns:
            Set of file paths that were written to during the session.
        """
        paths: set[str] = set()

        for event in session_events:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue

            common = payload.get("common", {})
            if not isinstance(common, dict):
                continue

            tool_name = common.get("tool_name", "")

            # Skip read-class tools explicitly
            if tool_name in self._READ_TOOLS:
                continue

            # Check write-class tools (Edit, Write)
            if tool_name in self._write_tool_names:
                details = payload.get("details", {})
                if isinstance(details, dict):
                    file_path = details.get("file_path", "")
                    if file_path:
                        paths.add(file_path)
                continue

            # Best-effort Bash write detection
            if tool_name == "Bash":
                command_text = common.get("text", "")
                if command_text and self._has_bash_write_indicator(command_text):
                    # Bash writes are hard to extract file paths from reliably.
                    # We note the activity but don't try to extract specific paths
                    # unless obvious patterns are present.
                    pass

        return paths

    def _has_bash_write_indicator(self, command_text: str) -> bool:
        """Check if a Bash command text contains write indicators."""
        for indicator in self._bash_write_indicators:
            if indicator in command_text:
                return True
        return False

    def _matches_tolerance(self, file_path: str) -> bool:
        """Check if a file path matches any tolerance pattern."""
        for pattern in self._tolerance_patterns:
            if fnmatch(file_path, pattern):
                return True
            # Also check just the filename component
            parts = file_path.rsplit("/", 1)
            filename = parts[-1] if parts else file_path
            if fnmatch(filename, pattern):
                return True
        return False

    def _get_tool_name(self, event: dict[str, Any]) -> str:
        """Extract tool_name from an event dict.

        Mirrors the extraction logic in _extract_write_paths for consistency.

        Args:
            event: Event dict from read_events().

        Returns:
            Tool name string, or empty string if not found.
        """
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return ""
        common = payload.get("common", {})
        if not isinstance(common, dict):
            return ""
        return common.get("tool_name", "")

    def _compute_tool_ratio_signal(
        self, session_events: list[dict[str, Any]]
    ) -> DriftSignal | None:
        """Detect high read-to-write ratio indicating possible Discovery Mode.

        Sessions that are heavily read-dominant (>10:1 read/write ratio with
        at least 20 read events) may indicate the agent has drifted into
        exploratory behavior rather than executing the plan.

        Args:
            session_events: List of event dicts from read_events().

        Returns:
            DriftSignal with signal_type="high_read_ratio" if ratio exceeds
            threshold, None otherwise.
        """
        read_count = sum(
            1 for e in session_events if self._get_tool_name(e) in self._READ_TOOLS
        )
        write_count = len(self._extract_write_paths(session_events))

        if read_count < self._MIN_READ_EVENTS_FOR_RATIO:
            return None

        if write_count == 0:
            return DriftSignal(
                signal_type="high_read_ratio",
                detail=f"read={read_count}, write=0 — session appears exploratory",
                weight=0.5,
            )

        ratio = read_count / write_count
        if ratio > self._HIGH_RATIO_THRESHOLD:
            return DriftSignal(
                signal_type="high_read_ratio",
                detail=f"read/write ratio {ratio:.1f}:1 — heavily read-dominant",
                weight=0.3,
            )

        return None
