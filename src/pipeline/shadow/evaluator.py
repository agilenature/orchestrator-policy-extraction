"""Shadow mode evaluator for comparing recommendations against actual decisions.

Computes agreement metrics between a RAG recommendation and the actual
human decision recorded in the episode: mode agreement, risk agreement,
scope overlap (Jaccard similarity), and gate agreement.

Exports:
    ShadowEvaluator: Compare recommendation against actual human decision
"""

from __future__ import annotations

import json
from uuid import uuid4

from src.pipeline.rag.recommender import Recommendation


class ShadowEvaluator:
    """Compare a shadow recommendation against the actual human decision.

    Evaluates a single episode's recommendation by computing:
    - mode_agrees: whether recommended mode matches actual
    - risk_agrees: whether recommended risk matches actual
    - scope_overlap: Jaccard similarity between recommended and actual scope paths
    - gate_agrees: whether recommended gates match actual gates exactly
    - is_dangerous / danger_reasons: propagated from recommendation
    """

    def evaluate(self, episode: dict, recommendation: Recommendation) -> dict:
        """Evaluate a single recommendation against the actual episode decision.

        Args:
            episode: Episode dict with mode, risk, orchestrator_action fields.
            recommendation: Recommendation from the RAG recommender.

        Returns:
            Result dict matching shadow_mode_results table columns.
        """
        # Extract human decision from episode
        human_mode = episode.get("mode", "unknown")
        human_risk = episode.get("risk", "medium")
        human_reaction_label = episode.get("reaction_label")

        # Extract actual scope and gates from orchestrator_action
        actual_scope_paths: list[str] = []
        actual_gates: list[str] = []
        action = episode.get("orchestrator_action")
        if action:
            if isinstance(action, str):
                try:
                    action = json.loads(action)
                except (json.JSONDecodeError, TypeError):
                    action = {}
            if isinstance(action, dict):
                scope = action.get("scope", {})
                if isinstance(scope, dict):
                    actual_scope_paths = scope.get("paths", []) or []
                actual_gates = action.get("gates", []) or []

        # Mode agreement
        mode_agrees = recommendation.recommended_mode == human_mode

        # Risk agreement
        risk_agrees = recommendation.recommended_risk == human_risk

        # Scope overlap (Jaccard similarity)
        rec_scope = set(recommendation.recommended_scope_paths)
        actual_scope = set(actual_scope_paths)
        if not rec_scope and not actual_scope:
            # Both empty = agreement (no scope to compare)
            scope_overlap = 1.0
        elif not rec_scope or not actual_scope:
            # One empty, one not = no overlap
            scope_overlap = 0.0
        else:
            intersection = rec_scope & actual_scope
            union = rec_scope | actual_scope
            scope_overlap = len(intersection) / len(union)

        # Gate agreement (exact set match)
        rec_gates_set = set(recommendation.recommended_gates)
        actual_gates_set = set(actual_gates)
        if not rec_gates_set and not actual_gates_set:
            gate_agrees = True
        else:
            gate_agrees = rec_gates_set == actual_gates_set

        # Collect source episode info
        source_episode_ids = [
            ref.episode_id for ref in recommendation.source_episodes
        ]
        retrieval_scores = [
            ref.similarity_score for ref in recommendation.source_episodes
        ]

        return {
            "shadow_run_id": str(uuid4()),
            "episode_id": episode.get("episode_id", ""),
            "session_id": episode.get("session_id", ""),
            "human_mode": human_mode,
            "human_risk": human_risk,
            "human_reaction_label": human_reaction_label,
            "shadow_mode": recommendation.recommended_mode,
            "shadow_risk": recommendation.recommended_risk,
            "shadow_confidence": recommendation.confidence,
            "mode_agrees": mode_agrees,
            "risk_agrees": risk_agrees,
            "scope_overlap": scope_overlap,
            "gate_agrees": gate_agrees,
            "is_dangerous": recommendation.is_dangerous,
            "danger_reasons": recommendation.danger_reasons,
            "source_episode_ids": source_episode_ids,
            "retrieval_scores": retrieval_scores,
        }
