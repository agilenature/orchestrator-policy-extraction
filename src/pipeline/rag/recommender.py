"""Action recommender with explainable provenance and danger detection.

Selects recommended orchestrator actions from retrieved similar episodes
using weighted majority vote. Checks recommendations against constraints
and protected paths for safety.

Action selection strategy:
1. Filter to approved episodes (trusted signal)
2. Weight by RRF similarity score
3. Mode: weighted majority vote among approved episodes
4. Risk: max risk from approved episodes (conservative)
5. Gates/scope: union from top approved episode
6. Constraints: union from corrected/blocked episodes (additive safety)

Danger detection checks four categories:
1. scope_violation: recommendation scope overlaps forbidden constraint paths
2. risk_underestimate: recommends lower risk than actual (when actual >= high)
3. gate_dropped: actual episode had critical gates that recommendation omits
4. protected_path: recommendation scope includes config protected_paths

Exports:
    SourceEpisodeRef: Reference to a source episode used in recommendation
    Recommendation: RAG baseline recommendation with provenance
    Recommender: Action recommender using hybrid retrieval
    check_dangerous: Check if a recommendation would be dangerous
"""

from __future__ import annotations

import json

import duckdb
from loguru import logger
from pydantic import BaseModel

from src.pipeline.rag.embedder import observation_to_text


class SourceEpisodeRef(BaseModel, frozen=True):
    """Reference to a source episode used in the recommendation.

    Provides explainable provenance by citing the episode ID, its
    similarity score, what mode it used, and whether it was approved.

    Attributes:
        episode_id: Unique episode identifier.
        similarity_score: RRF fusion score (higher = more similar).
        mode: Orchestrator mode from this episode.
        reaction_label: Human reaction (approve/correct/block/None).
        relevance: Human-readable reason this episode was retrieved.
    """

    episode_id: str
    similarity_score: float
    mode: str
    reaction_label: str | None = None
    relevance: str = ""


class Recommendation(BaseModel, frozen=True):
    """RAG baseline recommendation with explainable provenance.

    Contains the recommended orchestrator action (mode, risk, scope, gates),
    confidence score, list of source episodes with provenance, human-readable
    reasoning, and danger assessment.

    Attributes:
        recommended_mode: Recommended orchestrator mode (e.g., Implement).
        recommended_risk: Recommended risk level (low/medium/high/critical).
        recommended_scope_paths: File paths in recommendation scope.
        recommended_gates: Recommended gates (e.g., run_tests).
        confidence: Confidence score (0-1).
        source_episodes: List of source episode references.
        reasoning: Human-readable explanation of recommendation.
        is_dangerous: Whether danger detection flagged this recommendation.
        danger_reasons: List of danger categories triggered.
    """

    recommended_mode: str
    recommended_risk: str
    recommended_scope_paths: list[str] = []
    recommended_gates: list[str] = []
    confidence: float
    source_episodes: list[SourceEpisodeRef]
    reasoning: str
    is_dangerous: bool = False
    danger_reasons: list[str] = []


