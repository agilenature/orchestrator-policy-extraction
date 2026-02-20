"""Tests for Phase 12 governance foundation layer.

Covers:
- GovernanceConfig default values and custom stability checks
- GovernanceConfig loads from config.yaml
- Constraint schema accepts source_excerpt field
- Constraint schema rejects unknown fields
- WisdomEntity metadata round-trip through WisdomStore
- WisdomEntity metadata=None case
- DuckDB stability_outcomes table creation
- DuckDB episodes governance columns
- DuckDB project_wisdom metadata column
- Schema idempotency (create_schema twice)
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import jsonschema
import pytest

from src.pipeline.models.config import (
    GovernanceConfig,
    PipelineConfig,
    StabilityCheckDef,
    load_config,
)
from src.pipeline.storage.schema import create_schema, get_connection
from src.pipeline.wisdom.models import WisdomEntity
from src.pipeline.wisdom.store import WisdomStore


# ---------------------------------------------------------------------------
# GovernanceConfig tests
# ---------------------------------------------------------------------------


class TestGovernanceConfigDefaults:
    """Test GovernanceConfig default values."""

    def test_default_bulk_ingest_threshold(self) -> None:
        config = GovernanceConfig()
        assert config.bulk_ingest_threshold == 5

    def test_default_stability_checks_empty(self) -> None:
        config = GovernanceConfig()
        assert config.stability_checks == []

    def test_in_pipeline_config(self) -> None:
        config = PipelineConfig()
        assert isinstance(config.governance, GovernanceConfig)
        assert config.governance.bulk_ingest_threshold == 5


class TestGovernanceConfigCustom:
    """Test GovernanceConfig with custom stability check definitions."""

    def test_custom_stability_check(self) -> None:
        check = StabilityCheckDef(
            id="pytest-check",
            command=["python", "-m", "pytest", "tests/"],
            timeout_seconds=300,
            description="Run full test suite",
        )
        config = GovernanceConfig(
            bulk_ingest_threshold=10,
            stability_checks=[check],
        )
        assert config.bulk_ingest_threshold == 10
        assert len(config.stability_checks) == 1
        assert config.stability_checks[0].id == "pytest-check"
        assert config.stability_checks[0].timeout_seconds == 300

    def test_stability_check_defaults(self) -> None:
        check = StabilityCheckDef(id="lint", command=["ruff", "check", "."])
        assert check.timeout_seconds == 120
        assert check.description == ""


class TestGovernanceConfigFromYaml:
    """Test GovernanceConfig loads from config.yaml."""

    def test_loads_from_yaml(self) -> None:
        config = load_config("data/config.yaml")
        assert isinstance(config.governance, GovernanceConfig)
        assert config.governance.bulk_ingest_threshold == 5
        assert config.governance.stability_checks == []


# ---------------------------------------------------------------------------
# Constraint schema tests
# ---------------------------------------------------------------------------


class TestConstraintSchemaSourceExcerpt:
    """Test constraint schema accepts source_excerpt field."""

    @pytest.fixture
    def schema(self) -> dict:
        with open("data/schemas/constraint.schema.json") as f:
            return json.load(f)

    def test_source_excerpt_in_schema(self, schema: dict) -> None:
        assert "source_excerpt" in schema["properties"]
        assert schema["properties"]["source_excerpt"]["type"] == "string"

    def test_constraint_with_source_excerpt_validates(self, schema: dict) -> None:
        constraint = {
            "constraint_id": "test-001",
            "text": "Never use eval()",
            "severity": "forbidden",
            "scope": {"paths": []},
            "source_excerpt": "The user said: never use eval() in production code",
        }
        # Should not raise
        jsonschema.validate(constraint, schema)

    def test_constraint_without_source_excerpt_validates(self, schema: dict) -> None:
        constraint = {
            "constraint_id": "test-002",
            "text": "Always run tests",
            "severity": "requires_approval",
            "scope": {"paths": ["tests/"]},
        }
        # source_excerpt is optional, should still validate
        jsonschema.validate(constraint, schema)

    def test_constraint_with_unknown_field_rejected(self, schema: dict) -> None:
        constraint = {
            "constraint_id": "test-003",
            "text": "Test constraint",
            "severity": "warning",
            "scope": {"paths": []},
            "totally_unknown_field": "should fail",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(constraint, schema)


# ---------------------------------------------------------------------------
# WisdomEntity metadata tests
# ---------------------------------------------------------------------------


class TestWisdomEntityMetadata:
    """Test WisdomEntity metadata field round-trips through WisdomStore."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> WisdomStore:
        return WisdomStore(tmp_path / "wisdom_meta.db")

    def test_metadata_round_trip(self, store: WisdomStore) -> None:
        entity = WisdomEntity.create(
            "dead_end",
            "Avoid regex for parsing",
            "Regex is insufficient for nested structures",
            metadata={"related_constraint_ids": ["c-abc123", "c-def456"]},
        )
        store.upsert(entity)
        retrieved = store.get(entity.wisdom_id)

        assert retrieved is not None
        assert retrieved.metadata == {"related_constraint_ids": ["c-abc123", "c-def456"]}

    def test_metadata_none_case(self, store: WisdomStore) -> None:
        entity = WisdomEntity.create(
            "breakthrough",
            "DuckDB is fast",
            "DuckDB handles analytical queries efficiently",
        )
        assert entity.metadata is None
        store.upsert(entity)
        retrieved = store.get(entity.wisdom_id)

        assert retrieved is not None
        assert retrieved.metadata is None

    def test_metadata_via_add_and_get(self, store: WisdomStore) -> None:
        entity = WisdomEntity.create(
            "scope_decision",
            "Use src/ prefix",
            "All source under src/",
            metadata={"governance_batch": "batch-001"},
        )
        store.add(entity)
        retrieved = store.get(entity.wisdom_id)

        assert retrieved is not None
        assert retrieved.metadata == {"governance_batch": "batch-001"}

    def test_metadata_update(self, store: WisdomStore) -> None:
        entity = WisdomEntity.create(
            "method_decision",
            "Use Pydantic v2",
            "Pydantic v2 for all models",
            metadata={"version": 1},
        )
        store.add(entity)

        updated = entity.model_copy(update={"metadata": {"version": 2, "reviewed": True}})
        store.update(updated)

        retrieved = store.get(entity.wisdom_id)
        assert retrieved is not None
        assert retrieved.metadata == {"version": 2, "reviewed": True}

    def test_metadata_in_list(self, store: WisdomStore) -> None:
        e1 = WisdomEntity.create(
            "breakthrough", "Insight A", "Desc A", metadata={"key": "val"}
        )
        e2 = WisdomEntity.create(
            "breakthrough", "Insight B", "Desc B",
        )
        store.upsert(e1)
        store.upsert(e2)

        entities = store.list(entity_type="breakthrough")
        assert len(entities) == 2
        meta_values = {e.wisdom_id: e.metadata for e in entities}
        assert meta_values[e1.wisdom_id] == {"key": "val"}
        assert meta_values[e2.wisdom_id] is None


