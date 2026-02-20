"""Escalation detection package (Phase 9).

Detects obstacle escalation patterns: when an agent bypasses an authorization
constraint via an alternative path after being blocked.

Exports:
    EscalationCandidate: Frozen model capturing a detected escalation event pair
    EscalationDetector: Sliding window sequence detector for escalation patterns
"""

from src.pipeline.escalation.detector import EscalationDetector
from src.pipeline.escalation.models import EscalationCandidate

__all__ = ["EscalationCandidate", "EscalationDetector"]
