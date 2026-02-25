"""Pipeline runner -- orchestrates all stages end-to-end.

Wires together: JSONL loading -> normalization -> tagging -> segmentation ->
DuckDB storage -> episode population -> reaction labeling -> validation ->
episode storage.

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
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

from src.pipeline.adapters.claude_jsonl import load_jsonl_to_duckdb, normalize_jsonl_events
from src.pipeline.adapters.git_history import parse_git_history
from src.pipeline.constraint_extractor import ConstraintExtractor
from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.episode_validator import EpisodeValidator
from src.pipeline.durability.amnesia import AmnesiaDetector
from src.pipeline.durability.evaluator import SessionConstraintEvaluator
from src.pipeline.durability.scope_extractor import extract_session_scope
from src.pipeline.escalation.constraint_gen import EscalationConstraintGenerator
from src.pipeline.escalation.detector import EscalationDetector
from src.pipeline.models.config import PipelineConfig, load_config
from src.pipeline.models.events import TaggedEvent
from src.pipeline.normalizer import normalize_events
from src.pipeline.populator import EpisodePopulator
from src.pipeline.reaction_labeler import ReactionLabeler
from src.pipeline.segmenter import EpisodeSegmenter
from src.pipeline.storage.schema import create_schema, get_connection
from src.pipeline.storage.writer import (
    read_events,
    write_amnesia_events,
    write_constraint_evals,
    write_episodes,
    write_escalation_episodes,
    write_events,
    write_segments,
)
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

    def __init__(
        self,
        config: PipelineConfig,
        db_path: str = "data/ope.db",
        constraints_path: str | Path | None = None,
    ) -> None:
        self._config = config
        self._db_path = db_path
        self._conn = get_connection(db_path)
        create_schema(self._conn)
        self._tagger = EventTagger(config)
        self._segmenter = EpisodeSegmenter(config)
        self._populator = EpisodePopulator(config)
        self._reaction_labeler = ReactionLabeler(config)
        self._validator = EpisodeValidator()
        self._constraint_extractor = ConstraintExtractor(config)

        # Constraint store path: configurable for test isolation
        if constraints_path is not None:
            c_path = Path(constraints_path)
        else:
            c_path = Path("data/constraints.json")
        self._constraint_store = ConstraintStore(
            path=c_path,
            schema_path=Path("data/schemas/constraint.schema.json"),
        )

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
        8. Populate episodes from segments
        9. Label reactions from next human messages
        10. Validate episodes against JSON Schema
        11. Write valid episodes to DuckDB via MERGE
        12. Extract constraints from correct/block episodes
        13. Escalation detection
        14. Session constraint evaluation (decision durability)
        15. DDF Tier 1 flame event detection (L0-2 markers + O_AXS)
        16. DDF Tier 2 LLM enrichment (L3-7)
        17. Deposit Level 6 to memory_candidates
        18. DDF-09 False Integration + DDF-10 Causal Isolation
        19. GeneralizationRadius + spiral promotion
        20. Compute and return stats

        Args:
            jsonl_path: Path to the JSONL session file.
            repo_path: Optional git repo path for temporal alignment.

        Returns:
            Stats dict with session_id, event_count, tag_distribution,
            episode_count, outcome_distribution, episode stats, errors, warnings.
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
                # Check if isSidechain column exists in raw_records
                raw_cols = {
                    row[0]
                    for row in self._conn.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'raw_records'"
                    ).fetchall()
                }
                sidechain_clause = (
                    "AND (isSidechain IS NULL OR isSidechain = false)"
                    if "isSidechain" in raw_cols
                    else ""
                )
                filtered_count = self._conn.execute(
                    "SELECT count(*) FROM raw_records "
                    "WHERE type NOT IN ('progress', 'file-history-snapshot', 'queue-operation') "
                    + sidechain_clause
                ).fetchone()[0]
            except Exception:
                # Fallback: if the query fails entirely, use raw count
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

        # Step 9: Populate episodes + label reactions
        populated_episodes: list[dict] = []
        reaction_distribution: Counter[str] = Counter()

        try:
            # Read all stored events for this session
            all_session_events = read_events(self._conn, session_id=session_id)

            # Build event lookup by event_id for fast access
            event_by_id: dict[str, dict] = {
                e["event_id"]: e for e in all_session_events
            }

            # Build tag lookup from tagged_events (for reaction labeling)
            tag_by_event_id: dict[str, list[str]] = {}
            for te in tagged_events:
                te_tags: list[str] = []
                if te.primary:
                    te_tags.append(te.primary.label)
                if te.secondaries:
                    for sec in te.secondaries:
                        te_tags.append(sec.label)
                tag_by_event_id[te.event.event_id] = te_tags

            prev_episode_id = None
            for seg in segments:
                try:
                    # Get events within this segment
                    segment_events = [
                        event_by_id[eid]
                        for eid in seg.events
                        if eid in event_by_id
                    ]

                    # Get context events: events before segment start
                    max_context = self._config.episode_population.observation_context_events
                    context_events = [
                        e for e in all_session_events
                        if e["ts_utc"] < seg.start_ts
                    ][-max_context:]

                    # Populate episode
                    episode = self._populator.populate(seg, segment_events, context_events)

                    # Set parent_episode_id for causal chain (Phase 14.1)
                    episode["parent_episode_id"] = prev_episode_id

                    # Find next human message after segment end for reaction labeling
                    next_human_msg = self._find_next_human_message(
                        all_session_events, seg.end_ts, tag_by_event_id
                    )

                    # Label reaction
                    reaction = self._reaction_labeler.label(
                        next_human_msg, seg.end_trigger, seg.outcome
                    )
                    if reaction is not None:
                        episode.setdefault("outcome", {})["reaction"] = reaction
                        reaction_distribution[reaction["label"]] += 1

                    # Store episode for validation
                    # Metadata will be added AFTER validation
                    populated_episodes.append({
                        "episode": episode,
                        "session_id": session_id,
                        "segment_id": seg.segment_id,
                        "outcome_type": seg.outcome,
                        "config_hash": self._config_hash,
                    })

                    # Track previous episode_id for causal chain (Phase 14.1)
                    prev_episode_id = episode.get("episode_id")

                except Exception as e:
                    logger.warning(
                        "Failed to populate episode for segment {}: {}",
                        seg.segment_id, e,
                    )
                    warnings.append(f"Episode population failed for {seg.segment_id}: {e}")

            logger.info(
                "Step 9: Populated {} episodes from {} segments",
                len(populated_episodes), len(segments),
            )

        except Exception as e:
            logger.error("Episode population failed for {}: {}", session_id, e)
            warnings.append(f"Episode population failed: {e}")

        # Step 10: Validate episodes
        valid_episodes: list[dict] = []
        episode_invalid_count = 0

        for ep_wrapper in populated_episodes:
            # Extract episode and metadata
            episode = ep_wrapper["episode"]
            metadata = {
                "session_id": ep_wrapper["session_id"],
                "segment_id": ep_wrapper["segment_id"],
                "outcome_type": ep_wrapper["outcome_type"],
                "config_hash": ep_wrapper["config_hash"],
            }

            try:
                # Validate the episode WITHOUT metadata fields
                is_valid, validation_errors = self._validator.validate(episode)
                if is_valid:
                    # Add metadata AFTER successful validation
                    episode_with_metadata = {**episode, **metadata}
                    valid_episodes.append(episode_with_metadata)
                else:
                    episode_invalid_count += 1
                    logger.warning(
                        "Episode {} failed validation: {}",
                        episode.get("episode_id", "?"),
                        "; ".join(validation_errors[:3]),
                    )
            except Exception as e:
                episode_invalid_count += 1
                logger.warning(
                    "Episode validation error for {}: {}",
                    episode.get("episode_id", "?"), e,
                )

        logger.info(
            "Step 10: Validated episodes: {} valid, {} invalid",
            len(valid_episodes), episode_invalid_count,
        )

        # Step 11: Write valid episodes to DuckDB
        episode_write_stats: dict[str, int] = {"inserted": 0, "updated": 0, "total": 0}
        try:
            if valid_episodes:
                episode_write_stats = write_episodes(self._conn, valid_episodes)
                logger.info(
                    "Step 11: Wrote {} episodes ({} inserted, {} updated)",
                    episode_write_stats["total"],
                    episode_write_stats["inserted"],
                    episode_write_stats["updated"],
                )
        except Exception as e:
            logger.error("Episode write failed for {}: {}", session_id, e)
            warnings.append(f"Episode write failed: {e}")

        # Step 11.5: Ingest staged premises from PAG hook
        premise_staging_stats: dict[str, int] = {}
        try:
            from src.pipeline.premise.ingestion import ingest_staging as _ingest_staging
            from src.pipeline.premise.registry import PremiseRegistry as _PremiseRegistry
            from src.pipeline.premise.schema import create_premise_schema as _create_premise_schema
            _create_premise_schema(self._conn)
            _premise_registry = _PremiseRegistry(self._conn)
            premise_staging_stats = _ingest_staging(_premise_registry)
            if premise_staging_stats.get("ingested", 0) > 0:
                logger.info(
                    "Step 11.5: Ingested {} staged premises ({} errors, {} begging_the_question)",
                    premise_staging_stats["ingested"],
                    premise_staging_stats["errors"],
                    premise_staging_stats["begging_the_question"],
                )
        except ImportError:
            pass  # Premise module not available
        except Exception as e:
            logger.warning("Premise staging ingestion failed: {}", e)
            warnings.append(f"Premise staging ingestion failed: {e}")

        # Step 12: Extract constraints from correct/block episodes
        constraints_new = 0
        constraints_dup = 0
        for episode in valid_episodes:
            try:
                constraint = self._constraint_extractor.extract(episode)
                if constraint is not None:
                    added = self._constraint_store.add(constraint)
                    if added:
                        constraints_new += 1
                    else:
                        constraints_dup += 1
            except Exception as e:
                logger.warning(
                    "Constraint extraction failed for episode {}: {}",
                    episode.get("episode_id", "?"),
                    e,
                )

        if constraints_new > 0 or constraints_dup > 0:
            self._constraint_store.save()
            logger.info(
                "Step 12: Extracted {} new constraints ({} duplicate, {} total)",
                constraints_new,
                constraints_dup,
                self._constraint_store.count,
            )

        # Step 13: Escalation detection
        escalation_detected = 0
        escalation_constraints_generated = 0
        try:
            detector = EscalationDetector(self._config)
            candidates = detector.detect(tagged_events)
            escalation_detected = len(candidates)

            if candidates:
                constraint_gen = EscalationConstraintGenerator()
                detector_version_major = self._config.escalation.detector_version.split(".")[0]
                escalation_episodes: list[dict] = []

                for candidate in candidates:
                    # Generate escalation episode ID: SHA-256(session_id + block_event_ref + bypass_event_ref + detector_version_major)[:16]
                    esc_id_input = (
                        f"{candidate.session_id}"
                        f"{candidate.block_event_id}"
                        f"{candidate.bypass_event_id}"
                        f"{detector_version_major}"
                    )
                    o_esc_id = hashlib.sha256(esc_id_input.encode()).hexdigest()[:16]

                    # Determine reaction_label from the episode that contains this segment
                    reaction_label_for_esc = None
                    for ep_wrapper in populated_episodes:
                        ep = ep_wrapper["episode"]
                        outcome = ep.get("outcome", {})
                        reaction = outcome.get("reaction")
                        if reaction:
                            reaction_label_for_esc = reaction.get("label")
                            break  # Use first available reaction

                    # Generate constraint from escalation
                    constraint = constraint_gen.generate(
                        candidate,
                        reaction_label_for_esc,
                        existing_constraints=self._constraint_store.constraints,
                    )
                    if constraint is not None:
                        added = self._constraint_store.add(constraint)
                        if added:
                            escalation_constraints_generated += 1

                    # Find bypassed constraint ID
                    bypassed_constraint_id = constraint_gen.find_matching_constraint(
                        candidate, self._constraint_store.constraints
                    )

                    # Determine approval status from reaction
                    approval_status = self._determine_approval_status(reaction_label_for_esc)

                    # Build escalation episode dict
                    esc_episode = {
                        "episode_id": o_esc_id,
                        "session_id": candidate.session_id,
                        "segment_id": "",
                        "timestamp": candidate.block_event_id,  # will use block event timestamp
                        "mode": "ESCALATE",
                        "escalate_block_event_ref": candidate.block_event_id,
                        "escalate_bypass_event_ref": candidate.bypass_event_id,
                        "escalate_bypassed_constraint_id": bypassed_constraint_id,
                        "escalate_approval_status": approval_status,
                        "escalate_confidence": candidate.confidence,
                        "escalate_detector_version": candidate.detector_version,
                    }

                    # Resolve block event timestamp for the episode
                    block_ev = event_by_id.get(candidate.block_event_id)
                    if block_ev:
                        esc_episode["timestamp"] = block_ev["ts_utc"]

                    escalation_episodes.append(esc_episode)

                # Write escalation episodes to DuckDB
                if escalation_episodes:
                    esc_write_stats = write_escalation_episodes(self._conn, escalation_episodes)
                    logger.info(
                        "Step 13: Wrote {} escalation episodes ({} inserted, {} updated)",
                        esc_write_stats["total"],
                        esc_write_stats["inserted"],
                        esc_write_stats["updated"],
                    )

                # Save constraint store if new escalation constraints were generated
                if escalation_constraints_generated > 0:
                    self._constraint_store.save()

                logger.info(
                    "Step 13: Detected {} escalations, generated {} constraints",
                    escalation_detected,
                    escalation_constraints_generated,
                )
        except Exception as e:
            logger.warning("Escalation detection failed: {}", e)
            warnings.append(f"Escalation detection failed: {e}")

        # Step 14: Session constraint evaluation (decision durability)
        eval_count = 0
        amnesia_count = 0
        try:
            # Derive session scope from events
            session_scope_paths = extract_session_scope(
                [e.__dict__ if hasattr(e, '__dict__') and not isinstance(e, dict) else e
                 for e in all_session_events]
            )

            # Get session start time
            session_start_time = None
            if all_session_events:
                first_ev = all_session_events[0]
                first_ts = first_ev.get("ts_utc") if isinstance(first_ev, dict) else getattr(first_ev, "ts_utc", None)
                session_start_time = str(first_ts) if first_ts else None

            if session_start_time and self._constraint_store.constraints:
                # Build escalation violations map from DuckDB
                escalation_violations: dict[str, str] = {}
                try:
                    esc_rows = self._conn.execute(
                        "SELECT escalate_bypassed_constraint_id FROM episodes "
                        "WHERE session_id = ? AND mode = 'ESCALATE' "
                        "AND escalate_bypassed_constraint_id IS NOT NULL",
                        [session_id],
                    ).fetchall()
                    for (cid,) in esc_rows:
                        escalation_violations[cid] = session_id
                except Exception:
                    pass  # Table may not have escalation columns in old DBs

                # Evaluate constraints
                evaluator = SessionConstraintEvaluator(self._config)
                eval_results = evaluator.evaluate(
                    session_id=session_id,
                    session_scope_paths=session_scope_paths,
                    session_start_time=session_start_time,
                    events=all_session_events,
                    constraints=self._constraint_store.constraints,
                    escalation_violations=escalation_violations,
                )

                if eval_results:
                    write_constraint_evals(self._conn, eval_results)
                    eval_count = len(eval_results)

                    # Detect amnesia events
                    detector = AmnesiaDetector()
                    amnesia_events = detector.detect(
                        eval_results, self._constraint_store.constraints
                    )
                    if amnesia_events:
                        write_amnesia_events(self._conn, amnesia_events)
                        amnesia_count = len(amnesia_events)

                    logger.info(
                        "Step 14: Evaluated {} constraints ({} amnesia events)",
                        eval_count,
                        amnesia_count,
                    )
        except Exception as e:
            logger.warning("Constraint evaluation failed: {}", e)
            warnings.append(f"Constraint evaluation failed: {e}")

        # Step 14.5: Run premise staining from amnesia events
        premise_staining_stats: dict[str, int] = {}
        try:
            from src.pipeline.premise.ingestion import run_staining as _run_staining
            from src.pipeline.premise.registry import PremiseRegistry as _PremiseRegistry2
            from src.pipeline.premise.schema import create_premise_schema as _create_premise_schema2
            _create_premise_schema2(self._conn)
            _premise_registry2 = _PremiseRegistry2(self._conn)
            # Collect amnesia events from Step 14
            if amnesia_count > 0:
                # Re-read amnesia events from DuckDB for this session
                try:
                    amnesia_rows = self._conn.execute(
                        "SELECT amnesia_id, session_id, constraint_id, constraint_type, "
                        "severity, evidence, detected_at FROM amnesia_events "
                        "WHERE session_id = ?",
                        [session_id],
                    ).fetchall()
                    from src.pipeline.durability.amnesia import AmnesiaEvent as _AmnesiaEvent
                    import json as _json
                    amnesia_event_list = []
                    for row in amnesia_rows:
                        evidence = row[5]
                        if isinstance(evidence, str):
                            try:
                                evidence = _json.loads(evidence)
                            except Exception:
                                evidence = []
                        amnesia_event_list.append(_AmnesiaEvent(
                            amnesia_id=row[0],
                            session_id=row[1],
                            constraint_id=row[2],
                            constraint_type=row[3],
                            severity=row[4],
                            evidence=evidence if evidence else [],
                            detected_at=str(row[6]) if row[6] else "",
                        ))
                    if amnesia_event_list:
                        premise_staining_stats = _run_staining(
                            _premise_registry2, amnesia_event_list
                        )
                        if premise_staining_stats.get("direct_stains", 0) > 0:
                            logger.info(
                                "Step 14.5: Stained {} premises ({} direct, {} propagated)",
                                premise_staining_stats["direct_stains"] + premise_staining_stats["propagated_stains"],
                                premise_staining_stats["direct_stains"],
                                premise_staining_stats["propagated_stains"],
                            )
                except Exception as e2:
                    logger.warning("Amnesia event re-read for staining failed: {}", e2)
        except ImportError:
            pass  # Premise module not available
        except Exception as e:
            logger.warning("Premise staining failed: {}", e)
            warnings.append(f"Premise staining failed: {e}")

        # Step 15: DDF Tier 1 flame event detection (markers L0-2 + O_AXS)
        ddf_tier1_count = 0
        o_axs_count = 0
        try:
            from src.pipeline.ddf.tier1.markers import detect_markers as _detect_markers
            from src.pipeline.ddf.tier1.o_axs import OAxsDetector as _OAxsDetector
            from src.pipeline.ddf.writer import write_flame_events as _write_flame_events
            from src.pipeline.ddf.schema import create_ddf_schema as _create_ddf_schema

            _create_ddf_schema(self._conn)

            # Tier 1 L0-2 markers from human messages
            tier1_events = _detect_markers(all_session_events, session_id)

            # O_AXS detection (per-session state)
            o_axs_detector = _OAxsDetector(self._config.ddf.o_axs)
            for event_dict in all_session_events:
                actor = event_dict.get("actor", "")
                text = ""
                payload = event_dict.get("payload", {})
                if isinstance(payload, dict):
                    text = payload.get("common", {}).get("text", "")
                elif isinstance(payload, str):
                    import json as _json2
                    try:
                        p = _json2.loads(payload)
                        text = p.get("common", {}).get("text", "") if isinstance(p, dict) else ""
                    except Exception:
                        text = ""
                detected, evidence = o_axs_detector.detect(text, actor)
                if detected:
                    from src.pipeline.ddf.models import FlameEvent as _FlameEvent
                    o_axs_event = _FlameEvent(
                        flame_event_id=_FlameEvent.make_id(session_id, o_axs_count, "o_axs"),
                        session_id=session_id,
                        human_id="default_human",
                        prompt_number=o_axs_count,
                        marker_level=2,  # O_AXS is Level 2 (assertive identification)
                        marker_type="o_axs",
                        evidence_excerpt=str(evidence)[:500] if evidence else None,
                        axis_identified=evidence.get("novel_concept") if evidence else None,
                        subject="human",
                        detection_source="stub",
                    )
                    tier1_events.append(o_axs_event)
                    o_axs_count += 1

            if tier1_events:
                _write_flame_events(self._conn, tier1_events)
                ddf_tier1_count = len(tier1_events)
                logger.info("Step 15: Detected {} Tier 1 flame events ({} O_AXS)", ddf_tier1_count, o_axs_count)
        except ImportError:
            pass  # DDF module not available
        except Exception as e:
            logger.warning("DDF Tier 1 detection failed: {}", e)
            warnings.append(f"DDF Tier 1 detection failed: {e}")

        # Step 16: DDF Tier 2 LLM enrichment (L3-7)
        ddf_tier2_count = 0
        try:
            from src.pipeline.ddf.tier2.flame_extractor import FlameEventExtractor as _FlameExtractor
            from src.pipeline.ddf.writer import write_flame_events as _write_flame_events2

            extractor = _FlameExtractor(self._config, self._conn)
            enriched = extractor.enrich_tier1(session_id, valid_episodes)

            # Build tagged_events as dicts for AI marker detection
            tagged_event_dicts = []
            for te in tagged_events:
                te_dict = {
                    "actor": te.event.actor,
                    "payload": te.event.payload if isinstance(te.event.payload, dict) else {},
                }
                # Wrap payload in common.text format if not already
                if "common" not in te_dict["payload"]:
                    te_dict["payload"] = {"common": {"text": ""}}
                tagged_event_dicts.append(te_dict)

            ai_markers = extractor.detect_ai_markers(session_id, valid_episodes, tagged_event_dicts)

            all_tier2 = enriched + ai_markers
            if all_tier2:
                _write_flame_events2(self._conn, all_tier2)
                ddf_tier2_count = len(all_tier2)
                logger.info("Step 16: Enriched/detected {} Tier 2 flame events", ddf_tier2_count)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("DDF Tier 2 enrichment failed: {}", e)
            warnings.append(f"DDF Tier 2 enrichment failed: {e}")

        # Step 17: Deposit Level 6 to memory_candidates
        ddf_deposits = 0
        try:
            from src.pipeline.ddf.tier2.flame_extractor import FlameEventExtractor as _FlameExtractor2
            extractor2 = _FlameExtractor2(self._config, self._conn)
            # Read all Level 6+ flood-confirmed events not yet deposited
            all_flame = self._conn.execute(
                "SELECT * FROM flame_events WHERE session_id = ? AND marker_level >= 6 AND flood_confirmed = TRUE AND deposited_to_candidates = FALSE",
                [session_id],
            ).fetchall()
            if all_flame:
                from src.pipeline.ddf.models import FlameEvent as _FE2
                flame_events_to_deposit = []
                # Get column names from DESCRIBE
                cols_result = self._conn.execute("DESCRIBE flame_events").fetchall()
                cols = [row[0] for row in cols_result]
                for row in all_flame:
                    row_dict = dict(zip(cols, row))
                    fe = _FE2(**{k: v for k, v in row_dict.items() if k in _FE2.model_fields})
                    flame_events_to_deposit.append(fe)
                ddf_deposits = extractor2.deposit_level6(self._conn, flame_events_to_deposit)
                if ddf_deposits > 0:
                    logger.info("Step 17: Deposited {} Level 6 events to memory_candidates", ddf_deposits)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("DDF deposit failed: {}", e)
            warnings.append(f"DDF deposit failed: {e}")

        # Step 18: DDF-09 False Integration + DDF-10 Causal Isolation
        ddf_false_integration = 0
        ddf_causal_isolation = 0
        try:
            from src.pipeline.ddf.tier2.false_integration import FalseIntegrationDetector as _FID
            from src.pipeline.ddf.tier2.causal_isolation import CausalIsolationRecorder as _CIR
            from src.pipeline.ddf.writer import write_flame_events as _write_flame_events3

            # False Integration (DDF-09)
            fid = _FID(self._config, self._conn)
            fi_events, fi_hypotheses = fid.detect(session_id, valid_episodes)
            if fi_events:
                _write_flame_events3(self._conn, fi_events)
                ddf_false_integration = len(fi_events)

            # Causal Isolation (DDF-10)
            cir = _CIR(self._conn)
            ci_events = cir.record(session_id)
            if ci_events:
                _write_flame_events3(self._conn, ci_events)
                ddf_causal_isolation = len(ci_events)

            if ddf_false_integration > 0 or ddf_causal_isolation > 0:
                logger.info("Step 18: {} false integration, {} causal isolation markers", ddf_false_integration, ddf_causal_isolation)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("DDF-09/DDF-10 detection failed: {}", e)
            warnings.append(f"DDF-09/DDF-10 detection failed: {e}")

        # Step 19: GeneralizationRadius + epistemological origin + spiral promotion
        ddf_metrics_count = 0
        ddf_spiral_promotions = 0
        try:
            from src.pipeline.ddf.generalization import compute_all_metrics as _compute_all, write_constraint_metrics as _write_metrics

            metrics = _compute_all(self._conn, self._config)
            if metrics:
                ddf_metrics_count = _write_metrics(self._conn, metrics)
                logger.info("Step 19: Computed {} constraint metrics", ddf_metrics_count)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("DDF metrics computation failed: {}", e)
            warnings.append(f"DDF metrics computation failed: {e}")

        # DDF-06 terminal act: promote spiral candidates to project_wisdom
        try:
            from src.pipeline.ddf.spiral import promote_spirals_to_wisdom as _promote_spirals
            from pathlib import Path as _Path
            db_path = _Path(self._db_path) if self._db_path != ":memory:" else _Path("data/ope.db")
            ddf_spiral_promotions = _promote_spirals(self._conn, db_path)
            if ddf_spiral_promotions > 0:
                logger.info("Step 19: Promoted {} spiral candidates to project_wisdom", ddf_spiral_promotions)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("DDF spiral promotion failed: {}", e)
            warnings.append(f"DDF spiral promotion failed: {e}")

        # Step 20: TransportEfficiency computation + backfill (Phase 16)
        ddf_te_count = 0
        ddf_trunk_backfill = 0
        ddf_te_delta_backfill = 0
        try:
            from src.pipeline.ddf.transport_efficiency import (
                compute_te_for_session as _compute_te,
                write_te_rows as _write_te,
                backfill_trunk_quality as _backfill_trunk,
                backfill_te_delta as _backfill_delta,
            )

            te_rows = _compute_te(self._conn, session_id)
            if te_rows:
                ddf_te_count = _write_te(self._conn, te_rows)
                logger.info("Step 20: Computed {} TE rows", ddf_te_count)

            # Run backfill jobs (may update rows from earlier sessions)
            ddf_trunk_backfill = _backfill_trunk(self._conn)
            ddf_te_delta_backfill = _backfill_delta(self._conn)
            if ddf_trunk_backfill > 0 or ddf_te_delta_backfill > 0:
                logger.info(
                    "Step 20: Backfilled {} trunk_quality rows, {} te_delta entries",
                    ddf_trunk_backfill, ddf_te_delta_backfill,
                )
        except ImportError:
            pass  # TE module not available
        except Exception as e:
            logger.warning("TransportEfficiency computation failed: {}", e)
            warnings.append(f"TransportEfficiency computation failed: {e}")

        # Step 21: Structural integrity analysis (Phase 18)
        ddf_structural_count = 0
        ddf_op8_count = 0
        try:
            from src.pipeline.ddf.structural.detectors import (
                detect_structural_signals as _detect_structural,
            )
            from src.pipeline.ddf.structural.writer import (
                write_structural_events as _write_structural,
            )
            from src.pipeline.ddf.structural.op8 import (
                deposit_op8_corrections as _deposit_op8,
            )
            from src.pipeline.ddf.structural.schema import (
                create_structural_schema as _create_structural_schema,
            )

            _create_structural_schema(self._conn)

            structural_events = _detect_structural(self._conn, session_id)
            _write_structural(self._conn, structural_events)
            ddf_structural_count = len(structural_events)

            ddf_op8_count = _deposit_op8(self._conn, session_id)

            if ddf_structural_count > 0 or ddf_op8_count > 0:
                logger.info(
                    "Step 21: Structural: {} events, {} Op-8 corrections",
                    ddf_structural_count,
                    ddf_op8_count,
                )
        except ImportError:
            pass  # DDF structural module not available
        except Exception as e:
            logger.warning("Structural integrity analysis failed: {}", e)
            warnings.append(f"Structural integrity analysis failed: {e}")

        # Step 22: Compute stats
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
            "episode_populated_count": len(populated_episodes),
            "episode_valid_count": len(valid_episodes),
            "episode_invalid_count": episode_invalid_count,
            "reaction_distribution": dict(reaction_distribution),
            "constraints_extracted": constraints_new,
            "constraints_duplicate": constraints_dup,
            "constraints_total": self._constraint_store.count,
            "escalation_detected": escalation_detected,
            "escalation_constraints_generated": escalation_constraints_generated,
            "constraint_evals": eval_count,
            "amnesia_events_detected": amnesia_count,
            "ddf_tier1_count": ddf_tier1_count,
            "ddf_tier2_count": ddf_tier2_count,
            "ddf_deposits": ddf_deposits,
            "ddf_o_axs_count": o_axs_count,
            "ddf_false_integration": ddf_false_integration,
            "ddf_causal_isolation": ddf_causal_isolation,
            "ddf_metrics_count": ddf_metrics_count,
            "ddf_spiral_promotions": ddf_spiral_promotions,
            "ddf_te_count": ddf_te_count,
            "ddf_trunk_backfill": ddf_trunk_backfill,
            "ddf_te_delta_backfill": ddf_te_delta_backfill,
            "ddf_structural_count": ddf_structural_count,
            "ddf_op8_count": ddf_op8_count,
            "errors": errors,
            "warnings": warnings,
            "duration_seconds": round(duration_s, 2),
        }

        logger.info(
            "Session {} complete: {} events, {} episodes, {} valid episodes in {:.1f}s",
            session_id,
            len(canonical_events),
            len(segments),
            len(valid_episodes),
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

        # Aggregate tag distribution and episode stats
        agg_tags: Counter[str] = Counter()
        agg_outcomes: Counter[str] = Counter()
        agg_reactions: Counter[str] = Counter()
        total_valid_episodes = 0
        total_invalid_episodes = 0
        total_constraints_extracted = 0
        total_constraints_duplicate = 0
        for r in results:
            for tag, count in r.get("tag_distribution", {}).items():
                agg_tags[tag] += count
            for outcome, count in r.get("outcome_distribution", {}).items():
                agg_outcomes[outcome] += count
            for label, count in r.get("reaction_distribution", {}).items():
                agg_reactions[label] += count
            total_valid_episodes += r.get("episode_valid_count", 0)
            total_invalid_episodes += r.get("episode_invalid_count", 0)
            total_constraints_extracted += r.get("constraints_extracted", 0)
            total_constraints_duplicate += r.get("constraints_duplicate", 0)

        return {
            "sessions_processed": len(results),
            "total_events": total_events,
            "total_episodes": total_episodes,
            "total_valid_episodes": total_valid_episodes,
            "total_invalid_episodes": total_invalid_episodes,
            "tag_distribution": dict(agg_tags),
            "outcome_distribution": dict(agg_outcomes),
            "reaction_distribution": dict(agg_reactions),
            "constraints_extracted": total_constraints_extracted,
            "constraints_duplicate": total_constraints_duplicate,
            "constraints_total": self._constraint_store.count,
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
    def _find_next_human_message(
        all_events: list[dict],
        after_ts: Any,
        tag_by_event_id: dict[str, list[str]],
    ) -> dict | None:
        """Find the next human_orchestrator user_msg event after a timestamp.

        Constructs the message dict with 'tags' and 'payload' keys that
        ReactionLabeler expects.

        Args:
            all_events: All session events ordered by ts_utc.
            after_ts: Timestamp to search after (segment end_ts).
            tag_by_event_id: Mapping of event_id -> list of tag labels.

        Returns:
            Dict with tags and payload, or None if no next human message.
        """
        if after_ts is None:
            return None

        for event in all_events:
            if event["ts_utc"] <= after_ts:
                continue
            if event["actor"] == "human_orchestrator" and event["event_type"] == "user_msg":
                event_tags = tag_by_event_id.get(event["event_id"], [])
                # Build message dict for ReactionLabeler
                payload = event.get("payload", {})
                if isinstance(payload, dict):
                    text = payload.get("common", {}).get("text", "")
                elif isinstance(payload, str):
                    try:
                        parsed = json.loads(payload)
                        text = parsed.get("common", {}).get("text", "") if isinstance(parsed, dict) else ""
                    except Exception:
                        text = ""
                else:
                    text = ""

                return {
                    "tags": event_tags,
                    "payload": {"text": text},
                }

        return None

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
    def _determine_approval_status(reaction_label: str | None) -> str:
        """Determine escalation approval status from human reaction.

        Mapping:
        - approve -> APPROVED (human approved the escalation)
        - block/correct -> REJECTED (human explicitly rejected)
        - None/redirect/question/unknown -> UNAPPROVED (no explicit approval)

        Args:
            reaction_label: The human reaction label, or None.

        Returns:
            Approval status string: APPROVED, REJECTED, or UNAPPROVED.
        """
        if reaction_label == "approve":
            return "APPROVED"
        if reaction_label in ("block", "correct"):
            return "REJECTED"
        return "UNAPPROVED"

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
            "episode_populated_count": 0,
            "episode_valid_count": 0,
            "episode_invalid_count": 0,
            "reaction_distribution": {},
            "constraints_extracted": 0,
            "constraints_duplicate": 0,
            "constraints_total": 0,
            "escalation_detected": 0,
            "escalation_constraints_generated": 0,
            "constraint_evals": 0,
            "amnesia_events_detected": 0,
            "ddf_tier1_count": 0,
            "ddf_tier2_count": 0,
            "ddf_deposits": 0,
            "ddf_o_axs_count": 0,
            "ddf_false_integration": 0,
            "ddf_causal_isolation": 0,
            "ddf_metrics_count": 0,
            "ddf_spiral_promotions": 0,
            "ddf_structural_count": 0,
            "ddf_op8_count": 0,
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
