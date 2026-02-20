"""Tests for PolicyViolationChecker -- pre-surfacing constraint check.

TDD RED phase: Tests written against the behavior spec before implementation.
Covers:
- Suppression of recommendations matching forbidden/requires_approval constraint hints
- Warning constraints logged but not suppressed
- No match returns (False, None)
- Case-insensitive matching
- Empty detection_hints skipped
- First match wins with multiple constraints
- build_recommendation_text concatenation
- Only active constraints are checked
- Scope overlap without detection_hints is NOT matched (intentional deferral)
"""

from __future__ import annotations

import pytest

from src.pipeline.feedback.checker import PolicyViolationChecker
from src.pipeline.rag.recommender import Recommendation, SourceEpisodeRef


# --- Helpers ---


def _make_constraint(
    constraint_id: str = "c-001",
    severity: str = "forbidden",
    detection_hints: list[str] | None = None,
    status: str = "active",
    scope_paths: list[str] | None = None,
) -> dict:
    """Create a test constraint dict with sensible defaults."""
    return {
        "constraint_id": constraint_id,
        "text": f"Test constraint {constraint_id}",
        "severity": severity,
        "scope": {"paths": scope_paths or ["src/"]},
        "detection_hints": detection_hints if detection_hints is not None else ["delete", "rm"],
        "source": "human_correction",
        "status": status,
        "type": "behavioral_constraint",
        "created_at": "2025-01-01T00:00:00Z",
        "status_history": [{"status": status, "changed_at": "2025-01-01T00:00:00Z"}],
        "examples": [],
    }


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


class _FakeConstraintStore:
    """Minimal constraint store for testing checker."""

    def __init__(self, constraints: list[dict]):
        self._constraints = constraints

    def get_active_constraints(self) -> list[dict]:
        return [c for c in self._constraints if c.get("status") == "active"]


# --- Fixtures ---


@pytest.fixture
def forbidden_constraint():
    return _make_constraint(
        constraint_id="c-forbidden",
        severity="forbidden",
        detection_hints=["delete", "rm -rf"],
    )


@pytest.fixture
def requires_approval_constraint():
    return _make_constraint(
        constraint_id="c-approval",
        severity="requires_approval",
        detection_hints=["deploy", "push to production"],
    )


@pytest.fixture
def warning_constraint():
    return _make_constraint(
        constraint_id="c-warning",
        severity="warning",
        detection_hints=["refactor", "restructure"],
    )


# --- Tests ---


class TestSuppressForbidden:
    """Forbidden constraint hints should suppress recommendations."""

    def test_suppress_forbidden_constraint(self, forbidden_constraint):
        """Recommendation text contains forbidden constraint hint -> (True, constraint)."""
        store = _FakeConstraintStore([forbidden_constraint])
        checker = PolicyViolationChecker(store)
        rec = _make_recommendation(reasoning="We need to delete the old files")
        text = PolicyViolationChecker.build_recommendation_text(rec)
        should_suppress, matched = checker.check(text)
        assert should_suppress is True
        assert matched is not None
        assert matched["constraint_id"] == "c-forbidden"


class TestSuppressRequiresApproval:
    """requires_approval constraint hints should suppress recommendations."""

    def test_suppress_requires_approval_constraint(self, requires_approval_constraint):
        """requires_approval hint match -> (True, constraint)."""
        store = _FakeConstraintStore([requires_approval_constraint])
        checker = PolicyViolationChecker(store)
        text = "We should deploy to production now"
        should_suppress, matched = checker.check(text)
        assert should_suppress is True
        assert matched is not None
        assert matched["constraint_id"] == "c-approval"


class TestWarningNotSuppressed:
    """Warning constraints are logged but not suppressed."""

    def test_warning_constraint_not_suppressed(self, warning_constraint):
        """Warning severity hint match -> (False, constraint) [logged, not suppressed]."""
        store = _FakeConstraintStore([warning_constraint])
        checker = PolicyViolationChecker(store)
        text = "We should refactor the auth module"
        should_suppress, matched = checker.check(text)
        assert should_suppress is False
        assert matched is not None
        assert matched["constraint_id"] == "c-warning"


class TestNoMatch:
    """No matching hints returns (False, None)."""

    def test_no_match_returns_false_none(self, forbidden_constraint):
        """No hint matches -> (False, None)."""
        store = _FakeConstraintStore([forbidden_constraint])
        checker = PolicyViolationChecker(store)
        text = "We should add a new feature for users"
        should_suppress, matched = checker.check(text)
        assert should_suppress is False
        assert matched is None


class TestCaseInsensitive:
    """Case-insensitive matching."""

    def test_case_insensitive_matching(self):
        """'DELETE' in text matches 'delete' hint."""
        constraint = _make_constraint(
            constraint_id="c-case",
            severity="forbidden",
            detection_hints=["delete"],
        )
        store = _FakeConstraintStore([constraint])
        checker = PolicyViolationChecker(store)
        text = "We need to DELETE the old config"
        should_suppress, matched = checker.check(text)
        assert should_suppress is True
        assert matched is not None
        assert matched["constraint_id"] == "c-case"


