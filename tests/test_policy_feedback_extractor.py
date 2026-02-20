"""Tests for PolicyFeedbackExtractor -- constraint generation from blocked recommendations.

TDD RED phase: Tests written against the behavior spec before implementation.
Covers:
- Block reaction creates forbidden constraint with source=policy_feedback, status=candidate
- Correct reaction creates requires_approval constraint
- Approve/None reactions return None
- Constraint ID uses SHA-256 with :policy_feedback suffix
- Deterministic IDs
- Dedup via 2+ shared detection_hints with existing human constraints
- Status history included
- Type is behavioral_constraint
- Detection hints extracted from recommendation fields
- Promotion of candidates with 3+ sessions
"""

from __future__ import annotations

import hashlib
import json

import duckdb
import pytest

from src.pipeline.feedback.extractor import PolicyFeedbackExtractor
from src.pipeline.rag.recommender import Recommendation, SourceEpisodeRef
from src.pipeline.storage.schema import create_schema


# --- Helpers ---


def _make_recommendation(
    reasoning: str = "We should delete the old config files",
    scope_paths: list[str] | None = None,
    mode: str = "Implement",
    gates: list[str] | None = None,
) -> Recommendation:
    """Create a test Recommendation with sensible defaults."""
    return Recommendation(
        recommended_mode=mode,
        recommended_risk="medium",
        recommended_scope_paths=scope_paths or ["src/config.py"],
        recommended_gates=gates or ["run_tests"],
        confidence=0.85,
        source_episodes=[
            SourceEpisodeRef(
                episode_id="ep-001",
                similarity_score=0.9,
                mode="Implement",
            )
        ],
        reasoning=reasoning,
    )


def _make_episode(
    reaction_label: str | None = "block",
    episode_id: str = "ep-001",
    session_id: str = "sess-001",
) -> dict:
    """Create a test episode dict with sensible defaults."""
    return {
        "episode_id": episode_id,
        "session_id": session_id,
        "reaction_label": reaction_label,
    }


class _FakeConstraintStore:
    """Minimal constraint store for testing extractor."""

    def __init__(self, constraints: list[dict] | None = None):
        self._constraints = constraints or []
        self._added: list[dict] = []
        self._status_updates: list[tuple] = []

    def find_by_hints(
        self, detection_hints: list[str], min_overlap: int = 2
    ) -> dict | None:
        """Find constraint with >= min_overlap shared hints."""
        given_set = {h.lower() for h in detection_hints}
        for c in self._constraints:
            existing_set = {h.lower() for h in c.get("detection_hints", [])}
            if len(given_set & existing_set) >= min_overlap:
                return c
        return None

    def add(self, constraint: dict) -> bool:
        self._added.append(constraint)
        return True

    def get_active_constraints(self) -> list[dict]:
        return [c for c in self._constraints if c.get("status") == "active"]

    def add_status_history_entry(
        self, constraint_id: str, status: str, changed_at: str
    ) -> bool:
        self._status_updates.append((constraint_id, status, changed_at))
        # Also update the constraint status in-memory for testing
        for c in self._constraints:
            if c.get("constraint_id") == constraint_id:
                c["status"] = status
                c.setdefault("status_history", []).append(
                    {"status": status, "changed_at": changed_at}
                )
                return True
        return False


# --- Fixtures ---


@pytest.fixture
def extractor():
    return PolicyFeedbackExtractor()


@pytest.fixture
def block_episode():
    return _make_episode(reaction_label="block")


@pytest.fixture
def correct_episode():
    return _make_episode(reaction_label="correct")


@pytest.fixture
def approve_episode():
    return _make_episode(reaction_label="approve")


@pytest.fixture
def recommendation():
    return _make_recommendation()


@pytest.fixture
def empty_store():
    return _FakeConstraintStore([])


