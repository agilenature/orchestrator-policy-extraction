"""FalseIntegrationDetector: heuristic proxy for DDF-09 (Package Deal fallacy).

Detects false integration by checking scope path diversity per episode.
Episodes with 2+ distinct scope path prefixes are suspected of conflating
distinct concerns into a single orchestrator action.

Dual output:
1. axis_hypotheses table writes (all detections above minimum confidence)
2. ai_flame_events markers (only high-confidence detections above threshold)

Confidence is computed as min(0.9, 0.3 * len(distinct_prefixes)).

Exports:
    FalseIntegrationDetector
"""

from __future__ import annotations

import json

import duckdb

from src.pipeline.ddf.models import AxisHypothesis, FlameEvent
from src.pipeline.models.config import PipelineConfig


class FalseIntegrationDetector:
    """Heuristic proxy for DDF-09 False Integration (Package Deal fallacy).

    Dual output: axis_hypotheses table + ai_flame_events.
    """

    def __init__(
        self, config: PipelineConfig, conn: duckdb.DuckDBPyConnection
    ) -> None:
        self.config = config
        self.conn = conn
        self.threshold = config.ddf.false_integration_confidence_threshold

    def detect(
        self, session_id: str, episodes: list[dict]
    ) -> tuple[list[FlameEvent], list[AxisHypothesis]]:
        """Detect false integration by checking scope path diversity per episode.

        Args:
            session_id: Session identifier.
            episodes: List of episode dicts with orchestrator_action containing
                scope and constraints fields.

        Returns:
            Tuple of (flame_events, axis_hypotheses). Flame events are emitted
            only for high-confidence detections (>= threshold). Hypotheses are
            emitted for all detections with 2+ distinct scope prefixes.
        """
        flame_events: list[FlameEvent] = []
        hypotheses: list[AxisHypothesis] = []
        prompt_num = 0

        for ep in episodes:
            prompt_num += 1
            action = ep.get("orchestrator_action", {})
            if isinstance(action, str):
                try:
                    action = json.loads(action)
                except Exception:
                    action = {}

            scope = (
                action.get("scope", [])
                if isinstance(action, dict)
                else []
            )
            constraints = (
                action.get("constraints", [])
                if isinstance(action, dict)
                else []
            )

            if len(scope) < 2:
                continue  # Need 2+ distinct scopes to suspect false integration

            # Check scope path prefix diversity
            prefixes: set[str] = set()
            for path in scope:
                if isinstance(path, str) and "/" in path:
                    prefixes.add(path.split("/")[0])
                elif isinstance(path, str):
                    prefixes.add(path)

            if len(prefixes) < 2:
                continue

            # Compute confidence based on number of distinct scope prefixes
            confidence = min(0.9, 0.3 * len(prefixes))

            # Build hypothesis
            constraint_text = (
                str(constraints[:1]) if constraints else "unknown rule"
            )
            hypothesis = AxisHypothesis(
                hypothesis_id=AxisHypothesis.make_id(
                    session_id,
                    ep.get("episode_id"),
                    constraint_text[:50],
                ),
                session_id=session_id,
                episode_id=ep.get("episode_id"),
                hypothesized_axis=f"possible_package_deal:{constraint_text[:50]}",
                confidence=confidence,
                marker_type="false_integration",
                evidence=(
                    f"Scope prefixes: {sorted(prefixes)}, "
                    f"constraints: {constraint_text[:100]}"
                ),
            )
            hypotheses.append(hypothesis)

            if confidence >= self.threshold:
                # High confidence: emit ai_flame_events marker
                flame_events.append(
                    FlameEvent(
                        flame_event_id=FlameEvent.make_id(
                            session_id, prompt_num, "false_integration"
                        ),
                        session_id=session_id,
                        marker_level=5,
                        marker_type="false_integration",
                        evidence_excerpt=(
                            hypothesis.evidence[:200]
                            if hypothesis.evidence
                            else None
                        ),
                        subject="ai",
                        detection_source="opeml",
                        source_episode_id=ep.get("episode_id"),
                    )
                )

        # Write hypotheses to DuckDB
        self._write_hypotheses(hypotheses)

        return flame_events, hypotheses

    def _write_hypotheses(self, hypotheses: list[AxisHypothesis]) -> int:
        """Write axis hypotheses to DuckDB axis_hypotheses table.

        Uses INSERT OR REPLACE for idempotent writes.

        Args:
            hypotheses: List of AxisHypothesis objects to write.

        Returns:
            Number of hypotheses written.
        """
        if not hypotheses:
            return 0
        rows = [
            (
                h.hypothesis_id,
                h.session_id,
                h.episode_id,
                h.hypothesized_axis,
                h.confidence,
                h.marker_type,
                h.evidence,
            )
            for h in hypotheses
        ]
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO axis_hypotheses
            (hypothesis_id, session_id, episode_id, hypothesized_axis,
             confidence, marker_type, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return len(hypotheses)