class TestEmptyDetectionHints:
    """Constraints with no detection_hints are skipped."""

    def test_empty_detection_hints_skipped(self):
        """Constraint with no hints is never matched."""
        constraint = _make_constraint(
            constraint_id="c-empty-hints",
            severity="forbidden",
            detection_hints=[],
        )
        store = _FakeConstraintStore([constraint])
        checker = PolicyViolationChecker(store)
        text = "delete everything rm -rf all the files"
        should_suppress, matched = checker.check(text)
        assert should_suppress is False
        assert matched is None


class TestMultipleConstraints:
    """Multiple constraints, first match wins."""

    def test_multiple_constraints_first_match_wins(self):
        """Multiple constraints with matching hints, returns first match."""
        c1 = _make_constraint(
            constraint_id="c-first",
            severity="forbidden",
            detection_hints=["delete"],
        )
        c2 = _make_constraint(
            constraint_id="c-second",
            severity="requires_approval",
            detection_hints=["delete"],
        )
        store = _FakeConstraintStore([c1, c2])
        checker = PolicyViolationChecker(store)
        text = "We need to delete the config"
        should_suppress, matched = checker.check(text)
        assert should_suppress is True
        assert matched["constraint_id"] == "c-first"


class TestBuildRecommendationText:
    """Test build_recommendation_text concatenation."""

    def test_build_recommendation_text(self):
        """Concatenates reasoning + scope_paths + mode + gates into single string."""
        rec = _make_recommendation(
            reasoning="Delete old config",
            scope_paths=["src/config.py", "src/utils.py"],
            mode="Implement",
            gates=["run_tests", "review"],
        )
        text = PolicyViolationChecker.build_recommendation_text(rec)
        assert "Delete old config" in text
        assert "src/config.py" in text
        assert "src/utils.py" in text
        assert "Implement" in text
        assert "run_tests" in text
        assert "review" in text

    def test_build_recommendation_text_empty_fields(self):
        """Handles empty lists gracefully."""
        rec = Recommendation(
            recommended_mode="Implement",
            recommended_risk="low",
            recommended_scope_paths=[],
            recommended_gates=[],
            confidence=0.5,
            source_episodes=[],
            reasoning="Simple change",
        )
        text = PolicyViolationChecker.build_recommendation_text(rec)
        assert "Simple change" in text
        assert "Implement" in text


class TestOnlyActiveConstraints:
    """Only active constraints are checked."""

    def test_only_active_constraints_checked(self):
        """Candidate/retired constraints are not loaded."""
        active = _make_constraint(
            constraint_id="c-active",
            severity="forbidden",
            detection_hints=["deploy"],
            status="active",
        )
        candidate = _make_constraint(
            constraint_id="c-candidate",
            severity="forbidden",
            detection_hints=["deploy"],
            status="candidate",
        )
        retired = _make_constraint(
            constraint_id="c-retired",
            severity="forbidden",
            detection_hints=["deploy"],
            status="retired",
        )
        store = _FakeConstraintStore([active, candidate, retired])
        checker = PolicyViolationChecker(store)
        text = "We need to deploy now"
        should_suppress, matched = checker.check(text)
        assert should_suppress is True
        assert matched["constraint_id"] == "c-active"


class TestEmptyStore:
    """Checker with no constraints."""

    def test_checker_with_no_constraints(self):
        """Empty store -> always returns (False, None)."""
        store = _FakeConstraintStore([])
        checker = PolicyViolationChecker(store)
        text = "delete everything deploy now"
        should_suppress, matched = checker.check(text)
        assert should_suppress is False
        assert matched is None


class TestScopePathInHints:
    """File path from scope_paths matches constraint hint containing same path."""

    def test_scope_path_in_recommendation_text_matches_path_hint(self):
        """Constraint with path hint matches when recommendation text includes that path."""
        constraint = _make_constraint(
            constraint_id="c-path-hint",
            severity="forbidden",
            detection_hints=["src/secrets.py"],
        )
        store = _FakeConstraintStore([constraint])
        checker = PolicyViolationChecker(store)
        rec = _make_recommendation(
            reasoning="Modify configuration",
            scope_paths=["src/secrets.py", "src/config.py"],
        )
        text = PolicyViolationChecker.build_recommendation_text(rec)
        should_suppress, matched = checker.check(text)
        assert should_suppress is True
        assert matched["constraint_id"] == "c-path-hint"


class TestNoDetectionHintsNotScopeMatched:
    """Intentional deferral: scope overlap without detection_hints is NOT matched."""

    def test_no_detection_hints_skipped_not_scope_matched(self):
        """Constraint with empty detection_hints but overlapping scope_paths is NOT matched.

        Documents the intentional deferral of scope_overlap_warning fallback
        (CONTEXT.md Gray Area 2 answer deferred to future gap closure plan).
        """
        constraint = _make_constraint(
            constraint_id="c-scope-only",
            severity="forbidden",
            detection_hints=[],  # No detection hints
            scope_paths=["src/config.py"],  # Overlaps with recommendation
        )
        store = _FakeConstraintStore([constraint])
        checker = PolicyViolationChecker(store)
        rec = _make_recommendation(
            reasoning="Update config settings",
            scope_paths=["src/config.py"],  # Overlapping scope
        )
        text = PolicyViolationChecker.build_recommendation_text(rec)
        should_suppress, matched = checker.check(text)
        assert should_suppress is False
        assert matched is None
