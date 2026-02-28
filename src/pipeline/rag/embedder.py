"""Episode embedding generator for RAG retrieval.

Generates 384-dim embeddings from episode observation text using
sentence-transformers all-MiniLM-L6-v2. Stores embeddings in DuckDB
with HNSW cosine index for similarity search.

Uses RxPY observables with ThreadPoolScheduler for parallel embedding
computation (Phase 27 adoption). DuckDB writes remain sequential on the
subscriber thread for predictability.

Exports:
    observation_to_text: Convert structured observation to searchable text
    EpisodeEmbedder: Episode embedding generator with DuckDB storage
"""

from __future__ import annotations

import json

import duckdb
import reactivex as rx
from loguru import logger
from reactivex import operators as ops
from reactivex.scheduler import ThreadPoolScheduler

from src.pipeline.rx_operators import create_work_observable


def observation_to_text(
    observation: dict, orchestrator_action: dict | None = None
) -> str:
    """Convert structured observation to searchable text.

    Extracts and joins text from observation fields (context, repo_state,
    quality_state) and optional orchestrator_action (goal, executor_instruction).

    Handles missing/None sub-fields gracefully. Changed_files truncated to
    first 10 entries. Parts joined with ' | ' separator.

    Args:
        observation: Episode observation dict with nested fields.
        orchestrator_action: Optional orchestrator action dict.

    Returns:
        Searchable text string with parts joined by ' | '.
        Empty string if all parts are empty.
    """
    parts: list[str] = []

    # Context is the richest text field
    context = observation.get("context")
    if isinstance(context, dict):
        summary = context.get("recent_summary", "")
        if summary:
            parts.append(str(summary))

        questions = context.get("open_questions")
        if questions and isinstance(questions, (list, tuple)):
            joined = " ".join(str(q) for q in questions)
            if joined.strip():
                parts.append(joined)

        constraints = context.get("constraints_in_force")
        if constraints and isinstance(constraints, (list, tuple)):
            parts.append("Constraints: " + ", ".join(str(c) for c in constraints))

    # Repo state adds file context
    repo = observation.get("repo_state")
    if isinstance(repo, dict):
        files = repo.get("changed_files")
        if files and isinstance(files, (list, tuple)):
            truncated = [str(f) for f in files[:10]]
            parts.append("Files: " + ", ".join(truncated))

    # Quality state adds test/lint context
    quality = observation.get("quality_state")
    if isinstance(quality, dict):
        tests = quality.get("tests_status", "")
        lint = quality.get("lint_status", "")
        if tests:
            parts.append(f"Tests: {tests}")
        if lint:
            parts.append(f"Lint: {lint}")

    # Orchestrator action fields (goal and executor instruction)
    if orchestrator_action and isinstance(orchestrator_action, dict):
        goal = orchestrator_action.get("goal", "")
        if goal:
            parts.append(str(goal))
        instruction = orchestrator_action.get("executor_instruction", "")
        if instruction:
            parts.append(str(instruction))

    return " | ".join(parts)


