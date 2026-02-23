"""Pool builder for identification review instances.

Sources IdentificationPoint instances from existing DuckDB tables for
each of the 35 identification point types across 8 pipeline layers.

Each instance carries all five decision-boundary externalization properties
(trigger, observation_state, action_taken, downstream_impact, provenance_pointer)
with traceable source references.

Design decisions:
- Uses LIMIT + ORDER BY RANDOM() in SQL for varied sampling
- Falls back gracefully when a source table has no rows
- max_per_point caps instances per point_id to prevent any single source dominating
- L5 reads from data/constraints.json (JSON file) since constraints are not in DuckDB
- L7 reads from episodes with non-null escalation columns (no separate escalation_events table)

Exports:
    PoolBuilder
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import duckdb

from src.pipeline.review.models import IdentificationLayer, IdentificationPoint


class PoolBuilder:
    """Sources IdentificationPoint instances from pipeline artifacts.

    Reads from existing DuckDB tables and JSON files to create reviewable
    instances covering all 35 identification point types.

    Args:
        conn: DuckDB connection to read source data from.
        max_per_point: Maximum instances per point_id.
        constraints_path: Path to constraints.json file for L5 data.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        max_per_point: int = 10,
        constraints_path: Optional[Path] = None,
    ):
        self.conn = conn
        self.max_per_point = max_per_point
        self.constraints_path = constraints_path or Path("data/constraints.json")

    def build(self) -> list[IdentificationPoint]:
        """Return pool covering all 35 point_ids, up to max_per_point each.

        Returns:
            List of IdentificationPoint instances spanning 8 layers.
        """
        instances: list[IdentificationPoint] = []
        instances.extend(self._build_l1())
        instances.extend(self._build_l2())
        instances.extend(self._build_l3())
        instances.extend(self._build_l4())
        instances.extend(self._build_l5())
        instances.extend(self._build_l6())
        instances.extend(self._build_l7())
        instances.extend(self._build_l8())
        return instances

    # --- Layer 1: Event filtering and actor assignment ---

    def _build_l1(self) -> list[IdentificationPoint]:
        """L1-1: Record meaningfulness, L1-2: Actor assignment."""
        points: list[IdentificationPoint] = []
        points.extend(self._build_l1_1())
        points.extend(self._build_l1_2())
        return points

    def _build_l1_1(self) -> list[IdentificationPoint]:
        """L1-1: Record meaningfulness -- is this event meaningful or noise?"""
        try:
            rows = self.conn.execute(f"""
                SELECT event_id, session_id, actor, event_type,
                       COALESCE(primary_tag, 'untagged') as tag,
                       source_ref
                FROM events
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"events:{row[0]}:L1-1",
                layer=IdentificationLayer.L1_EVENT_FILTER,
                point_id="L1-1",
                point_label="Record meaningfulness",
                pipeline_component="EventFilter",
                trigger=f"JSONL record ingested from session {row[1]}",
                observation_state=(
                    f"actor={row[2]}, event_type={row[3]}, tag={row[4]}"
                ),
                action_taken="Stored as meaningful event",
                downstream_impact="Event available for tagging (L2) and segmentation (L3)",
                provenance_pointer=f"{row[1]}:{row[0]}:events:{row[5]}",
                source_session_id=row[1],
                source_event_id=row[0],
            )
            for row in rows
        ]

    def _build_l1_2(self) -> list[IdentificationPoint]:
        """L1-2: Actor assignment -- orchestrator/tool/human/environment."""
        try:
            rows = self.conn.execute(f"""
                SELECT event_id, session_id, actor, event_type, source_ref
                FROM events
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"events:{row[0]}:L1-2",
                layer=IdentificationLayer.L1_EVENT_FILTER,
                point_id="L1-2",
                point_label="Actor assignment",
                pipeline_component="EventFilter",
                trigger=f"JSONL record from session {row[1]} with event_type={row[3]}",
                observation_state=f"event_type={row[3]}, source_ref={row[4]}",
                action_taken=f"actor={row[2]}",
                downstream_impact="Actor field used by tagger (L2) for label selection",
                provenance_pointer=f"{row[1]}:{row[0]}:events:{row[4]}",
                source_session_id=row[1],
                source_event_id=row[0],
            )
            for row in rows
        ]

    # --- Layer 2: Tagging ---

    def _build_l2(self) -> list[IdentificationPoint]:
        """L2-1 through L2-5: Tagging classification acts."""
        points: list[IdentificationPoint] = []
        points.extend(self._build_l2_1())
        points.extend(self._build_l2_2())
        points.extend(self._build_l2_3())
        points.extend(self._build_l2_4())
        points.extend(self._build_l2_5())
        return points

    def _build_l2_1(self) -> list[IdentificationPoint]:
        """L2-1: Primary label assignment."""
        try:
            rows = self.conn.execute(f"""
                SELECT event_id, session_id, actor, event_type,
                       primary_tag, primary_tag_confidence, source_ref
                FROM events
                WHERE primary_tag IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"events:{row[0]}:L2-1",
                layer=IdentificationLayer.L2_TAGGING,
                point_id="L2-1",
                point_label="Primary label",
                pipeline_component="EventTagger",
                trigger=f"Event {row[3]} from actor={row[2]} requires classification",
                observation_state=f"actor={row[2]}, event_type={row[3]}",
                action_taken=f"primary_tag={row[4]} (confidence={row[5]:.2f})",
                downstream_impact="Primary tag drives episode population mode/risk inference",
                provenance_pointer=f"{row[1]}:{row[0]}:events:{row[6]}",
                source_session_id=row[1],
                source_event_id=row[0],
            )
            for row in rows
        ]

    def _build_l2_2(self) -> list[IdentificationPoint]:
        """L2-2: Confidence score."""
        try:
            rows = self.conn.execute(f"""
                SELECT event_id, session_id, primary_tag,
                       primary_tag_confidence, source_ref
                FROM events
                WHERE primary_tag_confidence IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"events:{row[0]}:L2-2",
                layer=IdentificationLayer.L2_TAGGING,
                point_id="L2-2",
                point_label="Confidence score",
                pipeline_component="EventTagger",
                trigger=f"Primary tag {row[2]} assigned, confidence required",
                observation_state=f"tag={row[2]}, raw_confidence={row[3]:.3f}",
                action_taken=f"confidence={row[3]:.2f}",
                downstream_impact="Confidence affects label resolution (min 0.5 threshold)",
                provenance_pointer=f"{row[1]}:{row[0]}:events:{row[4]}",
                source_session_id=row[1],
                source_event_id=row[0],
            )
            for row in rows
        ]

    def _build_l2_3(self) -> list[IdentificationPoint]:
        """L2-3: Secondary labels."""
        try:
            rows = self.conn.execute(f"""
                SELECT event_id, session_id, primary_tag,
                       secondary_tags, source_ref
                FROM events
                WHERE secondary_tags IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"events:{row[0]}:L2-3",
                layer=IdentificationLayer.L2_TAGGING,
                point_id="L2-3",
                point_label="Secondary labels",
                pipeline_component="EventTagger",
                trigger=f"Multi-pass tagging produced candidates beyond primary={row[2]}",
                observation_state=f"primary={row[2]}, secondary_tags={row[3]}",
                action_taken=f"secondary_tags={row[3]}",
                downstream_impact="Secondary labels provide alternative classifications for review",
                provenance_pointer=f"{row[1]}:{row[0]}:events:{row[4]}",
                source_session_id=row[1],
                source_event_id=row[0],
            )
            for row in rows
        ]

    def _build_l2_4(self) -> list[IdentificationPoint]:
        """L2-4: Mode inference from tagged events."""
        try:
            rows = self.conn.execute(f"""
                SELECT e.episode_id, e.session_id, e.segment_id, e.mode,
                       e.reaction_label
                FROM episodes e
                WHERE e.mode IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L2-4",
                layer=IdentificationLayer.L2_TAGGING,
                point_id="L2-4",
                point_label="Mode inference",
                pipeline_component="EpisodePopulator",
                trigger=f"Episode {row[0]} requires mode assignment",
                observation_state=f"segment={row[2]}, reaction_label={row[4]}",
                action_taken=f"mode={row[3]}",
                downstream_impact="Mode determines constraint scope matching and shadow mode evaluation",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l2_5(self) -> list[IdentificationPoint]:
        """L2-5: Risk assessment."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id, risk, mode
                FROM episodes
                WHERE risk IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L2-5",
                layer=IdentificationLayer.L2_TAGGING,
                point_id="L2-5",
                point_label="Risk assessment",
                pipeline_component="EpisodePopulator",
                trigger=f"Episode {row[0]} requires risk assessment",
                observation_state=f"mode={row[4]}, segment={row[2]}",
                action_taken=f"risk={row[3]}",
                downstream_impact="Risk level affects constraint evaluation severity and shadow mode danger detection",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    # --- Layer 3: Segmentation ---

    def _build_l3(self) -> list[IdentificationPoint]:
        """L3-1 through L3-6: Segmentation boundary decisions."""
        points: list[IdentificationPoint] = []
        points.extend(self._build_l3_1())
        points.extend(self._build_l3_2())
        points.extend(self._build_l3_3())
        points.extend(self._build_l3_4())
        points.extend(self._build_l3_5())
        points.extend(self._build_l3_6())
        return points

    def _build_l3_1(self) -> list[IdentificationPoint]:
        """L3-1: Episode start trigger."""
        try:
            rows = self.conn.execute(f"""
                SELECT segment_id, session_id, start_event_id,
                       start_trigger, start_ts
                FROM episode_segments
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episode_segments:{row[0]}:L3-1",
                layer=IdentificationLayer.L3_SEGMENTATION,
                point_id="L3-1",
                point_label="Episode start",
                pipeline_component="Segmenter",
                trigger=f"Event {row[2]} evaluated as potential episode boundary",
                observation_state=f"start_event={row[2]}, ts={row[4]}",
                action_taken=f"start_trigger={row[3]}",
                downstream_impact="Episode boundary determines which events are grouped for population",
                provenance_pointer=f"{row[1]}:{row[2]}:episode_segments:{row[0]}",
                source_session_id=row[1],
                source_event_id=row[2],
            )
            for row in rows
        ]

    def _build_l3_2(self) -> list[IdentificationPoint]:
        """L3-2: Episode close trigger."""
        try:
            rows = self.conn.execute(f"""
                SELECT segment_id, session_id, end_event_id,
                       end_trigger, end_ts
                FROM episode_segments
                WHERE end_trigger IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episode_segments:{row[0]}:L3-2",
                layer=IdentificationLayer.L3_SEGMENTATION,
                point_id="L3-2",
                point_label="Episode close",
                pipeline_component="Segmenter",
                trigger=f"Event {row[2]} evaluated as potential episode end",
                observation_state=f"end_event={row[2]}, ts={row[4]}",
                action_taken=f"end_trigger={row[3]}",
                downstream_impact="End trigger determines episode completeness and outcome extraction",
                provenance_pointer=f"{row[1]}:{row[2]}:episode_segments:{row[0]}",
                source_session_id=row[1],
                source_event_id=row[2],
            )
            for row in rows
        ]

    def _build_l3_3(self) -> list[IdentificationPoint]:
        """L3-3: Timeout expiry boundaries."""
        try:
            rows = self.conn.execute(f"""
                SELECT segment_id, session_id, end_event_id,
                       end_trigger, start_ts, end_ts
                FROM episode_segments
                WHERE end_trigger = 'timeout'
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episode_segments:{row[0]}:L3-3",
                layer=IdentificationLayer.L3_SEGMENTATION,
                point_id="L3-3",
                point_label="Timeout expiry",
                pipeline_component="Segmenter",
                trigger=f"30-min timeout reached between events in session {row[1]}",
                observation_state=f"start_ts={row[4]}, end_ts={row[5]}",
                action_taken="end_trigger=timeout",
                downstream_impact="Timeout boundary may split logically contiguous work",
                provenance_pointer=f"{row[1]}:{row[2]}:episode_segments:{row[0]}",
                source_session_id=row[1],
                source_event_id=row[2],
            )
            for row in rows
        ]

    def _build_l3_4(self) -> list[IdentificationPoint]:
        """L3-4: Episode supersede (start trigger overriding an open episode)."""
        try:
            rows = self.conn.execute(f"""
                SELECT segment_id, session_id, start_event_id,
                       start_trigger, outcome
                FROM episode_segments
                WHERE outcome = 'superseded' OR outcome IS NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episode_segments:{row[0]}:L3-4",
                layer=IdentificationLayer.L3_SEGMENTATION,
                point_id="L3-4",
                point_label="Episode supersede",
                pipeline_component="Segmenter",
                trigger=f"New start trigger {row[3]} while previous episode open",
                observation_state=f"start_trigger={row[3]}, outcome={row[4]}",
                action_taken=f"outcome={row[4]} (previous episode closed by supersede)",
                downstream_impact="Superseded episodes may have incomplete observation/outcome",
                provenance_pointer=f"{row[1]}:{row[2]}:episode_segments:{row[0]}",
                source_session_id=row[1],
                source_event_id=row[2],
            )
            for row in rows
        ]

    def _build_l3_5(self) -> list[IdentificationPoint]:
        """L3-5: Outcome determination."""
        try:
            rows = self.conn.execute(f"""
                SELECT segment_id, session_id, end_event_id,
                       outcome, event_count, complexity
                FROM episode_segments
                WHERE outcome IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episode_segments:{row[0]}:L3-5",
                layer=IdentificationLayer.L3_SEGMENTATION,
                point_id="L3-5",
                point_label="Outcome determination",
                pipeline_component="Segmenter",
                trigger=f"Segment {row[0]} closed with {row[4]} events",
                observation_state=f"event_count={row[4]}, complexity={row[5]}",
                action_taken=f"outcome={row[3]}",
                downstream_impact="Outcome feeds episode population and constraint extraction",
                provenance_pointer=f"{row[1]}:{row[2]}:episode_segments:{row[0]}",
                source_session_id=row[1],
                source_event_id=row[2],
            )
            for row in rows
        ]

    def _build_l3_6(self) -> list[IdentificationPoint]:
        """L3-6: Complexity classification."""
        try:
            rows = self.conn.execute(f"""
                SELECT segment_id, session_id, start_event_id,
                       complexity, event_count, interruption_count,
                       context_switches
                FROM episode_segments
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episode_segments:{row[0]}:L3-6",
                layer=IdentificationLayer.L3_SEGMENTATION,
                point_id="L3-6",
                point_label="Complexity",
                pipeline_component="Segmenter",
                trigger=f"Segment {row[0]} requires complexity classification",
                observation_state=(
                    f"event_count={row[4]}, interruptions={row[5]}, "
                    f"context_switches={row[6]}"
                ),
                action_taken=f"complexity={row[3]}",
                downstream_impact="Complexity affects episode weight in shadow mode evaluation",
                provenance_pointer=f"{row[1]}:{row[2]}:episode_segments:{row[0]}",
                source_session_id=row[1],
                source_event_id=row[2],
            )
            for row in rows
        ]

    # --- Layer 4: Episode population ---

    def _build_l4(self) -> list[IdentificationPoint]:
        """L4-1 through L4-7: Episode population acts."""
        points: list[IdentificationPoint] = []
        points.extend(self._build_l4_1())
        points.extend(self._build_l4_2())
        points.extend(self._build_l4_3())
        points.extend(self._build_l4_4())
        points.extend(self._build_l4_5())
        points.extend(self._build_l4_6())
        points.extend(self._build_l4_7())
        return points

    def _build_l4_1(self) -> list[IdentificationPoint]:
        """L4-1: Observation extraction."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       observation.context.recent_summary as obs_summary
                FROM episodes
                WHERE observation IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-1",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-1",
                point_label="Observation extraction",
                pipeline_component="EpisodePopulator",
                trigger=f"Segment {row[2]} completed, episode requires observation",
                observation_state=f"obs_summary={str(row[3])[:200]}",
                action_taken="Observation struct populated from segment events",
                downstream_impact="Observation quality determines constraint extraction accuracy",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l4_2(self) -> list[IdentificationPoint]:
        """L4-2: Action extraction."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       orchestrator_action
                FROM episodes
                WHERE orchestrator_action IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-2",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-2",
                point_label="Action extraction",
                pipeline_component="EpisodePopulator",
                trigger=f"Episode {row[0]} requires orchestrator action extraction",
                observation_state=f"orchestrator_action={str(row[3])[:200]}",
                action_taken="Orchestrator action JSON populated from tagged events",
                downstream_impact="Action accuracy determines constraint applicability assessment",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l4_3(self) -> list[IdentificationPoint]:
        """L4-3: Outcome extraction."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       outcome_type, outcome
                FROM episodes
                WHERE outcome IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-3",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-3",
                point_label="Outcome extraction",
                pipeline_component="EpisodePopulator",
                trigger=f"Episode {row[0]} closed, outcome required",
                observation_state=f"outcome_type={row[3]}, outcome={str(row[4])[:200]}",
                action_taken=f"outcome_type={row[3]}",
                downstream_impact="Outcome type drives reaction labeling and constraint extraction",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l4_4(self) -> list[IdentificationPoint]:
        """L4-4: Reaction label."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       reaction_label, reaction_confidence
                FROM episodes
                WHERE reaction_label IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-4",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-4",
                point_label="Reaction label",
                pipeline_component="ReactionLabeler",
                trigger=f"Episode {row[0]} outcome determined, reaction needed",
                observation_state=f"segment={row[2]}, raw_label={row[3]}",
                action_taken=f"reaction_label={row[3]} (confidence={row[4]:.2f})",
                downstream_impact="Reaction label drives constraint extraction (correct/block -> constraint)",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l4_5(self) -> list[IdentificationPoint]:
        """L4-5: Reaction confidence."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       reaction_label, reaction_confidence
                FROM episodes
                WHERE reaction_confidence IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-5",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-5",
                point_label="Reaction confidence",
                pipeline_component="ReactionLabeler",
                trigger=f"Reaction label {row[3]} assigned, confidence required",
                observation_state=f"reaction_label={row[3]}",
                action_taken=f"reaction_confidence={row[4]:.2f}",
                downstream_impact="Low confidence reactions may be excluded from constraint extraction",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l4_6(self) -> list[IdentificationPoint]:
        """L4-6: Episode mode assignment."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id, mode, risk
                FROM episodes
                WHERE mode IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-6",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-6",
                point_label="Episode mode",
                pipeline_component="EpisodePopulator",
                trigger=f"Episode {row[0]} requires operational mode assignment",
                observation_state=f"risk={row[4]}, segment={row[2]}",
                action_taken=f"mode={row[3]}",
                downstream_impact="Mode determines constraint scope matching and evaluation strategy",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l4_7(self) -> list[IdentificationPoint]:
        """L4-7: Risk level assignment."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id, risk, mode
                FROM episodes
                WHERE risk IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L4-7",
                layer=IdentificationLayer.L4_EPISODE_POPULATION,
                point_id="L4-7",
                point_label="Risk level",
                pipeline_component="EpisodePopulator",
                trigger=f"Episode {row[0]} requires risk level assignment",
                observation_state=f"mode={row[4]}, segment={row[2]}",
                action_taken=f"risk={row[3]}",
                downstream_impact="Risk level affects constraint evaluation severity thresholds",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[2]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    # --- Layer 5: Constraint extraction ---

    def _build_l5(self) -> list[IdentificationPoint]:
        """L5-1 through L5-5: Constraint extraction acts.

        Reads from data/constraints.json (JSON file) since constraints
        are not stored in DuckDB.
        """
        constraints = self._load_constraints()
        if not constraints:
            return []

        points: list[IdentificationPoint] = []
        points.extend(self._build_l5_1(constraints))
        points.extend(self._build_l5_2(constraints))
        points.extend(self._build_l5_3(constraints))
        points.extend(self._build_l5_4(constraints))
        points.extend(self._build_l5_5(constraints))
        return points

    def _load_constraints(self) -> list[dict]:
        """Load constraints from JSON file."""
        try:
            with open(self.constraints_path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _build_l5_1(self, constraints: list[dict]) -> list[IdentificationPoint]:
        """L5-1: Constraint presence detection."""
        import random

        sample = random.sample(constraints, min(self.max_per_point, len(constraints)))
        return [
            IdentificationPoint(
                instance_id=f"constraints:{c['constraint_id']}:L5-1",
                layer=IdentificationLayer.L5_CONSTRAINT_EXTRACTION,
                point_id="L5-1",
                point_label="Constraint presence",
                pipeline_component="ConstraintExtractor",
                trigger=f"Episode contained correction/block pattern",
                observation_state=f"text={c.get('text', '')[:200]}",
                action_taken="Constraint extracted and stored",
                downstream_impact="Constraint enters store for future session evaluation",
                provenance_pointer=(
                    f"{c.get('source_episode_id', 'unknown')}:"
                    f"{c['constraint_id']}:constraints.json"
                ),
                source_episode_id=c.get("source_episode_id"),
            )
            for c in sample
        ]

    def _build_l5_2(self, constraints: list[dict]) -> list[IdentificationPoint]:
        """L5-2: Constraint text extraction."""
        import random

        sample = random.sample(constraints, min(self.max_per_point, len(constraints)))
        return [
            IdentificationPoint(
                instance_id=f"constraints:{c['constraint_id']}:L5-2",
                layer=IdentificationLayer.L5_CONSTRAINT_EXTRACTION,
                point_id="L5-2",
                point_label="Constraint text",
                pipeline_component="ConstraintExtractor",
                trigger=f"Constraint {c['constraint_id']} requires text extraction",
                observation_state=f"raw_text={c.get('text', '')[:200]}",
                action_taken=f"text={c.get('text', '')[:100]}",
                downstream_impact="Constraint text used for scope matching and detection hints",
                provenance_pointer=(
                    f"{c.get('source_episode_id', 'unknown')}:"
                    f"{c['constraint_id']}:constraints.json"
                ),
                source_episode_id=c.get("source_episode_id"),
            )
            for c in sample
        ]

    def _build_l5_3(self, constraints: list[dict]) -> list[IdentificationPoint]:
        """L5-3: Scope assignment."""
        import random

        sample = random.sample(constraints, min(self.max_per_point, len(constraints)))
        return [
            IdentificationPoint(
                instance_id=f"constraints:{c['constraint_id']}:L5-3",
                layer=IdentificationLayer.L5_CONSTRAINT_EXTRACTION,
                point_id="L5-3",
                point_label="Scope assignment",
                pipeline_component="ConstraintExtractor",
                trigger=f"Constraint {c['constraint_id']} requires scope",
                observation_state=f"text={c.get('text', '')[:100]}, scope={c.get('scope', {})}",
                action_taken=f"scope={c.get('scope', {})}",
                downstream_impact="Scope determines which sessions/files this constraint applies to",
                provenance_pointer=(
                    f"{c.get('source_episode_id', 'unknown')}:"
                    f"{c['constraint_id']}:constraints.json"
                ),
                source_episode_id=c.get("source_episode_id"),
            )
            for c in sample
        ]

    def _build_l5_4(self, constraints: list[dict]) -> list[IdentificationPoint]:
        """L5-4: Severity assignment."""
        import random

        sample = random.sample(constraints, min(self.max_per_point, len(constraints)))
        return [
            IdentificationPoint(
                instance_id=f"constraints:{c['constraint_id']}:L5-4",
                layer=IdentificationLayer.L5_CONSTRAINT_EXTRACTION,
                point_id="L5-4",
                point_label="Severity assignment",
                pipeline_component="ConstraintExtractor",
                trigger=f"Constraint {c['constraint_id']} requires severity level",
                observation_state=f"text={c.get('text', '')[:100]}",
                action_taken=f"severity={c.get('severity', 'unknown')}",
                downstream_impact="Severity determines enforcement behavior (warning vs requires_approval vs forbidden)",
                provenance_pointer=(
                    f"{c.get('source_episode_id', 'unknown')}:"
                    f"{c['constraint_id']}:constraints.json"
                ),
                source_episode_id=c.get("source_episode_id"),
            )
            for c in sample
        ]

    def _build_l5_5(self, constraints: list[dict]) -> list[IdentificationPoint]:
        """L5-5: Duplicate detection."""
        import random

        # Only include constraints that have examples (enriched duplicates)
        enriched = [c for c in constraints if len(c.get("examples", [])) > 1]
        if not enriched:
            enriched = constraints
        sample = random.sample(enriched, min(self.max_per_point, len(enriched)))
        return [
            IdentificationPoint(
                instance_id=f"constraints:{c['constraint_id']}:L5-5",
                layer=IdentificationLayer.L5_CONSTRAINT_EXTRACTION,
                point_id="L5-5",
                point_label="Duplicate detection",
                pipeline_component="ConstraintStore",
                trigger=f"New constraint candidate checked against {len(constraints)} existing",
                observation_state=(
                    f"hints={c.get('detection_hints', [])}, "
                    f"examples_count={len(c.get('examples', []))}"
                ),
                action_taken=(
                    f"{'Enriched existing' if len(c.get('examples', [])) > 1 else 'Added as new'}"
                ),
                downstream_impact="Duplicate detection prevents constraint inflation",
                provenance_pointer=(
                    f"{c.get('source_episode_id', 'unknown')}:"
                    f"{c['constraint_id']}:constraints.json"
                ),
                source_episode_id=c.get("source_episode_id"),
            )
            for c in sample
        ]

    # --- Layer 6: Constraint evaluation ---

    def _build_l6(self) -> list[IdentificationPoint]:
        """L6-1 through L6-3: Constraint evaluation acts."""
        points: list[IdentificationPoint] = []
        points.extend(self._build_l6_1())
        points.extend(self._build_l6_2())
        points.extend(self._build_l6_3())
        return points

    def _build_l6_1(self) -> list[IdentificationPoint]:
        """L6-1: Constraint honored/violated determination."""
        try:
            rows = self.conn.execute(f"""
                SELECT session_id, constraint_id, eval_state,
                       scope_matched
                FROM session_constraint_eval
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"session_constraint_eval:{row[0]}:{row[1]}:L6-1",
                layer=IdentificationLayer.L6_CONSTRAINT_EVALUATION,
                point_id="L6-1",
                point_label="Constraint honored",
                pipeline_component="DurabilityEvaluator",
                trigger=f"Constraint {row[1]} evaluated in session {row[0]}",
                observation_state=f"constraint_id={row[1]}, scope_matched={row[3]}",
                action_taken=f"eval_state={row[2]}",
                downstream_impact="Violated constraints trigger amnesia detection and durability scoring",
                provenance_pointer=(
                    f"{row[0]}:{row[1]}:session_constraint_eval"
                ),
                source_session_id=row[0],
            )
            for row in rows
        ]

    def _build_l6_2(self) -> list[IdentificationPoint]:
        """L6-2: Evidence extraction for constraint evaluation."""
        try:
            rows = self.conn.execute(f"""
                SELECT session_id, constraint_id, eval_state,
                       evidence_json
                FROM session_constraint_eval
                WHERE evidence_json IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"session_constraint_eval:{row[0]}:{row[1]}:L6-2",
                layer=IdentificationLayer.L6_CONSTRAINT_EVALUATION,
                point_id="L6-2",
                point_label="Evidence extraction",
                pipeline_component="DurabilityEvaluator",
                trigger=f"Eval state {row[2]} for constraint {row[1]} requires evidence",
                observation_state=f"evidence={str(row[3])[:200]}",
                action_taken=f"Evidence extracted: {str(row[3])[:100]}",
                downstream_impact="Evidence quality determines amnesia detection accuracy",
                provenance_pointer=(
                    f"{row[0]}:{row[1]}:session_constraint_eval"
                ),
                source_session_id=row[0],
            )
            for row in rows
        ]

    def _build_l6_3(self) -> list[IdentificationPoint]:
        """L6-3: Amnesia detection."""
        try:
            rows = self.conn.execute(f"""
                SELECT amnesia_id, session_id, constraint_id,
                       severity, constraint_type
                FROM amnesia_events
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"amnesia_events:{row[0]}:L6-3",
                layer=IdentificationLayer.L6_CONSTRAINT_EVALUATION,
                point_id="L6-3",
                point_label="Amnesia detection",
                pipeline_component="AmnesiaDetector",
                trigger=f"Constraint {row[2]} evaluated as forgotten in session {row[1]}",
                observation_state=(
                    f"constraint_type={row[4]}, severity={row[3]}"
                ),
                action_taken=f"Amnesia event recorded (severity={row[3]})",
                downstream_impact="Amnesia events measure cross-session decision durability",
                provenance_pointer=f"{row[1]}:{row[0]}:amnesia_events:{row[2]}",
                source_session_id=row[1],
            )
            for row in rows
        ]

    # --- Layer 7: Escalation detection ---

    def _build_l7(self) -> list[IdentificationPoint]:
        """L7-1 through L7-4: Escalation detection acts.

        Reads from episodes table escalation columns (no separate
        escalation_events table exists).
        """
        points: list[IdentificationPoint] = []
        points.extend(self._build_l7_1())
        points.extend(self._build_l7_2())
        points.extend(self._build_l7_3())
        points.extend(self._build_l7_4())
        return points

    def _build_l7_1(self) -> list[IdentificationPoint]:
        """L7-1: Block event detection."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       escalate_block_event_ref
                FROM episodes
                WHERE escalate_block_event_ref IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L7-1",
                layer=IdentificationLayer.L7_ESCALATION_DETECTION,
                point_id="L7-1",
                point_label="Block event",
                pipeline_component="EscalationDetector",
                trigger=f"Episode {row[0]} contains potential block event",
                observation_state=f"block_event_ref={row[3]}",
                action_taken="Block event detected and linked to episode",
                downstream_impact="Block events are the first signal of an escalation sequence",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[3]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l7_2(self) -> list[IdentificationPoint]:
        """L7-2: Bypass event detection."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       escalate_bypass_event_ref
                FROM episodes
                WHERE escalate_bypass_event_ref IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L7-2",
                layer=IdentificationLayer.L7_ESCALATION_DETECTION,
                point_id="L7-2",
                point_label="Bypass event",
                pipeline_component="EscalationDetector",
                trigger=f"Episode {row[0]} contains potential bypass event",
                observation_state=f"bypass_event_ref={row[3]}",
                action_taken="Bypass event detected and linked to episode",
                downstream_impact="Bypass following block forms valid escalation sequence",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[3]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l7_3(self) -> list[IdentificationPoint]:
        """L7-3: Valid escalation sequence (block -> bypass)."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       escalate_block_event_ref, escalate_bypass_event_ref,
                       escalate_approval_status
                FROM episodes
                WHERE escalate_block_event_ref IS NOT NULL
                  AND escalate_bypass_event_ref IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L7-3",
                layer=IdentificationLayer.L7_ESCALATION_DETECTION,
                point_id="L7-3",
                point_label="Valid escalation sequence",
                pipeline_component="EscalationDetector",
                trigger=f"Both block and bypass detected in episode {row[0]}",
                observation_state=(
                    f"block={row[3]}, bypass={row[4]}, "
                    f"approval={row[5]}"
                ),
                action_taken=f"Escalation sequence validated (approval={row[5]})",
                downstream_impact="Valid escalation sequences generate O_ESC tags and constraint candidates",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[3]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    def _build_l7_4(self) -> list[IdentificationPoint]:
        """L7-4: Constraint bypassed identification."""
        try:
            rows = self.conn.execute(f"""
                SELECT episode_id, session_id, segment_id,
                       escalate_bypassed_constraint_id,
                       escalate_confidence
                FROM episodes
                WHERE escalate_bypassed_constraint_id IS NOT NULL
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"episodes:{row[0]}:L7-4",
                layer=IdentificationLayer.L7_ESCALATION_DETECTION,
                point_id="L7-4",
                point_label="Constraint bypassed",
                pipeline_component="EscalationDetector",
                trigger=f"Bypass in episode {row[0]} linked to specific constraint",
                observation_state=(
                    f"bypassed_constraint={row[3]}, "
                    f"confidence={row[4]}"
                ),
                action_taken=f"Constraint {row[3]} identified as bypassed",
                downstream_impact="Bypassed constraint affects durability scoring and amnesia detection",
                provenance_pointer=f"{row[1]}:{row[0]}:episodes:{row[3]}",
                source_session_id=row[1],
                source_episode_id=row[0],
            )
            for row in rows
        ]

    # --- Layer 8: Policy feedback ---

    def _build_l8(self) -> list[IdentificationPoint]:
        """L8-1 through L8-3: Policy feedback acts."""
        points: list[IdentificationPoint] = []
        points.extend(self._build_l8_1())
        points.extend(self._build_l8_2())
        points.extend(self._build_l8_3())
        return points

    def _build_l8_1(self) -> list[IdentificationPoint]:
        """L8-1: Policy recommendation suppression."""
        try:
            rows = self.conn.execute(f"""
                SELECT error_id, session_id, episode_id, error_type,
                       constraint_id, recommendation_mode
                FROM policy_error_events
                WHERE error_type = 'suppressed'
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"policy_error_events:{row[0]}:L8-1",
                layer=IdentificationLayer.L8_POLICY_FEEDBACK,
                point_id="L8-1",
                point_label="Suppression",
                pipeline_component="PolicyViolationChecker",
                trigger=f"Policy recommendation generated for episode {row[2]}",
                observation_state=(
                    f"constraint={row[4]}, mode={row[5]}"
                ),
                action_taken=f"Recommendation suppressed (error_type={row[3]})",
                downstream_impact="Suppressed recommendations are invisible to the user",
                provenance_pointer=(
                    f"{row[1]}:{row[0]}:policy_error_events:{row[4]}"
                ),
                source_session_id=row[1],
                source_episode_id=row[2],
            )
            for row in rows
        ]

    def _build_l8_2(self) -> list[IdentificationPoint]:
        """L8-2: Surface decision (surfaced-and-blocked)."""
        try:
            rows = self.conn.execute(f"""
                SELECT error_id, session_id, episode_id, error_type,
                       constraint_id, recommendation_mode
                FROM policy_error_events
                WHERE error_type = 'surfaced_and_blocked'
                ORDER BY RANDOM()
                LIMIT {self.max_per_point}
            """).fetchall()
        except Exception:
            return []

        return [
            IdentificationPoint(
                instance_id=f"policy_error_events:{row[0]}:L8-2",
                layer=IdentificationLayer.L8_POLICY_FEEDBACK,
                point_id="L8-2",
                point_label="Surface decision",
                pipeline_component="PolicyViolationChecker",
                trigger=f"Policy violation detected for episode {row[2]}",
                observation_state=(
                    f"constraint={row[4]}, mode={row[5]}"
                ),
                action_taken=f"Surfaced and blocked (error_type={row[3]})",
                downstream_impact="Surfaced violations create visible policy feedback for the user",
                provenance_pointer=(
                    f"{row[1]}:{row[0]}:policy_error_events:{row[4]}"
                ),
                source_session_id=row[1],
                source_episode_id=row[2],
            )
            for row in rows
        ]

    def _build_l8_3(self) -> list[IdentificationPoint]:
        """L8-3: Duplicate detection (policy vs human-sourced constraint)."""
        # L8-3 uses constraints.json to find policy_feedback type constraints
        # that may duplicate human_correction constraints
        constraints = self._load_constraints()
        policy_constraints = [
            c for c in constraints if c.get("type") == "policy_feedback"
        ]
        if not policy_constraints:
            return []

        import random

        sample = random.sample(
            policy_constraints,
            min(self.max_per_point, len(policy_constraints)),
        )
        return [
            IdentificationPoint(
                instance_id=f"constraints:{c['constraint_id']}:L8-3",
                layer=IdentificationLayer.L8_POLICY_FEEDBACK,
                point_id="L8-3",
                point_label="Duplicate detection",
                pipeline_component="PolicyFeedbackExtractor",
                trigger="Policy-generated constraint checked against human-sourced constraints",
                observation_state=(
                    f"hints={c.get('detection_hints', [])}, "
                    f"type={c.get('type')}"
                ),
                action_taken=(
                    f"{'Superseded existing' if c.get('supersedes') else 'Added as new'}"
                ),
                downstream_impact="Duplicate policy constraints inflate the constraint store",
                provenance_pointer=(
                    f"{c.get('source_episode_id', 'unknown')}:"
                    f"{c['constraint_id']}:constraints.json"
                ),
                source_episode_id=c.get("source_episode_id"),
            )
            for c in sample
        ]
