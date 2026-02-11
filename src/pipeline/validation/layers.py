"""Five validation layer implementations for GenusValidator.

Each layer conforms to the ValidationLayer Protocol:
    validate(episode: dict) -> tuple[bool, list[str]]

Layers:
    A. SchemaLayer -- wraps EpisodeValidator (JSON Schema + business rules)
    B. EvidenceGroundingLayer -- mode-specific evidence heuristics (warnings only)
    C. NonContradictionLayer -- mode/gate consistency checks (warnings only)
    D. ConstraintEnforcementLayer -- constraint scope/severity checking
    E. EpisodeIntegrityLayer -- structural coherence checks

Exports:
    ValidationLayer, SchemaLayer, EvidenceGroundingLayer,
    NonContradictionLayer, ConstraintEnforcementLayer, EpisodeIntegrityLayer
"""

from __future__ import annotations

from typing import Any, Protocol


class ValidationLayer(Protocol):
    """Protocol for pluggable validation layers."""

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate an episode dict.

        Returns:
            Tuple of (is_valid, error_messages). Warnings are prefixed
            with "warning:" and do not count as hard errors.
        """
        ...


# ============================================================
# Layer A: Schema Validity
# ============================================================


class SchemaLayer:
    """Wraps EpisodeValidator for JSON Schema + business rule checks.

    Delegates entirely to the existing EpisodeValidator.validate() method.

    Args:
        episode_validator: An EpisodeValidator instance.
    """

    def __init__(self, episode_validator: Any) -> None:
        self._validator = episode_validator

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Delegate to EpisodeValidator.validate()."""
        return self._validator.validate(episode)


# ============================================================
# Layer B: Evidence Grounding (warnings only)
# ============================================================


class EvidenceGroundingLayer:
    """Checks mode-specific evidence heuristics.

    All checks produce warnings (prefixed 'warning:evidence:'), never
    hard failures. This layer always returns is_valid=True.

    Checks:
        - Implement mode: scope.paths should be non-empty
        - Verify mode: outcome should have executor_effects or test-related content
        - Integrate mode: outcome should have git-related content
    """

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Check mode-specific evidence, returning warnings only."""
        warnings: list[str] = []
        action = episode.get("orchestrator_action", {})
        if not isinstance(action, dict):
            return (True, [])

        mode = action.get("mode", "")
        scope = action.get("scope", {})
        scope_paths = scope.get("paths", []) if isinstance(scope, dict) else []
        outcome = episode.get("outcome", {})
        if not isinstance(outcome, dict):
            outcome = {}

        if mode == "Implement":
            if not scope_paths:
                warnings.append(
                    "warning:evidence: Implement mode has no scope paths"
                )

        elif mode == "Verify":
            # Check for test/lint results in outcome
            effects = outcome.get("executor_effects", {})
            quality = outcome.get("quality", {})
            has_test_evidence = bool(effects) or bool(quality)
            if not has_test_evidence:
                warnings.append(
                    "warning:evidence: Verify mode has no test results in outcome"
                )

        elif mode == "Integrate":
            # Check for git events in outcome
            effects = outcome.get("executor_effects", {})
            commands = effects.get("commands_ran", []) if isinstance(effects, dict) else []
            has_git_evidence = any("git" in str(c).lower() for c in commands) if commands else False
            # Also check for git_events key
            git_events = outcome.get("git_events", [])
            if not has_git_evidence and not git_events:
                warnings.append(
                    "warning:evidence: Integrate mode has no git events in outcome"
                )

        return (True, warnings)


# ============================================================
# Layer C: Non-Contradiction (warnings only)
# ============================================================


class NonContradictionLayer:
    """Checks mode/gate consistency for contradictions.

    All checks produce warnings (prefixed 'warning:contradiction:'),
    never hard failures. This layer always returns is_valid=True.

    Three rules from AUTHORITATIVE_DESIGN.md Part 5.2.C:
        1. mode=Explore with write_allowed gate -> contradiction
        2. gate contains no_network and instruction mentions network -> contradiction
        3. gate contains no_write_before_plan and mode=Implement -> contradiction
    """

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Check for mode/gate contradictions, returning warnings only."""
        warnings: list[str] = []
        action = episode.get("orchestrator_action", {})
        if not isinstance(action, dict):
            return (True, [])

        mode = action.get("mode", "")
        gates = action.get("gates", [])
        if not isinstance(gates, list):
            gates = []

        gate_types = {
            g.get("type", "") for g in gates if isinstance(g, dict)
        }

        # Rule 1: Explore + write_allowed -> contradiction
        if mode == "Explore" and "write_allowed" in gate_types:
            warnings.append(
                "warning:contradiction: Explore mode with write_allowed gate"
            )

        # Rule 2: no_network gate + network-related instruction
        if "no_network" in gate_types:
            instruction = action.get("executor_instruction", "")
            network_terms = ["http", "api", "fetch", "download", "curl", "request", "url"]
            if any(term in instruction.lower() for term in network_terms):
                warnings.append(
                    "warning:contradiction: no_network gate with network-related instruction"
                )

        # Rule 3: no_write_before_plan + Implement -> contradiction
        if mode == "Implement" and "no_write_before_plan" in gate_types:
            warnings.append(
                "warning:contradiction: Implement mode with no_write_before_plan gate"
            )

        return (True, warnings)


