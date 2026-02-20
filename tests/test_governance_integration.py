"""End-to-end integration tests for the governance pipeline.

Tests the full ingestion pipeline using the real objectivism_premortem.md
fixture and verifying constraint counts, wisdom entity counts, metadata
linkage, idempotency, DECISIONS.md handling, bulk flagging, and stability
runner flow.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.cli.__main__ import cli
from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.governance.ingestor import GovDocIngestor
from src.pipeline.governance.stability import StabilityRunner
from src.pipeline.models.config import GovernanceConfig, StabilityCheckDef
from src.pipeline.storage.schema import create_schema, get_connection
from src.pipeline.wisdom.store import WisdomStore


PREMORTEM_PATH = Path("data/objectivism_premortem.md")


@pytest.fixture
def constraint_store(tmp_path: Path) -> ConstraintStore:
    """ConstraintStore with isolated tmp_path and schema validation."""
    return ConstraintStore(
        path=tmp_path / "constraints.json",
        schema_path=Path("data/schemas/constraint.schema.json"),
    )


@pytest.fixture
def wisdom_store(tmp_path: Path) -> WisdomStore:
    """WisdomStore using a temp DuckDB file."""
    return WisdomStore(db_path=tmp_path / "wisdom.duckdb")


@pytest.fixture
def ingestor(
    constraint_store: ConstraintStore, wisdom_store: WisdomStore
) -> GovDocIngestor:
    """GovDocIngestor with default bulk threshold of 5."""
    return GovDocIngestor(
        constraint_store=constraint_store,
        wisdom_store=wisdom_store,
        bulk_threshold=5,
    )


# --- Full pre-mortem ingestion ---


class TestFullPremortemIngest:
    """Tests against the real objectivism_premortem.md fixture."""

    def test_constraint_count(
        self, ingestor: GovDocIngestor, constraint_store: ConstraintStore
    ) -> None:
        result = ingestor.ingest_file(PREMORTEM_PATH)
        assert result.constraints_added == 15
        assert constraint_store.count == 15

    def test_wisdom_count(
        self, ingestor: GovDocIngestor, wisdom_store: WisdomStore
    ) -> None:
        result = ingestor.ingest_file(PREMORTEM_PATH)
        assert result.wisdom_added == 11
        entities = wisdom_store.list()
        assert len(entities) == 11

    def test_all_wisdom_are_dead_end(
        self, ingestor: GovDocIngestor, wisdom_store: WisdomStore
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        entities = wisdom_store.list()
        assert all(e.entity_type == "dead_end" for e in entities)

    def test_constraint_source_field(
        self, ingestor: GovDocIngestor, constraint_store: ConstraintStore
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        for c in constraint_store.constraints:
            assert c["source"] == "govern_ingest"

    def test_constraint_type_field(
        self, ingestor: GovDocIngestor, constraint_store: ConstraintStore
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        for c in constraint_store.constraints:
            assert c["type"] == "behavioral_constraint"

    def test_constraint_source_excerpt_populated(
        self, ingestor: GovDocIngestor, constraint_store: ConstraintStore
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        for c in constraint_store.constraints:
            assert "source_excerpt" in c
            assert c["source_excerpt"] is not None
            assert c["source_excerpt"] != ""

    def test_forbidden_severity_count(
        self, ingestor: GovDocIngestor, constraint_store: ConstraintStore
    ) -> None:
        """At least 2 constraints should have 'forbidden' severity."""
        ingestor.ingest_file(PREMORTEM_PATH)
        forbidden_count = sum(
            1 for c in constraint_store.constraints if c["severity"] == "forbidden"
        )
        assert forbidden_count >= 2

    def test_remaining_severity_requires_approval(
        self, ingestor: GovDocIngestor, constraint_store: ConstraintStore
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        for c in constraint_store.constraints:
            assert c["severity"] in ("forbidden", "requires_approval")


# --- Wisdom metadata linkage ---


class TestPremortemWisdomMetadata:
    """Tests for co-occurrence linkage in wisdom metadata."""

    def test_dead_end_has_related_constraint_ids(
        self, ingestor: GovDocIngestor, wisdom_store: WisdomStore
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        entities = wisdom_store.list()
        for entity in entities:
            assert entity.metadata is not None
            assert "related_constraint_ids" in entity.metadata
            assert len(entity.metadata["related_constraint_ids"]) == 15

    def test_constraint_ids_match_store(
        self,
        ingestor: GovDocIngestor,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        store_ids = {c["constraint_id"] for c in constraint_store.constraints}
        entities = wisdom_store.list()
        for entity in entities:
            linked_ids = set(entity.metadata["related_constraint_ids"])
            assert linked_ids == store_ids


# --- Idempotency ---


class TestPremortemIdempotent:
    """Tests for idempotent re-ingestion."""

    def test_second_ingest_skips_constraints(
        self,
        ingestor: GovDocIngestor,
        constraint_store: ConstraintStore,
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        result2 = ingestor.ingest_file(PREMORTEM_PATH)
        assert result2.constraints_added == 0
        assert result2.constraints_skipped == 15
        assert constraint_store.count == 15

    def test_second_ingest_updates_wisdom(
        self,
        ingestor: GovDocIngestor,
        wisdom_store: WisdomStore,
    ) -> None:
        ingestor.ingest_file(PREMORTEM_PATH)
        result2 = ingestor.ingest_file(PREMORTEM_PATH)
        assert result2.wisdom_updated == 11
        assert result2.wisdom_added == 0
        assert len(wisdom_store.list()) == 11


# --- DECISIONS.md ---


class TestDecisionsMdIngestion:
    """Tests for DECISIONS.md-style fixture ingestion."""

    def test_decisions_produce_only_wisdom(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """# DECISIONS.md

