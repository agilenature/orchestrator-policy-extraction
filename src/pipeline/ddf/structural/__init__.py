"""Structural integrity detection sub-package (Phase 18).

Provides models, schema, and writer for the structural_events table
that stores bridge-warden structural integrity signals.

StructuralConfig lives in src.pipeline.models.config (not here)
because it is a DDFConfig sub-model, not a structural domain model.

Exports:
    StructuralEvent
    StructuralIntegrityResult
"""

from src.pipeline.ddf.structural.models import (
    StructuralEvent,
    StructuralIntegrityResult,
)

__all__ = [
    "StructuralEvent",
    "StructuralIntegrityResult",
]
