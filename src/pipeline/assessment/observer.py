"""Post-session JSONL analysis via existing pipeline (Phase 17, Plan 03).

The AssessmentObserver runs the full OPE pipeline on a completed
assessment session's JSONL file, then tags the resulting flame_events
with the assessment_session_id to distinguish them from production data.

Exports:
    AssessmentObserver
    run_observer
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.pipeline.assessment.models import AssessmentSession

logger = logging.getLogger(__name__)


class AssessmentObserver:
    """Post-session observer that runs the OPE pipeline on assessment JSONL.

    Reuses the existing PipelineRunner to process assessment JSONL files
    identically to production sessions, then tags flame_events with
    assessment_session_id so IntelligenceProfile queries can exclude them.

    Args:
        db_path: DuckDB database path for pipeline and tagging.
        config_path: YAML config path for PipelineRunner.
    """

    def __init__(
        self,
        db_path: str = "data/ope.db",
        config_path: str = "data/config.yaml",
    ) -> None:
        self._db_path = db_path
        self._config_path = config_path

    def run_observation(self, session: AssessmentSession) -> dict[str, Any]:
        """Run the full OPE pipeline on an assessment session's JSONL.

        1. Verify JSONL exists at session.jsonl_path
        2. Load config and create PipelineRunner
        3. Run pipeline on the JSONL file
        4. Tag flame_events with assessment_session_id

        Args:
            session: Completed AssessmentSession with jsonl_path set.

        Returns:
            Pipeline stats dict from PipelineRunner.run_session().

        Raises:
            FileNotFoundError: If JSONL file doesn't exist at session.jsonl_path.
        """
        if not session.jsonl_path or not os.path.exists(session.jsonl_path):
            raise FileNotFoundError(
                f"JSONL file not found at: {session.jsonl_path}"
            )

        # Lazy imports to avoid circular dependencies at module load time
        from src.pipeline.models.config import load_config
        from src.pipeline.runner import PipelineRunner

        config = load_config(self._config_path)

        runner = PipelineRunner(config, db_path=self._db_path)
        stats = runner.run_session(session.jsonl_path)

        # Tag assessment flame_events with assessment_session_id
        import duckdb

        conn = duckdb.connect(self._db_path)
        try:
            conn.execute(
                "UPDATE flame_events "
                "SET assessment_session_id = ? "
                "WHERE session_id = ?",
                [session.session_id, session.session_id],
            )
        finally:
            conn.close()

        logger.info(
            "Observation complete for session %s: %d events processed",
            session.session_id,
            stats.get("event_count", 0),
        )

        return stats


def run_observer(
    session: AssessmentSession,
    db_path: str = "data/ope.db",
    config_path: str = "data/config.yaml",
) -> dict[str, Any]:
    """Convenience: run observer pipeline on an assessment session.

    Args:
        session: Completed AssessmentSession.
        db_path: DuckDB database path.
        config_path: YAML config path.

    Returns:
        Pipeline stats dict.
    """
    observer = AssessmentObserver(db_path=db_path, config_path=config_path)
    return observer.run_observation(session)
