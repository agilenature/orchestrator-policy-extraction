"""Edge generator for topological edge creation.

Transforms ConjunctiveTrigger detections into EdgeRecord candidates
with evidence and activation_condition populated from the triggering
episode context.

Exports:
    EdgeGenerator
"""
from __future__ import annotations

from itertools import combinations

from src.pipeline.ddf.topology.detector import ConjunctiveTrigger
from src.pipeline.ddf.topology.models import ActivationCondition, EdgeRecord


class EdgeGenerator:
    """Generates EdgeRecord candidates from conjunctive flame triggers.

    For each ConjunctiveTrigger, generates one EdgeRecord per axis pair
    (if >2 axes active, generates C(n,2) pairs). Each EdgeRecord carries:
    - evidence: {session_id, episode_id, flame_event_ids}
    - activation_condition: derived from triggering context
    - abstraction_level: from the triggering flame event
    - status: 'candidate' (requires human review to become 'active')
    """

    def generate(
        self,
        trigger: ConjunctiveTrigger,
        relationship_text: str | None = None,
        goal_type: list[str] | None = None,
        scope_prefix: str = "",
    ) -> list[EdgeRecord]:
        """Generate EdgeRecord candidates from a conjunctive trigger.

        Args:
            trigger: The ConjunctiveTrigger that qualified.
            relationship_text: Human-readable relationship description.
                If None, auto-generates from axis names.
            goal_type: Goal types for activation_condition. Defaults to ["any"].
            scope_prefix: Scope prefix for activation_condition.

        Returns:
            List of EdgeRecord candidates (one per axis pair).
        """
        axes = sorted(set(trigger.active_axes))
        if len(axes) < 2:
            return []

        evidence = {
            "session_id": trigger.session_id,
            "episode_id": trigger.episode_id,
            "flame_event_ids": [trigger.flame_event.flame_event_id],
        }

        activation = ActivationCondition(
            goal_type=goal_type or ["any"],
            scope_prefix=scope_prefix,
            min_axes_simultaneously_active=len(axes),
        )

        records = []
        for axis_a, axis_b in combinations(axes, 2):
            rel_text = relationship_text or (
                f"{axis_a} constrains {axis_b} when both "
                f"simultaneously active at abstraction level "
                f"{trigger.flame_event.marker_level}"
            )
            edge_id = EdgeRecord.make_id(axis_a, axis_b, rel_text)
            record = EdgeRecord(
                edge_id=edge_id,
                axis_a=axis_a,
                axis_b=axis_b,
                relationship_text=rel_text,
                activation_condition=activation,
                evidence=evidence,
                abstraction_level=trigger.flame_event.marker_level,
                status="candidate",
                trunk_quality=1.0,
                created_session_id=trigger.session_id,
            )
            records.append(record)

        return records
