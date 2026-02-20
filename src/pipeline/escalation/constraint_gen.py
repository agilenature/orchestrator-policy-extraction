"""Escalation constraint generator -- auto-generates constraint candidates.

Implements three-tier severity logic from detected escalation sequences:
  1. reaction in (correct, block) -> severity = forbidden, status = candidate
  2. reaction is None (silence) -> severity = requires_approval, status = candidate
  3. reaction == approve -> None (no constraint; escalation approved)
  4. reaction == redirect -> severity = requires_approval (treat like silence)
  5. reaction == question -> severity = requires_approval

All generated constraints start as status=candidate with source=inferred_from_escalation.
Promotion to active is out of scope (handled by human review).

Exports:
    EscalationConstraintGenerator
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from src.pipeline.escalation.models import EscalationCandidate


# Operation type inference patterns: (regex, operation_type)
_OPERATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgit\s+push\b", re.IGNORECASE), "push"),
    (re.compile(r"\bgit\s+force[-\s]push\b", re.IGNORECASE), "push"),
    (re.compile(r"\brm\s+", re.IGNORECASE), "delete"),
    (re.compile(r"\bdelete\b", re.IGNORECASE), "delete"),
    (re.compile(r"\bremove\b", re.IGNORECASE), "delete"),
    (re.compile(r"\bwrite\b", re.IGNORECASE), "write"),
    (re.compile(r"\becho\s+.*>", re.IGNORECASE), "write"),
    (re.compile(r"\btee\b", re.IGNORECASE), "write"),
    (re.compile(r"\bpip\s+install\b", re.IGNORECASE), "execute"),
    (re.compile(r"\bnpm\s+install\b", re.IGNORECASE), "execute"),
    (re.compile(r"\bcurl\b", re.IGNORECASE), "execute"),
    (re.compile(r"\bwget\b", re.IGNORECASE), "execute"),
    (re.compile(r"\bchmod\b", re.IGNORECASE), "execute"),
]

# Reactions that produce forbidden severity
_FORBIDDEN_REACTIONS = frozenset({"correct", "block"})

# Reactions that produce requires_approval severity
_REQUIRES_APPROVAL_REACTIONS = frozenset({None, "redirect", "question"})

# The reaction that means "no constraint"
_APPROVE_REACTION = "approve"

# Constraint text template (locked decision from research)
_TEMPLATE = (
    "Forbid {tool_category} performing {operation_type} on {resource} "
    "without prior approval following a rejected {gate_type} gate"
)


class EscalationConstraintGenerator:
    """Auto-generates constraint candidates from detected escalation sequences.

    Stateless: does not hold ConstraintStore state. The caller (pipeline
    integration) handles calling ConstraintStore.add().

    Usage:
        gen = EscalationConstraintGenerator()
        candidate = gen.generate(escalation_candidate, reaction="block")
        # candidate is a dict compatible with ConstraintStore, or None
    """

    def generate(
        self,
        candidate: EscalationCandidate,
        reaction: str | None,
        existing_constraints: list[dict] | None = None,
    ) -> dict | None:
        """Generate a constraint candidate from an escalation and reaction.

        Args:
            candidate: The detected EscalationCandidate.
            reaction: The human reaction label (block, correct, approve,
                      redirect, question) or None for silence.
            existing_constraints: Optional list of existing constraint dicts
                                  for linking via bypassed_constraint_id.

        Returns:
            Constraint dict compatible with ConstraintStore, or None if
            reaction is 'approve' (no constraint needed).
        """
        # Tier 3: approve -> no constraint
        if reaction == _APPROVE_REACTION:
            return None

        # Determine severity
        if reaction in _FORBIDDEN_REACTIONS:
            severity = "forbidden"
        else:
            # None, redirect, question -> requires_approval
            severity = "requires_approval"

        # Infer operation type and resource
        operation_type = self._infer_operation_type(
            candidate.bypass_command, candidate.bypass_tool_name
        )
        resource = candidate.bypass_resource if candidate.bypass_resource else "any path"

        # Build constraint text from locked template
        text = _TEMPLATE.format(
            tool_category=candidate.bypass_tool_name,
            operation_type=operation_type,
            resource=resource,
            gate_type=candidate.block_event_tag,
        )

        # Build detection hints
        detection_hints = self._build_detection_hints(candidate)

        # Generate deterministic constraint ID
        constraint_id = self._make_constraint_id(candidate, operation_type, resource)

        # Build scope from bypass resource
        scope_paths = [candidate.bypass_resource] if candidate.bypass_resource else []

        # Check for matching existing constraint
        bypassed_constraint_id = None
        if existing_constraints:
            bypassed_constraint_id = self.find_matching_constraint(
                candidate, existing_constraints
            )

        created_at = datetime.now(timezone.utc).isoformat()

        return {
            "constraint_id": constraint_id,
            "text": text,
            "severity": severity,
            "scope": {"paths": scope_paths},
            "detection_hints": detection_hints,
            "source_episode_id": "",
            "created_at": created_at,
            "status": "candidate",
            "source": "inferred_from_escalation",
            "examples": [],
            "bypassed_constraint_id": bypassed_constraint_id,
            "type": "behavioral_constraint",
            "status_history": [{"status": "candidate", "changed_at": created_at}],
        }

    def find_matching_constraint(
        self,
        candidate: EscalationCandidate,
        existing_constraints: list[dict],
    ) -> str | None:
        """Find an existing constraint whose detection_hints overlap.

        Searches existing constraints for detection_hints that overlap with
        the escalation candidate's tool name and command signature.

        Args:
            candidate: The detected EscalationCandidate.
            existing_constraints: List of existing constraint dicts with
                                  detection_hints arrays.

        Returns:
            constraint_id of the matching constraint, or None.
        """
        if not existing_constraints:
            return None

        # Build candidate hints set for comparison
        candidate_hints = set(self._build_detection_hints(candidate))

        # Also include resource path prefix matching
        if candidate.bypass_resource:
            candidate_hints.add(candidate.bypass_resource)

        for constraint in existing_constraints:
            existing_hints = set(constraint.get("detection_hints", []))
            if not existing_hints:
                continue

            # Check for overlap: tool name match + any other hint overlap
            overlap = candidate_hints & existing_hints
            if len(overlap) >= 2:
                # At least two hints overlap (e.g., tool name + command)
                return constraint["constraint_id"]

            # Single overlap: check if it's the tool name plus path prefix
            if overlap:
                hint = next(iter(overlap))
                # Tool name match counts as strong signal with path containment
                if hint == candidate.bypass_tool_name:
                    # Check if any existing hint is a prefix of candidate resource
                    for eh in existing_hints:
                        if (
                            candidate.bypass_resource
                            and candidate.bypass_resource.startswith(eh)
                        ):
                            return constraint["constraint_id"]

        return None

    @staticmethod
    def _infer_operation_type(command: str, tool_name: str) -> str:
        """Infer operation type from command text and tool name.

        Checks command against known patterns. Falls back to tool name
        heuristics, then defaults to 'execute'.

        Args:
            command: The bypass command text.
            tool_name: The bypass tool name (Bash, Write, Edit, etc.).

        Returns:
            Operation type string: push, delete, write, execute, etc.
        """
        # Check command against patterns
        for pattern, op_type in _OPERATION_PATTERNS:
            if pattern.search(command):
                return op_type

        # Tool name heuristics
        tool_lower = tool_name.lower()
        if tool_lower in ("write",):
            return "write"
        if tool_lower in ("edit",):
            return "write"
        if tool_lower in ("read",):
            return "read"

        # Default
        return "execute"

    @staticmethod
    def _build_detection_hints(candidate: EscalationCandidate) -> list[str]:
        """Build detection_hints list from escalation candidate fields.

        Includes tool name and key command elements for future matching.

        Args:
            candidate: The detected EscalationCandidate.

        Returns:
            List of detection hint strings.
        """
        hints: list[str] = []
        seen: set[str] = set()

        # Always include tool name
        if candidate.bypass_tool_name and candidate.bypass_tool_name not in seen:
            seen.add(candidate.bypass_tool_name)
            hints.append(candidate.bypass_tool_name)

        # Extract key command signature
        command_sig = _extract_command_signature(candidate.bypass_command)
        if command_sig and command_sig not in seen:
            seen.add(command_sig)
            hints.append(command_sig)

        return hints

    @staticmethod
    def _make_constraint_id(
        candidate: EscalationCandidate,
        operation_type: str,
        resource: str,
    ) -> str:
        """Generate deterministic constraint ID.

        SHA-256(o_esc_id + constraint_target_signature) truncated to 16 hex chars.

        o_esc_id = block_event_id + ":" + bypass_event_id
        constraint_target_signature = tool_name + ":" + operation_type + ":" + resource

        Args:
            candidate: The detected EscalationCandidate.
            operation_type: Inferred operation type.
            resource: Resource path or "any path".

        Returns:
            16 hex character constraint ID.
        """
        o_esc_id = f"{candidate.block_event_id}:{candidate.bypass_event_id}"
        target_sig = (
            f"{candidate.bypass_tool_name}:{operation_type}:{resource}"
        )
        key = f"{o_esc_id}:{target_sig}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


def _extract_command_signature(command: str) -> str:
    """Extract a short command signature for detection hints.

    For git commands: 'git push', 'git commit', etc.
    For other commands: first two tokens or the full short command.

    Args:
        command: Full command text.

    Returns:
        Short command signature string, or empty string if no command.
    """
    if not command.strip():
        return ""

    # For git commands, extract 'git <subcommand>'
    git_match = re.match(r"(git\s+\w+)", command, re.IGNORECASE)
    if git_match:
        return git_match.group(1)

    # For pip/npm commands
    pkg_match = re.match(r"((?:pip|npm)\s+\w+)", command, re.IGNORECASE)
    if pkg_match:
        return pkg_match.group(1)

    # For rm commands
    rm_match = re.match(r"(rm\b.*)", command, re.IGNORECASE)
    if rm_match:
        return "rm"

    # For write/echo commands
    if re.match(r"(write|echo)\b", command, re.IGNORECASE):
        return command.split()[0]

    # Default: first word
    tokens = command.strip().split()
    return tokens[0] if tokens else ""