# ============================================================
# Layer D: Constraint Enforcement (severity-aware)
# ============================================================


class ConstraintEnforcementLayer:
    """Checks episode actions against stored constraints.

    Severity mapping:
        - forbidden -> hard error (is_valid=False)
        - requires_approval -> warning (prefixed 'warning:constraint:')
        - warning -> warning (prefixed 'warning:constraint:')

    Scope matching:
        - Constraint with empty paths -> repo-wide, applies to all episodes
        - Constraint with specific paths -> checks overlap with episode scope.paths

    Args:
        constraints: List of constraint dicts (from ConstraintStore.constraints).
    """

    def __init__(self, constraints: list[dict[str, Any]] | None = None) -> None:
        self._constraints = constraints or []

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Check episode against constraints, respecting severity levels."""
        errors: list[str] = []
        has_hard_error = False

        action = episode.get("orchestrator_action", {})
        if not isinstance(action, dict):
            return (True, [])

        scope = action.get("scope", {})
        episode_paths = scope.get("paths", []) if isinstance(scope, dict) else []

        for constraint in self._constraints:
            cid = constraint.get("constraint_id", "unknown")
            severity = constraint.get("severity", "warning")
            constraint_scope = constraint.get("scope", {})
            constraint_paths = (
                constraint_scope.get("paths", [])
                if isinstance(constraint_scope, dict)
                else []
            )

            # Check scope overlap
            if not self._scopes_overlap(episode_paths, constraint_paths):
                continue

            # Severity-based response
            text = constraint.get("text", "")
            if severity == "forbidden":
                errors.append(
                    f"constraint_enforcement: violates forbidden constraint '{cid}' - {text}"
                )
                has_hard_error = True
            elif severity == "requires_approval":
                errors.append(
                    f"warning:constraint: requires approval for constraint '{cid}' - {text}"
                )
            else:  # "warning" severity
                errors.append(
                    f"warning:constraint: warning constraint '{cid}' applies - {text}"
                )

        return (not has_hard_error, errors)

    @staticmethod
    def _scopes_overlap(
        episode_paths: list[str], constraint_paths: list[str]
    ) -> bool:
        """Check if episode paths overlap with constraint paths.

        A constraint with empty paths is repo-wide and applies to everything.
        Otherwise, checks if any episode path starts with or is a prefix of
        any constraint path (or vice versa).
        """
        # Repo-wide constraint (empty paths) applies to all episodes
        if not constraint_paths:
            return True

        for ep in episode_paths:
            for cp in constraint_paths:
                # Check prefix-based overlap in both directions
                if ep.startswith(cp) or cp.startswith(ep):
                    return True

        return False


# ============================================================
# Layer E: Episode Integrity (hard failures)
# ============================================================


class EpisodeIntegrityLayer:
    """Checks structural coherence of episode data.

    Hard failures for:
        - Missing or empty episode_id
        - Missing or empty provenance.sources
        - Reaction confidence outside [0, 1] range

    All failures are errors (not warnings).
    """

    def validate(self, episode: dict[str, Any]) -> tuple[bool, list[str]]:
        """Check structural integrity of episode."""
        errors: list[str] = []

        # Check episode_id
        episode_id = episode.get("episode_id")
        if not episode_id or not isinstance(episode_id, str) or not episode_id.strip():
            errors.append("integrity: episode_id is empty or missing")

        # Check provenance.sources
        provenance = episode.get("provenance")
        if not isinstance(provenance, dict):
            errors.append("integrity: provenance is missing")
        else:
            sources = provenance.get("sources")
            if not isinstance(sources, list) or len(sources) == 0:
                errors.append("integrity: provenance.sources is empty")

        # Check reaction confidence range
        outcome = episode.get("outcome", {})
        if isinstance(outcome, dict):
            reaction = outcome.get("reaction")
            if isinstance(reaction, dict):
                confidence = reaction.get("confidence")
                if confidence is not None and isinstance(confidence, (int, float)):
                    if not (0.0 <= confidence <= 1.0):
                        errors.append(
                            f"integrity: reaction confidence out of range: {confidence}"
                        )

        return (len(errors) == 0, errors)
