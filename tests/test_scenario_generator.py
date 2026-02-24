"""Tests for ScenarioGenerator (Phase 17, Plan 02).

Covers:
- L3 dead_end scenario generation (no handicap)
- L1 breakthrough scenario generation (no handicap, no seed)
- L6 scope_decision scenario generation (with handicap)
- Unannotated entry raises ValueError
- File generation creates expected files
- Broken impl validation (fails correctly)
- Broken impl validation (false if succeeds)
- ScenarioSpec make_id deterministic
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from src.pipeline.assessment.models import ScenarioSpec
from src.pipeline.assessment.scenario_generator import (
    ScenarioGenerator,
    generate_scenario,
)


@pytest.fixture
def conn_with_wisdom():
    """In-memory DuckDB with project_wisdom table and test entries."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_wisdom (
            wisdom_id VARCHAR PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            description TEXT NOT NULL,
            scenario_seed TEXT,
            ddf_target_level INTEGER
        )
    """)

    # dead_end, L3, has seed
    conn.execute(
        "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
        [
            "w-deadend001",
            "dead_end",
            "Circular import deadlock",
            "The pipeline hit a circular import between the tagger and the "
            "schema module. Solution: restructure to lazy imports.",
            "def main():\n    raise RuntimeError('circular import detected')",
            3,
        ],
    )

    # breakthrough, L1, no seed
    conn.execute(
        "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
        [
            "w-breakthrough001",
            "breakthrough",
            "Episode boundary via stream_end",
            "Discovered that stream_end events reliably mark episode "
            "boundaries. This insight simplified the segmenter logic.",
            None,
            1,
        ],
    )

    # scope_decision, L6, no seed
    conn.execute(
        "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
        [
            "w-scope001",
            "scope_decision",
            "DuckDB over SQLite for analytics",
            "Chose DuckDB over SQLite for the analytics store because "
            "columnar storage enabled faster aggregation queries across "
            "millions of episode rows.",
            None,
            6,
        ],
    )

    # Unannotated entry (ddf_target_level is NULL)
    conn.execute(
        "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
        [
            "w-unannotated001",
            "dead_end",
            "Unannotated entry",
            "This entry has no DDF target level assigned.",
            None,
            None,
        ],
    )

    yield conn
    conn.close()


# ── Test 1: L3 dead_end generates without handicap ──


def test_generate_scenario_l3_dead_end(conn_with_wisdom):
    """L3 dead_end scenario has no handicap_claude_md."""
    gen = ScenarioGenerator(conn_with_wisdom)
    spec = gen.generate_scenario("w-deadend001")

    assert spec.wisdom_id == "w-deadend001"
    assert spec.ddf_target_level == 3
    assert spec.entity_type == "dead_end"
    assert spec.title == "Circular import deadlock"
    assert spec.handicap_claude_md is None  # L3 < L5, no handicap
    assert "Assessment Scenario" in spec.scenario_context
    assert spec.broken_impl_content  # Not empty
    assert spec.broken_impl_filename == "broken_impl.py"
    assert "circular import detected" in spec.broken_impl_content


# ── Test 2: L1 breakthrough generates without handicap ──


def test_generate_scenario_l1_breakthrough(conn_with_wisdom):
    """L1 breakthrough has no handicap and generates broken impl from default template."""
    gen = ScenarioGenerator(conn_with_wisdom)
    spec = gen.generate_scenario("w-breakthrough001")

    assert spec.wisdom_id == "w-breakthrough001"
    assert spec.ddf_target_level == 1
    assert spec.entity_type == "breakthrough"
    assert spec.handicap_claude_md is None
    assert spec.broken_impl_content  # Not empty
    assert "RuntimeError" in spec.broken_impl_content  # Default template uses RuntimeError


# ── Test 3: L6 scope_decision generates with handicap ──


def test_generate_scenario_l6_with_handicap(conn_with_wisdom):
    """L6 scope_decision scenario includes handicap_claude_md."""
    gen = ScenarioGenerator(conn_with_wisdom)
    spec = gen.generate_scenario("w-scope001")

    assert spec.wisdom_id == "w-scope001"
    assert spec.ddf_target_level == 6
    assert spec.entity_type == "scope_decision"
    assert spec.handicap_claude_md is not None
    assert "Project Analysis" in spec.handicap_claude_md
    assert "Root Cause Analysis" in spec.handicap_claude_md
    assert "Suggested Fix" in spec.handicap_claude_md


# ── Test 4: Unannotated entry raises ValueError ──


def test_generate_scenario_unannotated_raises(conn_with_wisdom):
    """NULL ddf_target_level raises ValueError."""
    gen = ScenarioGenerator(conn_with_wisdom)
    with pytest.raises(ValueError, match="no ddf_target_level"):
        gen.generate_scenario("w-unannotated001")


# ── Test 5: File generation creates expected files ──


def test_generate_scenario_files_creates_files(conn_with_wisdom, tmp_path):
    """generate_scenario_files creates scenario_context.md, broken_impl.py, and CLAUDE.md for L6+."""
    gen = ScenarioGenerator(conn_with_wisdom)

    # Test L6 (with handicap)
    spec_l6 = gen.generate_scenario("w-scope001")
    output_dir = tmp_path / "l6_scenario"
    ctx_path, impl_path, claude_path = gen.generate_scenario_files(spec_l6, output_dir)

    assert ctx_path.exists()
    assert ctx_path.name == "scenario_context.md"
    assert "Assessment Scenario" in ctx_path.read_text()

    assert impl_path.exists()
    assert impl_path.name == "broken_impl.py"

    assert claude_path is not None
    assert claude_path.exists()
    assert claude_path.parent.name == ".claude"
    assert claude_path.name == "CLAUDE.md"
    assert "Project Analysis" in claude_path.read_text()

    # Test L3 (without handicap)
    spec_l3 = gen.generate_scenario("w-deadend001")
    output_dir_l3 = tmp_path / "l3_scenario"
    ctx_path3, impl_path3, claude_path3 = gen.generate_scenario_files(spec_l3, output_dir_l3)

    assert ctx_path3.exists()
    assert impl_path3.exists()
    assert claude_path3 is None  # L3 < L5, no handicap file


# ── Test 6: Broken impl fails correctly ──


def test_validate_broken_impl_fails_correctly(conn_with_wisdom, tmp_path):
    """Seed that raises RuntimeError validates as correctly failing."""
    gen = ScenarioGenerator(conn_with_wisdom)
    spec = gen.generate_scenario("w-deadend001")

    output_dir = tmp_path / "validate_fail"
    gen.generate_scenario_files(spec, output_dir)

    assert gen.validate_broken_impl(spec, output_dir) is True


# ── Test 7: Broken impl false if succeeds ──


def test_validate_broken_impl_false_if_succeeds(tmp_path):
    """An implementation that succeeds (exit 0) returns False."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE project_wisdom (
            wisdom_id VARCHAR PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            description TEXT NOT NULL,
            scenario_seed TEXT,
            ddf_target_level INTEGER
        )
    """)
    conn.execute(
        "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
        [
            "w-success001",
            "dead_end",
            "Success test",
            "This should succeed.",
            'def main():\n    print("ok")',
            3,
        ],
    )

    gen = ScenarioGenerator(conn)
    spec = gen.generate_scenario("w-success001")

    output_dir = tmp_path / "validate_success"
    gen.generate_scenario_files(spec, output_dir)

    assert gen.validate_broken_impl(spec, output_dir) is False
    conn.close()


# ── Test 8: ScenarioSpec make_id deterministic ──


def test_scenario_spec_make_id_deterministic():
    """Same wisdom_id + level -> same ID."""
    id1 = ScenarioSpec.make_id("w-deadend001", 3)
    id2 = ScenarioSpec.make_id("w-deadend001", 3)
    id3 = ScenarioSpec.make_id("w-deadend001", 4)

    assert id1 == id2, "Same inputs produce same ID"
    assert id1 != id3, "Different level produces different ID"
    assert len(id1) == 16


# ── Test 9: generate_scenario convenience function ──


def test_generate_scenario_convenience(conn_with_wisdom):
    """generate_scenario() convenience function works."""
    spec = generate_scenario(conn_with_wisdom, "w-deadend001")
    assert isinstance(spec, ScenarioSpec)
    assert spec.wisdom_id == "w-deadend001"


# ── Test 10: Nonexistent wisdom_id raises ValueError ──


def test_generate_scenario_nonexistent_raises(conn_with_wisdom):
    """Nonexistent wisdom_id raises ValueError."""
    gen = ScenarioGenerator(conn_with_wisdom)
    with pytest.raises(ValueError, match="not found"):
        gen.generate_scenario("w-nonexistent")


# ── Test 11: Solution hints stripped from context ──


def test_scenario_context_strips_solution_hints(conn_with_wisdom):
    """Solution hint lines are stripped from scenario context."""
    conn_with_wisdom.execute(
        "INSERT INTO project_wisdom VALUES (?, ?, ?, ?, ?, ?)",
        [
            "w-hints001",
            "dead_end",
            "Hints test",
            "The code fails on import.\nSolution: move import to function body.\nMore detail here.",
            None,
            3,
        ],
    )

    gen = ScenarioGenerator(conn_with_wisdom)
    spec = gen.generate_scenario("w-hints001")

    assert "Solution:" not in spec.scenario_context
    assert "The code fails on import" in spec.scenario_context
    assert "More detail here" in spec.scenario_context
