"""Genus-based multi-layer validation for orchestrator episodes.

Extends the single-layer EpisodeValidator (JSON Schema) into a five-layer
validation system: Schema, Evidence Grounding, Non-Contradiction,
Constraint Enforcement, and Episode Integrity.

Exports:
    GenusValidator: Composed five-layer validator
    SchemaLayer: Wraps EpisodeValidator (Layer A)
    EvidenceGroundingLayer: Mode-specific evidence checks (Layer B)
    NonContradictionLayer: Mode/gate consistency checks (Layer C)
    ConstraintEnforcementLayer: Constraint scope/severity checks (Layer D)
    EpisodeIntegrityLayer: Structural integrity checks (Layer E)
"""

from src.pipeline.validation.genus_validator import GenusValidator
from src.pipeline.validation.layers import (
    ConstraintEnforcementLayer,
    EpisodeIntegrityLayer,
    EvidenceGroundingLayer,
    NonContradictionLayer,
    SchemaLayer,
)

__all__ = [
    "GenusValidator",
    "SchemaLayer",
    "EvidenceGroundingLayer",
    "NonContradictionLayer",
    "ConstraintEnforcementLayer",
    "EpisodeIntegrityLayer",
]
