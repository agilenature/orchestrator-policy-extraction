"""Tier 2 OPE enrichment: upgrades Tier 1 stubs to L3-7, detects AI markers.

FlameEventExtractor reads existing Tier 1 stub flame_events from DuckDB and
upgrades them using episode context (scope paths, reaction labels, outcomes).
It also detects DDF markers in AI (executor) text and deposits Level 6+
flood-confirmed events to memory_candidates.

Upgrade rules (heuristic):
- L0 stub + multi-scope episode -> L3 (cross-context)
- L1 stub + successful outcome -> L4 (principle identified)
- L2 stub + correction reaction -> L5 (deep naming)
- Any reaction=approve + axis + evidence -> L6 (flood confirmed)

AI marker detection:
- Assertive causal claim -> L2, subject='ai'
- Concretization flood (3+ examples) -> L6, subject='ai', flood_confirmed=True

Exports:
    FlameEventExtractor
"""

from __future__ import annotations

import json
import re
from typing import Any

import duckdb

from src.pipeline.ddf.deposit import deposit_to_memory_candidates, mark_deposited
from src.pipeline.ddf.models import FlameEvent
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.models.config import PipelineConfig

# Pre-compiled patterns for AI marker detection
_CAUSAL_PAT = re.compile(
    r"\b(?:because|caused by|leads to|results in|the reason|therefore)\b",
    re.IGNORECASE,
)
_ASSERTIVE_PAT = re.compile(
    r"\b(?:the cause is|the root cause|I'm certain|the principle here"
    r"|the invariant|the rule is)\b",
    re.IGNORECASE,
)
_FLOOD_PAT = re.compile(
    r"(?:for example|for instance|such as|specifically)", re.IGNORECASE
)


