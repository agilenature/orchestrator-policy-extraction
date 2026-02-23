"""Foil instantiation with historical premise lookup and divergence detection.

Provides three-tier matching to find historical premises where the current
foil was the active premise, and divergence detection to identify where
the foil and claim execution paths diverged.

Three-tier matching:
  1. Exact claim match via registry.find_by_foil (ILIKE)
  2. Keyword overlap for partial matches (if tier 1 returns <3 results)
  3. Combine and deduplicate, return up to 10 results

Divergence detection (simplified Phase 14.1 heuristic):
  Given a foil match with episode data, compare tool_name sequences
  from the episode's events to identify the first divergence point.

Exports:
    FoilInstantiator: Three-tier matching + divergence detection
    FoilMatch: A matched historical premise with match metadata
    DivergenceNode: First point of tool call divergence between foil and claim
"""

from __future__ import annotations

import json
from typing import Literal

import duckdb
from pydantic import BaseModel

from src.pipeline.premise.models import PremiseRecord
from src.pipeline.premise.registry import PremiseRegistry

# Common English stopwords (short list for keyword extraction)
_STOPWORDS = frozenset({
    "the", "and", "that", "this", "with", "from", "have", "has",
    "been", "were", "are", "was", "for", "not", "but", "what",
    "all", "can", "had", "her", "one", "our", "out", "you",
    "his", "how", "its", "may", "new", "now", "old", "see",
    "way", "who", "did", "get", "let", "say", "she", "too",
    "use", "will", "does", "into", "than", "them", "then",
    "they", "when", "where", "which", "while", "about", "after",
    "before", "being", "between", "both", "each", "more", "most",
    "other", "some", "such", "only", "over", "same", "also",
    "just", "because", "should", "would", "could", "there",
    "their", "very", "still", "through", "using", "none",
})


class DivergenceNode(BaseModel, frozen=True):
    """First point of tool call divergence between foil and claim paths.

    Identifies the event index where the foil episode's tool sequence
    diverges from the baseline, along with the differing tool names.

    Attributes:
        event_index: 0-based index of the divergent event.
        foil_tool: Tool name in the foil episode at the divergence point.
        claim_tool: Tool name in the baseline at the divergence point (or "END").
        episode_id: Episode containing the foil events.
    """

    event_index: int
    foil_tool: str
    claim_tool: str
    episode_id: str


class FoilMatch(BaseModel, frozen=True):
    """A matched historical premise with match metadata.

    Attributes:
        premise: The matched PremiseRecord from the registry.
        match_tier: How the match was found ("exact" or "keyword").
        keyword_overlap: Number of matching keywords (0 for exact tier).
        divergence_node: First divergence point, if detected.
    """

    premise: PremiseRecord
    match_tier: Literal["exact", "keyword"]
    keyword_overlap: int = 0
    divergence_node: DivergenceNode | None = None


