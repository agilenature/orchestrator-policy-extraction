"""GovernorDaemon -- reads active constraints and generates briefings.

Reads active constraints from data/constraints.json (the ConstraintStore
source of truth). Stateless between requests -- reads fresh on each call.
Respects DuckDB single-writer invariant: never reads ope.db directly.

DDF co-pilot interventions (LIVE-06) remain stubbed until post-OpenClaw.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .briefing import ConstraintBriefing, generate_briefing


class GovernorDaemon:
    """Reads active constraints from data/constraints.json and generates constraint briefings.

    Stateless between requests -- reads fresh on each call.
    Reads constraints.json directly (DuckDB single-writer invariant: no ope.db reads).
    """

    def __init__(
        self,
        db_path: str = "data/ope.db",
        constraints_path: str = "data/constraints.json",
    ) -> None:
        self._db_path = db_path
        self._constraints_path = constraints_path

    def get_briefing(self, session_id: str, run_id: str) -> ConstraintBriefing:
        """Return a constraint briefing for the given session.

        Reads all active constraints from constraints.json on each call
        (stateless). The session_id and run_id are accepted for future
        scope filtering but are not used for filtering yet.

        Args:
            session_id: Requesting session identifier.
            run_id: Run identifier for the session.

        Returns:
            ConstraintBriefing with severity-sorted active constraints.
        """
        constraints = self._load_active_constraints()
        return generate_briefing(constraints)

    def _load_active_constraints(self) -> list[dict[str, Any]]:
        """Load active constraints from constraints.json.

        Filters out retired and superseded constraints. Constraints
        without a status field default to active (included).

        Returns:
            List of active constraint dicts. Empty on any error (fail-open).
        """
        try:
            path = Path(self._constraints_path)
            if not path.exists():
                return []
            data = json.loads(path.read_text())
            constraints = data if isinstance(data, list) else data.get("constraints", [])
            return [
                c for c in constraints
                if c.get("status", "active") not in ("retired", "superseded")
            ]
        except Exception:
            return []
