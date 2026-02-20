"""Pydantic v2 models for orchestrator decision-point episodes.

Mirrors the JSON Schema structure in data/schemas/orchestrator-episode.schema.json.
All models are frozen (immutable) for consistency with Phase 1 patterns.

Episode hierarchy:
  Episode (top-level)
    -> ProjectRef
    -> Observation -> RepoState, QualityState, ContextState
    -> OrchestratorAction -> Scope, Gate
    -> Outcome -> ExecutorEffects, OutcomeQuality, Reaction, RewardSignals
    -> Provenance -> SourceRef
    -> ConstraintRef
    -> EpisodeLabels

Exports:
    Episode, ProjectRef, Observation, RepoState, DiffStat, QualityState,
    TestState, LintState, BuildState, ContextState, OrchestratorAction,
    Scope, Gate, Outcome, ExecutorEffects, GitEvent, OutcomeQuality,
    Reaction, RewardSignals, ObjectiveRewards, PreferenceModelRewards,
    ConstraintRef, ConstraintScope, SourceRef, Provenance, EpisodeLabels
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Shared / leaf models ---


class DiffStat(BaseModel, frozen=True):
    """File diff statistics (files, insertions, deletions)."""

    model_config = ConfigDict(populate_by_name=True)

    files: int = Field(..., ge=0)
    insertions: int = Field(..., ge=0)
    deletions: int = Field(..., ge=0)


# --- Observation sub-models ---


class RepoState(BaseModel, frozen=True):
    """Repository state at the decision point."""

    model_config = ConfigDict(populate_by_name=True)

    changed_files: list[str]
    diff_stat: DiffStat
    hotspots: list[str] = Field(default_factory=list)


class TestState(BaseModel, frozen=True):
    """Test execution state."""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["unknown", "pass", "fail", "not_run"]
    last_command: str | None = None
    failing: list[str] = Field(default_factory=list)


class LintState(BaseModel, frozen=True):
    """Lint execution state."""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["unknown", "pass", "fail", "not_run"]
    last_command: str | None = None
    issues_count: int | None = None


class BuildState(BaseModel, frozen=True):
    """Build execution state."""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["unknown", "pass", "fail", "not_run"]
    last_command: str | None = None


class QualityState(BaseModel, frozen=True):
    """Code quality state (tests, lint, build)."""

    model_config = ConfigDict(populate_by_name=True)

    tests: TestState
    lint: LintState
    build: BuildState | None = None


class ContextState(BaseModel, frozen=True):
    """Contextual state at the decision point."""

    model_config = ConfigDict(populate_by_name=True)

    recent_summary: str
    open_questions: list[str] = Field(default_factory=list)
    constraints_in_force: list[str] = Field(default_factory=list)


class Observation(BaseModel, frozen=True):
    """What the orchestrator observes before making a decision."""

    model_config = ConfigDict(populate_by_name=True)

    repo_state: RepoState
    quality_state: QualityState
    context: ContextState


# --- OrchestratorAction sub-models ---


class Scope(BaseModel, frozen=True):
    """File/path scope for an action."""

    model_config = ConfigDict(populate_by_name=True)

    paths: list[str]
    avoid: list[str] = Field(default_factory=list)


class Gate(BaseModel, frozen=True):
    """A gate/check required before proceeding."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal[
        "require_human_approval",
        "run_tests",
        "run_lint",
        "diff_size_cap",
        "no_write_before_plan",
        "protected_paths",
        "no_network",
        "no_secrets_access",
    ]
    params: dict | None = None


class OrchestratorAction(BaseModel, frozen=True):
    """The orchestrator's decision/action at a decision point."""

    model_config = ConfigDict(populate_by_name=True)

    mode: Literal[
        "Explore", "Plan", "Implement", "Verify", "Integrate", "Triage", "Refactor",
        "ESCALATE",
    ]
    goal: str
    scope: Scope
    executor_instruction: str
    gates: list[Gate]
    risk: Literal["low", "medium", "high", "critical"]
    expected_artifacts: list[str] = Field(default_factory=list)


# --- Outcome sub-models ---


