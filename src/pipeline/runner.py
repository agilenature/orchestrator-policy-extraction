"""Pipeline runner -- orchestrates all stages end-to-end.

Wires together: JSONL loading -> normalization -> tagging -> segmentation -> DuckDB storage.
Provides PipelineRunner for single-session and batch processing with comprehensive
error handling following the multi-level strategy (Q16/Q17).

Error handling levels:
  Level 1 (Reject): Non-parseable JSONL lines -> skip, count as invalid
  Level 2 (Degrade): Missing optional fields -> use defaults, log WARNING
  Level 3 (Alternative): Failed temporal alignment -> timestamp order with confidence=0.0
  Level 4 (Logging): All errors logged with event context via loguru
  Level 5 (Metrics): Stats dict includes error counts and quality metrics
  Abort: If invalid_rate > 10% for a session, skip session and log ERROR

Exports:
    PipelineRunner: Main pipeline orchestrator
    run_session: Convenience function for single-session processing
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

from src.pipeline.adapters.claude_jsonl import load_jsonl_to_duckdb, normalize_jsonl_events
from src.pipeline.adapters.git_history import parse_git_history
from src.pipeline.models.config import PipelineConfig, load_config
from src.pipeline.models.events import TaggedEvent
from src.pipeline.normalizer import normalize_events
from src.pipeline.segmenter import EpisodeSegmenter
from src.pipeline.storage.schema import create_schema, get_connection
from src.pipeline.storage.writer import write_events, write_segments
from src.pipeline.tagger import EventTagger


# Regex to extract UUID from JSONL filename (e.g., "abc12345-...-6789.jsonl")
_UUID_PATTERN = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


class PipelineRunner:
    """Orchestrates the full extraction pipeline: load -> normalize -> tag -> segment -> store.

    Args:
        config: Pipeline configuration (loaded from YAML).
        db_path: DuckDB database path. Use ':memory:' for testing.
    """

    def __init__(self, config: PipelineConfig, db_path: str = "data/ope.db") -> None:
        self._config = config
        self._db_path = db_path
        self._conn = get_connection(db_path)
        create_schema(self._conn)
        self._tagger = EventTagger(config)
        self._segmenter = EpisodeSegmenter(config)
        self._config_hash = self._compute_config_hash(config)
        logger.info(
            "PipelineRunner initialized (db={}, config_hash={})",
            db_path,
            self._config_hash,
        )

    def run_session(
        self,
        jsonl_path: str | Path,
        repo_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Process a single JSONL session through the full pipeline.

        Steps:
        1. Load JSONL via DuckDB read_json_auto
        2. Normalize JSONL events into CanonicalEvent instances
        3. Optionally load and merge git history
        4. Validate event quality (abort if >10% invalid per Q16)
        5. Tag events with multi-pass classifier
        6. Segment tagged events into episodes
        7. Write events and segments to DuckDB
        8. Compute and return stats

        Args:
            jsonl_path: Path to the JSONL session file.
            repo_path: Optional git repo path for temporal alignment.

        Returns:
            Stats dict with session_id, event_count, tag_distribution,
            episode_count, outcome_distribution, errors, warnings.
        """
        jsonl_path = Path(jsonl_path)
        session_id = self._extract_session_id(jsonl_path)
        t0 = time.monotonic()

        logger.info("--- Processing session: {} ---", session_id)

        errors: list[str] = []
        warnings: list[str] = []
        invalid_count = 0

        # Step 1: Load JSONL via DuckDB
        try:
            raw_count = load_jsonl_to_duckdb(self._conn, jsonl_path, session_id)
            logger.info("Step 1: Loaded {} raw records", raw_count)
        except Exception as e:
            logger.error("Failed to load JSONL {}: {}", jsonl_path.name, e)
            return self._error_result(session_id, f"JSONL load failed: {e}")

        # Step 2: Normalize JSONL events
        try:
            jsonl_events = normalize_jsonl_events(self._conn, session_id)
            logger.info("Step 2: Normalized {} JSONL events", len(jsonl_events))
        except Exception as e:
            logger.error("Failed to normalize events for {}: {}", session_id, e)
            return self._error_result(session_id, f"Normalization failed: {e}")

        # Step 3: Load git history (optional)
        git_events = []
        if repo_path is not None:
            try:
                git_events = parse_git_history(repo_path, session_id=session_id)
                logger.info("Step 3: Parsed {} git events", len(git_events))
            except Exception as e:
                logger.warning("Git history parsing failed (degrading): {}", e)
                warnings.append(f"Git history unavailable: {e}")

        # Step 4: Merge + normalize (temporal alignment, dedup)
        try:
            canonical_events = normalize_events(jsonl_events, git_events, self._config)
            logger.info("Step 4: Merged to {} canonical events", len(canonical_events))
        except Exception as e:
            logger.warning("Temporal alignment failed, using timestamp order: {}", e)
            warnings.append(f"Temporal alignment failed: {e}")
            # Level 3 alternative: use JSONL events without alignment
            canonical_events = jsonl_events

        # Step 5: Validate event quality (Q16)
        # The invalid rate is measured against records that PASSED filtering
        # (i.e., were not progress/file-history-snapshot/queue-operation types)
        # but FAILED parsing into CanonicalEvent instances.
        # raw_count includes ALL records; the adapter filters ~45% as irrelevant types.
        # We query the filtered count to compute the true invalid rate.
        if raw_count > 0:
            try:
                filtered_count = self._conn.execute(
                    "SELECT count(*) FROM raw_records "
                    "WHERE type NOT IN ('progress', 'file-history-snapshot', 'queue-operation') "
                    "AND (isSidechain IS NULL OR isSidechain = false)"
                ).fetchone()[0]
            except Exception:
                # Fallback: if the query fails (column missing), use raw count
                filtered_count = raw_count

            invalid_count = max(0, filtered_count - len(jsonl_events))
            if filtered_count > 0:
                invalid_rate = invalid_count / filtered_count
            else:
                invalid_rate = 0.0

            abort_threshold = self._config.validation.invalid_event_abort_threshold

            if invalid_rate > abort_threshold:
                msg = (
                    f"Session {session_id} aborted: {invalid_rate:.1%} invalid events "
                    f"({invalid_count}/{filtered_count}) exceeds {abort_threshold:.0%} threshold"
                )
                logger.error(msg)
                errors.append(msg)
                return self._error_result(session_id, msg, invalid_count=invalid_count)

        # Step 6: Tag events
        try:
            tagged_events = self._tagger.tag(canonical_events)
            logger.info("Step 6: Tagged {} events", len(tagged_events))
        except Exception as e:
            logger.error("Tagging failed for {}: {}", session_id, e)
            return self._error_result(session_id, f"Tagging failed: {e}")

        # Step 7: Segment events into episodes
        try:
            # Create a fresh segmenter for each session (clean state)
            segmenter = EpisodeSegmenter(self._config)
            segments = segmenter.segment(tagged_events)
            seg_stats = segmenter.get_stats()

            # Attach config_hash to each segment for provenance
            for seg in segments:
                seg.config_hash = self._config_hash

            logger.info(
                "Step 7: Segmented into {} episodes (orphans: {})",
                len(segments),
                seg_stats["orphan_count"],
            )
        except Exception as e:
            logger.error("Segmentation failed for {}: {}", session_id, e)
            return self._error_result(session_id, f"Segmentation failed: {e}")

        # Step 8: Write to DuckDB
        try:
            event_write_stats = write_events(
                self._conn, canonical_events, tagged_events
            )
            segment_write_stats = write_segments(self._conn, segments)
            logger.info(
                "Step 8: Wrote {} events, {} segments to DuckDB",
                event_write_stats["total"],
                segment_write_stats["total"],
            )
        except Exception as e:
            logger.error("DuckDB write failed for {}: {}", session_id, e)
            return self._error_result(session_id, f"Write failed: {e}")

        # Step 9: Compute stats
        tag_distribution = self._compute_tag_distribution(tagged_events)
        outcome_distribution = seg_stats.get("by_outcome", {})
        duration_s = time.monotonic() - t0

        result = {
            "session_id": session_id,
            "event_count": len(canonical_events),
            "raw_count": raw_count,
            "tag_distribution": tag_distribution,
            "episode_count": len(segments),
            "outcome_distribution": outcome_distribution,
            "orphan_count": seg_stats.get("orphan_count", 0),
            "duplicate_count": event_write_stats.get("updated", 0),
            "invalid_count": invalid_count,
            "errors": errors,
            "warnings": warnings,
            "duration_seconds": round(duration_s, 2),
        }

        logger.info(
            "Session {} complete: {} events, {} episodes in {:.1f}s",
            session_id,
            len(canonical_events),
            len(segments),
            duration_s,
        )

        return result

    def run_batch(
        self,
        jsonl_dir: str | Path,
        repo_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Process all JSONL files in a directory.

        Args:
            jsonl_dir: Directory containing .jsonl session files.
            repo_path: Optional git repo path for temporal alignment.

        Returns:
            Aggregate stats dict with per-session results.
        """
        jsonl_dir = Path(jsonl_dir)
        jsonl_files = sorted(jsonl_dir.glob("*.jsonl"))

        if not jsonl_files:
            logger.warning("No .jsonl files found in {}", jsonl_dir)
            return {
                "sessions_processed": 0,
                "total_events": 0,
                "total_episodes": 0,
                "results": [],
                "errors": [],
            }

        logger.info("Batch processing {} JSONL files from {}", len(jsonl_files), jsonl_dir)

        results: list[dict[str, Any]] = []
        total_events = 0
        total_episodes = 0
        batch_errors: list[str] = []

        try:
            from tqdm import tqdm
            file_iter = tqdm(jsonl_files, desc="Processing sessions", unit="session")
        except ImportError:
            file_iter = jsonl_files

        for jsonl_file in file_iter:
            try:
                result = self.run_session(jsonl_file, repo_path=repo_path)
                results.append(result)
                total_events += result.get("event_count", 0)
                total_episodes += result.get("episode_count", 0)
                if result.get("errors"):
                    batch_errors.extend(result["errors"])
            except Exception as e:
                logger.error("Unexpected error processing {}: {}", jsonl_file.name, e)
                batch_errors.append(f"{jsonl_file.name}: {e}")

        # Aggregate tag distribution
        agg_tags: Counter[str] = Counter()
        agg_outcomes: Counter[str] = Counter()
        for r in results:
            for tag, count in r.get("tag_distribution", {}).items():
                agg_tags[tag] += count
            for outcome, count in r.get("outcome_distribution", {}).items():
                agg_outcomes[outcome] += count

        return {
            "sessions_processed": len(results),
            "total_events": total_events,
            "total_episodes": total_episodes,
            "tag_distribution": dict(agg_tags),
            "outcome_distribution": dict(agg_outcomes),
            "results": results,
            "errors": batch_errors,
        }

    def close(self) -> None:
        """Close the DuckDB connection."""
        try:
            self._conn.close()
            logger.info("PipelineRunner closed")
        except Exception:
            pass

    # --- Private helpers ---

    @staticmethod
    def _extract_session_id(jsonl_path: Path) -> str:
        """Extract session ID from JSONL filename.

        Looks for a UUID pattern in the filename. Falls back to the stem.
        """
        match = _UUID_PATTERN.search(jsonl_path.stem)
        if match:
            return match.group(1)
        return jsonl_path.stem

    @staticmethod
    def _compute_config_hash(config: PipelineConfig) -> str:
        """Compute SHA-256 hash of config for provenance tracking.

        Returns first 8 hex chars of the hash.
        """
        config_str = config.model_dump_json(indent=None)
        return hashlib.sha256(config_str.encode()).hexdigest()[:8]

    @staticmethod
    def _compute_tag_distribution(tagged_events: list[TaggedEvent]) -> dict[str, int]:
        """Count events by primary tag label."""
        counts: Counter[str] = Counter()
        for te in tagged_events:
            if te.primary is not None:
                counts[te.primary.label] += 1
            else:
                counts["untagged"] += 1
        return dict(counts)

    @staticmethod
    def _error_result(
        session_id: str,
        error_msg: str,
        invalid_count: int = 0,
    ) -> dict[str, Any]:
        """Create an error result dict for a failed session."""
        return {
            "session_id": session_id,
            "event_count": 0,
            "raw_count": 0,
            "tag_distribution": {},
            "episode_count": 0,
            "outcome_distribution": {},
            "orphan_count": 0,
            "duplicate_count": 0,
            "invalid_count": invalid_count,
            "errors": [error_msg],
            "warnings": [],
            "duration_seconds": 0,
        }


def run_session(
    jsonl_path: str | Path,
    config_path: str | Path = "data/config.yaml",
    db_path: str = "data/ope.db",
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convenience function to process a single session.

    Creates a PipelineRunner, processes the session, and closes.
    For batch processing or repeated calls, use PipelineRunner directly.

    Args:
        jsonl_path: Path to the JSONL session file.
        config_path: Path to the config YAML file.
        db_path: DuckDB database path.
        repo_path: Optional git repo path for temporal alignment.

    Returns:
        Stats dict from PipelineRunner.run_session().
    """
    config = load_config(config_path)
    runner = PipelineRunner(config, db_path=db_path)
    try:
        return runner.run_session(jsonl_path, repo_path=repo_path)
    finally:
        runner.close()