## Scope Decisions

### Batch Processing
Use batch over sequential.

### Upload Pipeline
Only process unknown-category files.

## Method Decisions

### Vector Search
Use HNSW indexing.
"""
        p = tmp_path / "DECISIONS.md"
        p.write_text(content)

        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        result = ingestor.ingest_file(p)

        assert result.constraints_added == 0
        assert constraint_store.count == 0
        assert result.wisdom_added == 3

        entities = wisdom_store.list()
        types = {e.entity_type for e in entities}
        assert types == {"scope_decision", "method_decision"}

    def test_decisions_wisdom_has_no_constraints(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        tmp_path: Path,
    ) -> None:
        content = """# DECISIONS.md

## Scope Decisions

### Example Decision
Details here.
"""
        p = tmp_path / "DECISIONS.md"
        p.write_text(content)

        ingestor = GovDocIngestor(constraint_store, wisdom_store)
        ingestor.ingest_file(p)

        entities = wisdom_store.list()
        for entity in entities:
            if entity.metadata and "related_constraint_ids" in entity.metadata:
                assert entity.metadata["related_constraint_ids"] == []


# --- Bulk ingest flag ---


class TestBulkIngestFlag:
    """Tests for is_bulk flag on GovIngestResult."""

    def test_premortem_is_bulk(self, ingestor: GovDocIngestor) -> None:
        result = ingestor.ingest_file(PREMORTEM_PATH)
        # 11 wisdom + 15 constraints = 26 entities > threshold of 5
        assert result.is_bulk is True
        assert result.total_entities >= 26


# --- Stability runner flow ---


class TestStabilityRunnerFlow:
    """Tests for the stability check execution and flagging pipeline."""

    def test_run_checks_passing(self) -> None:
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        config = GovernanceConfig(
            stability_checks=[
                StabilityCheckDef(
                    id="echo-check", command=["echo", "stability-ok"]
                )
            ]
        )
        runner = StabilityRunner(conn=conn, config=config)
        outcomes = runner.run_checks(repo_root=".")

        assert len(outcomes) == 1
        assert outcomes[0].status == "pass"
        assert outcomes[0].exit_code == 0
        conn.close()

    def test_flag_missing_validation_empty_episodes(self) -> None:
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        config = GovernanceConfig(
            stability_checks=[
                StabilityCheckDef(id="check", command=["echo", "ok"])
            ]
        )
        runner = StabilityRunner(conn=conn, config=config)
        count = runner.flag_missing_validation(conn)
        assert count == 0
        conn.close()

    def test_flag_and_validate_episodes(self) -> None:
        """Insert episodes needing checks, flag them, then validate."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        # Insert a minimal episode that requires stability check
        conn.execute(
            """
            INSERT INTO episodes (
                episode_id, session_id, segment_id, timestamp,
                requires_stability_check, stability_check_status
            ) VALUES (
                'ep-1', 'sess-1', 'seg-1', '2026-01-01T00:00:00Z',
                TRUE, NULL
            )
            """
        )

        config = GovernanceConfig(
            stability_checks=[
                StabilityCheckDef(id="check", command=["echo", "ok"])
            ]
        )
        runner = StabilityRunner(conn=conn, config=config)

        # Flag missing
        missing = runner.flag_missing_validation(conn)
        assert missing == 1

        status = conn.execute(
            "SELECT stability_check_status FROM episodes WHERE episode_id = 'ep-1'"
        ).fetchone()[0]
        assert status == "missing"

        # Run passing checks
        runner.run_checks(repo_root=".")

        # Mark validated
        validated = runner.mark_validated(conn)
        assert validated == 1

        status = conn.execute(
            "SELECT stability_check_status FROM episodes WHERE episode_id = 'ep-1'"
        ).fetchone()[0]
        assert status == "validated"
        conn.close()


# --- CLI integration ---


class TestGovernCLIIntegration:
    """Tests for the full govern CLI with real pre-mortem fixture."""

    def test_premortem_cli_dry_run(self, tmp_path: Path) -> None:
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        shutil.copy("data/config.yaml", config_path)
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "ingest",
                str(PREMORTEM_PATH),
                "--dry-run",
                "--db",
                db_path,
                "--constraints",
                str(tmp_path / "c.json"),
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "DRY RUN" in result.output
        assert "15 added" in result.output  # constraints
        assert "11 added" in result.output  # wisdom

    def test_premortem_cli_full_ingest(self, tmp_path: Path) -> None:
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        shutil.copy("data/config.yaml", config_path)
        db_path = str(tmp_path / "test.duckdb")

        result = runner.invoke(
            cli,
            [
                "govern",
                "ingest",
                str(PREMORTEM_PATH),
                "--db",
                db_path,
                "--constraints",
                str(tmp_path / "c.json"),
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "15 added" in result.output
        assert "11 added" in result.output
        assert "BULK INGEST" in result.output
