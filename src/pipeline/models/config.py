"""Pipeline configuration models and loader.

Loads configuration from data/config.yaml and validates it using Pydantic v2
models. All 21 locked decisions from CLARIFICATIONS-ANSWERED.md are encoded
in the config structure.

Exports:
    PipelineConfig: Top-level configuration model
    load_config: Load and validate config from YAML file
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


# --- Sub-models ---


class TemporalConfig(BaseModel):
    """Temporal alignment settings (Q1)."""

    causal_window_seconds: int = 2
    link_confidence: dict[str, float] = Field(
        default_factory=lambda: {"explicit": 1.0, "windowing": 0.8, "none": 0.0}
    )


class CombinationModeConfig(BaseModel):
    """Risk factor combination mode (Q11)."""

    classification: str = "max"
    scoring: str = "weighted_average"


class RiskModelConfig(BaseModel):
    """Risk model settings (Q10, Q11, Q12)."""

    threshold: float = 0.7
    combination_mode: CombinationModeConfig = Field(
        default_factory=CombinationModeConfig
    )
    risky_tools: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    false_positive_tolerance: bool = True
    acceptable_false_positive_rate: float = 0.20

    @field_validator("threshold")
    @classmethod
    def threshold_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"threshold must be between 0.0 and 1.0, got {v}")
        return v


class LabelDefinition(BaseModel):
    """A classification label definition (Q5)."""

    definition: str
    properties: list[str] = Field(default_factory=list)
    canonical_examples: list[str] = Field(default_factory=list)
    non_examples: list[str] = Field(default_factory=list)


class ClassificationConfig(BaseModel):
    """Event classification settings (Q5, Q6, Q9)."""

    labels: dict[str, LabelDefinition] = Field(default_factory=dict)
    reaction_keywords: dict[str, list[str]] = Field(default_factory=dict)
    min_confidence: float = 0.5
    precedence: list[str] = Field(default_factory=lambda: ["O_CORR", "O_DIR", "O_GATE"])

    @field_validator("min_confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"min_confidence must be between 0.0 and 1.0, got {v}")
        return v


class PayloadFieldsConfig(BaseModel):
    """Payload field definitions (Q7)."""

    required: list[str] = Field(default_factory=lambda: ["text"])
    optional: list[str] = Field(
        default_factory=lambda: [
            "reasoning",
            "tool_name",
            "duration_ms",
            "error_message",
            "files_touched",
        ]
    )


class PayloadConfig(BaseModel):
    """Payload structure settings (Q7)."""

    common_fields: PayloadFieldsConfig = Field(default_factory=PayloadFieldsConfig)


class ValidationConfig(BaseModel):
    """Validation and error handling settings (Q16, Q17)."""

    mode: str = "strict"
    invalid_event_abort_threshold: float = 0.10
    abort_scope: str = "per_session"

    @field_validator("mode")
    @classmethod
    def mode_valid(cls, v: str) -> str:
        if v not in ("strict", "permissive"):
            raise ValueError(f"mode must be 'strict' or 'permissive', got '{v}'")
        return v

    @field_validator("invalid_event_abort_threshold")
    @classmethod
    def abort_threshold_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"invalid_event_abort_threshold must be between 0.0 and 1.0, got {v}"
            )
        return v


class DeduplicationConfig(BaseModel):
    """Deduplication settings (Q13, Q14, Q15)."""

    track_metadata: bool = True
    log_duplicates: bool = True
    duplicate_alert_threshold: float = 0.05


class TemporalAnomalyConfig(BaseModel):
    """Temporal anomaly handling settings (Q18)."""

    tolerate: bool = True
    flag: bool = True
    log_level: str = "warning"
    microsecond_noise: str = "deterministic"


class EpisodePopulationConfig(BaseModel):
    """Episode population settings (Phase 2).

    Controls the observation context window used when constructing
    episodes from episode segments.
    """

    observation_context_events: int = 20
    observation_context_seconds: int = 300


class EscalationConfig(BaseModel):
    """Escalation detection settings (Phase 9).

    Controls the obstacle escalation detector that identifies when an
    agent bypasses an authorization constraint via an alternative path
    after being blocked.
    """

    window_turns: int = 5
    exempt_tools: list[str] = Field(default_factory=lambda: [
        "Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task",
    ])
    always_bypass_patterns: list[str] = Field(default_factory=lambda: [
        "rm ", "rm -", "chmod", "chown", "sudo", "curl -X DELETE", "drop table",
    ])
    bypass_eligible_tools: list[str] = Field(default_factory=lambda: [
        "Write", "Edit", "Bash",
    ])
    detector_version: str = "1.0.0"


class DurabilityConfig(BaseModel):
    """Decision durability tracking settings (Phase 10)."""

    min_sessions_for_score: int = 3
    evidence_excerpt_max_chars: int = 500


class StabilityCheckDef(BaseModel):
    """Single stability check command definition (Phase 12)."""

    id: str
    command: list[str]
    timeout_seconds: int = 120
    description: str = ""


class GovernanceConfig(BaseModel):
    """Governance protocol settings (Phase 12)."""

    bulk_ingest_threshold: int = 5
    stability_checks: list[StabilityCheckDef] = Field(default_factory=list)


class GitCommands(BaseModel):
    """Git command patterns for tagging."""

    commit: list[str] = Field(default_factory=lambda: ["git commit"])
    push: list[str] = Field(default_factory=lambda: ["git push"])
    merge: list[str] = Field(default_factory=lambda: ["git merge"])
    rebase: list[str] = Field(default_factory=lambda: ["git rebase"])
    checkout: list[str] = Field(
        default_factory=lambda: ["git checkout", "git switch"]
    )
    branch: list[str] = Field(default_factory=lambda: ["git branch"])
    status: list[str] = Field(default_factory=lambda: ["git status"])
    diff: list[str] = Field(default_factory=lambda: ["git diff"])


class TagPatterns(BaseModel):
    """Event tag command patterns for tool classification."""

    test_commands: list[str] = Field(default_factory=list)
    lint_commands: list[str] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    git_commands: GitCommands = Field(default_factory=GitCommands)
    risky_commands: list[str] = Field(default_factory=list)


# --- Top-level config ---


class PipelineConfig(BaseModel):
    """Complete pipeline configuration.

    Loaded from data/config.yaml. All values correspond to locked decisions
    from CLARIFICATIONS-ANSWERED.md (Q1-Q21).
    """

    episode_timeout_seconds: int = 30
    classification: ClassificationConfig = Field(
        default_factory=ClassificationConfig
    )
    risk_model: RiskModelConfig = Field(default_factory=RiskModelConfig)
    payload: PayloadConfig = Field(default_factory=PayloadConfig)
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    temporal_anomalies: TemporalAnomalyConfig = Field(
        default_factory=TemporalAnomalyConfig
    )
    tags: TagPatterns = Field(default_factory=TagPatterns)
    episode_population: EpisodePopulationConfig = Field(
        default_factory=EpisodePopulationConfig
    )
    escalation: EscalationConfig = Field(
        default_factory=EscalationConfig
    )
    durability: DurabilityConfig = Field(
        default_factory=DurabilityConfig
    )
    governance: GovernanceConfig = Field(
        default_factory=GovernanceConfig
    )

    # Preserved from existing config (used by downstream components)
    mode_inference: dict[str, Any] = Field(default_factory=dict)
    gate_patterns: dict[str, Any] = Field(default_factory=dict)
    constraint_patterns: dict[str, Any] = Field(default_factory=dict)

    @field_validator("episode_timeout_seconds")
    @classmethod
    def timeout_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(
                f"episode_timeout_seconds must be positive, got {v}"
            )
        return v


def load_config(path: str | Path = Path("data/config.yaml")) -> PipelineConfig:
    """Load and validate pipeline configuration from a YAML file.

    Args:
        path: Path to the YAML config file. Defaults to data/config.yaml.

    Returns:
        Validated PipelineConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config file contains invalid YAML.
        pydantic.ValidationError: If config values fail validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Config file is empty: {path}")

    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a YAML mapping, got {type(raw).__name__}")

    return PipelineConfig(**raw)
