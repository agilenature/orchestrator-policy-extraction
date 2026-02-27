"""EBC Pydantic models for behavioral contract and drift alerts.

Defines the data structures that formalize PLAN.md frontmatter into
machine-readable contracts and represent drift detection results.

Exports:
    EBCArtifact: Artifact entry from must_haves.artifacts
    EBCKeyLink: Key link entry from must_haves.key_links
    ExternalBehavioralContract: Full contract parsed from PLAN.md frontmatter
    DriftSignal: Individual drift signal component
    EBCDriftAlert: Alert artifact for detected drift
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EBCArtifact(BaseModel, frozen=True):
    """An artifact entry from must_haves.artifacts in PLAN.md frontmatter."""

    path: str
    provides: str = ""
    exports: list[str] = Field(default_factory=list)
    contains: str = ""


class EBCKeyLink(BaseModel, frozen=True):
    """A key link entry from must_haves.key_links in PLAN.md frontmatter.

    Supports construction via both alias names (from/to) and field names
    (from_path/to_target) for convenience.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_path: str = Field(..., alias="from")
    to_target: str = Field(..., alias="to")
    via: str = ""
    pattern: str = ""


class ExternalBehavioralContract(BaseModel, frozen=True):
    """Full behavioral contract parsed from PLAN.md frontmatter.

    Represents the expected behavior of a plan execution: which files
    will be modified, what artifacts will be produced, and what truths
    must hold after execution.
    """

    phase: str
    plan: int | str
    plan_type: str = "execute"
    wave: int = 1
    depends_on: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    autonomous: bool = True
    truths: list[str] = Field(default_factory=list)
    artifacts: list[EBCArtifact] = Field(default_factory=list)
    key_links: list[EBCKeyLink] = Field(default_factory=list)

    @property
    def expected_write_paths(self) -> set[str]:
        """Union of files_modified and artifact paths.

        These are the files the plan declares it will create or modify.
        """
        paths = set(self.files_modified)
        for artifact in self.artifacts:
            paths.add(artifact.path)
        return paths


class DriftSignal(BaseModel, frozen=True):
    """An individual drift signal detected during EBC comparison.

    signal_type is one of: "unexpected_file", "missing_expected_file", "no_progress"
    """

    signal_type: str
    detail: str
    weight: float


class EBCDriftAlert(BaseModel, frozen=True):
    """Alert artifact for detected EBC drift.

    Persisted to data/alerts/{session_id}-ebc-drift.json when drift
    exceeds the configured threshold.
    """

    session_id: str
    drift_score: float
    signals: list[DriftSignal]
    ebc_phase: str
    ebc_plan: str
    unexpected_files: list[str] = Field(default_factory=list)
    missing_expected_files: list[str] = Field(default_factory=list)
