"""CLI entry point for the extraction pipeline.

Processes Claude Code JSONL session files through the full pipeline:
load -> normalize -> tag -> segment -> store in DuckDB.

Usage:
    python -m src.pipeline.cli.extract <path> [options]

    <path> can be a single .jsonl file or a directory of .jsonl files.

Examples:
    # Process a single session file
    python -m src.pipeline.cli.extract session.jsonl --db data/ope.db

    # Process all sessions in a directory
    python -m src.pipeline.cli.extract ~/.claude/projects/myproject/ -v

    # Process with git history for temporal alignment
    python -m src.pipeline.cli.extract session.jsonl --repo /path/to/repo

Exports:
    main: Click CLI entry point
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from loguru import logger

from src.pipeline.models.config import load_config
from src.pipeline.runner import PipelineRunner


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--db", default="data/ope.db", help="DuckDB output path (use :memory: for no persistence).")
@click.option("--config", "config_path", default="data/config.yaml", help="Config YAML path.")
@click.option("--repo", default=None, help="Git repo path for temporal alignment.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging (DEBUG level).")
@click.option("--plan", "plan_path", default=None, help="Path to PLAN.md file for EBC drift detection.")
@click.option("--inject-state", "inject_state_path", default=None,
              help="Path to STATE.md for drift alert injection.")
def main(
    input_path: str,
    db: str,
    config_path: str,
    repo: str | None,
    verbose: bool,
    plan_path: str | None,
    inject_state_path: str | None,
) -> None:
    """Process Claude Code JSONL sessions into tagged, segmented events in DuckDB.

    INPUT_PATH can be a single .jsonl file or a directory containing .jsonl files.

    Run with: python -m src.pipeline.cli.extract
    """
    # Configure logging
    logger.remove()  # Remove default handler
    log_level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=log_level, format="{time:HH:mm:ss} | {level:<7} | {message}")

    # Load config
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Error: Config file not found: {config_path}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    # Initialize runner
    runner = PipelineRunner(config, db_path=db)

    # Parse EBC from plan if provided
    ebc = None
    if plan_path:
        try:
            from src.pipeline.ebc.parser import parse_ebc_from_plan

            ebc = parse_ebc_from_plan(plan_path)
            if ebc is not None:
                runner.set_ebc(ebc)
                click.echo(f"EBC loaded from: {plan_path} (phase={ebc.phase}, plan={ebc.plan})")
            else:
                click.echo(f"Warning: Could not parse EBC from {plan_path}", err=True)
        except ImportError:
            click.echo("Warning: EBC module not available, --plan flag ignored", err=True)
        except Exception as e:
            click.echo(f"Warning: EBC parsing failed: {e}", err=True)

    try:
        input_p = Path(input_path)

        if input_p.is_file() and input_p.suffix == ".jsonl":
            # Single file mode
            click.echo(f"Processing single session: {input_p.name}")
            result = runner.run_session(input_p, repo_path=repo)
            _print_session_summary(result)
            has_errors = bool(result.get("errors"))

            # Inject drift alert into STATE.md if requested and drift detected
            if inject_state_path and result.get("ebc_drift_detected"):
                try:
                    from src.pipeline.ebc.state_injector import inject_alert_into_state

                    alert_filename = f"{result['session_id']}-ebc-drift.json"
                    alert_block = _format_state_alert_block(result, ebc, alert_filename)
                    injected = inject_alert_into_state(
                        Path(inject_state_path), alert_block
                    )
                    if injected:
                        click.echo(f"Drift alert injected into {inject_state_path}")
                except ImportError:
                    pass
                except Exception as e:
                    click.echo(f"Warning: STATE.md injection failed: {e}", err=True)
        elif input_p.is_dir():
            # Batch mode
            click.echo(f"Batch processing directory: {input_p}")
            batch_result = runner.run_batch(input_p, repo_path=repo)
            _print_batch_summary(batch_result)
            has_errors = bool(batch_result.get("errors"))
        else:
            click.echo(f"Error: {input_path} is not a .jsonl file or directory", err=True)
            sys.exit(1)

    finally:
        runner.close()

    sys.exit(1 if has_errors else 0)


def _format_state_alert_block(result: dict, ebc: object | None, alert_filename: str) -> str:
    """Format a drift alert block for STATE.md injection."""
    lines = [f"> **WARNING:** Session `{result['session_id']}` drifted from EBC"]
    if ebc is not None:
        lines.append(f"> - Phase: {ebc.phase}, Plan: {ebc.plan}")  # type: ignore[attr-defined]
    lines.extend([
        f"> - Alert artifact: `data/alerts/{alert_filename}`",
        "> - Recovery: Run `/project:autonomous-loop-mode-switch` for options",
    ])
    return "\n".join(lines)


def _print_session_summary(result: dict) -> None:
    """Print a summary table for a single session result."""
    click.echo("\n--- Session Summary ---")
    click.echo(f"  Session ID:  {result['session_id']}")
    click.echo(f"  Events:      {result['event_count']}")
    click.echo(f"  Episodes:    {result['episode_count']}")
    click.echo(f"  Orphans:     {result.get('orphan_count', 0)}")
    click.echo(f"  Duplicates:  {result.get('duplicate_count', 0)}")
    click.echo(f"  Invalid:     {result.get('invalid_count', 0)}")
    click.echo(f"  Duration:    {result.get('duration_seconds', 0):.2f}s")

    # Episode stats (Phase 2)
    ep_populated = result.get("episode_populated_count", 0)
    ep_valid = result.get("episode_valid_count", 0)
    ep_invalid = result.get("episode_invalid_count", 0)
    if ep_populated > 0 or ep_valid > 0 or ep_invalid > 0:
        click.echo(f"\n  Episode Stats:")
        click.echo(f"    Populated: {ep_populated}")
        click.echo(f"    Valid:     {ep_valid}")
        click.echo(f"    Invalid:   {ep_invalid}")

    if result.get("tag_distribution"):
        click.echo("\n  Tag Distribution:")
        for tag, count in sorted(result["tag_distribution"].items(), key=lambda x: -x[1]):
            click.echo(f"    {tag:16s} {count:>5d}")

    if result.get("outcome_distribution"):
        click.echo("\n  Outcome Distribution:")
        for outcome, count in sorted(result["outcome_distribution"].items(), key=lambda x: -x[1]):
            click.echo(f"    {outcome:20s} {count:>5d}")

    if result.get("reaction_distribution"):
        click.echo("\n  Reaction Label Distribution:")
        for label, count in sorted(result["reaction_distribution"].items(), key=lambda x: -x[1]):
            click.echo(f"    {label:16s} {count:>5d}")

    # Constraint stats (Phase 3)
    c_extracted = result.get("constraints_extracted", 0)
    c_dup = result.get("constraints_duplicate", 0)
    c_total = result.get("constraints_total", 0)
    if c_extracted > 0 or c_dup > 0:
        click.echo(f"\n  Constraints: {c_extracted} extracted, {c_dup} duplicate, {c_total} total in store")

    if result.get("errors"):
        click.echo("\n  Errors:")
        for err in result["errors"]:
            click.echo(f"    - {err}")

    if result.get("warnings"):
        click.echo("\n  Warnings:")
        for warn in result["warnings"]:
            click.echo(f"    - {warn}")

    click.echo()


def _print_batch_summary(result: dict) -> None:
    """Print a summary table for batch processing results."""
    click.echo("\n=== Batch Processing Summary ===")
    click.echo(f"  Sessions processed: {result['sessions_processed']}")
    click.echo(f"  Total events:       {result['total_events']}")
    click.echo(f"  Total episodes:     {result['total_episodes']}")

    # Episode stats (Phase 2)
    total_valid = result.get("total_valid_episodes", 0)
    total_invalid = result.get("total_invalid_episodes", 0)
    if total_valid > 0 or total_invalid > 0:
        click.echo(f"  Valid episodes:     {total_valid}")
        click.echo(f"  Invalid episodes:   {total_invalid}")

    if result.get("tag_distribution"):
        click.echo("\n  Aggregate Tag Distribution:")
        for tag, count in sorted(result["tag_distribution"].items(), key=lambda x: -x[1]):
            click.echo(f"    {tag:16s} {count:>5d}")

    if result.get("outcome_distribution"):
        click.echo("\n  Aggregate Outcome Distribution:")
        for outcome, count in sorted(result["outcome_distribution"].items(), key=lambda x: -x[1]):
            click.echo(f"    {outcome:20s} {count:>5d}")

    if result.get("reaction_distribution"):
        click.echo("\n  Aggregate Reaction Label Distribution:")
        for label, count in sorted(result["reaction_distribution"].items(), key=lambda x: -x[1]):
            click.echo(f"    {label:16s} {count:>5d}")

    # Constraint stats (Phase 3)
    c_extracted = result.get("constraints_extracted", 0)
    c_dup = result.get("constraints_duplicate", 0)
    c_total = result.get("constraints_total", 0)
    if c_extracted > 0 or c_dup > 0:
        click.echo(f"\n  Constraints: {c_extracted} extracted, {c_dup} duplicate, {c_total} total in store")

    if result.get("errors"):
        click.echo(f"\n  Errors ({len(result['errors'])}):")
        for err in result["errors"]:
            click.echo(f"    - {err}")

    # Per-session summaries
    if result.get("results"):
        click.echo("\n  Per-Session Results:")
        for r in result["results"]:
            status = "OK" if not r.get("errors") else "ERROR"
            click.echo(
                f"    [{status:5s}] {r['session_id']}: "
                f"{r['event_count']} events, {r['episode_count']} episodes"
            )

    click.echo()


if __name__ == "__main__":
    main()
