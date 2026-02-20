"""Decision durability evaluation module.

Provides session-level constraint evaluation, amnesia detection,
durability score computation, and scope extraction.

Exports:
    SessionConstraintEvaluator: Evaluates constraints against session events
    ConstraintEvalResult: Frozen model for evaluation results
    AmnesiaDetector: Detects amnesia events from VIOLATED evaluations
    AmnesiaEvent: Frozen model for amnesia events
    extract_session_scope: Derives file paths from event payloads
    DurabilityIndex: Computes durability scores via SQL aggregation
    migrate_constraints: Migrates constraints to Phase 10 schema
"""

from src.pipeline.durability.amnesia import AmnesiaDetector, AmnesiaEvent
from src.pipeline.durability.evaluator import (
    ConstraintEvalResult,
    SessionConstraintEvaluator,
)
from src.pipeline.durability.index import DurabilityIndex
from src.pipeline.durability.migration import migrate_constraints
from src.pipeline.durability.scope_extractor import extract_session_scope

__all__ = [
    "AmnesiaDetector",
    "AmnesiaEvent",
    "ConstraintEvalResult",
    "DurabilityIndex",
    "SessionConstraintEvaluator",
    "extract_session_scope",
    "migrate_constraints",
]
