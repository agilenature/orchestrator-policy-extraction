"""Constraint extractor -- derives durable constraints from correct/block reactions.

Implements EXTRACT-06, CONST-01, CONST-03, CONST-04: Turns human corrections
into structured, enforceable constraints with severity levels and scoped
applicability.

Only processes episodes where reaction label is 'correct' or 'block'. Other
reaction types (approve, question, redirect, unknown) are filtered out.

Severity assignment:
    - block -> forbidden (always)
    - correct + forbidden keywords (don't, never, avoid, do not) -> requires_approval
    - correct + preferred keywords only (use, prefer, better to) -> warning
    - correct default -> requires_approval

Scope inference (narrowest applicable):
    1. File paths mentioned in reaction message
    2. Episode's orchestrator_action.scope.paths
    3. Empty list (repo-wide)

Exports:
    ConstraintExtractor
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from src.pipeline.ddf.epistemological import classify_epistemological_origin
from src.pipeline.models.config import PipelineConfig


class ConstraintExtractor:
    """Extracts durable constraints from correct/block episode reactions.

    Usage:
        extractor = ConstraintExtractor(config)
        constraint = extractor.extract(episode)
        # constraint is a dict matching constraint.schema.json, or None
    """

    def __init__(self, config: PipelineConfig) -> None:
        """Initialize with compiled regex patterns from config.

        Args:
            config: Pipeline configuration with constraint_patterns keywords.
        """
        self._config = config

        # Compile keyword patterns from config.constraint_patterns
        self._forbidden_patterns = self._compile_patterns(
            config.constraint_patterns.get("forbidden", [])
        )
        self._required_patterns = self._compile_patterns(
            config.constraint_patterns.get("required", [])
        )
        self._preferred_patterns = self._compile_patterns(
            config.constraint_patterns.get("preferred", [])
        )

        # Reuse scope path extraction regex from EpisodePopulator
        self._scope_path_re = re.compile(
            r'(?:^|\s)((?:[\w.-]+/)+[\w.-]+\.[\w]+|[\w.-]+\.(?:py|js|ts|tsx|jsx|rs|go|java|rb|c|cpp|h|hpp|md|yaml|yml|json|toml|sql|sh|css|html))'
        )

        # Prefix patterns to strip during text normalization
        self._prefix_patterns = [
            re.compile(r"^(?:no|nope|wrong|stop|never),?\s+", re.IGNORECASE),
            re.compile(r"^(?:don't|do\s+not)\s+(?:do\s+that),?\s*", re.IGNORECASE),
            re.compile(
                r"^(?:that'?s?\s+(?:wrong|not\s+right|incorrect)),?\s+", re.IGNORECASE
            ),
        ]

        # Prohibition-adjacent term extraction patterns
        self._prohibition_re = re.compile(
            r"(?:don't\s+use|avoid|never\s+use|stop\s+using)\s+([\w.-]+)",
            re.IGNORECASE,
        )

        # Quoted string extraction (double quotes, single quotes, backticks)
        self._quoted_re = re.compile(r'["`\']([\w\s.*/-]+)["`\']')

    def extract(self, episode: dict) -> dict | None:
        """Extract a constraint from an episode with correct/block reaction.

        Args:
            episode: Episode dict with outcome.reaction populated.

        Returns:
            Constraint dict matching constraint.schema.json, or None if
            no constraint can be extracted.
        """
        reaction = episode.get("outcome", {}).get("reaction")
        if reaction is None:
            return None

        label = reaction.get("label")
        if label not in ("correct", "block"):
            return None

        message = reaction.get("message", "")
        if not message.strip():
            return None

        text = self._normalize_text(message)
        severity = self._assign_severity(label, message)
        scope_paths = self._infer_scope(message, episode)
        detection_hints = self._extract_detection_hints(message)
        constraint_id = self._make_constraint_id(text, scope_paths)

        created_at = episode.get("timestamp", "")

        # Classify epistemological origin from the source episode
        origin, confidence = classify_epistemological_origin(episode)

        return {
            "constraint_id": constraint_id,
            "text": text,
            "severity": severity,
            "scope": {"paths": scope_paths},
            "detection_hints": detection_hints,
            "source_episode_id": episode.get("episode_id", ""),
            "created_at": created_at,
            "examples": [
                {
                    "episode_id": episode.get("episode_id", ""),
                    "violation_description": text,
                }
            ],
            "type": "behavioral_constraint",
            "status_history": [{"status": "active", "changed_at": created_at}] if created_at else [],
            "epistemological_origin": origin,
            "epistemological_confidence": confidence,
        }

    def _normalize_text(self, message: str) -> str:
        """Normalize reaction message into a constraint statement.

        Applies:
        1. Strip leading correction prefixes (no, nope, wrong, that's wrong)
        2. Capitalize first letter
        3. Ensure ends with period (unless already ends with . or !)
        """
        text = message.strip()

        # Remove leading correction prefixes
        for pattern in self._prefix_patterns:
            text = pattern.sub("", text).strip()

        # Capitalize first letter
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        # Ensure ends with period (not if already ends with . or !)
        if text and text[-1] not in ".!":
            text = text + "."

        return text

    def _assign_severity(self, reaction_label: str, message: str) -> str:
        """Assign severity based on reaction label + keyword analysis.

        Rules:
        - block -> forbidden (always)
        - correct + forbidden keywords -> requires_approval
        - correct + preferred keywords only -> warning
        - correct default -> requires_approval
        """
        if reaction_label == "block":
            return "forbidden"

        # correct reaction: check keywords
        message_lower = message.lower()

        has_forbidden = any(p.search(message_lower) for p in self._forbidden_patterns)
        has_preferred = any(p.search(message_lower) for p in self._preferred_patterns)

        if has_forbidden:
            return "requires_approval"
        elif has_preferred:
            return "warning"
        else:
            return "requires_approval"

    def _infer_scope(self, message: str, episode: dict) -> list[str]:
        """Infer constraint scope from mentioned paths.

        Priority (narrowest first):
        1. Paths mentioned in reaction message
        2. Paths from episode's orchestrator_action.scope
        3. Empty list (repo-wide) as last resort
        """
        # First: extract paths from reaction message
        paths = self._extract_paths(message)
        if paths:
            return paths

        # Second: use episode's scope paths
        action_scope = episode.get("orchestrator_action", {}).get("scope", {})
        episode_paths = action_scope.get("paths", [])
        if episode_paths:
            return list(episode_paths)

        # Last resort: repo-wide (empty array per schema)
        return []

    def _extract_paths(self, text: str) -> list[str]:
        """Extract file paths mentioned in text using regex.

        Reuses the same scope path regex from EpisodePopulator.
        Deduplicates while preserving order.
        """
        if not text:
            return []

        matches = self._scope_path_re.findall(text)
        seen: set[str] = set()
        paths: list[str] = []
        for match in matches:
            path = match.strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    def _extract_detection_hints(self, message: str) -> list[str]:
        """Extract detection hint patterns from reaction message.

        Looks for:
        1. Quoted strings (likely specific terms to detect)
        2. File paths and globs
        3. Terms after prohibition keywords (don't use X, avoid X, never X)
        """
        hints: list[str] = []
        seen: set[str] = set()

        # Quoted strings: "regex", 'eval', `rm -rf`
        for match in self._quoted_re.finditer(message):
            hint = match.group(1).strip()
            if hint and hint not in seen:
                seen.add(hint)
                hints.append(hint)

        # File paths
        for path in self._extract_paths(message):
            if path not in seen:
                seen.add(path)
                hints.append(path)

        # Terms after prohibition keywords: "don't use X", "avoid X", "never X"
        for match in self._prohibition_re.finditer(message):
            term = match.group(1).strip()
            if term and term not in seen:
                seen.add(term)
                hints.append(term)

        return hints

    def _make_constraint_id(
        self, text: str, scope_paths: list[str], source: str = "human_correction"
    ) -> str:
        """Generate deterministic constraint ID.

        SHA-256(lowercase_text + sorted_scope_paths + source) truncated to
        16 hex chars. Same text + same scope + same source = same ID = dedup
        on re-run.

        The source parameter was added in Phase 13 to distinguish constraints
        from different origins. This intentionally produces different IDs from
        the old format (without source), but existing constraints.json IDs are
        NOT retroactively recomputed.

        Args:
            text: Normalized constraint text.
            scope_paths: List of file path scopes.
            source: Origin of the constraint (default 'human_correction').
                Future sources include 'feedback_loop'.

        Returns:
            16-character hex string constraint ID.
        """
        scope_key = "|".join(sorted(scope_paths))
        key = f"{text.lower().strip()}:{scope_key}:{source}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @staticmethod
    def _compile_patterns(keywords: list[str]) -> list[re.Pattern[str]]:
        """Compile keyword list into word-boundary regex patterns.

        Args:
            keywords: List of keyword strings to match.

        Returns:
            List of compiled case-insensitive regex patterns.
        """
        patterns: list[re.Pattern[str]] = []
        for kw in keywords:
            escaped = re.escape(kw.lower())
            patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
        return patterns