class FlameEventExtractor:
    """Tier 2 OPE enrichment: upgrades Tier 1 stubs to L3-7, detects AI markers."""

    def __init__(
        self, config: PipelineConfig, conn: duckdb.DuckDBPyConnection
    ) -> None:
        self.config = config
        self.conn = conn

    def enrich_tier1(
        self, session_id: str, episodes: list[dict]
    ) -> list[FlameEvent]:
        """Read existing Tier 1 stub flame_events and upgrade using episode context.

        Args:
            session_id: Session to enrich stubs for.
            episodes: List of episode dicts with episode_id, orchestrator_action,
                reaction_label, outcome_type fields.

        Returns:
            List of enriched FlameEvent objects with detection_source='opeml'.
        """
        rows = self.conn.execute(
            """
            SELECT flame_event_id, marker_level, marker_type, evidence_excerpt,
                   axis_identified, prompt_number, human_id, source_episode_id,
                   session_event_ref, quality_score
            FROM flame_events
            WHERE session_id = ? AND detection_source = 'stub'
            """,
            [session_id],
        ).fetchall()

        if not rows:
            return []

        enriched: list[FlameEvent] = []
        for row in rows:
            (
                feid,
                ml,
                mt,
                ee,
                axis,
                pnum,
                hid,
                sep_id,
                ser,
                qs,
            ) = row

            # Find matching episode (if any)
            ep = self._find_episode(sep_id, episodes)
            new_level = ml
            flood_confirmed = False

            if ep:
                scope_paths = ep.get("orchestrator_action", {})
                if isinstance(scope_paths, str):
                    try:
                        scope_paths = json.loads(scope_paths)
                    except Exception:
                        scope_paths = {}

                scope_list = (
                    scope_paths.get("scope", [])
                    if isinstance(scope_paths, dict)
                    else []
                )
                reaction = ep.get("reaction_label", "")

                # Upgrade rules (heuristic)
                if ml == 0 and len(scope_list) >= 2:
                    new_level = 3  # L0 trunk + multi-scope -> L3 (cross-context)
                elif ml == 1 and ep.get("outcome_type") in (
                    "committed",
                    "success",
                ):
                    new_level = 4  # L1 causal + successful outcome -> L4
                elif ml == 2 and reaction in ("correct", "block"):
                    new_level = 5  # L2 assertive + correction -> L5

                # L6 upgrade: approve + axis + evidence suggests flood
                if (
                    reaction == "approve"
                    and axis
                    and ee
                    and len(ee) > 50
                ):
                    new_level = 6
                    flood_confirmed = True

            # CRITICAL: set flood_confirmed=True on L6+ upgrades
            if new_level >= 6:
                flood_confirmed = True

            enriched.append(
                FlameEvent(
                    flame_event_id=feid + "_enriched",
                    session_id=session_id,
                    human_id=hid,
                    prompt_number=pnum,
                    marker_level=new_level,
                    marker_type=(
                        mt + "_enriched" if new_level > ml else mt
                    ),
                    evidence_excerpt=ee,
                    quality_score=qs,
                    axis_identified=axis,
                    flood_confirmed=flood_confirmed,
                    subject="human",
                    detection_source="opeml",
                    source_episode_id=sep_id,
                    session_event_ref=ser,
                )
            )

        return enriched

    def _find_episode(
        self, episode_id: str | None, episodes: list[dict]
    ) -> dict | None:
        """Find episode dict by episode_id.

        Args:
            episode_id: Episode ID to search for.
            episodes: List of episode dicts.

        Returns:
            Matching episode dict, or None.
        """
        if not episode_id:
            return None
        for ep in episodes:
            if ep.get("episode_id") == episode_id:
                return ep
        return None

    def detect_ai_markers(
        self,
        session_id: str,
        episodes: list[dict],
        tagged_events: list[dict],
    ) -> list[FlameEvent]:
        """Detect DDF markers in AI (executor) text.

        Scans executor/assistant events for assertive causal claims (L2)
        and concretization floods (L6).

        Args:
            session_id: Session identifier.
            episodes: Episode dicts (currently unused, reserved for future use).
            tagged_events: List of tagged event dicts with actor and payload.

        Returns:
            List of FlameEvent objects with subject='ai'.
        """
        ai_events: list[FlameEvent] = []
        prompt_num = 0

        for evt in tagged_events:
            actor = evt.get("actor", "")
            if actor not in ("executor", "assistant"):
                continue

            text = (
                evt.get("payload", {}).get("common", {}).get("text", "")
            )
            if not text:
                continue

            prompt_num += 1

            # AI Level 2: assertive causal claim (spontaneous CCD by AI)
            if _ASSERTIVE_PAT.search(text):
                ai_events.append(
                    FlameEvent(
                        flame_event_id=FlameEvent.make_id(
                            session_id, prompt_num, "ai_l2_assertive"
                        ),
                        session_id=session_id,
                        marker_level=2,
                        marker_type="ai_assertive_causal",
                        evidence_excerpt=text[:200],
                        subject="ai",
                        detection_source="opeml",
                    )
                )

            # AI Level 6: Concretization Flood (3+ examples in one message)
            flood_matches = _FLOOD_PAT.findall(text)
            if len(flood_matches) >= 3:
                ai_events.append(
                    FlameEvent(
                        flame_event_id=FlameEvent.make_id(
                            session_id, prompt_num, "ai_l6_flood"
                        ),
                        session_id=session_id,
                        marker_level=6,
                        marker_type="ai_concretization_flood",
                        evidence_excerpt=text[:200],
                        flood_confirmed=True,
                        subject="ai",
                        detection_source="opeml",
                    )
                )

        return ai_events

    def deposit_level6(
        self,
        conn: duckdb.DuckDBPyConnection,
        events: list[FlameEvent],
    ) -> int:
        """Deposit Level 6+ flood_confirmed events to memory_candidates.

        Filters events on marker_level >= 6 AND flood_confirmed = True,
        then deposits each to memory_candidates. Marks deposited events
        in the flame_events table.

        Args:
            conn: DuckDB connection with memory_candidates table.
            events: FlameEvent objects to consider for deposit.

        Returns:
            Count of events successfully deposited.
        """
        count = 0
        for evt in events:
            if evt.marker_level >= 6 and evt.flood_confirmed:
                axis = evt.axis_identified or f"axis_from_{evt.marker_type}"
                scope_rule = (
                    f"Applies to sessions where this axis is active: "
                    f"{evt.marker_type}"
                )
                example = (
                    evt.evidence_excerpt
                    or "Detected via DDF Tier 2 enrichment"
                )

                candidate_id = deposit_to_memory_candidates(
                    conn=conn,
                    ccd_axis=axis,
                    scope_rule=scope_rule,
                    flood_example=example,
                    source_flame_event_id=evt.flame_event_id,
                    pipeline_component="ddf_tier2",
                    fidelity=2,
                )
                if candidate_id:
                    mark_deposited(conn, evt.flame_event_id)
                    count += 1
        return count
