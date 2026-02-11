"""Episode populator -- derives observation, action, outcome from segments.

Transforms raw EpisodeSegment objects (boundaries + event IDs) into fully
populated episode dicts matching orchestrator-episode.schema.json.

The populator reads events from within and around each segment to derive:
- observation: from context events preceding the episode
- orchestrator_action: from the start trigger event with mode inference
- outcome: from body events within the episode
- provenance: from event source refs and git commit links

Exports:
    EpisodePopulator: Main class with populate() method
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.pipeline.models.config import PipelineConfig
from src.pipeline.models.segments import EpisodeSegment


class EpisodePopulator:
    """Derives observation, orchestrator_action, and outcome from segment events.

    Takes three inputs:
    1. An EpisodeSegment (from Phase 1 segmenter)
    2. A list of event dicts within the segment (queried from DuckDB)
    3. A list of context event dicts BEFORE the segment (same session)

    And produces a dict matching orchestrator-episode.schema.json.

    Args:
        config: Pipeline configuration with mode_inference, gate_patterns, etc.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config
        self._mode_lookup = self._build_mode_lookup()
        self._gate_patterns = self._build_gate_patterns()
        self._scope_path_re = re.compile(
            r'(?:^|\s)((?:[\w.-]+/)+[\w.-]+\.[\w]+|[\w.-]+\.(?:py|js|ts|tsx|jsx|rs|go|java|rb|c|cpp|h|hpp|md|yaml|yml|json|toml|sql|sh|css|html))'
        )

    def populate(
        self,
        segment: EpisodeSegment,
        events: list[dict],
        context_events: list[dict],
    ) -> dict:
        """Populate episode fields from segment events.

        Args:
            segment: The episode segment with boundaries and metadata.
            events: Events within this segment (from DuckDB by event_ids).
            context_events: Events BEFORE this segment (same session, preceding).

        Returns:
            A dict matching orchestrator-episode.schema.json structure.
        """
        start_event = self._find_start_event(events, segment.start_event_id)
        body_events = [e for e in events if e["event_id"] != segment.start_event_id]

        observation = self._derive_observation(context_events, start_event)
        action = self._derive_action(start_event, segment)
        outcome = self._derive_outcome(body_events, segment)
        provenance = self._build_provenance(events, segment)

        episode = {
            "episode_id": self._make_episode_id(segment),
            "timestamp": segment.start_ts.isoformat(),
            "project": self._get_project_ref(events),
            "observation": observation,
            "orchestrator_action": action,
            "outcome": outcome,
            "provenance": provenance,
        }

        return episode

    # --- Private helpers ---

    def _find_start_event(self, events: list[dict], start_event_id: str) -> dict:
        """Find the start trigger event from the event list."""
        for event in events:
            if event["event_id"] == start_event_id:
                return event
        # Fallback: use first event if start not found
        if events:
            return events[0]
        return {
            "event_id": start_event_id,
            "payload": "{}",
            "links": "{}",
            "source_system": "claude_jsonl",
            "source_ref": "unknown",
        }

    def _derive_observation(
        self, context_events: list[dict], start_event: dict
    ) -> dict:
        """Derive observation from events before the episode start.

        Context events are events from the same session with ts_utc < episode.start_ts.
        Looks back at the most recent events to determine repo_state, quality_state,
        and context.
        """
        max_events = self._config.episode_population.observation_context_events

        changed_files: set[str] = set()
        tests_status = "unknown"
        lint_status = "unknown"
        recent_texts: list[str] = []

        for event in context_events[-max_events:]:
            payload = self._parse_payload(event.get("payload"))
            common = payload.get("common", {})

            # Accumulate files from tool events
            files = common.get("files_touched", [])
            if isinstance(files, list):
                changed_files.update(f for f in files if isinstance(f, str))

            # Track test/lint status from most recent T_TEST/T_LINT events
            tag = event.get("primary_tag")
            if tag == "T_TEST":
                text = common.get("text", "")
                if "passed" in text.lower() or "pass" in text.lower():
                    tests_status = "pass"
                elif "failed" in text.lower() or "fail" in text.lower():
                    tests_status = "fail"
                else:
                    tests_status = "not_run"
            elif tag == "T_LINT":
                text = common.get("text", "")
                if "fail" in text.lower() or "error" in text.lower():
                    lint_status = "fail"
                else:
                    lint_status = "pass"

            # Collect recent text for summary
            text = common.get("text", "")
            if text and event.get("actor") in ("human_orchestrator", "executor"):
                recent_texts.append(text[:200])

        # Build recent summary from last few texts
        summary = "; ".join(recent_texts[-3:]) if recent_texts else "Session start"

        sorted_files = sorted(changed_files)

        return {
            "repo_state": {
                "changed_files": sorted_files,
                "diff_stat": {
                    "files": len(sorted_files),
                    "insertions": 0,
                    "deletions": 0,
                },
            },
            "quality_state": {
                "tests": {"status": tests_status},
                "lint": {"status": lint_status},
            },
            "context": {
                "recent_summary": summary[:500],
                "open_questions": [],
                "constraints_in_force": [],
            },
        }

    def _derive_action(self, start_event: dict, segment: EpisodeSegment) -> dict:
        """Derive orchestrator_action from the episode start trigger event."""
        payload = self._parse_payload(start_event.get("payload"))
        text = payload.get("common", {}).get("text", "")

        # Infer mode from start event text using config keywords
        mode, _confidence = self._infer_mode(text, segment.start_trigger)

        # Extract file paths mentioned in text
        scope_paths = self._extract_scope_paths(text)

        # Extract gates from gate patterns
        gates = self._extract_gates(text)

        # Compute risk from mode + scope
        risk = self._compute_risk(mode, scope_paths)

        return {
            "mode": mode,
            "goal": text[:500],
            "scope": {"paths": scope_paths},
            "executor_instruction": text,
            "gates": gates,
            "risk": risk,
        }

    def _derive_outcome(self, body_events: list[dict], segment: EpisodeSegment) -> dict:
        """Derive outcome from events within the episode body."""
        files_touched: set[str] = set()
        commands_ran: list[str] = []
        git_events: list[dict] = []
        tool_calls_count = 0
        tests_status = "unknown"
        lint_status = "unknown"

        for event in body_events:
            payload = self._parse_payload(event.get("payload"))
            common = payload.get("common", {})
            tag = event.get("primary_tag")

            # Count tool calls
            if event.get("event_type") in ("tool_use", "tool_result"):
                tool_calls_count += 1

            # Accumulate files
            files = common.get("files_touched", [])
            if isinstance(files, list):
                files_touched.update(f for f in files if isinstance(f, str))

            # Accumulate commands from tool_use events
            if event.get("event_type") == "tool_use":
                cmd = common.get("text", "")
                if cmd:
                    commands_ran.append(cmd[:200])

            # Track test/lint outcomes
            if tag == "T_TEST":
                tests_status = "pass" if segment.outcome == "success" else "fail"
            elif tag == "T_LINT":
                lint_status = "pass"

            # Track git events
            if tag == "T_GIT_COMMIT":
                links = self._parse_links(event.get("links"))
                commit_hash = links.get("commit_hash", "")
                if commit_hash:
                    git_events.append({
                        "type": "commit",
                        "ref": commit_hash,
                    })

        diff_files = len(files_touched)
        diff_risk = min(1.0, diff_files * 0.1)

        return {
            "executor_effects": {
                "tool_calls_count": tool_calls_count,
                "files_touched": sorted(files_touched),
                "commands_ran": commands_ran[:20],
                "git_events": git_events,
            },
            "quality": {
                "tests_status": tests_status,
                "lint_status": lint_status,
                "diff_stat": {
                    "files": diff_files,
                    "insertions": 0,
                    "deletions": 0,
                },
            },
            "reward_signals": {
                "objective": {
                    "tests": (
                        1.0
                        if tests_status == "pass"
                        else (0.0 if tests_status == "fail" else 0.5)
                    ),
                    "lint": (
                        1.0
                        if lint_status == "pass"
                        else (0.0 if lint_status == "fail" else 0.5)
                    ),
                    "diff_risk": diff_risk,
                },
            },
        }

    def _build_provenance(self, events: list[dict], segment: EpisodeSegment) -> dict:
        """Build provenance from events within the episode.

        Deduplicates source refs and includes git commit references
        from event links.
        """
        sources: list[dict] = []
        seen_refs: set[str] = set()

        for event in events:
            source_type = event.get("source_system", "claude_jsonl")
            source_ref = event.get("source_ref", "")

            if source_ref and source_ref not in seen_refs:
                seen_refs.add(source_ref)
                sources.append({
                    "type": source_type,
                    "ref": source_ref,
                })

            # Include git commit references from links
            links = self._parse_links(event.get("links"))
            commit_hash = links.get("commit_hash")
            if commit_hash:
                git_ref_key = f"commit:{commit_hash}"
                if git_ref_key not in seen_refs:
                    seen_refs.add(git_ref_key)
                    sources.append({"type": "git", "ref": commit_hash})

        # Ensure at least one source
        if not sources:
            sources.append({"type": "claude_jsonl", "ref": "unknown"})

        return {"sources": sources}

    def _infer_mode(self, text: str, start_trigger: str) -> tuple[str, float]:
        """Infer the orchestrator mode from text using config keywords.

        Uses priority ordering from config.mode_inference. Lower priority
        number = higher priority. When priorities tie, the keyword that
        appears earliest in the text wins (position-based tie-breaking).

        Returns:
            Tuple of (mode, confidence).
        """
        if not text:
            return ("Implement", 0.3)

        text_lower = text.lower()
        # (priority, match_position, mode, confidence)
        matches: list[tuple[int, int, str, float]] = []

        for mode, entry in self._mode_lookup.items():
            priority = entry["priority"]
            for pattern in entry["patterns"]:
                m = pattern.search(text_lower)
                if m:
                    matches.append((priority, m.start(), mode, 0.7))
                    break

        if not matches:
            return ("Implement", 0.3)

        # Sort by priority (ascending), then by match position (ascending)
        matches.sort(key=lambda x: (x[0], x[1]))
        return (matches[0][2], matches[0][3])

    def _extract_scope_paths(self, text: str) -> list[str]:
        """Extract file paths mentioned in text using regex.

        Matches paths containing / separators or common file extensions.
        """
        if not text:
            return []

        matches = self._scope_path_re.findall(text)
        # Deduplicate while preserving order
        seen: set[str] = set()
        paths: list[str] = []
        for match in matches:
            path = match.strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    def _extract_gates(self, text: str) -> list[dict]:
        """Extract gates from text using config.gate_patterns."""
        if not text:
            return []

        text_lower = text.lower()
        gates: list[dict] = []
        seen_types: set[str] = set()

        for gate_type, patterns in self._gate_patterns.items():
            if gate_type in seen_types:
                continue
            for pattern in patterns:
                if pattern in text_lower:
                    gates.append({"type": gate_type})
                    seen_types.add(gate_type)
                    break

        return gates

    def _compute_risk(self, mode: str, scope_paths: list[str]) -> str:
        """Compute risk level from mode and scope paths.

        Risk levels:
        - low: Explore, Plan, Verify (non-write modes)
        - medium: Implement, Refactor, Triage, Integrate (default)
        - high: Implement/Integrate with protected paths
        - critical: reserved for future use
        """
        # Base risk from mode
        base_risk: dict[str, str] = {
            "Explore": "low",
            "Plan": "low",
            "Verify": "low",
            "Triage": "low",
            "Implement": "medium",
            "Refactor": "medium",
            "Integrate": "medium",
        }
        risk = base_risk.get(mode, "medium")

        # Check for protected paths
        if scope_paths and self._has_protected_path(scope_paths):
            risk = self._bump_risk(risk)

        return risk

    def _has_protected_path(self, scope_paths: list[str]) -> bool:
        """Check if any scope path matches a protected path pattern."""
        protected = self._config.risk_model.protected_paths
        for path in scope_paths:
            for pattern in protected:
                # Simple glob matching: ** matches anything, * matches segment
                regex_pattern = pattern.replace("**", ".*").replace("*", "[^/]*")
                if re.search(regex_pattern, path):
                    return True
        return False

    def _bump_risk(self, current: str) -> str:
        """Bump risk one level up."""
        levels = ["low", "medium", "high", "critical"]
        idx = levels.index(current) if current in levels else 1
        return levels[min(idx + 1, len(levels) - 1)]

    def _parse_payload(self, payload: Any) -> dict:
        """Parse payload from JSON string or dict."""
        if payload is None:
            return {}
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _parse_links(self, links: Any) -> dict:
        """Parse links from JSON string or dict."""
        if links is None:
            return {}
        if isinstance(links, str):
            try:
                return json.loads(links)
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(links, dict):
            return links
        return {}

    def _make_episode_id(self, segment: EpisodeSegment) -> str:
        """Generate deterministic episode ID.

        SHA-256(session_id + segment_id + config_hash) truncated to 16 hex chars.
        """
        config_hash = segment.config_hash or ""
        key = f"{segment.session_id}:{segment.segment_id}:{config_hash}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _get_project_ref(self, events: list[dict]) -> dict:
        """Extract project reference from events.

        Attempts to find repo path from event metadata.
        Falls back to 'unknown' if not available.
        """
        # Look for source refs that might indicate the repo
        for event in events:
            source_ref = event.get("source_ref", "")
            if source_ref:
                # source_ref format is typically session_id:uuid
                # The session file path could indicate the project
                session_id = event.get("session_id", "")
                if session_id:
                    return {"repo_path": session_id}

        return {"repo_path": "unknown"}

    def _build_mode_lookup(self) -> dict[str, dict]:
        """Build mode inference lookup from config.

        Pre-compiles regex patterns with word boundaries for each mode's
        keywords.
        """
        mode_lookup: dict[str, dict] = {}
        mode_inference = self._config.mode_inference

        for mode_name, mode_data in mode_inference.items():
            if not isinstance(mode_data, dict):
                continue
            keywords = mode_data.get("keywords", [])
            priority = mode_data.get("priority", 99)

            patterns = []
            for keyword in keywords:
                # Word-boundary regex, case-insensitive (text is already lowered)
                escaped = re.escape(keyword.lower())
                patterns.append(re.compile(rf"\b{escaped}\b"))

            mode_lookup[mode_name] = {
                "priority": priority,
                "patterns": patterns,
            }

        return mode_lookup

    def _build_gate_patterns(self) -> dict[str, list[str]]:
        """Build gate pattern lookup from config.

        Returns a dict mapping gate type to list of lowercase pattern strings.
        """
        result: dict[str, list[str]] = {}
        for gate_type, patterns in self._config.gate_patterns.items():
            if isinstance(patterns, list):
                result[gate_type] = [p.lower() for p in patterns if isinstance(p, str)]
        return result
