"""Tests for identification review DuckDB schema.

Verifies:
- identification_reviews DDL creates table with UNIQUE constraint
- Inserting duplicate identification_instance_id raises error
- CCD format constraint on memory_candidates rejects empty fields
- layer_coverage_snapshots table creation
- identification_rule_trust table creation and constraints
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from src.pipeline.review.schema import (
    IDENTIFICATION_REVIEWS_DDL,
    IDENTIFICATION_RULE_TRUST_DDL,
    LAYER_COVERAGE_SNAPSHOTS_DDL,
    MEMORY_CANDIDATES_DDL,
    create_review_schema,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection with review schema."""
    c = duckdb.connect(":memory:")
    create_review_schema(c)
    yield c
    c.close()


class TestIdentificationReviewsTable:
    """identification_reviews table DDL and constraints."""

    def test_table_created(self, conn: duckdb.DuckDBPyConnection):
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "identification_reviews" in table_names

    def test_unique_constraint_on_instance_id(
        self, conn: duckdb.DuckDBPyConnection
    ):
        """Inserting two rows with same identification_instance_id raises error."""
        review_id_1 = str(uuid.uuid4())
        review_id_2 = str(uuid.uuid4())
        instance_id = "events:evt1:L2-1"

        conn.execute(
            """
            INSERT INTO identification_reviews (
                review_id, identification_instance_id, layer, point_id,
                pipeline_component, trigger_text, observation_state,
                action_taken, downstream_impact, provenance_pointer,
                verdict
            ) VALUES (?, ?, 'L2', 'L2-1', 'EventTagger', 'trigger',
                      'obs', 'action', 'impact', 'prov', 'accept')
            """,
            [review_id_1, instance_id],
        )

        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO identification_reviews (
                    review_id, identification_instance_id, layer, point_id,
                    pipeline_component, trigger_text, observation_state,
                    action_taken, downstream_impact, provenance_pointer,
                    verdict
                ) VALUES (?, ?, 'L2', 'L2-1', 'EventTagger', 'trigger',
                          'obs', 'action', 'impact', 'prov', 'reject')
                """,
                [review_id_2, instance_id],
            )

    def test_verdict_check_constraint(self, conn: duckdb.DuckDBPyConnection):
        """Only 'accept' and 'reject' are valid verdicts."""
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO identification_reviews (
                    review_id, identification_instance_id, layer, point_id,
                    pipeline_component, trigger_text, observation_state,
                    action_taken, downstream_impact, provenance_pointer,
                    verdict
                ) VALUES ('r1', 'inst1', 'L1', 'L1-1', 'comp', 'trig',
                          'obs', 'act', 'imp', 'prov', 'maybe')
                """
            )

    def test_valid_insert(self, conn: duckdb.DuckDBPyConnection):
        """Valid row inserts without error."""
        conn.execute(
            """
            INSERT INTO identification_reviews (
                review_id, identification_instance_id, layer, point_id,
                pipeline_component, trigger_text, observation_state,
                action_taken, downstream_impact, provenance_pointer,
                verdict, opinion, session_id
            ) VALUES ('r1', 'inst1', 'L3', 'L3-1', 'Segmenter',
                      'trigger text', 'observation', 'action taken',
                      'downstream', 'provenance', 'accept', NULL, 'sess1')
            """
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM identification_reviews"
        ).fetchone()[0]
        assert count == 1

    def test_idempotent_creation(self, conn: duckdb.DuckDBPyConnection):
        """Running DDL twice does not error."""
        conn.execute(IDENTIFICATION_REVIEWS_DDL)
        tables = conn.execute("SHOW TABLES").fetchall()
        assert any(t[0] == "identification_reviews" for t in tables)


