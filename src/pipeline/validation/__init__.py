"""Genus-based multi-layer validation for orchestrator episodes.

Extends the single-layer EpisodeValidator (JSON Schema) into a five-layer
validation system: Schema, Evidence Grounding, Non-Contradiction,
Constraint Enforcement, and Episode Integrity.

Also provides gold-standard validation workflow, quality metrics, and
Parquet export for ML training pipelines.

Exports:
    GenusValidator: Composed five-layer validator
    SchemaLayer: Wraps EpisodeValidator (Layer A)
    EvidenceGroundingLayer: Mode-specific evidence checks (Layer B)
    NonContradictionLayer: Mode/gate consistency checks (Layer C)
    ConstraintEnforcementLayer: Constraint scope/severity checks (Layer D)
    EpisodeIntegrityLayer: Structural integrity checks (Layer E)
    export_for_review: Export episodes for human review
    import_labels: Import gold-standard labels
    compute_metrics: Calculate quality metrics
    MetricsReport: Metrics result dataclass
    export_parquet: Parquet export via DuckDB COPY
"""

from src.pipeline.validation.exporter import export_parquet, export_parquet_partitioned
from src.pipeline.validation.genus_validator import GenusValidator
from src.pipeline.validation.gold_standard import export_for_review, import_labels
from src.pipeline.validation.layers import (
    ConstraintEnforcementLayer,
    EpisodeIntegrityLayer,
    EvidenceGroundingLayer,
    NonContradictionLayer,
    SchemaLayer,
)
from src.pipeline.validation.metrics import MetricsReport, compute_metrics

__all__ = [
    "GenusValidator",
    "SchemaLayer",
    "EvidenceGroundingLayer",
    "NonContradictionLayer",
    "ConstraintEnforcementLayer",
    "EpisodeIntegrityLayer",
    "export_for_review",
    "import_labels",
    "compute_metrics",
    "MetricsReport",
    "export_parquet",
    "export_parquet_partitioned",
]
