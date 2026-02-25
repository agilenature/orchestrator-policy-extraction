"""Structural integrity detection sub-package (Phase 18).

Provides models, schema, writer, detectors, computer, and Op-8 depositor
for the structural_events table and bridge-warden structural integrity signals.

StructuralConfig lives in src.pipeline.models.config (not here)
because it is a DDFConfig sub-model, not a structural domain model.

Exports:
    StructuralEvent
    StructuralIntegrityResult
    detect_structural_signals
    compute_structural_integrity
    deposit_op8_corrections
"""

from src.pipeline.ddf.structural.models import (
    StructuralEvent,
    StructuralIntegrityResult,
)
from src.pipeline.ddf.structural.detectors import detect_structural_signals
from src.pipeline.ddf.structural.computer import (
    compute_structural_integrity,
    backfill_structural_integrity,
)
from src.pipeline.ddf.structural.op8 import deposit_op8_corrections

__all__ = [
    "StructuralEvent",
    "StructuralIntegrityResult",
    "detect_structural_signals",
    "compute_structural_integrity",
    "backfill_structural_integrity",
    "deposit_op8_corrections",
]