class TestMemoryCandidatesTable:
    """memory_candidates table with CCD format constraints."""

    def test_table_created(self, conn: duckdb.DuckDBPyConnection):
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "memory_candidates" in table_names

    def test_valid_ccd_insert(self, conn: duckdb.DuckDBPyConnection):
        """Row with valid CCD fields inserts successfully."""
        conn.execute(
            """
            INSERT INTO memory_candidates (id, ccd_axis, scope_rule, flood_example)
            VALUES ('mc1', 'deposit-not-detect', 'Every component evaluated by deposit',
                    'write-on-detect is load-bearing')
            """
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates"
        ).fetchone()[0]
        assert count == 1

    def test_rejects_empty_ccd_axis(self, conn: duckdb.DuckDBPyConnection):
        """Empty ccd_axis violates CHECK constraint."""
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO memory_candidates (id, ccd_axis, scope_rule, flood_example)
                VALUES ('mc2', '', 'scope', 'flood')
                """
            )

    def test_rejects_whitespace_scope_rule(self, conn: duckdb.DuckDBPyConnection):
        """Whitespace-only scope_rule violates CHECK constraint."""
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO memory_candidates (id, ccd_axis, scope_rule, flood_example)
                VALUES ('mc3', 'axis', '   ', 'flood')
                """
            )

    def test_rejects_empty_flood_example(self, conn: duckdb.DuckDBPyConnection):
        """Empty flood_example violates CHECK constraint."""
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO memory_candidates (id, ccd_axis, scope_rule, flood_example)
                VALUES ('mc4', 'axis', 'scope', '')
                """
            )

    def test_source_instance_id_link(self, conn: duckdb.DuckDBPyConnection):
        """source_instance_id links to identification_reviews."""
        conn.execute(
            """
            INSERT INTO memory_candidates
            (id, source_instance_id, ccd_axis, scope_rule, flood_example)
            VALUES ('mc5', 'events:evt1:L2-1', 'axis', 'scope', 'flood')
            """
        )
        row = conn.execute(
            "SELECT source_instance_id FROM memory_candidates WHERE id='mc5'"
        ).fetchone()
        assert row[0] == "events:evt1:L2-1"

    def test_status_default_pending(self, conn: duckdb.DuckDBPyConnection):
        """Default status is 'pending'."""
        conn.execute(
            """
            INSERT INTO memory_candidates (id, ccd_axis, scope_rule, flood_example)
            VALUES ('mc6', 'axis', 'scope', 'flood')
            """
        )
        row = conn.execute(
            "SELECT status FROM memory_candidates WHERE id='mc6'"
        ).fetchone()
        assert row[0] == "pending"

    def test_status_check_constraint(self, conn: duckdb.DuckDBPyConnection):
        """Invalid status values are rejected."""
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO memory_candidates
                (id, ccd_axis, scope_rule, flood_example, status)
                VALUES ('mc7', 'axis', 'scope', 'flood', 'invalid_status')
                """
            )


class TestLayerCoverageSnapshots:
    """layer_coverage_snapshots table creation."""

    def test_table_created(self, conn: duckdb.DuckDBPyConnection):
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "layer_coverage_snapshots" in table_names

    def test_insert_snapshot(self, conn: duckdb.DuckDBPyConnection):
        conn.execute(
            """
            INSERT INTO layer_coverage_snapshots
            (snapshot_id, layer, reviewed_count, pool_count, coverage_ratio)
            VALUES ('snap1', 'L2', 5, 10, 0.5)
            """
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM layer_coverage_snapshots"
        ).fetchone()[0]
        assert count == 1


class TestIdentificationRuleTrust:
    """identification_rule_trust table DDL and constraints."""

    def test_table_created(self, conn: duckdb.DuckDBPyConnection):
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "identification_rule_trust" in table_names

    def test_valid_insert(self, conn: duckdb.DuckDBPyConnection):
        conn.execute(
            """
            INSERT INTO identification_rule_trust
            (rule_id, pipeline_component, point_id, accept_count, reject_count, trust_level)
            VALUES ('r1', 'EventTagger', 'L2-1', 5, 0, 'unverified')
            """
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM identification_rule_trust"
        ).fetchone()[0]
        assert count == 1

    def test_trust_level_check_constraint(self, conn: duckdb.DuckDBPyConnection):
        """Invalid trust_level values are rejected."""
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                """
                INSERT INTO identification_rule_trust
                (rule_id, pipeline_component, point_id, trust_level)
                VALUES ('r2', 'Comp', 'L1-1', 'invalid')
                """
            )

    def test_default_trust_level_unverified(self, conn: duckdb.DuckDBPyConnection):
        conn.execute(
            """
            INSERT INTO identification_rule_trust
            (rule_id, pipeline_component, point_id)
            VALUES ('r3', 'Comp', 'L1-1')
            """
        )
        row = conn.execute(
            "SELECT trust_level FROM identification_rule_trust WHERE rule_id='r3'"
        ).fetchone()
        assert row[0] == "unverified"


class TestCreateReviewSchema:
    """create_review_schema() helper function."""

    def test_creates_all_four_tables(self):
        c = duckdb.connect(":memory:")
        create_review_schema(c)
        tables = c.execute("SHOW TABLES").fetchall()
        table_names = {t[0] for t in tables}
        assert "identification_reviews" in table_names
        assert "memory_candidates" in table_names
        assert "layer_coverage_snapshots" in table_names
        assert "identification_rule_trust" in table_names
        c.close()

    def test_idempotent(self):
        c = duckdb.connect(":memory:")
        create_review_schema(c)
        create_review_schema(c)  # Second call should not error
        tables = c.execute("SHOW TABLES").fetchall()
        assert len(tables) == 4
        c.close()
