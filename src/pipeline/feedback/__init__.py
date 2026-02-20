"""Policy-to-constraint feedback loop package (Phase 13).

Detects policy errors (suppressed corrections, surfaced-and-blocked actions)
and feeds them back into the constraint extraction pipeline for automated
constraint promotion.

Exports:
    PolicyErrorEvent: Frozen model for policy error event storage
    make_policy_error_event: Factory function with deterministic ID generation
"""

from src.pipeline.feedback.models import PolicyErrorEvent, make_policy_error_event

__all__ = ["PolicyErrorEvent", "make_policy_error_event"]
