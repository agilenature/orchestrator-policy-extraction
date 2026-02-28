"""GovernorDaemon -- reads active constraints and generates briefings.

Reads active constraints from data/constraints.json and doc_index from
DuckDB read-only for doc delivery.  Stateless between requests -- reads
fresh on each call.

Phase 21: daemon gains DuckDB access for doc_index queries (SELECT only).
Uses a regular connection (not read_only=True) because DuckDB rejects
read_only connections when a read-write connection is already open to the
same file.  Only SELECT queries are issued -- MVCC makes reads safe.

DDF co-pilot interventions (LIVE-06) remain stubbed until post-OpenClaw.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from .briefing import ConstraintBriefing, generate_briefing


class GovernorDaemon:
    """Reads active constraints from constraints.json and doc_index from DuckDB read-only for doc delivery.

    Stateless between requests -- reads fresh on each call.
    Constraints: read from constraints.json (ConstraintStore source of truth).
    Doc index: read from DuckDB via read-only connection (Phase 21).
    """

    def __init__(
        self,
        db_path: str = "data/ope.db",
        constraints_path: str = "data/constraints.json",
    ) -> None:
        self._db_path = db_path
        self._constraints_path = constraints_path

    def get_briefing(
        self, session_id: str, run_id: str, repo: str | None = None,
    ) -> ConstraintBriefing:
        """Return a constraint briefing for the given session.

        Reads all active constraints from constraints.json on each call
        (stateless). When *repo* is provided, constraints with a non-empty
        ``repo_scope`` list are filtered to only those whose ``repo_scope``
        includes the requesting repo.  Constraints without ``repo_scope``
        (or with ``repo_scope=None`` / ``repo_scope=[]``) are universal and
        always delivered.  When *repo* is ``None``, all constraints are
        delivered (backward compatible).

        Args:
            session_id: Requesting session identifier.
            run_id: Run identifier for the session.
            repo: Repository name of the requesting session.  When ``None``
                (default), no repo filtering is applied.

        Returns:
            ConstraintBriefing with severity-sorted active constraints.
        """
        constraints = self._load_active_constraints()
        if repo is not None:
            constraints = self._filter_by_repo(constraints, repo)
        briefing = generate_briefing(constraints)
        relevant_docs = self._query_relevant_docs()
        genus_count = self._query_genus_count(repo=repo)
        return briefing.model_copy(update={"relevant_docs": relevant_docs, "genus_count": genus_count})

    @staticmethod
    def _filter_by_repo(
        constraints: list[dict[str, Any]], repo: str,
    ) -> list[dict[str, Any]]:
        """Filter constraints by repo scope.

        Rules:
        - ``repo_scope`` absent, ``None``, or empty list → universal (included).
        - ``repo_scope`` is a non-empty list and *repo* is in it → included.
        - ``repo_scope`` is a non-empty list and *repo* is NOT in it → excluded.
        """
        result: list[dict[str, Any]] = []
        for c in constraints:
            repo_scope = c.get("repo_scope")
            if repo_scope is None or not isinstance(repo_scope, list) or len(repo_scope) == 0:
                result.append(c)  # universal: no restriction
            elif repo in repo_scope:
                result.append(c)  # scoped and matches
            # else: scoped but no match -- skip
        return result

    def _query_relevant_docs(self) -> list[dict[str, Any]]:
        """Query doc_index for relevant documentation entries.

        Returns top 3 non-unclassified docs, deduplicated by doc_path,
        with always-show docs first then ranked by extracted_confidence DESC.

        Fails open: returns [] on any error (missing table, invalid DB path,
        DuckDB errors).  Opens a regular connection (not read_only=True) because
        DuckDB rejects read_only connections when a read-write connection is
        already open to the same file (e.g., the bus server's write connection).
        Only SELECT queries are issued -- safe under MVCC.
        """
        try:
            conn = duckdb.connect(self._db_path)
            try:
                # Check if doc_index table exists (graceful pre-Phase-21 fallback)
                tables = conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'doc_index'"
                ).fetchall()
                if not tables:
                    return []

                rows = conn.execute(
                    "SELECT doc_path, ccd_axis, description_cache, extracted_confidence "
                    "FROM doc_index "
                    "WHERE association_type != 'unclassified' "
                    "ORDER BY "
                    "    CASE WHEN ccd_axis = 'always-show' THEN 0 ELSE 1 END, "
                    "    extracted_confidence DESC"
                ).fetchall()

                # Deduplicate by doc_path (first occurrence wins due to ORDER BY)
                seen: set[str] = set()
                result: list[dict[str, Any]] = []
                for doc_path, ccd_axis, description_cache, _confidence in rows:
                    if doc_path in seen:
                        continue
                    seen.add(doc_path)
                    result.append({
                        "doc_path": doc_path,
                        "ccd_axis": ccd_axis,
                        "description_cache": description_cache,
                    })
                    if len(result) >= 3:
                        break

                return result
            finally:
                conn.close()
        except Exception:
            return []

    def _query_genus_count(self, repo: str | None = None) -> int:
        """Query axis_edges for count of distinct genus_of edges.

        When *repo* is provided and bus_sessions table exists, scopes the
        count to edges created by sessions in that repo.  When *repo* is
        ``None`` or bus_sessions is missing, returns the global count.

        Fails open: returns 0 on any error (missing table, invalid DB path,
        DuckDB errors).
        """
        try:
            conn = duckdb.connect(self._db_path)
            try:
                # Check if axis_edges table exists
                tables = conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'axis_edges'"
                ).fetchall()
                if not tables:
                    return 0

                # Check if bus_sessions exists for repo-scoped query
                has_bus_sessions = False
                if repo is not None:
                    bs_tables = conn.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = 'bus_sessions'"
                    ).fetchall()
                    has_bus_sessions = bool(bs_tables)

                if repo is not None and has_bus_sessions:
                    result = conn.execute(
                        "SELECT COUNT(DISTINCT ae.axis_a) FROM axis_edges ae "
                        "JOIN bus_sessions bs ON ae.created_session_id = bs.session_id "
                        "WHERE ae.relationship_text = 'genus_of' "
                        "AND ae.status IN ('candidate', 'active') "
                        "AND bs.repo = ?",
                        [repo],
                    ).fetchone()
                else:
                    result = conn.execute(
                        "SELECT COUNT(DISTINCT axis_a) FROM axis_edges "
                        "WHERE relationship_text = 'genus_of' "
                        "AND status IN ('candidate', 'active')"
                    ).fetchone()

                return result[0] if result else 0
            finally:
                conn.close()
        except Exception:
            return 0

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
