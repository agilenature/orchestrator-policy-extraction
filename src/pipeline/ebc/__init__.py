"""EBC (External Behavioral Contract) drift detection package.

Formalizes the implicit behavioral contract in PLAN.md frontmatter into
machine-readable schemas, compares against actual session behavior, and
persists structured alert artifacts when drift exceeds threshold.

Exports:
    EBCArtifact: Artifact entry from must_haves.artifacts
    EBCKeyLink: Key link entry from must_haves.key_links
    ExternalBehavioralContract: Full contract parsed from PLAN.md frontmatter
    EBCDriftAlert: Alert artifact for detected drift
    DriftSignal: Individual drift signal (unexpected/missing file)
    parse_ebc_from_plan: Parser for PLAN.md frontmatter -> EBC
"""

from src.pipeline.ebc.models import (
    DriftSignal,
    EBCArtifact,
    EBCDriftAlert,
    EBCKeyLink,
    ExternalBehavioralContract,
)
from src.pipeline.ebc.parser import parse_ebc_from_plan

__all__ = [
    "DriftSignal",
    "EBCArtifact",
    "EBCDriftAlert",
    "EBCKeyLink",
    "ExternalBehavioralContract",
    "parse_ebc_from_plan",
]
