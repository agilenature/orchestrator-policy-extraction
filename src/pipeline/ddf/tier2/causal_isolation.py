"""CausalIsolationRecorder: records causal isolation markers from premise registry.

Reads FoilInstantiator results (DDF-08 Post Hoc Ergo Propter Hoc detection)
from the premise_registry table and emits flame_event markers based on
isolation status:

- Successful isolation (divergence_node present) -> L3, subject='ai'
- Failed isolation (foil outcomes without divergence) -> L2, subject='ai'
- Missing isolation (causal claim without foil) -> L1, subject='ai'

ALL events produced by this recorder use subject='ai' because they assess
the AI's causal reasoning quality, not the human's DDF markers.

Exports:
    CausalIsolationRecorder
"""

from __future__ import annotations

import json
import re

import duckdb

from src.pipeline.ddf.models import FlameEvent

_CAUSAL_CLAIM_PAT = re.compile(
    r"\b(?:because|caused by|leads to|results in|therefore|since)\b",
    re.IGNORECASE,
)


class CausalIsolationRecorder:
    """Records causal isolation markers from FoilInstantiator results (DDF-08).

    ALL events produced by this recorder use subject='ai'.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.conn = conn

    def record(self, session_id: str) -> list[FlameEvent]:
        """Read FoilInstantiator results and emit flame_event markers.

        Queries premise_registry for premises from this session, then
        classifies each based on foil_path_outcomes status.

        Args:
            session_id: Session to scan for causal isolation markers.

        Returns:
            List of FlameEvent objects with subject='ai'.
        """
        # Check if premise_registry table exists
        tables = [
            r[0]
            for r in self.conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'premise_registry'"
            ).fetchall()
        ]
        if not tables:
            return []

        try:
            rows = self.conn.execute(
                """
                SELECT premise_id, claim, foil_path_outcomes, foil
                FROM premise_registry
                WHERE session_id = ?
                """,
                [session_id],
            ).fetchall()
        except Exception:
            return []

        markers: list[FlameEvent] = []
        prompt_num = 0
        for row in rows:
            premise_id, claim, foil_outcomes_json, foil = row
            prompt_num += 1

            foil_outcomes = None
            if foil_outcomes_json:
                try:
                    foil_outcomes = (
                        json.loads(foil_outcomes_json)
                        if isinstance(foil_outcomes_json, str)
                        else foil_outcomes_json
                    )
                except Exception:
                    foil_outcomes = None

            if foil_outcomes:
                # Has foil results -- check if isolation succeeded
                divergence = (
                    foil_outcomes.get("divergence_node")
                    if isinstance(foil_outcomes, dict)
                    else None
                )
                if divergence:
                    # Successful isolation -> L3
                    markers.append(
                        FlameEvent(
                            flame_event_id=FlameEvent.make_id(
                                session_id,
                                prompt_num,
                                "causal_isolation_success",
                            ),
                            session_id=session_id,
                            marker_level=3,
                            marker_type="causal_isolation_success",
                            evidence_excerpt=str(foil_outcomes)[:200],
                            flood_confirmed=True,
                            subject="ai",
                            detection_source="opeml",
                            source_episode_id=premise_id,
                        )
                    )
                else:
                    # Foil had no divergence -> failed isolation -> L2
                    markers.append(
                        FlameEvent(
                            flame_event_id=FlameEvent.make_id(
                                session_id,
                                prompt_num,
                                "causal_isolation_failed",
                            ),
                            session_id=session_id,
                            marker_level=2,
                            marker_type="causal_isolation_failed",
                            evidence_excerpt=str(foil_outcomes)[:200],
                            flood_confirmed=False,
                            subject="ai",
                            detection_source="opeml",
                            source_episode_id=premise_id,
                        )
                    )
            elif claim and _CAUSAL_CLAIM_PAT.search(claim):
                # Causal claim without foil -> missing isolation -> L1
                markers.append(
                    FlameEvent(
                        flame_event_id=FlameEvent.make_id(
                            session_id,
                            prompt_num,
                            "missing_isolation",
                        ),
                        session_id=session_id,
                        marker_level=1,
                        marker_type="missing_isolation",
                        evidence_excerpt=claim[:200],
                        flood_confirmed=False,
                        subject="ai",
                        detection_source="opeml",
                        source_episode_id=premise_id,
                    )
                )

        return markers