class EpisodeEmbedder:
    """Generate and store embeddings for episodes.

    Uses sentence-transformers all-MiniLM-L6-v2 for 384-dim embeddings.
    Stores results in DuckDB episode_embeddings and episode_search_text tables.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._model_name = model_name
        self._dim = 384

    def embed_text(self, text: str) -> list[float]:
        """Generate a 384-dim embedding for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of 384 floats.
        """
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_episodes(self, conn: duckdb.DuckDBPyConnection) -> dict:
        """Embed all un-embedded episodes in the database.

        Reads episodes from the episodes table, extracts observation text,
        generates embeddings, and writes to episode_embeddings and
        episode_search_text tables. Skips already-embedded episodes.

        Uses RxPY observable pipeline with ThreadPoolScheduler for parallel
        embedding computation. DuckDB writes are sequential on the subscriber
        thread (on_next callbacks serialize after merge).

        Args:
            conn: DuckDB connection with schema already created.

        Returns:
            Stats dict with 'embedded' and 'skipped' counts.
        """
        # Find episodes not yet embedded
        rows = conn.execute("""
            SELECT e.episode_id,
                   e.observation,
                   e.orchestrator_action
            FROM episodes e
            LEFT JOIN episode_embeddings ee ON e.episode_id = ee.episode_id
            WHERE ee.episode_id IS NULL
        """).fetchall()

        # Count already-embedded
        total_episodes = conn.execute("SELECT count(*) FROM episodes").fetchone()[0]
        skipped = total_episodes - len(rows)

        if not rows:
            logger.info(
                "Embedded {} episodes ({} skipped, already embedded)",
                0,
                skipped,
            )
            return {"embedded": 0, "skipped": skipped}

        # --- RxPY observable pipeline ---
        scheduler = ThreadPoolScheduler(max_workers=4)
        embedded_ids: list[str] = []
        error_holder: list[Exception] = []

        def _process_row(row: tuple) -> dict:
            """Extract text and compute embedding for one episode row.

            Runs on ThreadPoolScheduler threads (CPU-bound model.encode).
            """
            episode_id = row[0]
            obs_struct = row[1]
            action_json = row[2]

            # Convert DuckDB STRUCT to dict for observation
            obs_dict = _struct_to_dict(obs_struct)

            # Parse orchestrator_action JSON
            action_dict = None
            if action_json:
                if isinstance(action_json, str):
                    try:
                        action_dict = json.loads(action_json)
                    except (json.JSONDecodeError, TypeError):
                        action_dict = None
                elif isinstance(action_json, dict):
                    action_dict = action_json

            # Extract search text
            search_text = observation_to_text(obs_dict, action_dict)

            # Generate embedding (CPU-bound -- runs on thread pool)
            embedding = self.embed_text(search_text)

            return {
                "episode_id": episode_id,
                "search_text": search_text,
                "embedding": embedding,
            }

        def _write_to_db(result: dict) -> None:
            """Write embedding result to DuckDB tables.

            Runs sequentially on subscriber thread (serialized by merge).
            """
            conn.execute(
                "INSERT INTO episode_search_text (episode_id, search_text) VALUES (?, ?)",
                [result["episode_id"], result["search_text"]],
            )
            conn.execute(
                "INSERT INTO episode_embeddings (episode_id, embedding, model_name) VALUES (?, ?::FLOAT[384], ?)",
                [result["episode_id"], result["embedding"], self._model_name],
            )
            embedded_ids.append(result["episode_id"])

        rx.from_iterable(rows).pipe(
            ops.map(
                lambda row: create_work_observable(_process_row, row).pipe(
                    ops.subscribe_on(scheduler),
                )
            ),
            ops.merge(max_concurrent=4),
            ops.do_action(on_next=_write_to_db),
        ).subscribe(
            on_next=lambda _: None,
            on_error=lambda e: error_holder.append(e),
            on_completed=lambda: None,
        )

        # Cleanup thread pool
        scheduler.executor.shutdown(wait=True)

        if error_holder:
            raise error_holder[0]

        embedded = len(embedded_ids)

        if embedded > 0:
            self.rebuild_fts_index(conn)

        logger.info(
            "Embedded {} episodes ({} skipped, already embedded)",
            embedded,
            skipped,
        )

        return {"embedded": embedded, "skipped": skipped}

    @staticmethod
    def rebuild_fts_index(conn: duckdb.DuckDBPyConnection) -> None:
        """Rebuild the FTS index on episode_search_text.

        Must be called after batch insertion for BM25 search to work.
        Uses overwrite=1 to replace any existing index.

        Args:
            conn: DuckDB connection.
        """
        conn.execute("INSTALL fts; LOAD fts;")
        conn.execute("""
            PRAGMA create_fts_index(
                'episode_search_text',
                'episode_id',
                'search_text',
                stemmer = 'porter',
                stopwords = 'english',
                lower = 1,
                overwrite = 1
            )
        """)


def _struct_to_dict(struct_val: object) -> dict:
    """Convert a DuckDB STRUCT value to a Python dict.

    DuckDB returns STRUCT columns as dicts in newer versions, but may
    return named tuples or other types. This handles all cases.

    Args:
        struct_val: DuckDB STRUCT value (dict, tuple, or other).

    Returns:
        Python dict representation.
    """
    if struct_val is None:
        return {}
    if isinstance(struct_val, dict):
        # Recursively convert nested structs
        return {k: _struct_to_dict(v) if isinstance(v, dict) else v for k, v in struct_val.items()}
    # Fallback: try to convert to dict
    try:
        return dict(struct_val)
    except (TypeError, ValueError):
        return {}
