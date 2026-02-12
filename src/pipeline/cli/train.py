"""CLI subcommands for training infrastructure.

Provides subcommands under `train`:
- embed: Generate embeddings for all episodes
- recommend: Get RAG recommendation for an episode (testing/debugging)
- shadow-run: Run shadow mode testing over historical episodes
- shadow-report: Generate shadow mode metrics report

Exports:
    train_group: Click group for training subcommands
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from loguru import logger

from src.pipeline.storage.schema import create_schema, get_connection


@click.group("train")
def train_group():
    """Training infrastructure commands."""
    pass


@train_group.command(name="embed")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def embed_cmd(db: str, verbose: bool) -> None:
    """Generate embeddings for all episodes."""
    _setup_logging(verbose)

    from src.pipeline.rag.embedder import EpisodeEmbedder

    conn = get_connection(db)
    create_schema(conn)

    embedder = EpisodeEmbedder()
    stats = embedder.embed_episodes(conn)

    conn.close()

    click.echo(f"Embedded {stats['embedded']} episodes ({stats['skipped']} skipped)")


@train_group.command(name="recommend")
@click.argument("episode_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--top-k", default=5, type=int, help="Number of similar episodes to retrieve.")
@click.option(
    "--constraints", default="data/constraints.json", help="Constraints file path."
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def recommend_cmd(
    episode_id: str, db: str, top_k: int, constraints: str, verbose: bool
) -> None:
    """Get RAG recommendation for an episode (for testing/debugging)."""
    _setup_logging(verbose)

    from src.pipeline.rag.embedder import EpisodeEmbedder
    from src.pipeline.rag.recommender import Recommender
    from src.pipeline.rag.retriever import HybridRetriever

    conn = get_connection(db)
    create_schema(conn)

    # Fetch episode
    row = conn.execute(
        "SELECT observation, orchestrator_action FROM episodes WHERE episode_id = ?",
        [episode_id],
    ).fetchone()

    if row is None:
        click.echo(f"Episode not found: {episode_id}", err=True)
        conn.close()
        sys.exit(1)

    obs_struct, action_json = row

    # Parse observation (STRUCT -> dict)
    obs_dict = obs_struct if isinstance(obs_struct, dict) else {}

    # Parse action JSON
    action_dict = None
    if action_json:
        if isinstance(action_json, str):
            try:
                action_dict = json.loads(action_json)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(action_json, dict):
            action_dict = action_json

    # Load constraints
    constraint_store = None
    constraints_path = Path(constraints)
    if constraints_path.exists():
        try:
            from src.pipeline.constraints.store import ConstraintStore

            constraint_store = ConstraintStore(constraints_path=constraints_path)
        except Exception as e:
            logger.warning("Could not load constraints: {}", e)

    # Build components
    embedder = EpisodeEmbedder()
    retriever = HybridRetriever(conn, top_k=top_k)
    recommender = Recommender(
        conn, embedder, retriever, constraint_store=constraint_store
    )

    # Generate recommendation (excluding this episode)
    rec = recommender.recommend(
        obs_dict, action_dict, exclude_episode_id=episode_id
    )

    conn.close()

    # Display recommendation
    click.echo(f"Recommendation for episode: {episode_id}")
    click.echo(f"  Mode:       {rec.recommended_mode}")
    click.echo(f"  Risk:       {rec.recommended_risk}")
    click.echo(f"  Confidence: {rec.confidence:.2f}")
    click.echo(f"  Dangerous:  {rec.is_dangerous}")
    if rec.danger_reasons:
        click.echo(f"  Dangers:    {', '.join(rec.danger_reasons)}")
    click.echo(f"  Scope:      {rec.recommended_scope_paths}")
    click.echo(f"  Gates:      {rec.recommended_gates}")
    click.echo(f"  Reasoning:  {rec.reasoning}")
    click.echo(f"  Sources:    {len(rec.source_episodes)} episodes")
    for src in rec.source_episodes:
        click.echo(
            f"    - {src.episode_id} (score={src.similarity_score:.3f}, "
            f"mode={src.mode}, reaction={src.reaction_label})"
        )


@train_group.command(name="shadow-run")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option(
    "--session", "session_id", default=None, help="Run for specific session only."
)
@click.option(
    "--constraints", default="data/constraints.json", help="Constraints file path."
)
@click.option("--top-k", default=5, type=int, help="Number of similar episodes to retrieve.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def shadow_run_cmd(
    db: str, session_id: str | None, constraints: str, top_k: int, verbose: bool
) -> None:
    """Run shadow mode testing over historical episodes."""
    _setup_logging(verbose)

    from src.pipeline.rag.embedder import EpisodeEmbedder
    from src.pipeline.rag.recommender import Recommender
    from src.pipeline.rag.retriever import HybridRetriever
    from src.pipeline.shadow.runner import ShadowModeRunner

    conn = get_connection(db)
    create_schema(conn)

    # Load constraints
    constraint_store = None
    constraints_path = Path(constraints)
    if constraints_path.exists():
        try:
            from src.pipeline.constraints.store import ConstraintStore

            constraint_store = ConstraintStore(constraints_path=constraints_path)
        except Exception as e:
            logger.warning("Could not load constraints: {}", e)

    # Build components
    embedder = EpisodeEmbedder()
    retriever = HybridRetriever(conn, top_k=top_k)
    recommender = Recommender(
        conn, embedder, retriever, constraint_store=constraint_store
    )
    runner = ShadowModeRunner(conn, embedder, recommender)

    if session_id:
        results = runner.run_session(session_id)
        click.echo(f"Shadow mode: {len(results)} episodes in session {session_id}")
        mode_agree = sum(1 for r in results if r["mode_agrees"])
        click.echo(
            f"  Mode agreement: {mode_agree}/{len(results)} "
            f"({mode_agree / max(len(results), 1):.1%})"
        )
    else:
        stats = runner.run_all()
        click.echo(f"Shadow mode complete: {stats['total']} episodes across {stats['sessions']} sessions")
        click.echo(
            f"  Mode agreements: {stats['mode_agreements']}/{stats['total']} "
            f"({stats['mode_agreements'] / max(stats['total'], 1):.1%})"
        )
        click.echo(f"  Dangerous: {stats['dangerous']}")
        click.echo(f"  Batch ID: {stats['batch_id']}")

    conn.close()


@train_group.command(name="shadow-report")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option(
    "--batch", "batch_id", default=None, help="Filter to specific batch."
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def shadow_report_cmd(db: str, batch_id: str | None, verbose: bool) -> None:
    """Generate shadow mode metrics report."""
    _setup_logging(verbose)

    from src.pipeline.shadow.reporter import ShadowReporter

    conn = get_connection(db)
    create_schema(conn)

    reporter = ShadowReporter(conn)
    report = reporter.compute_report(batch_id)
    click.echo(reporter.format_report(report))

    conn.close()


def _setup_logging(verbose: bool) -> None:
    """Configure logging level."""
    logger.remove()
    log_level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=log_level,
        format="{time:HH:mm:ss} | {level:<7} | {message}",
    )
