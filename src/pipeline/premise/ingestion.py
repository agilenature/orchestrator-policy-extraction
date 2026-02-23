"""Staging ingestion: bridge between PAG hook JSONL output and DuckDB premise_registry.

Reads premise records from the JSONL staging file (written by the PAG hook),
validates and ingests them into the premise_registry DuckDB table, computes
derivation depth, and detects Begging the Question (circular self-reference
in derivation chains).

Also provides run_staining() for integrating the StainingPipeline into the
batch pipeline runner.

Exports:
    ingest_staging: Read JSONL staging, write to DuckDB, compute depth, detect circularity
    run_staining: Execute staining pipeline from amnesia events
"""

from __future__ import annotations

import logging
from typing import Any

from src.pipeline.durability.amnesia import AmnesiaEvent
from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.staging import STAGING_PATH, clear_staging, read_staging
from src.pipeline.premise.staining import StainingPipeline

logger = logging.getLogger(__name__)


def ingest_staging(
    registry: PremiseRegistry,
    staging_path: str = STAGING_PATH,
) -> dict[str, int]:
    """Ingest staged premise records from JSONL into DuckDB premise_registry.

    Steps:
      1. Read all staged records from the JSONL file.
      2. For each record, validate by constructing a PremiseRecord.
      3. Register each valid record in the premise_registry.
      4. Compute derivation_depth and detect Begging the Question.
      5. Clear the staging file on success.
      6. Return stats dict.

    Begging the Question detection (PREMISE-06): If a premise's own
    premise_id appears in its derivation_chain (circular self-reference),
    the premise is stained with stained_by="begging_the_question" and
    its staleness_counter is incremented.

    Args:
        registry: PremiseRegistry instance for writing to DuckDB.
        staging_path: Path to the staging JSONL file.

    Returns:
        Stats dict: {"ingested": N, "skipped": M, "errors": E, "begging_the_question": B}
    """
    records = read_staging(staging_path)

    stats = {
        "ingested": 0,
        "skipped": 0,
        "errors": 0,
        "begging_the_question": 0,
    }

    if not records:
        return stats

    ingested_ids: list[str] = []

    for raw in records:
        try:
            # Validate by constructing a PremiseRecord
            record = _dict_to_record(raw)
            registry.register(record)
            ingested_ids.append(record.premise_id)
            stats["ingested"] += 1
        except Exception as e:
            logger.warning("Failed to ingest premise record: %s", e)
            stats["errors"] += 1

    # Post-ingestion: compute derivation depth + Begging the Question
    for premise_id in ingested_ids:
        try:
            record = registry.get(premise_id)
            if record is None:
                continue

            chain = record.derivation_chain
            if chain and isinstance(chain, list) and len(chain) > 0:
                depth = len(chain)
                registry.update_derivation_depth(premise_id, depth)

                # Begging the Question: check if premise_id appears
                # in its own derivation_chain
                if _is_circular(premise_id, chain):
                    registry.stain(
                        premise_id=premise_id,
                        stained_by="begging_the_question",
                        ground_truth_pointer={
                            "detection": "circular_self_reference",
                            "premise_id": premise_id,
                            "derivation_chain": chain,
                        },
                    )
                    registry.update_staleness(premise_id)
                    stats["begging_the_question"] += 1
        except Exception as e:
            logger.warning(
                "Post-ingestion processing failed for %s: %s", premise_id, e
            )

    # Clear staging file after successful ingestion
    if stats["ingested"] > 0 or stats["errors"] > 0:
        clear_staging(staging_path)

    return stats


def run_staining(
    registry: PremiseRegistry,
    amnesia_events: list[Any],
) -> dict[str, int]:
    """Run the staining pipeline from amnesia events.

    Creates a StainingPipeline, stains from amnesia events, then
    propagates staining through derivation chains.

    Args:
        registry: PremiseRegistry instance.
        amnesia_events: List of AmnesiaEvent objects.

    Returns:
        Stats dict: {"direct_stains": N, "propagated_stains": M}
    """
    pipeline = StainingPipeline(registry)

    # Filter to AmnesiaEvent objects (defensive)
    valid_events = [
        e for e in amnesia_events if isinstance(e, AmnesiaEvent)
    ]

    direct = pipeline.stain_from_amnesia(valid_events)
    propagated = pipeline.propagate_staining()

    return {
        "direct_stains": len(direct),
        "propagated_stains": len(propagated),
    }


def _dict_to_record(raw: dict) -> PremiseRecord:
    """Convert a raw dict from staging JSONL to a PremiseRecord.

    Handles field name variations and provides defaults for optional fields.

    Args:
        raw: Dict from staging JSONL.

    Returns:
        PremiseRecord instance.

    Raises:
        ValueError: If required fields are missing.
    """
    # Required fields
    if "premise_id" not in raw:
        raise ValueError("Missing required field: premise_id")
    if "claim" not in raw:
        raise ValueError("Missing required field: claim")
    if "session_id" not in raw:
        raise ValueError("Missing required field: session_id")

    return PremiseRecord(
        premise_id=raw["premise_id"],
        claim=raw["claim"],
        validated_by=raw.get("validated_by"),
        validation_context=raw.get("validation_context"),
        foil=raw.get("foil"),
        distinguishing_prop=raw.get("distinguishing_prop"),
        staleness_counter=raw.get("staleness_counter", 0),
        staining_record=raw.get("staining_record"),
        ground_truth_pointer=raw.get("ground_truth_pointer"),
        project_scope=raw.get("project_scope"),
        session_id=raw["session_id"],
        tool_use_id=raw.get("tool_use_id"),
        foil_path_outcomes=raw.get("foil_path_outcomes"),
        divergence_patterns=raw.get("divergence_patterns"),
        parent_episode_links=raw.get("parent_episode_links"),
        derivation_depth=raw.get("derivation_depth", 0),
        validation_calls_before_claim=raw.get("validation_calls_before_claim", 0),
        derivation_chain=raw.get("derivation_chain"),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )


def _is_circular(premise_id: str, chain: list[dict]) -> bool:
    """Check if premise_id appears in its own derivation chain.

    Begging the Question: a premise that derives from itself is
    a circular self-reference.

    Args:
        premise_id: The premise ID to check for.
        chain: List of derivation chain dicts with 'derives_from' keys.

    Returns:
        True if premise_id appears in the chain.
    """
    for entry in chain:
        if isinstance(entry, dict):
            derives_from = entry.get("derives_from", "")
            if derives_from == premise_id:
                return True
    return False
