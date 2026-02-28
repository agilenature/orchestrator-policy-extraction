"""Tests for episode embedding generation and DuckDB schema extensions.

Tests observation_to_text() extraction, EpisodeEmbedder embedding generation,
DuckDB episode_embeddings and episode_search_text tables, and FTS indexing.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from src.pipeline.rag.embedder import EpisodeEmbedder, observation_to_text
from src.pipeline.storage.schema import create_schema, drop_schema, get_connection
from src.pipeline.storage.writer import write_episodes


# --- Fixture helpers ---


def _make_episode(
    episode_id: str = "ep-001",
    session_id: str = "sess-abc",
    segment_id: str = "seg-001",
    mode: str = "Implement",
    risk: str = "medium",
    reaction_label: str | None = "approve",
    reaction_confidence: float | None = 0.85,
    outcome_type: str = "success",
    tests_status: str = "pass",
    lint_status: str = "pass",
    changed_files: list[str] | None = None,
    config_hash: str = "abc12345",
    recent_summary: str = "Working on feature X",
    open_questions: list[str] | None = None,
    constraints_in_force: list[str] | None = None,
    goal: str = "Implement feature X",
    executor_instruction: str = "Implement the feature",
) -> dict:
    """Create a valid episode dict matching the populator output format."""
    if changed_files is None:
        changed_files = ["src/main.py", "tests/test_main.py"]
    if open_questions is None:
        open_questions = ["How to handle edge case?"]
    if constraints_in_force is None:
        constraints_in_force = ["no-force-push"]

    reaction = None
    if reaction_label is not None:
        reaction = {
            "label": reaction_label,
            "message": "looks good",
            "confidence": reaction_confidence,
        }

    outcome: dict = {
        "executor_effects": {
            "tool_calls_count": 3,
            "files_touched": ["src/main.py"],
            "commands_ran": ["pytest tests/"],
            "git_events": [],
        },
        "quality": {
            "tests_status": tests_status,
            "lint_status": lint_status,
            "diff_stat": {"files": 2, "insertions": 10, "deletions": 3},
        },
        "reward_signals": {
            "objective": {"tests": 1.0, "lint": 1.0, "diff_risk": 0.2},
        },
    }
    if reaction is not None:
        outcome["reaction"] = reaction

    return {
        "episode_id": episode_id,
        "session_id": session_id,
        "segment_id": segment_id,
        "timestamp": "2026-02-11T12:00:00+00:00",
        "outcome_type": outcome_type,
        "observation": {
            "repo_state": {
                "changed_files": changed_files,
                "diff_stat": {"files": len(changed_files), "insertions": 5, "deletions": 2},
            },
            "quality_state": {
                "tests": {"status": tests_status},
                "lint": {"status": lint_status},
            },
            "context": {
                "recent_summary": recent_summary,
                "open_questions": open_questions,
                "constraints_in_force": constraints_in_force,
            },
        },
        "orchestrator_action": {
            "mode": mode,
            "goal": goal,
            "scope": {"paths": ["src/main.py"]},
            "executor_instruction": executor_instruction,
            "gates": [],
            "risk": risk,
        },
        "outcome": outcome,
        "provenance": {
            "sources": [
                {"type": "claude_jsonl", "ref": "session.jsonl:line-42"},
            ],
        },
        "config_hash": config_hash,
        "project": {"repo_path": "test-project"},
    }


@pytest.fixture
def db_conn():
    """Create in-memory DuckDB with schema."""
    conn = get_connection(":memory:")
    create_schema(conn)
    yield conn
    conn.close()


# --- observation_to_text tests ---


class TestObservationToText:
    """Tests for observation_to_text() extraction."""

    def test_full_observation_all_fields(self):
        """Full observation with all fields produces concatenated string."""
        obs = {
            "context": {
                "recent_summary": "Implementing auth module",
                "open_questions": ["How to handle tokens?", "Session expiry?"],
                "constraints_in_force": ["no-force-push", "protected-main"],
            },
            "repo_state": {
                "changed_files": ["src/auth.py", "tests/test_auth.py"],
                "diff_stat": {"files": 2, "insertions": 50, "deletions": 10},
            },
            "quality_state": {
                "tests_status": "pass",
                "lint_status": "pass",
            },
        }
        result = observation_to_text(obs)
        assert "Implementing auth module" in result
        assert "How to handle tokens?" in result
        assert "Session expiry?" in result
        assert "Constraints:" in result
        assert "no-force-push" in result
        assert "protected-main" in result
        assert "Files:" in result
        assert "src/auth.py" in result
        assert "Tests: pass" in result
        assert "Lint: pass" in result
        # Parts should be joined by " | "
        assert " | " in result

    def test_only_recent_summary(self):
        """Observation with only context.recent_summary produces that text."""
        obs = {
            "context": {
                "recent_summary": "Just the summary",
            },
        }
        result = observation_to_text(obs)
        assert result == "Just the summary"

    def test_missing_context_fallback_to_repo_quality(self):
        """Observation with empty/missing context falls back to repo_state and quality_state."""
        obs = {
            "repo_state": {
                "changed_files": ["fix.py"],
            },
            "quality_state": {
                "tests_status": "fail",
                "lint_status": "pass",
            },
        }
        result = observation_to_text(obs)
        assert "Files: fix.py" in result
        assert "Tests: fail" in result
        assert "Lint: pass" in result

    def test_orchestrator_action_goal_and_instruction(self):
        """Orchestrator action fields are included in output."""
        obs = {"context": {"recent_summary": "Summary text"}}
        action = {
            "goal": "Implement user login",
            "executor_instruction": "Use JWT tokens for auth",
        }
        result = observation_to_text(obs, orchestrator_action=action)
        assert "Implement user login" in result
        assert "Use JWT tokens for auth" in result
        assert "Summary text" in result

    def test_empty_observation_produces_empty_string(self):
        """Empty observation dict produces empty string."""
        result = observation_to_text({})
        assert result == ""

    def test_none_subfields_no_error(self):
        """None/missing sub-fields handled gracefully (no KeyError)."""
        obs = {
            "context": None,
            "repo_state": None,
            "quality_state": None,
        }
        result = observation_to_text(obs)
        assert isinstance(result, str)

    def test_changed_files_truncated_to_10(self):
        """Changed_files list is truncated to first 10 entries."""
        files = [f"file_{i}.py" for i in range(20)]
        obs = {
            "repo_state": {
                "changed_files": files,
            },
        }
        result = observation_to_text(obs)
        # Should only have first 10 files
        assert "file_0.py" in result
        assert "file_9.py" in result
        assert "file_10.py" not in result

    def test_parts_joined_with_separator(self):
        """All parts are joined with ' | ' separator."""
        obs = {
            "context": {"recent_summary": "Summary"},
            "repo_state": {"changed_files": ["a.py"]},
            "quality_state": {"tests_status": "pass"},
        }
        result = observation_to_text(obs)
        parts = result.split(" | ")
        assert len(parts) >= 3
        assert parts[0] == "Summary"


# --- EpisodeEmbedder tests ---


class TestEpisodeEmbedder:
    """Tests for EpisodeEmbedder embedding generation and storage."""

    def test_embed_text_returns_384_floats(self):
        """embed_text(str) returns a list of floats with length 384."""
        embedder = EpisodeEmbedder()
        result = embedder.embed_text("test input text")
        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)

    def test_embed_text_empty_string(self):
        """embed_text('') returns a list of floats with length 384."""
        embedder = EpisodeEmbedder()
        result = embedder.embed_text("")
        assert isinstance(result, list)
        assert len(result) == 384

    def test_embed_episodes_populates_embeddings_table(self, db_conn):
        """embed_episodes(conn) populates episode_embeddings table."""
        # Insert test episodes
        ep1 = _make_episode(episode_id="ep-001", recent_summary="Auth module")
        ep2 = _make_episode(episode_id="ep-002", recent_summary="Database layer")
        write_episodes(db_conn, [ep1, ep2])

        embedder = EpisodeEmbedder()
        stats = embedder.embed_episodes(db_conn)

        assert stats["embedded"] == 2

        # Verify embeddings table
        rows = db_conn.execute(
            "SELECT episode_id, embedding, model_name FROM episode_embeddings ORDER BY episode_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "ep-001"
        assert len(rows[0][1]) == 384
        assert rows[0][2] == "all-MiniLM-L6-v2"

    def test_embed_episodes_populates_search_text_table(self, db_conn):
        """embed_episodes(conn) populates episode_search_text table."""
        ep = _make_episode(episode_id="ep-001", recent_summary="Working on auth")
        write_episodes(db_conn, [ep])

        embedder = EpisodeEmbedder()
        embedder.embed_episodes(db_conn)

        rows = db_conn.execute(
            "SELECT episode_id, search_text FROM episode_search_text"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "ep-001"
        assert "Working on auth" in rows[0][1]

    def test_embed_episodes_idempotent(self, db_conn):
        """embed_episodes skips episodes that already have embeddings."""
        ep = _make_episode(episode_id="ep-001")
        write_episodes(db_conn, [ep])

        embedder = EpisodeEmbedder()
        stats1 = embedder.embed_episodes(db_conn)
        assert stats1["embedded"] == 1
        assert stats1["skipped"] == 0

        # Run again -- should skip
        stats2 = embedder.embed_episodes(db_conn)
        assert stats2["embedded"] == 0
        assert stats2["skipped"] == 1

        # Still only 1 row
        count = db_conn.execute("SELECT count(*) FROM episode_embeddings").fetchone()[0]
        assert count == 1

    def test_embed_episodes_rx_behavioral_parity(self, db_conn):
        """RxPY adoption produces identical DuckDB state and return values.

        Validates the full contract: return dict values, row counts in both
        tables, episode_id presence, and idempotency (second call skips all).
        """
        # Insert N=3 test episodes with distinct content
        episodes = [
            _make_episode(
                episode_id=f"ep-parity-{i:03d}",
                recent_summary=f"Parity test episode {i}",
                goal=f"Goal for episode {i}",
            )
            for i in range(3)
        ]
        write_episodes(db_conn, episodes)

        embedder = EpisodeEmbedder()

        # First call: embed all 3
        stats = embedder.embed_episodes(db_conn)
        assert stats == {"embedded": 3, "skipped": 0}

        # Verify episode_embeddings has exactly 3 rows
        emb_rows = db_conn.execute(
            "SELECT episode_id FROM episode_embeddings ORDER BY episode_id"
        ).fetchall()
        assert len(emb_rows) == 3

        # Verify episode_search_text has exactly 3 rows
        txt_rows = db_conn.execute(
            "SELECT episode_id FROM episode_search_text ORDER BY episode_id"
        ).fetchall()
        assert len(txt_rows) == 3

        # All 3 episode_ids present in both tables
        expected_ids = {f"ep-parity-{i:03d}" for i in range(3)}
        assert {r[0] for r in emb_rows} == expected_ids
        assert {r[0] for r in txt_rows} == expected_ids

        # Idempotency: second call skips all
        stats2 = embedder.embed_episodes(db_conn)
        assert stats2 == {"embedded": 0, "skipped": 3}

        # Row counts unchanged after second call
        emb_count = db_conn.execute(
            "SELECT count(*) FROM episode_embeddings"
        ).fetchone()[0]
        txt_count = db_conn.execute(
            "SELECT count(*) FROM episode_search_text"
        ).fetchone()[0]
        assert emb_count == 3
        assert txt_count == 3

    def test_rebuild_fts_index(self, db_conn):
        """rebuild_fts_index(conn) creates FTS index on episode_search_text."""
        # Insert search text directly
        db_conn.execute(
            "INSERT INTO episode_search_text VALUES ('ep-001', 'implementing auth module with JWT tokens')"
        )

        EpisodeEmbedder.rebuild_fts_index(db_conn)

        # Verify FTS search works
        rows = db_conn.execute("""
            SELECT episode_id, score
            FROM (
                SELECT *, fts_main_episode_search_text.match_bm25(
                    episode_id, 'auth JWT'
                ) AS score
                FROM episode_search_text
            )
            WHERE score IS NOT NULL
        """).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "ep-001"


# --- DuckDB schema extension tests ---


class TestSchemaExtensions:
    """Tests for episode_embeddings and episode_search_text schema extensions."""

    def test_episode_embeddings_table_created(self, db_conn):
        """create_schema creates episode_embeddings table with correct columns."""
        # Check table exists with correct columns
        cols = db_conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'episode_embeddings'
            ORDER BY ordinal_position
        """).fetchall()
        col_names = [c[0] for c in cols]
        assert "episode_id" in col_names
        assert "embedding" in col_names
        assert "model_name" in col_names
        assert "created_at" in col_names

    def test_episode_search_text_table_created(self, db_conn):
        """create_schema creates episode_search_text table with correct columns."""
        cols = db_conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'episode_search_text'
            ORDER BY ordinal_position
        """).fetchall()
        col_names = [c[0] for c in cols]
        assert "episode_id" in col_names
        assert "search_text" in col_names

    def test_new_tables_alongside_existing(self, db_conn):
        """New tables are created alongside existing events, episode_segments, episodes tables."""
        tables = db_conn.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
        """).fetchall()
        table_names = [t[0] for t in tables]
        # Existing tables
        assert "events" in table_names
        assert "episode_segments" in table_names
        assert "episodes" in table_names
        # New tables
        assert "episode_embeddings" in table_names
        assert "episode_search_text" in table_names

    def test_drop_schema_drops_new_tables(self):
        """drop_schema drops new tables too."""
        conn = get_connection(":memory:")
        create_schema(conn)

        # Verify tables exist
        count = conn.execute("""
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_name IN ('episode_embeddings', 'episode_search_text')
        """).fetchone()[0]
        assert count == 2

        drop_schema(conn)

        # Verify tables are gone
        count = conn.execute("""
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_name IN ('episode_embeddings', 'episode_search_text')
        """).fetchone()[0]
        assert count == 0

        conn.close()
