"""Tests for the GovernorDaemon and ConstraintBriefing (Phase 19-03).

Covers:
- ConstraintBriefing model and generate_briefing() logic
- GovernorDaemon constraints.json reading and filtering
- /api/check integration with the daemon
- Fail-open behavior on missing/malformed data

Uses tmp_path + monkeypatch.chdir for file-based test isolation.
"""

from __future__ import annotations

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.live.governor.briefing import (
    ConstraintBriefing,
    SEVERITY_ORDER,
    generate_briefing,
)
from src.pipeline.live.governor.daemon import GovernorDaemon


# ---------------------------------------------------------------------------
# Helper: write constraints.json in tmp_path/data/
# ---------------------------------------------------------------------------


def _write_constraints(tmp_path, constraints: list[dict]) -> None:
    """Write a constraints.json file to tmp_path/data/."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "constraints.json").write_text(json.dumps(constraints))


# ---------------------------------------------------------------------------
# ConstraintBriefing + generate_briefing() tests
# ---------------------------------------------------------------------------


class TestConstraintBriefing:
    """Tests for the ConstraintBriefing model and generate_briefing()."""

    def test_empty_constraints_returns_empty_briefing(self):
        """1. Empty constraints list produces empty briefing."""
        b = generate_briefing([])
        assert b.total_count == 0
        assert b.constraints == []
        assert b.interventions == []
        assert b.top_severity is None

    def test_constraints_sorted_by_severity_forbidden_first(self):
        """2. Constraints are sorted: forbidden first, then requires_approval, then warning."""
        constraints = [
            {"id": "c1", "severity": "warning"},
            {"id": "c2", "severity": "forbidden"},
            {"id": "c3", "severity": "requires_approval"},
        ]
        b = generate_briefing(constraints)
        assert b.constraints[0]["severity"] == "forbidden"
        assert b.constraints[1]["severity"] == "requires_approval"
        assert b.constraints[2]["severity"] == "warning"

    def test_top_severity_is_most_severe(self):
        """3. top_severity is the most severe across all constraints."""
        constraints = [
            {"id": "c1", "severity": "warning"},
            {"id": "c2", "severity": "requires_approval"},
        ]
        b = generate_briefing(constraints)
        assert b.top_severity == "requires_approval"

    def test_top_severity_forbidden_when_present(self):
        """3b. top_severity is forbidden when any constraint is forbidden."""
        constraints = [
            {"id": "c1", "severity": "warning"},
            {"id": "c2", "severity": "forbidden"},
        ]
        b = generate_briefing(constraints)
        assert b.top_severity == "forbidden"

    def test_no_ccd_axis_constraint_still_included(self):
        """4. Constraints without ccd_axis are still included in the briefing."""
        constraints = [{"id": "c1", "severity": "warning"}]
        b = generate_briefing(constraints)
        assert b.total_count == 1
        assert b.constraints[0]["id"] == "c1"

    def test_unknown_severity_sorted_last(self):
        """Constraints with unknown severity are sorted after warning."""
        constraints = [
            {"id": "c1", "severity": "unknown_sev"},
            {"id": "c2", "severity": "forbidden"},
        ]
        b = generate_briefing(constraints)
        assert b.constraints[0]["severity"] == "forbidden"
        assert b.constraints[1]["severity"] == "unknown_sev"

    def test_total_count_matches_constraint_count(self):
        """14. total_count matches the number of constraints."""
        constraints = [
            {"id": "c1", "severity": "warning"},
            {"id": "c2", "severity": "forbidden"},
            {"id": "c3", "severity": "requires_approval"},
        ]
        b = generate_briefing(constraints)
        assert b.total_count == 3
        assert b.total_count == len(b.constraints)

    def test_interventions_always_empty(self):
        """Interventions list is always empty (LIVE-06 deferred)."""
        constraints = [{"id": "c1", "severity": "warning"}]
        b = generate_briefing(constraints)
        assert b.interventions == []


# ---------------------------------------------------------------------------
# GovernorDaemon tests
# ---------------------------------------------------------------------------


class TestGovernorDaemon:
    """Tests for the GovernorDaemon constraint reader."""

    def test_get_briefing_returns_briefing_instance(self, tmp_path):
        """5. get_briefing() returns a ConstraintBriefing instance."""
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "nonexistent.json"),
        )
        b = daemon.get_briefing("s1", "r1")
        assert isinstance(b, ConstraintBriefing)

    def test_load_active_constraints_reads_from_json(self, tmp_path, monkeypatch):
        """6. _load_active_constraints() reads from constraints.json."""
        monkeypatch.chdir(tmp_path)
        _write_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "active"},
        ])
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "data" / "constraints.json"),
        )
        constraints = daemon._load_active_constraints()
        assert len(constraints) == 1
        assert constraints[0]["id"] == "c1"

    def test_filters_retired_constraints(self, tmp_path, monkeypatch):
        """7. Retired constraints are excluded."""
        monkeypatch.chdir(tmp_path)
        _write_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "retired"},
            {"id": "c2", "severity": "warning", "status": "active"},
        ])
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "data" / "constraints.json"),
        )
        constraints = daemon._load_active_constraints()
        assert len(constraints) == 1
        assert constraints[0]["id"] == "c2"

    def test_filters_superseded_constraints(self, tmp_path, monkeypatch):
        """8. Superseded constraints are excluded."""
        monkeypatch.chdir(tmp_path)
        _write_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "superseded"},
            {"id": "c2", "severity": "forbidden", "status": "active"},
        ])
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "data" / "constraints.json"),
        )
        constraints = daemon._load_active_constraints()
        assert len(constraints) == 1
        assert constraints[0]["id"] == "c2"

    def test_missing_constraints_file_returns_empty(self, tmp_path):
        """9. Missing constraints.json returns empty list (fail-open)."""
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "nonexistent" / "constraints.json"),
        )
        constraints = daemon._load_active_constraints()
        assert constraints == []

    def test_malformed_constraints_file_returns_empty(self, tmp_path, monkeypatch):
        """10. Malformed constraints.json returns empty list (fail-open)."""
        monkeypatch.chdir(tmp_path)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "constraints.json").write_text("this is not valid json!!!")
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "data" / "constraints.json"),
        )
        constraints = daemon._load_active_constraints()
        assert constraints == []

    def test_constraints_path_parameter_allows_test_isolation(self, tmp_path):
        """13. constraints_path parameter allows pointing to a test file."""
        test_file = tmp_path / "my_test_constraints.json"
        test_file.write_text(json.dumps([
            {"id": "isolated", "severity": "forbidden", "status": "active"},
        ]))
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(test_file),
        )
        constraints = daemon._load_active_constraints()
        assert len(constraints) == 1
        assert constraints[0]["id"] == "isolated"

    def test_missing_status_defaults_to_active(self, tmp_path):
        """Constraints without a status field default to active (included)."""
        test_file = tmp_path / "constraints.json"
        test_file.write_text(json.dumps([
            {"id": "no-status", "severity": "warning"},
        ]))
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(test_file),
        )
        constraints = daemon._load_active_constraints()
        assert len(constraints) == 1

    def test_stateless_reads_fresh_each_call(self, tmp_path):
        """Daemon reads fresh from file on each get_briefing() call."""
        test_file = tmp_path / "constraints.json"
        test_file.write_text(json.dumps([
            {"id": "c1", "severity": "warning", "status": "active"},
        ]))
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(test_file),
        )
        b1 = daemon.get_briefing("s1", "r1")
        assert b1.total_count == 1

        # Modify file between calls
        test_file.write_text(json.dumps([
            {"id": "c1", "severity": "warning", "status": "active"},
            {"id": "c2", "severity": "forbidden", "status": "active"},
        ]))
        b2 = daemon.get_briefing("s1", "r1")
        assert b2.total_count == 2

    def test_object_format_constraints_json(self, tmp_path):
        """Handles constraints.json with {constraints: [...]} format."""
        test_file = tmp_path / "constraints.json"
        test_file.write_text(json.dumps({
            "constraints": [
                {"id": "c1", "severity": "warning", "status": "active"},
            ]
        }))
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(test_file),
        )
        constraints = daemon._load_active_constraints()
        assert len(constraints) == 1


# ---------------------------------------------------------------------------
# /api/check integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCheckHandlerWithDaemon:
    """Integration tests for /api/check with GovernorDaemon."""

    async def test_check_returns_constraints_from_daemon(self, tmp_path, monkeypatch):
        """11. /api/check with daemon returns constraint count."""
        monkeypatch.chdir(tmp_path)
        _write_constraints(tmp_path, [
            {"id": "c1", "ccd_axis": "test", "severity": "warning", "status": "active"},
        ])
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "data" / "constraints.json"),
        )
        from src.pipeline.live.bus.server import create_app
        app = create_app(db_path=":memory:", daemon=daemon)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/check",
                json={"session_id": "s1", "run_id": "r1"},
            )
        assert r.status_code == 200
        data = r.json()
        assert len(data["constraints"]) == 1
        assert data["interventions"] == []

    async def test_check_with_no_daemon_uses_default(self, tmp_path, monkeypatch):
        """12. /api/check with no daemon still returns (uses default GovernorDaemon)."""
        monkeypatch.chdir(tmp_path)
        # No data/constraints.json exists => default daemon returns empty
        from src.pipeline.live.bus.server import create_app
        app = create_app(db_path=":memory:")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/check",
                json={"session_id": "s1", "run_id": "r1"},
            )
        assert r.status_code == 200
        data = r.json()
        assert "constraints" in data
        assert "interventions" in data

    async def test_check_multiple_constraints_severity_ordered(self, tmp_path, monkeypatch):
        """Constraints from /api/check are severity-ordered."""
        monkeypatch.chdir(tmp_path)
        _write_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "active"},
            {"id": "c2", "severity": "forbidden", "status": "active"},
            {"id": "c3", "severity": "requires_approval", "status": "active"},
        ])
        daemon = GovernorDaemon(
            db_path=str(tmp_path / "test.db"),
            constraints_path=str(tmp_path / "data" / "constraints.json"),
        )
        from src.pipeline.live.bus.server import create_app
        app = create_app(db_path=":memory:", daemon=daemon)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/check",
                json={"session_id": "s1", "run_id": "r1"},
            )
        data = r.json()
        assert len(data["constraints"]) == 3
        assert data["constraints"][0]["severity"] == "forbidden"
        assert data["constraints"][1]["severity"] == "requires_approval"
        assert data["constraints"][2]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Repo scope filtering tests (Phase 20-04)
# ---------------------------------------------------------------------------


def _write_scoped_constraints(tmp_path, constraints: list[dict]) -> str:
    """Write constraints to a temp file and return the path string."""
    test_file = tmp_path / "scoped_constraints.json"
    test_file.write_text(json.dumps(constraints))
    return str(test_file)


class TestRepoScopeFilter:
    """Tests for repo-based constraint scope filtering in GovernorDaemon."""

    def test_repo_scope_filters_constraints(self, tmp_path):
        """Scoped constraints delivered only when repo matches; universal always delivered."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "mw", "severity": "forbidden", "status": "active",
             "repo_scope": ["migration-workbox"]},
            {"id": "pc", "severity": "warning", "status": "active",
             "repo_scope": ["platform-core"]},
            {"id": "univ", "severity": "requires_approval", "status": "active"},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo="migration-workbox")
        ids = [c["id"] for c in briefing.constraints]
        assert "mw" in ids
        assert "univ" in ids
        assert "pc" not in ids

    def test_repo_scope_universal_when_absent(self, tmp_path):
        """Constraints without repo_scope field are universal (delivered to any repo)."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "active"},
            {"id": "c2", "severity": "forbidden", "status": "active"},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo="any-repo")
        assert len(briefing.constraints) == 2

    def test_repo_scope_universal_when_none(self, tmp_path):
        """Constraints with repo_scope=None are universal."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "active",
             "repo_scope": None},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo="ope")
        assert len(briefing.constraints) == 1
        assert briefing.constraints[0]["id"] == "c1"

    def test_repo_scope_universal_when_empty_list(self, tmp_path):
        """Constraints with repo_scope=[] are universal."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "c1", "severity": "warning", "status": "active",
             "repo_scope": []},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo="ope")
        assert len(briefing.constraints) == 1

    def test_repo_scope_no_filter_when_repo_none(self, tmp_path):
        """When repo=None (default), all constraints delivered regardless of scope."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "scoped", "severity": "forbidden", "status": "active",
             "repo_scope": ["migration-workbox"]},
            {"id": "univ", "severity": "warning", "status": "active"},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo=None)
        assert len(briefing.constraints) == 2

    def test_repo_scope_multiple_repos_in_scope(self, tmp_path):
        """Constraint with multiple repos in repo_scope matches any of them."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "multi", "severity": "warning", "status": "active",
             "repo_scope": ["migration-workbox", "platform-core"]},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo="platform-core")
        assert len(briefing.constraints) == 1
        assert briefing.constraints[0]["id"] == "multi"

    def test_repo_scope_excludes_non_matching(self, tmp_path):
        """Scoped constraint excluded when repo does not match."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "mw-only", "severity": "forbidden", "status": "active",
             "repo_scope": ["migration-workbox"]},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        briefing = daemon.get_briefing("s1", "r1", repo="platform-core")
        assert len(briefing.constraints) == 0


@pytest.mark.asyncio
class TestCheckWithRepoFilter:
    """Integration test: /api/check passes repo to daemon for filtering."""

    async def test_check_passes_repo_to_daemon(self, tmp_path):
        """POST /api/check with repo filters constraints by repo scope."""
        cp = _write_scoped_constraints(tmp_path, [
            {"id": "mw", "severity": "forbidden", "status": "active",
             "repo_scope": ["migration-workbox"]},
            {"id": "pc", "severity": "warning", "status": "active",
             "repo_scope": ["platform-core"]},
            {"id": "univ", "severity": "requires_approval", "status": "active"},
        ])
        daemon = GovernorDaemon(db_path=":memory:", constraints_path=cp)
        from src.pipeline.live.bus.server import create_app
        app = create_app(db_path=":memory:", daemon=daemon)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/check",
                json={"session_id": "s1", "run_id": "r1",
                      "repo": "migration-workbox"},
            )
        assert r.status_code == 200
        data = r.json()
        ids = [c["id"] for c in data["constraints"]]
        assert "mw" in ids
        assert "univ" in ids
        assert "pc" not in ids
        assert data["epistemological_signals"] == []
