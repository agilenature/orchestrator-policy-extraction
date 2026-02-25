"""Governor package -- constraint briefing delivery for the governance bus.

Provides the GovernorDaemon that reads active constraints from
data/constraints.json and generates severity-ordered ConstraintBriefings
for delivery via the /api/check endpoint.
"""

from .briefing import ConstraintBriefing, generate_briefing
from .daemon import GovernorDaemon

__all__ = ["ConstraintBriefing", "generate_briefing", "GovernorDaemon"]
