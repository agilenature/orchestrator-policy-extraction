"""Shadow mode runner for batch leave-one-out evaluation.

Processes all historical episodes using leave-one-out protocol: for each
episode, generates a recommendation EXCLUDING that episode from retrieval,
then compares the recommendation against the actual human decision.

Results are stored in the DuckDB shadow_mode_results table.

Exports:
    ShadowModeRunner: Run shadow mode testing in batch over historical episodes
"""

from __future__ import annotations

import json
from uuid import uuid4

import duckdb
from loguru import logger

from src.pipeline.rag.embedder import observation_to_text
from src.pipeline.shadow.evaluator import ShadowEvaluator


class ShadowModeRunner:
    """Run shadow mode testing in batch over historical episodes.

    Uses leave-one-out protocol: each episode's recommendation is generated
    EXCLUDING that episode from retrieval, ensuring the recommender does not
    cheat by seeing the answer.

    Args:
        conn: DuckDB connection with episodes, embeddings, search text.
        embedder: EpisodeEmbedder for generating query embeddings.
        recommender: Recommender for generating recommendations.
        evaluator: Optional ShadowEvaluator (created if not provided).
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        embedder,
        recommender,
        evaluator: ShadowEvaluator | None = None,
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._recommender = recommender
        self._evaluator = evaluator or ShadowEvaluator()

    def run_all(self, batch_id: str | None = None) -> dict:
        """Run shadow mode for ALL episodes in the database.

        Args:
            batch_id: Optional batch ID for grouping results. Generated
                      if not provided.

        Returns:
            Aggregate stats dict with total, agreements, dangerous,
            results_by_session keys.
        """
        if batch_id is None:
            batch_id = str(uuid4())

        # Fetch all distinct session_ids
        rows = self._conn.execute(
            "SELECT DISTINCT session_id FROM episodes ORDER BY session_id"
        ).fetchall()
        session_ids = [r[0] for r in rows]

        logger.info("Shadow mode: processing {} sessions", len(session_ids))

        all_results: list[dict] = []
        results_by_session: dict[str, list[dict]] = {}

        for session_id in session_ids:
            session_results = self.run_session(session_id, batch_id=batch_id)
            all_results.extend(session_results)
            results_by_session[session_id] = session_results

        # Write results to shadow_mode_results table
        self._write_results(all_results)

        # Compute aggregate stats
        total = len(all_results)
        mode_agreements = sum(1 for r in all_results if r["mode_agrees"])
        risk_agreements = sum(1 for r in all_results if r["risk_agrees"])
        dangerous = sum(1 for r in all_results if r["is_dangerous"])

        stats = {
            "total": total,
            "mode_agreements": mode_agreements,
            "risk_agreements": risk_agreements,
            "dangerous": dangerous,
            "batch_id": batch_id,
            "sessions": len(session_ids),
            "results_by_session": {
                sid: len(res) for sid, res in results_by_session.items()
            },
        }

        logger.info(
            "Shadow mode complete: {} episodes, {} mode agreements ({:.1%}), {} dangerous",
            total,
            mode_agreements,
            mode_agreements / max(total, 1),
            dangerous,
        )

        return stats

    def run_session(
        self, session_id: str, batch_id: str | None = None
    ) -> list[dict]:
        """Run shadow mode for all episodes in a single session.

        Args:
            session_id: Session ID to process.
            batch_id: Optional batch ID for grouping results.

        Returns:
            List of result dicts (one per episode) matching
            shadow_mode_results table columns.
        """
        # Fetch all episodes for this session
        rows = self._conn.execute(
            """
            SELECT episode_id, session_id, mode, risk, reaction_label,
                   observation, orchestrator_action
            FROM episodes
            WHERE session_id = ?
            ORDER BY timestamp
            """,
            [session_id],
        ).fetchall()

        results: list[dict] = []
        for row in rows:
            episode_id = row[0]
            session = row[1]
            mode = row[2]
            risk = row[3]
            reaction_label = row[4]
            obs_struct = row[5]
            action_json = row[6]

            # Build episode dict for evaluator
            episode = {
                "episode_id": episode_id,
                "session_id": session,
                "mode": mode or "unknown",
                "risk": risk or "medium",
                "reaction_label": reaction_label,
                "orchestrator_action": action_json,
            }

            # Parse observation (DuckDB STRUCT -> dict)
            obs_dict = _struct_to_dict(obs_struct)

            # Parse orchestrator_action JSON
            action_dict = None
            if action_json:
                if isinstance(action_json, str):
                    try:
                        action_dict = json.loads(action_json)
                    except (json.JSONDecodeError, TypeError):
                        action_dict = None
                elif isinstance(action_json, dict):
                    action_dict = action_json

            # Generate recommendation with leave-one-out exclusion
            try:
                recommendation = self._recommender.recommend(
                    obs_dict,
                    action_dict,
                    exclude_episode_id=episode_id,
                )
            except Exception as e:
                logger.warning(
                    "Shadow mode: failed to recommend for episode {}: {}",
                    episode_id,
                    e,
                )
                continue

            # Evaluate recommendation against actual decision
            result = self._evaluator.evaluate(episode, recommendation)
            result["run_batch_id"] = batch_id
            result["session_id"] = session_id
            results.append(result)

        return results

    def _write_results(self, results: list[dict]) -> None:
        """Write shadow mode results to the shadow_mode_results table.

        Uses INSERT OR REPLACE for idempotent re-runs.

        Args:
            results: List of result dicts from evaluate().
        """
        if not results:
            return

        for result in results:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO shadow_mode_results (
                    shadow_run_id, episode_id, session_id,
                    human_mode, human_risk, human_reaction_label,
                    shadow_mode, shadow_risk, shadow_confidence,
                    mode_agrees, risk_agrees, scope_overlap, gate_agrees,
                    is_dangerous, danger_reasons,
                    source_episode_ids, retrieval_scores,
                    run_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    result["shadow_run_id"],
                    result["episode_id"],
                    result["session_id"],
                    result["human_mode"],
                    result["human_risk"],
                    result.get("human_reaction_label"),
                    result["shadow_mode"],
                    result["shadow_risk"],
                    result.get("shadow_confidence"),
                    result["mode_agrees"],
                    result["risk_agrees"],
                    result.get("scope_overlap"),
                    result.get("gate_agrees"),
                    result["is_dangerous"],
                    json.dumps(result.get("danger_reasons", [])),
                    json.dumps(result.get("source_episode_ids", [])),
                    json.dumps(result.get("retrieval_scores", [])),
                    result.get("run_batch_id"),
                ],
            )


def _struct_to_dict(struct_val: object) -> dict:
    """Convert a DuckDB STRUCT value to a Python dict.

    Args:
        struct_val: DuckDB STRUCT value (dict, tuple, or other).

    Returns:
        Python dict representation.
    """
    if struct_val is None:
        return {}
    if isinstance(struct_val, dict):
        return {
            k: _struct_to_dict(v) if isinstance(v, dict) else v
            for k, v in struct_val.items()
        }
    try:
        return dict(struct_val)
    except (TypeError, ValueError):
        return {}
