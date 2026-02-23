"""Data models for the identification review system.

Defines the core types for the two-layer validation architecture:
- IdentificationLayer: The 8 pipeline layers (L1-L8)
- IdentificationPoint: One classification act with five externalization properties
- IdentificationReview: One completed verdict on a classification instance
- ReviewVerdict: Accept or reject

Every IdentificationPoint carries all five decision-boundary externalization
properties (trigger, observation_state, action_taken, downstream_impact,
provenance_pointer) per the decision-boundary-externalization CCD axis.

Exports:
    IdentificationLayer
    IdentificationPoint
    IdentificationReview
    ReviewVerdict
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IdentificationLayer(str, Enum):
    """The 8 pipeline layers where classification acts occur."""

    L1_EVENT_FILTER = "L1"  # Event filtering and actor assignment
    L2_TAGGING = "L2"  # Tagging
    L3_SEGMENTATION = "L3"  # Segmentation
    L4_EPISODE_POPULATION = "L4"  # Episode population
    L5_CONSTRAINT_EXTRACTION = "L5"  # Constraint extraction
    L6_CONSTRAINT_EVALUATION = "L6"  # Constraint evaluation
    L7_ESCALATION_DETECTION = "L7"  # Escalation detection
    L8_POLICY_FEEDBACK = "L8"  # Policy feedback


class ReviewVerdict(str, Enum):
    """Binary verdict on a classification instance."""

    ACCEPT = "accept"
    REJECT = "reject"


class IdentificationPoint(BaseModel):
    """One classification act the pipeline has performed.

    Each instance carries the five decision-boundary externalization
    properties required for retrospective improvement:
    1. trigger: what prompted this classification
    2. observation_state: the raw input the classifier saw
    3. action_taken: the label/classification chosen
    4. downstream_impact: what decisions depended on this
    5. provenance_pointer: traceable source reference
    """

    instance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    layer: IdentificationLayer
    point_id: str  # e.g. "L2-1", "L4-4"
    point_label: str  # human-readable name
    pipeline_component: str  # e.g. "OrchestratorTagger", "ReactionLabeler"
    # Five externalization properties
    trigger: str  # what prompted this classification
    observation_state: str  # the raw input the classifier saw
    action_taken: str  # the label/classification chosen
    downstream_impact: str  # what decisions depended on this
    provenance_pointer: str  # session_id + event_id + source_table:row_key
    # Source artifact references
    source_session_id: Optional[str] = None
    source_event_id: Optional[str] = None
    source_episode_id: Optional[str] = None


class IdentificationReview(BaseModel):
    """One completed review of an identification instance.

    Stored in the identification_reviews DuckDB table (append-only).
    Copies all five externalization properties from the instance for
    self-contained storage -- each review row is independently auditable
    without joining back to the source tables.
    """

    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    identification_instance_id: str
    layer: IdentificationLayer
    point_id: str
    pipeline_component: str
    # Five externalization properties (copied from instance)
    trigger: str
    observation_state: str
    action_taken: str
    downstream_impact: str
    provenance_pointer: str
    # Verdict
    verdict: ReviewVerdict
    opinion: Optional[str] = None  # required path when verdict=reject
    reviewed_at: str  # ISO-8601 UTC
    session_id: Optional[str] = None  # session in which this review occurred