class FoilInstantiator:
    """Three-tier foil matching with divergence detection.

    Searches the premise registry for historical premises where the
    current foil text was previously the active claim, using:
      1. Exact claim match (ILIKE via registry.find_by_foil)
      2. Keyword overlap (significant words from foil text)
      3. Deduplication and limit to 10 results

    Args:
        registry: PremiseRegistry instance for premise lookups.
        conn: DuckDB connection for episode/event queries.
    """

    def __init__(
        self,
        registry: PremiseRegistry,
        conn: duckdb.DuckDBPyConnection,
    ) -> None:
        self._registry = registry
        self._conn = conn

    def instantiate(
        self,
        foil_text: str,
        project_scope: str | None = None,
        current_session_id: str | None = None,
    ) -> list[FoilMatch]:
        """Find historical premises matching the given foil text.

        Three-tier matching:
          1. Exact claim match via registry.find_by_foil.
          2. Keyword overlap (if tier 1 returns <3 results): extract
             significant words (>3 chars, not stopwords) and query
             premises containing 3+ keywords.
          3. Deduplicate and return up to 10 results.

        Args:
            foil_text: Text to match against historical premise claims.
            project_scope: Optional project path filter.
            current_session_id: Optional session ID to exclude.

        Returns:
            List of FoilMatch objects, up to 10 results.
        """
        seen_ids: set[str] = set()
        matches: list[FoilMatch] = []

        # Tier 1: Exact claim match
        exact_results = self._registry.find_by_foil(
            foil_text,
            project_scope=project_scope,
            exclude_session=current_session_id,
            limit=10,
        )
        for premise in exact_results:
            if premise.premise_id not in seen_ids:
                seen_ids.add(premise.premise_id)
                matches.append(FoilMatch(
                    premise=premise,
                    match_tier="exact",
                    keyword_overlap=0,
                ))

        # Tier 2: Keyword overlap (if tier 1 returned <3 results)
        if len(matches) < 3:
            keywords = self._extract_keywords(foil_text)
            if len(keywords) >= 3:
                keyword_premises = self._keyword_search(
                    keywords,
                    project_scope=project_scope,
                    exclude_session=current_session_id,
                    min_overlap=3,
                )
                for premise, overlap_count in keyword_premises:
                    if premise.premise_id not in seen_ids and len(matches) < 10:
                        seen_ids.add(premise.premise_id)
                        matches.append(FoilMatch(
                            premise=premise,
                            match_tier="keyword",
                            keyword_overlap=overlap_count,
                        ))

        return matches[:10]

    def detect_divergence(
        self, foil_match: FoilMatch
    ) -> DivergenceNode | None:
        """Detect the first tool call divergence for a foil match.

        Simplified Phase 14.1 heuristic: compare tool_name sequences
        from the foil episode's events. The divergence node is the
        first event where event_type differs between adjacent tool
        use events.

        Args:
            foil_match: A FoilMatch with premise data.

        Returns:
            DivergenceNode if divergence found, None otherwise.
        """
        premise = foil_match.premise
        gtp = premise.ground_truth_pointer
        if gtp is None:
            return None

        episode_id = gtp.get("episode_id")
        if not episode_id:
            return None

        # Look up the episode to get session_id
        try:
            episode_row = self._conn.execute(
                "SELECT session_id FROM episodes WHERE episode_id = ?",
                [episode_id],
            ).fetchone()
        except Exception:
            return None

        if episode_row is None:
            return None

        session_id = episode_row[0]

        # Get events for this session, ordered by timestamp
        try:
            event_rows = self._conn.execute(
                "SELECT event_id, event_type, primary_tag, payload "
                "FROM events WHERE session_id = ? ORDER BY ts_utc",
                [session_id],
            ).fetchall()
        except Exception:
            return None

        if not event_rows or len(event_rows) < 2:
            return None

        # Extract tool names from events (tool_use events have tool_name in payload)
        tool_sequence: list[str] = []
        for _eid, event_type, _tag, payload in event_rows:
            tool_name = self._extract_tool_name(event_type, payload)
            if tool_name:
                tool_sequence.append(tool_name)

        if len(tool_sequence) < 2:
            return None

        # Simplified heuristic: find first point where adjacent tool calls
        # differ from an expected pattern (consecutive identical tools suggest
        # the same operation; a change suggests divergence)
        for i in range(1, len(tool_sequence)):
            if tool_sequence[i] != tool_sequence[i - 1]:
                return DivergenceNode(
                    event_index=i,
                    foil_tool=tool_sequence[i - 1],
                    claim_tool=tool_sequence[i],
                    episode_id=episode_id,
                )

        return None

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract significant words from text for keyword matching.

        Filters to words >3 characters that are not common stopwords.
        Returns lowercase unique words.

        Args:
            text: Text to extract keywords from.

        Returns:
            List of unique significant keywords.
        """
        words = set()
        for word in text.lower().split():
            # Strip common punctuation
            cleaned = word.strip(".,;:!?()[]{}\"'`")
            if len(cleaned) > 3 and cleaned not in _STOPWORDS:
                words.add(cleaned)
        return sorted(words)

    def _keyword_search(
        self,
        keywords: list[str],
        project_scope: str | None = None,
        exclude_session: str | None = None,
        min_overlap: int = 3,
    ) -> list[tuple[PremiseRecord, int]]:
        """Search for premises containing multiple keywords.

        Builds a SQL query with ILIKE conditions for each keyword,
        counting how many match each premise's claim.

        Args:
            keywords: List of keywords to search for.
            project_scope: Optional project path filter.
            exclude_session: Optional session ID to exclude.
            min_overlap: Minimum number of keywords that must match.

        Returns:
            List of (PremiseRecord, overlap_count) tuples, sorted by
            overlap count descending.
        """
        if not keywords:
            return []

        # Build CASE expressions to count keyword matches
        case_parts: list[str] = []
        kw_params: list[str] = []
        for kw in keywords:
            case_parts.append("CASE WHEN claim ILIKE ? THEN 1 ELSE 0 END")
            kw_params.append(f"%{kw}%")

        overlap_expr = " + ".join(case_parts)

        # The overlap_expr appears in both SELECT and WHERE, so keyword params
        # need to be provided twice (once for SELECT, once for WHERE).
        # Build params in order: SELECT kw_params, WHERE kw_params + min_overlap + filters
        select_params = list(kw_params)

        where_params: list = list(kw_params)
        where_params.append(min_overlap)

        conditions = [f"({overlap_expr}) >= ?"]

        if project_scope is not None:
            conditions.append("project_scope = ?")
            where_params.append(project_scope)

        if exclude_session is not None:
            conditions.append("session_id != ?")
            where_params.append(exclude_session)

        where = " AND ".join(conditions)
        all_params = select_params + where_params

        try:
            rows = self._conn.execute(
                f"SELECT *, ({overlap_expr}) AS overlap_count "
                f"FROM premise_registry "
                f"WHERE {where} "
                f"ORDER BY overlap_count DESC "
                f"LIMIT 10",
                all_params,
            ).fetchall()
        except Exception:
            return []

        results: list[tuple[PremiseRecord, int]] = []
        for row in rows:
            # Last column is overlap_count, rest are premise_registry columns
            overlap_count = row[-1]
            premise_row = row[:-1]
            record = self._registry._row_to_record(premise_row)
            results.append((record, int(overlap_count)))

        return results

    @staticmethod
    def _extract_tool_name(event_type: str, payload: str | dict | None) -> str | None:
        """Extract tool name from an event.

        For tool_use events, extracts the tool_name from payload JSON.
        For other event types, uses the event_type as the tool name.

        Args:
            event_type: The event type string.
            payload: The event payload (JSON string or dict).

        Returns:
            Tool name string, or None if not extractable.
        """
        if event_type not in ("tool_use", "tool_result"):
            return None

        if payload is None:
            return event_type

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                return event_type

        if isinstance(payload, dict):
            # Check common payload structures
            tool_name = payload.get("tool_name")
            if tool_name:
                return str(tool_name)
            common = payload.get("common", {})
            if isinstance(common, dict):
                tool_name = common.get("tool_name")
                if tool_name:
                    return str(tool_name)

        return event_type