# ---------------------------------------------------------------------------
# DuckDB schema tests
# ---------------------------------------------------------------------------


class TestDuckDBGovernanceSchema:
    """Test DuckDB schema extensions for governance."""

    @pytest.fixture
    def conn(self) -> duckdb.DuckDBPyConnection:
        c = get_connection(":memory:")
        create_schema(c)
        return c

    def test_stability_outcomes_table_exists(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'stability_outcomes'"
        ).fetchone()
        assert result is not None
        assert result[0] == "stability_outcomes"

    def test_stability_outcomes_columns(self, conn: duckdb.DuckDBPyConnection) -> None:
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'stability_outcomes' ORDER BY ordinal_position"
        ).fetchall()
        col_names = [c[0] for c in cols]
        expected = [
            "run_id", "check_id", "session_id", "status",
            "exit_code", "stdout", "stderr",
            "started_at", "ended_at", "actor_name", "actor_email",
        ]
        assert col_names == expected

    def test_stability_outcomes_status_check(self, conn: duckdb.DuckDBPyConnection) -> None:
        # Valid statuses should work
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO stability_outcomes (run_id, check_id, status, started_at) "
            "VALUES (?, ?, ?, ?)",
            ["run-1", "check-1", "pass", now],
        )
        # Invalid status should fail
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO stability_outcomes (run_id, check_id, status, started_at) "
                "VALUES (?, ?, ?, ?)",
                ["run-2", "check-1", "invalid_status", now],
            )

    def test_episodes_governance_columns(self, conn: duckdb.DuckDBPyConnection) -> None:
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'episodes' "
            "AND column_name IN ('requires_stability_check', 'stability_check_status')"
        ).fetchall()
        col_names = sorted([c[0] for c in cols])
        assert col_names == ["requires_stability_check", "stability_check_status"]

    def test_project_wisdom_metadata_column(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'project_wisdom' AND column_name = 'metadata'"
        ).fetchone()
        assert result is not None
        assert result[0] == "metadata"

    def test_schema_idempotent(self, conn: duckdb.DuckDBPyConnection) -> None:
        # Calling create_schema a second time should not raise
        create_schema(conn)
        # Verify tables still exist
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('stability_outcomes', 'episodes', 'project_wisdom') "
            "ORDER BY table_name"
        ).fetchall()
        assert len(tables) == 3
