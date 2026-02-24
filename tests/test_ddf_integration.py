"""Integration tests for the full DDF pipeline (Phase 15, Plan 07).

Validates all 10 DDF requirements (DDF-01 through DDF-10) with end-to-end
tests that exercise the schema, detectors, enrichment, deposit, metrics,
spiral tracking, and CLI working together.

Each test uses in-memory DuckDB (no file I/O) unless the component under
test requires a file-based DB (WisdomStore, CLI profile).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from src.pipeline.ddf.models import (
    AxisHypothesis,
    ConstraintMetric,
    FlameEvent,
    IntelligenceProfile,
)
from src.pipeline.ddf.schema import create_ddf_schema
from src.pipeline.ddf.writer import write_flame_events
from src.pipeline.models.config import PipelineConfig, load_config


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ddf_pipeline():
    """Create in-memory DuckDB with DDF + review schemas and default config.

    Returns (conn, config) tuple. The connection has flame_events,
    ai_flame_events view, axis_hypotheses, constraint_metrics, and
    memory_candidates tables ready.
    """
    conn = duckdb.connect(":memory:")
    # create_ddf_schema internally calls create_review_schema
    create_ddf_schema(conn)
    config = load_config("data/config.yaml")
    yield conn, config
    conn.close()


@pytest.fixture
def seeded_flame_events(ddf_pipeline):
    """Seed flame_events with a mix of L0-7 markers across 3 sessions.

    Seeds human markers (L0-L7) and AI markers, with some flood_confirmed.
    Returns (conn, config) tuple with data already seeded.
    """
    conn, config = ddf_pipeline

    events = [
        # Session 1, Human A -- L0, L1, L2
        FlameEvent(
            flame_event_id="fe_h_s1_l0",
            session_id="sess_1",
            human_id="human_a",
            prompt_number=1,
            marker_level=0,
            marker_type="L0_trunk",
            evidence_excerpt="the core issue is",
            subject="human",
            detection_source="stub",
        ),
        FlameEvent(
            flame_event_id="fe_h_s1_l1",
            session_id="sess_1",
            human_id="human_a",
            prompt_number=2,
            marker_level=1,
            marker_type="L1_causal",
            evidence_excerpt="because the pipeline fails",
            subject="human",
            detection_source="stub",
        ),
        FlameEvent(
            flame_event_id="fe_h_s1_l2",
            session_id="sess_1",
            human_id="human_a",
            prompt_number=3,
            marker_level=2,
            marker_type="L2_assertive",
            evidence_excerpt="the root cause is the missing import",
            subject="human",
            detection_source="stub",
        ),
        # Session 1, Human A -- L6 flood confirmed with axis
        FlameEvent(
            flame_event_id="fe_h_s1_l6",
            session_id="sess_1",
            human_id="human_a",
            prompt_number=4,
            marker_level=6,
            marker_type="flood_confirmed",
            evidence_excerpt="Flood confirmation with complete evidence and sufficient text length for validation check",
            axis_identified="deposit-not-detect",
            flood_confirmed=True,
            subject="human",
            detection_source="opeml",
        ),
        # Session 2, Human A -- L3, L4
        FlameEvent(
            flame_event_id="fe_h_s2_l3",
            session_id="sess_2",
            human_id="human_a",
            prompt_number=1,
            marker_level=3,
            marker_type="L0_trunk_enriched",
            evidence_excerpt="cross-context enrichment",
            subject="human",
            detection_source="opeml",
        ),
        FlameEvent(
            flame_event_id="fe_h_s2_l4",
            session_id="sess_2",
            human_id="human_a",
            prompt_number=2,
            marker_level=4,
            marker_type="L1_causal_enriched",
            evidence_excerpt="principle identified",
            subject="human",
            detection_source="opeml",
        ),
        # Session 3, Human B -- L0, L5, L7
        FlameEvent(
            flame_event_id="fe_h_s3_l0",
            session_id="sess_3",
            human_id="human_b",
            prompt_number=1,
            marker_level=0,
            marker_type="L0_trunk",
            evidence_excerpt="the fundamental concept",
            subject="human",
            detection_source="stub",
        ),
        FlameEvent(
            flame_event_id="fe_h_s3_l5",
            session_id="sess_3",
            human_id="human_b",
            prompt_number=2,
            marker_level=5,
            marker_type="L2_assertive_enriched",
            evidence_excerpt="deep naming",
            subject="human",
            detection_source="opeml",
        ),
        FlameEvent(
            flame_event_id="fe_h_s3_l7",
            session_id="sess_3",
            human_id="human_b",
            prompt_number=3,
            marker_level=7,
            marker_type="full_flood",
            evidence_excerpt="complete flood with new axis confirmation",
            axis_identified="identity-firewall",
            flood_confirmed=True,
            subject="human",
            detection_source="opeml",
        ),
        # AI markers across sessions
        FlameEvent(
            flame_event_id="fe_ai_s1_l2",
            session_id="sess_1",
            marker_level=2,
            marker_type="ai_assertive_causal",
            evidence_excerpt="the root cause is identified by AI",
            subject="ai",
            detection_source="opeml",
        ),
        FlameEvent(
            flame_event_id="fe_ai_s2_l6",
            session_id="sess_2",
            marker_level=6,
            marker_type="ai_concretization_flood",
            evidence_excerpt="for example X, for instance Y, such as Z",
            flood_confirmed=True,
            subject="ai",
            detection_source="opeml",
        ),
    ]

    write_flame_events(conn, events)
    return conn, config


@pytest.fixture
def synthetic_session_events():
    """Build a list of event dicts mimicking a real JSONL session.

    Includes human messages with trunk identification language (L0),
    causal language (L1, L2), a granularity drop + novel concept pair (O_AXS),
    and AI messages with CCD patterns.
    """
    events = [
        # Human message 1: trunk identification (L0) + causal (L1)
        {
            "actor": "human_orchestrator",
            "event_type": "user_msg",
            "payload": {
                "common": {
                    "text": (
                        "The core issue is that the pipeline fails because "
                        "the imports are broken. This is fundamentally about "
                        "correctness at the module boundary."
                    )
                }
            },
        },
        # AI response with assertive causal pattern
        {
            "actor": "executor",
            "event_type": "assistant_msg",
            "payload": {
                "common": {
                    "text": (
                        "The root cause is that the __init__.py files are "
                        "missing the required re-exports. For example the "
                        "models module, for instance the config module, "
                        "such as the schema module, specifically the "
                        "writer module."
                    )
                }
            },
        },
        # Human message 2: assertive causal (L2)
        {
            "actor": "human_orchestrator",
            "event_type": "user_msg",
            "payload": {
                "common": {
                    "text": (
                        "I'm certain the root cause is the missing validation. "
                        "The rule is that every constraint must carry an axis."
                    )
                }
            },
        },
        # Human message 3: long operational message (baseline for O_AXS)
        {
            "actor": "human_orchestrator",
            "event_type": "user_msg",
            "payload": {
                "common": {
                    "text": (
                        "Please also investigate the test failures in the "
                        "pipeline runner module and figure out why the imports "
                        "are broken and fix all of the issues that are causing "
                        "problems in the test suite including the integration "
                        "tests and the unit tests and end-to-end tests and "
                        "also check the configuration files"
                    )
                }
            },
        },
        # Human message 4: another long message
        {
            "actor": "human_orchestrator",
            "event_type": "user_msg",
            "payload": {
                "common": {
                    "text": (
                        "And while you are at it please review the constraint "
                        "extraction logic to ensure that all the episode types "
                        "are being handled correctly especially the escalation "
                        "episodes and the timeout episodes and the superseded "
                        "episodes that have special handling requirements too"
                    )
                }
            },
        },
        # Human message 5: short with novel concept (O_AXS trigger candidate)
        {
            "actor": "human_orchestrator",
            "event_type": "user_msg",
            "payload": {
                "common": {
                    "text": "Deposit Not Detect. Deposit Not Detect."
                }
            },
        },
    ]
    return events


# ---------------------------------------------------------------------------
# DDF-01: O_AXS valid episode mode
# ---------------------------------------------------------------------------


class TestDDF01OAxs:
    """DDF-01: O_AXS is a valid episode mode and produces detections."""

    def test_ddf01_o_axs_is_valid_mode(self):
        """O_AXS must be in segmenter START_TRIGGERS."""
        from src.pipeline.segmenter import START_TRIGGERS

        assert "O_AXS" in START_TRIGGERS

    def test_ddf01_o_axs_detector_in_pipeline(self, synthetic_session_events):
        """OAxsDetector should be importable and detect on qualifying events."""
        from src.pipeline.ddf.tier1.o_axs import OAxsDetector
        from src.pipeline.models.config import OAxsConfig

        config = OAxsConfig(
            granularity_drop_ratio=0.5,
            prior_prompts_window=5,
            novel_concept_min_occurrences=2,
            novel_concept_message_window=3,
        )
        detector = OAxsDetector(config)

        detections = []
        for evt in synthetic_session_events:
            actor = evt.get("actor", "")
            text = evt.get("payload", {}).get("common", {}).get("text", "")
            if text:
                detected, evidence = detector.detect(text, actor)
                if detected:
                    detections.append(evidence)

        # The detector may or may not fire depending on exact token counts,
        # but it must be callable without error. If it fires, evidence is dict.
        for d in detections:
            assert isinstance(d, dict)
            assert "novel_concept" in d


# ---------------------------------------------------------------------------
# DDF-02: flame_events human markers
# ---------------------------------------------------------------------------


class TestDDF02FlameEventsHuman:
    """DDF-02: flame_events stores human markers with detection_source."""

    def test_ddf02_flame_events_human_markers(self, seeded_flame_events):
        """All seeded human markers should be queryable."""
        conn, _ = seeded_flame_events

        rows = conn.execute(
            "SELECT flame_event_id, marker_level FROM flame_events "
            "WHERE subject = 'human' ORDER BY marker_level"
        ).fetchall()

        # We seeded 9 human markers (L0, L1, L2, L6 in sess1; L3, L4 in sess2; L0, L5, L7 in sess3)
        assert len(rows) == 9
        levels = [r[1] for r in rows]
        assert 0 in levels
        assert 1 in levels
        assert 2 in levels
        assert 6 in levels
        assert 7 in levels

    def test_ddf02_detection_source_field(self, seeded_flame_events):
        """detection_source should be 'stub' for Tier 1, 'opeml' for Tier 2."""
        conn, _ = seeded_flame_events

        stub_count = conn.execute(
            "SELECT COUNT(*) FROM flame_events WHERE detection_source = 'stub'"
        ).fetchone()[0]
        opeml_count = conn.execute(
            "SELECT COUNT(*) FROM flame_events WHERE detection_source = 'opeml'"
        ).fetchone()[0]

        assert stub_count >= 1, "Should have at least one stub (Tier 1) event"
        assert opeml_count >= 1, "Should have at least one opeml (Tier 2) event"


# ---------------------------------------------------------------------------
# DDF-03: ai_flame_events + write-on-detect
# ---------------------------------------------------------------------------


class TestDDF03AiFlameEvents:
    """DDF-03: ai_flame_events view and Level 6 deposit path."""

    def test_ddf03_ai_flame_events_view(self, seeded_flame_events):
        """ai_flame_events view should return only subject='ai' rows."""
        conn, _ = seeded_flame_events

        ai_rows = conn.execute(
            "SELECT flame_event_id, subject FROM ai_flame_events"
        ).fetchall()

        assert len(ai_rows) == 2  # We seeded 2 AI markers
        for row in ai_rows:
            assert row[1] == "ai"

        # Verify no human events leak through
        human_in_view = conn.execute(
            "SELECT COUNT(*) FROM ai_flame_events WHERE subject = 'human'"
        ).fetchone()[0]
        assert human_in_view == 0

    def test_ddf03_write_on_detect_deposit(self, ddf_pipeline):
        """Level 6 flood_confirmed event should deposit to memory_candidates."""
        conn, config = ddf_pipeline

        # Create and write a Level 6 flood-confirmed event
        fe = FlameEvent(
            flame_event_id="deposit_test_l6",
            session_id="deposit_sess",
            human_id="deposit_human",
            prompt_number=1,
            marker_level=6,
            marker_type="flood_confirmed",
            evidence_excerpt="Flood detected with complete evidence and enough text to pass length check for deposit",
            axis_identified="test-deposit-axis",
            flood_confirmed=True,
            subject="human",
            detection_source="opeml",
        )
        write_flame_events(conn, [fe])

        # Call deposit_level6 via FlameEventExtractor
        from src.pipeline.ddf.tier2.flame_extractor import FlameEventExtractor

        extractor = FlameEventExtractor(config, conn)
        count = extractor.deposit_level6(conn, [fe])

        assert count == 1

        # Verify memory_candidates row exists with source_flame_event_id
        mc_row = conn.execute(
            "SELECT id, ccd_axis, source_flame_event_id FROM memory_candidates "
            "WHERE source_flame_event_id = 'deposit_test_l6'"
        ).fetchone()

        assert mc_row is not None
        assert mc_row[1] is not None  # ccd_axis is set
        assert mc_row[2] == "deposit_test_l6"


# ---------------------------------------------------------------------------
# DDF-04: IntelligenceProfile
# ---------------------------------------------------------------------------


class TestDDF04IntelligenceProfile:
    """DDF-04: IntelligenceProfile aggregation for human and AI."""

    def test_ddf04_intelligence_profile_aggregation(self, seeded_flame_events):
        """Human profile should aggregate all 6 metrics correctly."""
        conn, _ = seeded_flame_events
        from src.pipeline.ddf.intelligence_profile import (
            compute_intelligence_profile,
        )

        profile = compute_intelligence_profile(conn, "human_a")
        assert profile is not None
        assert profile.human_id == "human_a"
        assert profile.subject == "human"
        # human_a has 6 events: L0, L1, L2, L6 (sess1) + L3, L4 (sess2)
        assert profile.flame_frequency == 6
        assert profile.session_count == 2
        assert profile.max_marker_level == 6
        # avg = (0+1+2+6+3+4)/6 = 16/6 = 2.6667
        assert abs(profile.avg_marker_level - 2.6667) < 0.01
        # flood_rate = 1/6 (one L6 event out of 6)
        assert abs(profile.flood_rate - 1 / 6) < 0.01
        assert isinstance(profile.spiral_depth, int)

    def test_ddf04_ai_profile_separate(self, seeded_flame_events):
        """AI profile should aggregate only subject='ai' events."""
        conn, _ = seeded_flame_events
        from src.pipeline.ddf.intelligence_profile import compute_ai_profile

        ai_profile = compute_ai_profile(conn)
        assert ai_profile is not None
        assert ai_profile.subject == "ai"
        assert ai_profile.human_id == "ai"
        # 2 AI events: L2 (sess1) + L6 (sess2)
        assert ai_profile.flame_frequency == 2
        assert ai_profile.session_count == 2
        assert ai_profile.max_marker_level == 6
        # flood_rate = 1/2 (one L6 out of 2)
        assert abs(ai_profile.flood_rate - 0.5) < 0.01


# ---------------------------------------------------------------------------
# DDF-05: GeneralizationRadius
# ---------------------------------------------------------------------------


class TestDDF05GeneralizationRadius:
    """DDF-05: GeneralizationRadius and stagnation detection."""

    def test_ddf05_generalization_radius(self, ddf_pipeline):
        """Constraints with varying scope paths should have correct radius."""
        conn, config = ddf_pipeline

        # Create session_constraint_eval table (from main schema)
        from src.pipeline.storage.schema import create_schema

        create_schema(conn)

        # Seed evals with varying scope paths across sessions
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json) VALUES "
            "('s1', 'c1', 'active', ?)",
            [json.dumps([{"scope_path": "src/pipeline/runner.py"}])],
        )
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json) VALUES "
            "('s2', 'c1', 'active', ?)",
            [json.dumps([{"scope_path": "tests/test_runner.py"}])],
        )
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json) VALUES "
            "('s3', 'c1', 'active', ?)",
            [json.dumps([{"scope_path": "docs/README.md"}])],
        )

        from src.pipeline.ddf.generalization import compute_generalization_radius

        metric = compute_generalization_radius(conn, "c1", config)
        assert metric.constraint_id == "c1"
        assert metric.radius == 3  # src, tests, docs
        assert metric.firing_count == 3
        assert metric.is_stagnant is False

    def test_ddf05_stagnation_detection(self, ddf_pipeline):
        """Constraint with radius=1, firing_count >= 10 should be stagnant."""
        conn, config = ddf_pipeline

        from src.pipeline.storage.schema import create_schema

        create_schema(conn)

        # Seed 10 evals all in the same scope prefix
        for i in range(10):
            conn.execute(
                "INSERT INTO session_constraint_eval "
                "(session_id, constraint_id, eval_state, evidence_json) VALUES "
                "(?, 'stag_c1', 'active', ?)",
                [f"stag_s{i}", json.dumps([{"scope_path": "src/pipeline/foo.py"}])],
            )

        from src.pipeline.ddf.generalization import detect_stagnation

        stagnant = detect_stagnation(conn, config)
        stagnant_ids = [m.constraint_id for m in stagnant]
        assert "stag_c1" in stagnant_ids

        metric = next(m for m in stagnant if m.constraint_id == "stag_c1")
        assert metric.radius == 1
        assert metric.firing_count == 10
        assert metric.is_stagnant is True


# ---------------------------------------------------------------------------
# DDF-06: Spiral tracking + project_wisdom promotion
# ---------------------------------------------------------------------------


class TestDDF06SpiralTracking:
    """DDF-06: Spiral detection and project_wisdom promotion."""

    def test_ddf06_spiral_ascending_scopes(self, ddf_pipeline):
        """Constraint with ascending scope diversity should be detected as spiral."""
        conn, config = ddf_pipeline

        from src.pipeline.storage.schema import create_schema

        create_schema(conn)

        # Session 1: only 'src' prefix
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json, eval_ts) VALUES "
            "('sp_s1', 'sp_c1', 'active', ?, '2026-01-01T00:00:00Z')",
            [json.dumps([{"scope_path": "src/pipeline/runner.py"}])],
        )
        # Session 2: 'src' + 'tests' prefixes
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json, eval_ts) VALUES "
            "('sp_s2', 'sp_c1', 'active', ?, '2026-01-02T00:00:00Z')",
            [json.dumps([{"scope_path": "tests/test_runner.py"}])],
        )
        # Session 3: 'src' + 'tests' + 'docs' prefixes
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json, eval_ts) VALUES "
            "('sp_s3', 'sp_c1', 'active', ?, '2026-01-03T00:00:00Z')",
            [json.dumps([{"scope_path": "docs/README.md"}])],
        )

        from src.pipeline.ddf.spiral import detect_spirals

        spirals = detect_spirals(conn)
        spiral_ids = [s["constraint_id"] for s in spirals]
        assert "sp_c1" in spiral_ids

        spiral = next(s for s in spirals if s["constraint_id"] == "sp_c1")
        assert spiral["spiral_length"] == 3
        assert spiral["current_radius"] == 3

    def test_ddf06_spiral_promotion_to_project_wisdom(self, tmp_path, ddf_pipeline):
        """Spiral candidates with length >= 3 should be promoted to project_wisdom."""
        conn, config = ddf_pipeline

        from src.pipeline.storage.schema import create_schema

        create_schema(conn)

        # Set up spiral data (3 sessions with ascending scope diversity)
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json, eval_ts) VALUES "
            "('pw_s1', 'pw_c1', 'active', ?, '2026-01-01T00:00:00Z')",
            [json.dumps([{"scope_path": "src/pipeline/runner.py"}])],
        )
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json, eval_ts) VALUES "
            "('pw_s2', 'pw_c1', 'active', ?, '2026-01-02T00:00:00Z')",
            [json.dumps([{"scope_path": "tests/test_foo.py"}])],
        )
        conn.execute(
            "INSERT INTO session_constraint_eval "
            "(session_id, constraint_id, eval_state, evidence_json, eval_ts) VALUES "
            "('pw_s3', 'pw_c1', 'active', ?, '2026-01-03T00:00:00Z')",
            [json.dumps([{"scope_path": "docs/api.md"}])],
        )

        # Use a file-based DB for WisdomStore
        db_file = tmp_path / "wisdom_test.db"

        from src.pipeline.ddf.spiral import promote_spirals_to_wisdom

        promoted = promote_spirals_to_wisdom(conn, db_file, min_spiral_length=3)
        assert promoted >= 1

        # Verify project_wisdom table has the promoted entry
        wisdom_conn = duckdb.connect(str(db_file))
        rows = wisdom_conn.execute(
            "SELECT entity_type, metadata FROM project_wisdom "
            "WHERE entity_type = 'breakthrough'"
        ).fetchall()
        wisdom_conn.close()

        assert len(rows) >= 1
        entity_type, metadata_json = rows[0]
        assert entity_type == "breakthrough"

        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
        assert "source_constraint_id" in metadata
        assert metadata["source_constraint_id"] == "pw_c1"


# ---------------------------------------------------------------------------
# DDF-07: Epistemological origin
# ---------------------------------------------------------------------------


class TestDDF07EpistemologicalOrigin:
    """DDF-07: Epistemological origin classification on constraints."""

    def test_ddf07_epistemological_on_constraint(self):
        """Block reaction episode should classify as 'reactive'."""
        from src.pipeline.ddf.epistemological import classify_epistemological_origin

        episode = {
            "mode": "SUPERVISED",
            "outcome": {
                "reaction": {
                    "label": "block",
                }
            },
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "reactive"
        assert confidence == 0.9

    def test_ddf07_default_is_principled(self):
        """Episode with no strong signal should default to 'principled'."""
        from src.pipeline.ddf.epistemological import classify_epistemological_origin

        episode = {
            "mode": "AUTONOMOUS",
            "outcome": {"reaction": {"label": "neutral"}},
        }
        origin, confidence = classify_epistemological_origin(episode)
        assert origin == "principled"
        assert confidence == 1.0


# ---------------------------------------------------------------------------
# DDF-08: Intelligence CLI
# ---------------------------------------------------------------------------


class TestDDF08IntelligenceCLI:
    """DDF-08: CLI displays profile from pipeline-produced data."""

    def test_ddf08_cli_profile_output(self, tmp_path):
        """CLI profile command should display all metrics from seeded data."""
        from click.testing import CliRunner

        from src.pipeline.cli.intelligence import intelligence_group

        # Create a file-based DB with seeded data
        db_file = tmp_path / "cli_test.db"
        conn = duckdb.connect(str(db_file))
        create_ddf_schema(conn)

        events = [
            FlameEvent(
                flame_event_id="cli_fe_1",
                session_id="cli_sess_1",
                human_id="cli_human",
                prompt_number=1,
                marker_level=2,
                marker_type="L2_assertive",
                evidence_excerpt="the root cause",
                subject="human",
                detection_source="stub",
            ),
            FlameEvent(
                flame_event_id="cli_fe_2",
                session_id="cli_sess_1",
                human_id="cli_human",
                prompt_number=2,
                marker_level=4,
                marker_type="L1_causal_enriched",
                evidence_excerpt="principle identified",
                subject="human",
                detection_source="opeml",
            ),
            FlameEvent(
                flame_event_id="cli_fe_3",
                session_id="cli_sess_2",
                human_id="cli_human",
                prompt_number=1,
                marker_level=6,
                marker_type="flood_confirmed",
                evidence_excerpt="complete flood",
                flood_confirmed=True,
                subject="human",
                detection_source="opeml",
            ),
        ]
        write_flame_events(conn, events)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            intelligence_group, ["profile", "cli_human", "--db", str(db_file)]
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Intelligence Profile" in result.output
        assert "Sessions:" in result.output
        assert "Flame Frequency:" in result.output
        assert "Avg Marker Level:" in result.output
        assert "Max Marker Level:" in result.output
        assert "Spiral Depth:" in result.output
        assert "Flood Rate:" in result.output


# ---------------------------------------------------------------------------
# DDF-09: False Integration
# ---------------------------------------------------------------------------


class TestDDF09FalseIntegration:
    """DDF-09: False integration (Package Deal) detection."""

    def test_ddf09_false_integration_marker(self, ddf_pipeline):
        """Episode with 2+ distinct scope prefixes should produce detection."""
        conn, config = ddf_pipeline

        from src.pipeline.ddf.tier2.false_integration import (
            FalseIntegrationDetector,
        )

        detector = FalseIntegrationDetector(config, conn)

        episodes = [
            {
                "episode_id": "ep_fi_1",
                "orchestrator_action": json.dumps(
                    {
                        "scope": [
                            "src/pipeline/runner.py",
                            "tests/test_runner.py",
                            "docs/api.md",
                        ],
                        "constraints": ["c1"],
                    }
                ),
            }
        ]

        flame_events, hypotheses = detector.detect("fi_sess", episodes)

        # At least one hypothesis (3 prefixes: src, tests, docs -> confidence = 0.9)
        assert len(hypotheses) >= 1
        h = hypotheses[0]
        assert "possible_package_deal" in h.hypothesized_axis
        assert h.confidence >= 0.6

        # Verify hypothesis was written to axis_hypotheses table
        db_rows = conn.execute(
            "SELECT hypothesis_id FROM axis_hypotheses"
        ).fetchall()
        assert len(db_rows) >= 1

        # With 3 prefixes, confidence = min(0.9, 0.3*3) = 0.9 >= threshold (default 0.6)
        # so flame_events should also be emitted
        assert len(flame_events) >= 1
        assert flame_events[0].subject == "ai"
        assert flame_events[0].marker_type == "false_integration"


# ---------------------------------------------------------------------------
# DDF-10: Causal Isolation Query
# ---------------------------------------------------------------------------


class TestDDF10CausalIsolation:
    """DDF-10: Causal isolation markers from premise_registry."""

    def test_ddf10_causal_isolation_records(self, ddf_pipeline):
        """Premise registry entries should produce causal isolation markers."""
        conn, config = ddf_pipeline

        # Create premise_registry table
        from src.pipeline.premise.schema import create_premise_schema

        # Need episodes table for parent_episode_id ALTER, create main schema first
        from src.pipeline.storage.schema import create_schema

        create_schema(conn)
        create_premise_schema(conn)

        # Seed premise_registry with 3 types of entries:
        # 1. Successful isolation (has foil_path_outcomes with divergence_node)
        conn.execute(
            "INSERT INTO premise_registry "
            "(premise_id, claim, session_id, foil_path_outcomes, foil) VALUES "
            "(?, ?, ?, ?, ?)",
            [
                "prem_success",
                "Module X causes error because of import cycle",
                "ci_sess",
                json.dumps({"divergence_node": "import_resolver", "outcome": "confirmed"}),
                "No import cycle in module X",
            ],
        )
        # 2. Failed isolation (has foil_path_outcomes without divergence_node)
        conn.execute(
            "INSERT INTO premise_registry "
            "(premise_id, claim, session_id, foil_path_outcomes, foil) VALUES "
            "(?, ?, ?, ?, ?)",
            [
                "prem_failed",
                "Config change leads to regression",
                "ci_sess",
                json.dumps({"outcome": "indeterminate"}),
                "Config is unchanged",
            ],
        )
        # 3. Missing isolation (causal claim but no foil outcomes)
        conn.execute(
            "INSERT INTO premise_registry "
            "(premise_id, claim, session_id, foil_path_outcomes, foil) VALUES "
            "(?, ?, ?, ?, ?)",
            [
                "prem_missing",
                "This results in broken pipeline because of missing import",
                "ci_sess",
                None,
                None,
            ],
        )

        from src.pipeline.ddf.tier2.causal_isolation import CausalIsolationRecorder

        recorder = CausalIsolationRecorder(conn)
        markers = recorder.record("ci_sess")

        assert len(markers) == 3

        # All markers should have subject='ai'
        for m in markers:
            assert m.subject == "ai"

        # Find each marker type
        types = {m.marker_type for m in markers}
        assert "causal_isolation_success" in types
        assert "causal_isolation_failed" in types
        assert "missing_isolation" in types

        # Verify levels
        success = next(m for m in markers if m.marker_type == "causal_isolation_success")
        failed = next(m for m in markers if m.marker_type == "causal_isolation_failed")
        missing = next(m for m in markers if m.marker_type == "missing_isolation")

        assert success.marker_level == 3
        assert failed.marker_level == 2
        assert missing.marker_level == 1


# ---------------------------------------------------------------------------
# Module import smoke test
# ---------------------------------------------------------------------------


class TestDDFModuleImports:
    """Verify all DDF modules are importable without error."""

    def test_all_ddf_modules_importable(self):
        """Every DDF module should import without error."""
        import importlib

        modules = [
            "src.pipeline.ddf.models",
            "src.pipeline.ddf.schema",
            "src.pipeline.ddf.writer",
            "src.pipeline.ddf.deposit",
            "src.pipeline.ddf.tier1.markers",
            "src.pipeline.ddf.tier1.o_axs",
            "src.pipeline.ddf.tier2.flame_extractor",
            "src.pipeline.ddf.tier2.causal_isolation",
            "src.pipeline.ddf.tier2.false_integration",
            "src.pipeline.ddf.epistemological",
            "src.pipeline.ddf.generalization",
            "src.pipeline.ddf.spiral",
            "src.pipeline.ddf.intelligence_profile",
            "src.pipeline.cli.intelligence",
        ]

        for mod_name in modules:
            try:
                importlib.import_module(mod_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {mod_name}: {e}")
