"""Staining pipeline: retrospective premise invalidation from amnesia events.

When OPE Layer 5 (AmnesiaDetector) finds constraint violations, premises that
relied on the violated constraint are marked stained. Staining propagates
through derivation chains for Stolen Concept detection: if a parent premise
is stained, all child premises that derive from it are also stained.

Three staining triggers:
  1. Amnesia events: premise validated_by references a violated constraint_id
  2. Propagation: parent premise in derivation_chain is stained (Stolen Concept)
  3. Policy violation: premise claim contradicts a known constraint

Exports:
    StainingPipeline: Staining from amnesia + propagation + policy violation
"""

from __future__ import annotations

import json

from src.pipeline.durability.amnesia import AmnesiaEvent
from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry


class StainingPipeline:
    """Retrospective staining pipeline for premise invalidation.

    Stains premises when:
      - AmnesiaDetector produces violations for constraints referenced
        in a premise's validated_by field
      - A parent premise in derivation_chain is already stained
        (Stolen Concept detection, max depth 20)
      - A premise claim contradicts a known constraint (policy violation)

    Args:
        registry: PremiseRegistry instance for premise lookups and staining.
    """

    def __init__(self, registry: PremiseRegistry) -> None:
        self._registry = registry

    def stain_from_amnesia(
        self, amnesia_events: list[AmnesiaEvent]
    ) -> list[str]:
        """Stain premises whose validated_by references violated constraints.

        For each AmnesiaEvent, finds all premises in the same session and
        checks if any premise's validated_by text mentions the violated
        constraint_id (substring check).

        Args:
            amnesia_events: List of AmnesiaEvent objects from AmnesiaDetector.

        Returns:
            List of stained premise_ids.
        """
        stained_ids: list[str] = []

        for event in amnesia_events:
            # Get all premises for the session
            session_premises = self._registry.get_by_session(event.session_id)

            for premise in session_premises:
                # Skip already stained premises
                if self._is_stained(premise):
                    continue

                # Check if validated_by references the violated constraint
                if premise.validated_by and event.constraint_id in premise.validated_by:
                    self._registry.stain(
                        premise_id=premise.premise_id,
                        stained_by=f"amnesia:{event.amnesia_id}",
                        ground_truth_pointer={
                            "amnesia_id": event.amnesia_id,
                            "constraint_id": event.constraint_id,
                            "session_id": event.session_id,
                        },
                    )
                    stained_ids.append(premise.premise_id)

        return stained_ids

    def propagate_staining(self) -> list[str]:
        """Propagate staining through derivation chains (Stolen Concept detection).

        When a parent premise is stained, all child premises whose
        derivation_chain contains the parent's premise_id are also stained.
        Uses a visited set and max depth of 20 to prevent infinite loops.

        Returns:
            List of newly stained premise_ids from propagation.
        """
        newly_stained: list[str] = []
        visited: set[str] = set()
        max_depth = 20

        # Start with all currently stained premises
        stained_premises = self._registry.get_stained()
        frontier = [p.premise_id for p in stained_premises]

        depth = 0
        while frontier and depth < max_depth:
            next_frontier: list[str] = []
            depth += 1

            for parent_id in frontier:
                if parent_id in visited:
                    continue
                visited.add(parent_id)

                # Find children: premises whose derivation_chain contains parent_id
                children = self._find_children(parent_id)

                for child in children:
                    if child.premise_id in visited:
                        continue
                    if self._is_stained(child):
                        continue

                    self._registry.stain(
                        premise_id=child.premise_id,
                        stained_by=f"propagation:{parent_id}",
                        ground_truth_pointer={
                            "parent_premise_id": parent_id,
                            "propagation_depth": depth,
                        },
                    )
                    newly_stained.append(child.premise_id)
                    next_frontier.append(child.premise_id)

            frontier = next_frontier

        return newly_stained

    def stain_from_policy_violation(
        self, constraint_id: str, session_id: str
    ) -> list[str]:
        """Stain premises that contradict a known constraint.

        Simple heuristic: a premise claim containing "does not apply"
        or "not relevant" in relation to a constraint is considered
        contradicting.

        Args:
            constraint_id: The constraint ID being violated.
            session_id: Session to search for contradicting premises.

        Returns:
            List of stained premise_ids.
        """
        stained_ids: list[str] = []
        session_premises = self._registry.get_by_session(session_id)

        contradiction_markers = ["does not apply", "not relevant"]

        for premise in session_premises:
            if self._is_stained(premise):
                continue

            claim_lower = premise.claim.lower()
            for marker in contradiction_markers:
                if marker in claim_lower:
                    self._registry.stain(
                        premise_id=premise.premise_id,
                        stained_by=f"policy_violation:{constraint_id}",
                        ground_truth_pointer={
                            "constraint_id": constraint_id,
                            "session_id": session_id,
                            "contradiction_marker": marker,
                        },
                    )
                    stained_ids.append(premise.premise_id)
                    break  # Only stain once per premise

        return stained_ids

    def _find_children(self, parent_id: str) -> list[PremiseRecord]:
        """Find premises whose derivation_chain references the given parent_id.

        Queries the premise_registry for rows where the derivation_chain
        JSON array contains an entry with derives_from matching parent_id.

        Args:
            parent_id: The parent premise_id to search for in derivation chains.

        Returns:
            List of child PremiseRecord instances.
        """
        try:
            # DuckDB JSON array search: check if any element in derivation_chain
            # has derives_from matching the parent_id.
            # Use string matching on the JSON column since DuckDB's JSON
            # functions vary by version.
            rows = self._registry._conn.execute(
                "SELECT * FROM premise_registry "
                "WHERE derivation_chain IS NOT NULL "
                "AND CAST(derivation_chain AS VARCHAR) LIKE ?",
                [f"%{parent_id}%"],
            ).fetchall()
            return [self._registry._row_to_record(row) for row in rows]
        except Exception:
            return []

    @staticmethod
    def _is_stained(premise: PremiseRecord) -> bool:
        """Check if a premise is already stained.

        Args:
            premise: PremiseRecord to check.

        Returns:
            True if the premise has a staining_record with stained=True.
        """
        if premise.staining_record is None:
            return False
        return premise.staining_record.get("stained", False) is True