@pytest.fixture
def db_conn():
    """In-memory DuckDB with schema for promote_confirmed tests."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn
    conn.close()


# --- Extract tests ---


class TestExtractBlockReaction:
    """Block reaction creates forbidden constraint."""

    def test_extract_block_reaction_creates_forbidden(
        self, extractor, recommendation, block_episode, empty_store
    ):
        """block -> severity='forbidden', source='policy_feedback', status='candidate'."""
        result = extractor.extract(recommendation, block_episode, empty_store)
        assert result is not None
        assert result["severity"] == "forbidden"
        assert result["source"] == "policy_feedback"
        assert result["status"] == "candidate"


class TestExtractCorrectReaction:
    """Correct reaction creates requires_approval constraint."""

    def test_extract_correct_reaction_creates_requires_approval(
        self, extractor, recommendation, correct_episode, empty_store
    ):
        """correct -> severity='requires_approval'."""
        result = extractor.extract(recommendation, correct_episode, empty_store)
        assert result is not None
        assert result["severity"] == "requires_approval"
        assert result["source"] == "policy_feedback"
        assert result["status"] == "candidate"


class TestExtractApproveReaction:
    """Approve reaction returns None."""

    def test_extract_approve_reaction_returns_none(
        self, extractor, recommendation, approve_episode, empty_store
    ):
        """approve -> None."""
        result = extractor.extract(recommendation, approve_episode, empty_store)
        assert result is None


class TestExtractNoneReaction:
    """None reaction returns None."""

    def test_extract_none_reaction_returns_none(
        self, extractor, recommendation, empty_store
    ):
        """None -> None."""
        episode = _make_episode(reaction_label=None)
        result = extractor.extract(recommendation, episode, empty_store)
        assert result is None


class TestConstraintId:
    """Constraint ID generation."""

    def test_constraint_id_uses_policy_feedback_source(
        self, extractor, recommendation, block_episode, empty_store
    ):
        """Verify ID includes ':policy_feedback' in hash input."""
        result = extractor.extract(recommendation, block_episode, empty_store)
        assert result is not None

        # Manually compute expected ID
        text = recommendation.reasoning
        scope_paths = recommendation.recommended_scope_paths
        key = (
            text.lower().strip()
            + ":"
            + json.dumps(sorted(scope_paths))
            + ":policy_feedback"
        )
        expected_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        assert result["constraint_id"] == expected_id

    def test_constraint_id_deterministic(
        self, extractor, recommendation, block_episode, empty_store
    ):
        """Same inputs -> same ID."""
        r1 = extractor.extract(recommendation, block_episode, empty_store)
        r2 = extractor.extract(recommendation, block_episode, empty_store)
        assert r1 is not None and r2 is not None
        assert r1["constraint_id"] == r2["constraint_id"]

    def test_constraint_id_differs_from_human(
        self, extractor, recommendation, block_episode, empty_store
    ):
        """Same text+scope but source='policy_feedback' vs 'human_correction' -> different IDs."""
        result = extractor.extract(recommendation, block_episode, empty_store)
        assert result is not None

        # Compute what a human_correction ID would be
        text = recommendation.reasoning
        scope_paths = recommendation.recommended_scope_paths
        human_key = (
            text.lower().strip()
            + ":"
            + json.dumps(sorted(scope_paths))
            + ":human_correction"
        )
        human_id = hashlib.sha256(human_key.encode()).hexdigest()[:16]
        assert result["constraint_id"] != human_id


class TestDedup:
    """Deduplication via shared detection_hints."""

    def test_dedup_enriches_existing_human_constraint(
        self, extractor, recommendation
    ):
        """Matching human constraint (2+ shared hints) -> return None."""
        existing = {
            "constraint_id": "c-human-001",
            "text": "Do not delete config files",
            "severity": "forbidden",
            "scope": {"paths": ["src/"]},
            "detection_hints": ["delete", "src/config.py", "Implement"],
            "source": "human_correction",
            "status": "active",
            "examples": [],
        }
        store = _FakeConstraintStore([existing])
        episode = _make_episode(reaction_label="block")
        result = extractor.extract(recommendation, episode, store)
        assert result is None

    def test_no_dedup_when_insufficient_hint_overlap(
        self, extractor, recommendation
    ):
        """Only 1 shared hint -> creates new constraint (no dedup)."""
        existing = {
            "constraint_id": "c-human-002",
            "text": "Protect secrets",
            "severity": "forbidden",
            "scope": {"paths": ["src/"]},
            "detection_hints": ["secrets.py", "credentials"],  # No overlap with rec
            "source": "human_correction",
            "status": "active",
            "examples": [],
        }
        store = _FakeConstraintStore([existing])
        episode = _make_episode(reaction_label="block")
        result = extractor.extract(recommendation, episode, store)
        assert result is not None
        assert result["source"] == "policy_feedback"


class TestConstraintFields:
    """Verify constraint output dict structure."""

    def test_constraint_has_status_history(
        self, extractor, recommendation, block_episode, empty_store
    ):
        """Output includes status_history with candidate entry."""
        result = extractor.extract(recommendation, block_episode, empty_store)
        assert result is not None
        assert "status_history" in result
        assert len(result["status_history"]) >= 1
        assert result["status_history"][0]["status"] == "candidate"

    def test_constraint_has_type_behavioral(
        self, extractor, recommendation, block_episode, empty_store
    ):
        """type='behavioral_constraint'."""
        result = extractor.extract(recommendation, block_episode, empty_store)
        assert result is not None
        assert result["type"] == "behavioral_constraint"

    def test_detection_hints_extracted_from_recommendation(
        self, extractor, block_episode, empty_store
    ):
        """Mode, scope paths appear in hints."""
        rec = _make_recommendation(
            reasoning="We should deploy to production",
            scope_paths=["src/deploy.py"],
            mode="Deploy",
            gates=["approval_required"],
        )
        result = extractor.extract(rec, block_episode, empty_store)
        assert result is not None
        hints = result["detection_hints"]
        # Mode and scope paths should appear in detection hints
        assert any("Deploy" in h or "deploy" in h.lower() for h in hints)
        assert any("src/deploy.py" in h for h in hints)


class TestPromoteConfirmed:
    """Promotion of candidates with 3+ sessions."""

    def test_promote_confirmed_promotes_after_3_sessions(
        self, extractor, db_conn
    ):
        """Candidates with 3+ session appearances -> promoted to active."""
        # Create a candidate constraint in the store
        candidate = {
            "constraint_id": "c-promote-001",
            "text": "Test constraint",
            "severity": "forbidden",
            "source": "policy_feedback",
            "status": "candidate",
            "status_history": [
                {"status": "candidate", "changed_at": "2025-01-01T00:00:00Z"}
            ],
        }
        store = _FakeConstraintStore([candidate])

        # Insert 3 distinct sessions into policy_error_events
        for i in range(3):
            db_conn.execute(
                "INSERT INTO policy_error_events "
                "(error_id, session_id, episode_id, error_type, constraint_id, "
                "recommendation_mode, recommendation_risk) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    f"err-{i}",
                    f"sess-{i}",
                    f"ep-{i}",
                    "surfaced_and_blocked",
                    "c-promote-001",
                    "Implement",
                    "medium",
                ],
            )

        count = extractor.promote_confirmed(store, db_conn, min_sessions=3)
        assert count == 1
        assert candidate["status"] == "active"

    def test_promote_confirmed_skips_insufficient_sessions(
        self, extractor, db_conn
    ):
        """Candidates with < 3 sessions stay candidate."""
        candidate = {
            "constraint_id": "c-promote-002",
            "text": "Test constraint",
            "severity": "forbidden",
            "source": "policy_feedback",
            "status": "candidate",
            "status_history": [
                {"status": "candidate", "changed_at": "2025-01-01T00:00:00Z"}
            ],
        }
        store = _FakeConstraintStore([candidate])

        # Only 2 sessions
        for i in range(2):
            db_conn.execute(
                "INSERT INTO policy_error_events "
                "(error_id, session_id, episode_id, error_type, constraint_id, "
                "recommendation_mode, recommendation_risk) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    f"err-{i}",
                    f"sess-{i}",
                    f"ep-{i}",
                    "surfaced_and_blocked",
                    "c-promote-002",
                    "Implement",
                    "medium",
                ],
            )

        count = extractor.promote_confirmed(store, db_conn, min_sessions=3)
        assert count == 0
        assert candidate["status"] == "candidate"

    def test_promote_confirmed_returns_count(self, extractor, db_conn):
        """Returns number of promoted constraints."""
        # Two candidates, both with 3+ sessions
        c1 = {
            "constraint_id": "c-promo-a",
            "text": "Constraint A",
            "severity": "forbidden",
            "source": "policy_feedback",
            "status": "candidate",
            "status_history": [
                {"status": "candidate", "changed_at": "2025-01-01T00:00:00Z"}
            ],
        }
        c2 = {
            "constraint_id": "c-promo-b",
            "text": "Constraint B",
            "severity": "forbidden",
            "source": "policy_feedback",
            "status": "candidate",
            "status_history": [
                {"status": "candidate", "changed_at": "2025-01-01T00:00:00Z"}
            ],
        }
        store = _FakeConstraintStore([c1, c2])

        for cid in ["c-promo-a", "c-promo-b"]:
            for i in range(3):
                db_conn.execute(
                    "INSERT INTO policy_error_events "
                    "(error_id, session_id, episode_id, error_type, constraint_id, "
                    "recommendation_mode, recommendation_risk) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        f"err-{cid}-{i}",
                        f"sess-{i}",
                        f"ep-{cid}-{i}",
                        "surfaced_and_blocked",
                        cid,
                        "Implement",
                        "medium",
                    ],
                )

        count = extractor.promote_confirmed(store, db_conn, min_sessions=3)
        assert count == 2