class Recommender:
    """Action recommender using hybrid retrieval.

    Uses HybridRetriever to find similar past episodes, then selects
    an action from approved episodes using weighted majority vote.
    Produces Recommendation with explainable provenance.

    Optionally enriched with project wisdom via WisdomRetriever. When
    wisdom_retriever is provided, recommend() returns EnrichedRecommendation
    wrapping the base Recommendation with relevant wisdom references.
    When wisdom_retriever is None, returns plain Recommendation (backward
    compatible).

    Args:
        conn: DuckDB connection with episodes, embeddings, search text.
        embedder: EpisodeEmbedder for generating query embeddings.
        retriever: HybridRetriever for finding similar episodes.
        constraint_store: Optional ConstraintStore for danger detection.
        protected_paths: Optional list of protected path patterns.
        wisdom_retriever: Optional WisdomRetriever for wisdom enrichment.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        embedder,
        retriever,
        constraint_store=None,
        protected_paths: list[str] | None = None,
        wisdom_retriever=None,
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._retriever = retriever
        self._constraint_store = constraint_store
        self._protected_paths = protected_paths or []
        self._wisdom_retriever = wisdom_retriever

    def recommend(
        self,
        observation: dict,
        orchestrator_action: dict | None = None,
        exclude_episode_id: str | None = None,
    ) -> Recommendation:
        """Generate a recommendation from similar past episodes.

        Steps:
        1. Build search text from observation via observation_to_text()
        2. Generate embedding via embedder.embed_text()
        3. Retrieve similar episodes via retriever.retrieve()
        4. Fetch full episode data for retrieved IDs from episodes table
        5. Select action via _select_action()
        6. Check danger via check_dangerous()
        7. Build and return Recommendation with provenance
        8. If wisdom_retriever set, enrich with wisdom refs

        When wisdom_retriever is provided, returns EnrichedRecommendation.
        Otherwise returns plain Recommendation (backward compatible).

        Args:
            observation: Episode observation dict with nested fields.
            orchestrator_action: Optional orchestrator action for context.
            exclude_episode_id: Episode ID to exclude (leave-one-out).

        Returns:
            Recommendation (or EnrichedRecommendation if wisdom_retriever set)
            with mode, risk, scope, gates, provenance.
        """
        # 1. Build search text
        search_text = observation_to_text(observation, orchestrator_action)

        # 2. Generate embedding
        query_embedding = self._embedder.embed_text(search_text)

        # 3. Retrieve similar episodes
        retrieved = self._retriever.retrieve(
            search_text, query_embedding, exclude_episode_id=exclude_episode_id
        )

        if not retrieved:
            base_rec = Recommendation(
                recommended_mode="Explore",
                recommended_risk="medium",
                confidence=0.0,
                source_episodes=[],
                reasoning="No similar episodes found in database",
            )
            return self._maybe_enrich(base_rec, search_text, [])

        # 4. Fetch full episode data for retrieved IDs
        episode_ids = [r["episode_id"] for r in retrieved]
        rrf_scores = {r["episode_id"]: r["rrf_score"] for r in retrieved}
        full_episodes = self._fetch_episodes(episode_ids)

        # Attach rrf_score to each episode
        for ep in full_episodes:
            ep["rrf_score"] = rrf_scores.get(ep["episode_id"], 0.0)

        # 5. Select action
        action = _select_action(full_episodes)

        # 6. Build source episode refs for provenance
        source_refs = []
        for ep in full_episodes:
            source_refs.append(
                SourceEpisodeRef(
                    episode_id=ep["episode_id"],
                    similarity_score=ep.get("rrf_score", 0.0),
                    mode=ep.get("mode", "unknown"),
                    reaction_label=ep.get("reaction_label"),
                    relevance=f"Retrieved via hybrid BM25+embedding search",
                )
            )

        # Build recommendation dict for danger check
        rec_dict = {
            "scope_paths": action.get("scope_paths", []),
            "risk": action["risk"],
            "gates": action.get("gates", []),
        }

        # 7. Check danger against actual episode (use top-1 episode as reference)
        is_dangerous = False
        danger_reasons: list[str] = []
        if full_episodes:
            top_episode = {
                "risk": full_episodes[0].get("risk", "low"),
                "gates": full_episodes[0].get("gates", []),
            }
            is_dangerous, danger_reasons = check_dangerous(
                rec_dict,
                top_episode,
                constraint_store=self._constraint_store,
                protected_paths=self._protected_paths,
            )

        # Compute confidence from number of approved episodes
        approved_count = sum(
            1 for ep in full_episodes if ep.get("reaction_label") == "approve"
        )
        confidence = min(approved_count / max(len(full_episodes), 1), 1.0)

        # Build reasoning
        approved_modes = [
            ep.get("mode", "?")
            for ep in full_episodes
            if ep.get("reaction_label") == "approve"
        ]
        reasoning_parts = [
            f"Based on {len(full_episodes)} similar episodes "
            f"({approved_count} approved)"
        ]
        if approved_modes:
            reasoning_parts.append(
                f"Approved modes: {', '.join(approved_modes)}"
            )
        if action.get("extra_constraints"):
            reasoning_parts.append(
                f"Constraints from corrected/blocked: "
                f"{len(action['extra_constraints'])}"
            )
        reasoning = ". ".join(reasoning_parts)

        # Extract scope_paths for wisdom retrieval
        scope_paths = action.get("scope_paths", [])

        base_rec = Recommendation(
            recommended_mode=action["mode"],
            recommended_risk=action["risk"],
            recommended_scope_paths=scope_paths,
            recommended_gates=action.get("gates", []),
            confidence=confidence,
            source_episodes=source_refs,
            reasoning=reasoning,
            is_dangerous=is_dangerous,
            danger_reasons=danger_reasons,
        )

        # 8. Enrich with wisdom if retriever available
        return self._maybe_enrich(base_rec, search_text, scope_paths)

    def _maybe_enrich(
        self,
        recommendation: Recommendation,
        search_text: str,
        scope_paths: list[str],
    ) -> Recommendation:
        """Optionally enrich a Recommendation with wisdom references.

        If wisdom_retriever is set, wraps the Recommendation in an
        EnrichedRecommendation with relevant wisdom references.
        Otherwise returns the original Recommendation unchanged.

        Args:
            recommendation: Base recommendation to potentially enrich.
            search_text: Query text for wisdom retrieval.
            scope_paths: Scope paths for wisdom scope filtering.

        Returns:
            EnrichedRecommendation if wisdom_retriever set, else Recommendation.
        """
        if self._wisdom_retriever is None:
            return recommendation

        from src.pipeline.wisdom.models import EnrichedRecommendation

        try:
            wisdom_refs = self._wisdom_retriever.retrieve(
                query=search_text, scope_paths=scope_paths
            )
        except Exception as e:
            logger.warning("Wisdom retrieval failed: {}", e)
            wisdom_refs = []

        return EnrichedRecommendation(
            recommendation=recommendation,
            wisdom_refs=wisdom_refs,
            has_dead_end_warning=any(r.is_dead_end_warning for r in wisdom_refs),
        )

    def _fetch_episodes(self, episode_ids: list[str]) -> list[dict]:
        """Fetch full episode data for a list of episode IDs.

        Reads mode, risk, reaction_label, orchestrator_action JSON
        from the episodes table.

        Args:
            episode_ids: List of episode IDs to fetch.

        Returns:
            List of episode dicts with mode, risk, reaction_label,
            scope paths, gates, and rrf_score placeholder.
        """
        if not episode_ids:
            return []

        # Build parameterized query
        placeholders = ", ".join(["?"] * len(episode_ids))
        rows = self._conn.execute(
            f"""
            SELECT episode_id, mode, risk, reaction_label,
                   orchestrator_action
            FROM episodes
            WHERE episode_id IN ({placeholders})
            """,
            episode_ids,
        ).fetchall()

        episodes = []
        for row in rows:
            ep_id, mode, risk, reaction_label, action_json = row

            # Parse orchestrator_action JSON for scope and gates
            scope_paths: list[str] = []
            gates: list[str] = []
            if action_json:
                if isinstance(action_json, str):
                    try:
                        action = json.loads(action_json)
                    except (json.JSONDecodeError, TypeError):
                        action = {}
                elif isinstance(action_json, dict):
                    action = action_json
                else:
                    action = {}

                scope = action.get("scope", {})
                if isinstance(scope, dict):
                    scope_paths = scope.get("paths", [])
                gates = action.get("gates", [])
                if gates is None:
                    gates = []

            episodes.append(
                {
                    "episode_id": ep_id,
                    "mode": mode or "Explore",
                    "risk": risk or "medium",
                    "reaction_label": reaction_label,
                    "scope_paths": scope_paths,
                    "gates": gates,
                    "rrf_score": 0.0,  # Will be overwritten by caller
                }
            )

        # Preserve retrieval order (by episode_ids order)
        id_order = {eid: i for i, eid in enumerate(episode_ids)}
        episodes.sort(key=lambda ep: id_order.get(ep["episode_id"], 999))

        return episodes


def _select_action(retrieved_episodes: list[dict]) -> dict:
    """Select recommended action from retrieved similar episodes.

    Strategy:
    1. Filter to approved episodes only (trusted signal)
    2. If none approved, fall back to top-1 by similarity
    3. Mode: weighted majority vote (weight = rrf_score)
    4. Risk: max risk from approved episodes (conservative)
    5. Scope: paths from top-1 approved episode
    6. Gates: union of gates from all approved episodes
    7. Constraints: union from corrected/blocked episodes

    Args:
        retrieved_episodes: Episodes with mode, risk, reaction_label,
            scope_paths, gates, rrf_score.

    Returns:
        Action dict with mode, risk, scope_paths, gates, extra_constraints.
    """
    approved = [
        ep for ep in retrieved_episodes if ep.get("reaction_label") == "approve"
    ]
    corrected = [
        ep
        for ep in retrieved_episodes
        if ep.get("reaction_label") in ("correct", "block")
    ]

    # Fall back to top-1 by similarity if no approved episodes
    if not approved:
        approved = retrieved_episodes[:1]

    # Mode: weighted majority vote among approved
    mode_votes: dict[str, float] = {}
    for ep in approved:
        mode = ep.get("mode", "Explore")
        mode_votes[mode] = mode_votes.get(mode, 0) + ep.get("rrf_score", 1.0)
    recommended_mode = (
        max(mode_votes, key=mode_votes.get) if mode_votes else "Explore"
    )

    # Risk: maximum risk from approved episodes (conservative)
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    max_risk = max(
        (risk_order.get(ep.get("risk", "low"), 0) for ep in approved),
        default=0,
    )
    risk_labels = {v: k for k, v in risk_order.items()}
    recommended_risk = risk_labels.get(max_risk, "medium")

    # Scope: paths from top-1 approved episode
    scope_paths = approved[0].get("scope_paths", []) if approved else []

    # Gates: union from all approved episodes
    gates: set[str] = set()
    for ep in approved:
        for gate in ep.get("gates", []):
            gates.add(gate)

    # Constraints: union from corrected/blocked episodes
    extra_constraints: list[str] = []
    for ep in corrected:
        constraints = ep.get("constraints_extracted", [])
        extra_constraints.extend(constraints)

    return {
        "mode": recommended_mode,
        "risk": recommended_risk,
        "scope_paths": scope_paths,
        "gates": sorted(gates),
        "extra_constraints": extra_constraints,
        "source_count": len(approved),
    }


def check_dangerous(
    recommendation: dict,
    episode: dict,
    constraint_store=None,
    protected_paths: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Check if a recommendation would be dangerous.

    Checks four danger categories:
    1. scope_violation: recommendation scope overlaps forbidden constraint paths
    2. risk_underestimate: recommends lower risk than actual (when actual >= high)
    3. gate_dropped: actual episode had critical gates that recommendation omits
    4. protected_path: recommendation scope includes config protected_paths

    Args:
        recommendation: Dict with scope_paths, risk, gates keys.
        episode: Dict with risk, gates keys (actual episode data).
        constraint_store: Optional ConstraintStore with forbidden constraints.
        protected_paths: Optional list of protected path patterns.

    Returns:
        Tuple of (is_dangerous: bool, reasons: list[str]).
        reasons contains danger category names that were triggered.
    """
    if protected_paths is None:
        protected_paths = []

    dangers: list[str] = []
    rec_scope = set(recommendation.get("scope_paths", []))

    # 1. Check constraint scope violations (bidirectional prefix match)
    if constraint_store is not None:
        scope_violated = False
        for constraint in constraint_store.constraints:
            if constraint.get("severity") == "forbidden":
                c_paths = constraint.get("scope", {}).get("paths", [])
                for rp in rec_scope:
                    for cp in c_paths:
                        # Bidirectional prefix: rec path under constraint
                        # dir, or constraint path under rec path
                        if rp.startswith(cp) or cp.startswith(rp):
                            scope_violated = True
                            break
                    if scope_violated:
                        break
            if scope_violated:
                dangers.append("scope_violation")
                break

    # 2. Check risk underestimate
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    rec_risk = risk_order.get(recommendation.get("risk", "low"), 0)
    actual_risk = risk_order.get(episode.get("risk", "low"), 0)
    if rec_risk < actual_risk and actual_risk >= 2:  # high or critical
        dangers.append("risk_underestimate")

    # 3. Check gate dropping
    actual_gates = set(episode.get("gates", []))
    rec_gates = set(recommendation.get("gates", []))
    critical_gates = {"require_human_approval", "protected_paths"}
    dropped_critical = (actual_gates & critical_gates) - rec_gates
    if dropped_critical:
        dangers.append("gate_dropped")

    # 4. Check protected paths (prefix match)
    for rec_path in rec_scope:
        for pp in protected_paths:
            # Strip glob patterns for prefix matching
            clean_pp = pp.rstrip("*").rstrip("/")
            if rec_path.startswith(clean_pp):
                dangers.append("protected_path")
                break
        if "protected_path" in dangers:
            break

    return (len(dangers) > 0, dangers)