class GitEvent(BaseModel, frozen=True):
    """A git event during executor execution."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal[
        "status", "diff", "add", "commit", "merge", "rebase", "push", "checkout",
        "branch",
    ]
    ref: str | None = None
    message: str | None = None


class ExecutorEffects(BaseModel, frozen=True):
    """What the executor actually did."""

    model_config = ConfigDict(populate_by_name=True)

    tool_calls_count: int = Field(..., ge=0)
    files_touched: list[str]
    commands_ran: list[str]
    git_events: list[GitEvent] = Field(default_factory=list)


class OutcomeQuality(BaseModel, frozen=True):
    """Quality metrics after executor execution."""

    model_config = ConfigDict(populate_by_name=True)

    tests_status: Literal["unknown", "pass", "fail", "not_run"]
    lint_status: Literal["unknown", "pass", "fail", "not_run"]
    diff_stat: DiffStat
    build_status: Literal["unknown", "pass", "fail", "not_run"] | None = None


class Reaction(BaseModel, frozen=True):
    """Human reaction to the outcome (optional)."""

    model_config = ConfigDict(populate_by_name=True)

    label: Literal["approve", "correct", "redirect", "block", "question", "unknown"]
    message: str
    confidence: float

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


class ObjectiveRewards(BaseModel, frozen=True):
    """Objective (automated) reward signals."""

    model_config = ConfigDict(populate_by_name=True)

    tests: float
    lint: float
    diff_risk: float


class PreferenceModelRewards(BaseModel, frozen=True):
    """Preference model reward signals (optional)."""

    model_config = ConfigDict(populate_by_name=True)

    predicted_reaction: Literal[
        "approve", "correct", "redirect", "block", "question", "unknown"
    ] | None = None
    confidence: float | None = None


class RewardSignals(BaseModel, frozen=True):
    """Reward signals for the outcome."""

    model_config = ConfigDict(populate_by_name=True)

    objective: ObjectiveRewards
    preference_model: PreferenceModelRewards | None = None


class Outcome(BaseModel, frozen=True):
    """Result of executor execution."""

    model_config = ConfigDict(populate_by_name=True)

    executor_effects: ExecutorEffects
    quality: OutcomeQuality
    reaction: Reaction | None = None
    reward_signals: RewardSignals


# --- Constraint model ---


class ConstraintScope(BaseModel, frozen=True):
    """Scope for a constraint (paths only, per JSON Schema)."""

    model_config = ConfigDict(populate_by_name=True)

    paths: list[str]


class ConstraintRef(BaseModel, frozen=True):
    """A constraint extracted from corrections/blocks."""

    model_config = ConfigDict(populate_by_name=True)

    constraint_id: str
    text: str
    severity: Literal["warning", "requires_approval", "forbidden"]
    scope: ConstraintScope
    detection_hints: list[str] = Field(default_factory=list)


# --- Provenance ---


class SourceRef(BaseModel, frozen=True):
    """Reference to source material."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["claude_jsonl", "terminal_log", "git", "ci"]
    ref: str


class Provenance(BaseModel, frozen=True):
    """Provenance tracking for the episode."""

    model_config = ConfigDict(populate_by_name=True)

    sources: list[SourceRef]

    @field_validator("sources")
    @classmethod
    def sources_not_empty(cls, v: list[SourceRef]) -> list[SourceRef]:
        if len(v) < 1:
            raise ValueError("provenance must have at least 1 source")
        return v


# --- Labels ---


class EpisodeLabels(BaseModel, frozen=True):
    """Optional labels for episode classification."""

    model_config = ConfigDict(populate_by_name=True)

    episode_type: Literal[
        "decision_point", "checkpoint", "handoff", "recovery", "milestone"
    ] | None = None
    notes: str | None = None


# --- Project reference ---


class ProjectRef(BaseModel, frozen=True):
    """Reference to the project/repository."""

    model_config = ConfigDict(populate_by_name=True)

    repo_path: str
    repo_remote: str | None = None
    branch: str | None = None
    commit_head: str | None = None


# --- Top-level Episode model ---


class Episode(BaseModel, frozen=True):
    """Top-level orchestrator decision-point episode.

    Mirrors data/schemas/orchestrator-episode.schema.json exactly.
    model_dump(exclude_none=True) produces a dict that validates
    against the JSON Schema.
    """

    model_config = ConfigDict(populate_by_name=True)

    episode_id: str
    timestamp: str
    project: ProjectRef
    observation: Observation
    orchestrator_action: OrchestratorAction
    outcome: Outcome
    provenance: Provenance

    # Optional fields
    phase: str | None = None
    task_id: str | None = None
    constraints_extracted: list[ConstraintRef] = Field(default_factory=list)
    labels: EpisodeLabels | None = None
    x_extensions: dict | None = None
