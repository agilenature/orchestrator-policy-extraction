"""CLI subcommands for auditing constraint compliance and durability.

Provides subcommands under `audit`:
- session: Audit session constraint compliance, detect amnesia events
- durability: Show durability scores per constraint

Exports:
    audit_group: Click group for audit subcommands
"""

from __future__ import annotations

import json
import sys

import click
from loguru import logger

from src.pipeline.storage.schema import create_schema, get_connection


@click.group("audit")
def audit_group():
    """Audit session constraint compliance and durability metrics."""
    pass


@audit_group.command(name="session")
@click.option(
    "--session-id", default=None, help="Specific session ID to audit (default: all sessions)."
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option(
    "--constraints", default="data/constraints.json", help="Constraints file path."
)
@click.option("--config", default="data/config.yaml", help="Pipeline config path.")
def audit_session(
    session_id: str | None,
    output_json: bool,
    db: str,
    constraints: str,
    config: str,
) -> None:
    """Audit session constraint compliance and detect amnesia events.

    Evaluates each active constraint against session events. Reports
    HONORED/VIOLATED per constraint with amnesia event details.

    Exit codes:
      0 - Clean (no amnesia events)
      1 - Runtime error
      2 - Amnesia events detected
    """
    _setup_logging()

    try:
        from pathlib import Path

        from src.pipeline.constraint_store import ConstraintStore
        from src.pipeline.durability.amnesia import AmnesiaDetector
        from src.pipeline.durability.evaluator import SessionConstraintEvaluator
        from src.pipeline.durability.scope_extractor import extract_session_scope
        from src.pipeline.models.config import load_config
        from src.pipeline.storage.writer import (
            read_events,
            write_amnesia_events,
            write_constraint_evals,
        )

        # Load config
        pipeline_config = load_config(config)

        # Connect to DB
        conn = get_connection(db)
        create_schema(conn)

        # Load constraints
        constraints_path = Path(constraints)
        schema_path = Path("data/schemas/constraint.schema.json")
        store = ConstraintStore(path=constraints_path, schema_path=schema_path)

        if not store.constraints:
            click.echo("No constraints found. Nothing to audit.")
            conn.close()
            sys.exit(0)

        # Determine sessions to audit
        if session_id:
            session_ids = [session_id]
        else:
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM events ORDER BY session_id"
            ).fetchall()
            session_ids = [r[0] for r in rows]

        if not session_ids:
            click.echo("No sessions found in database.")
            conn.close()
            sys.exit(0)

        total_amnesia = 0
        all_results: list[dict] = []

        for sid in session_ids:
            # Get session events
            events = read_events(conn, session_id=sid)
            if not events:
                continue

            # Derive session scope
            session_scope_paths = extract_session_scope(events)

            # Get session start time
            session_start_time = str(events[0]["ts_utc"]) if events else None
            if not session_start_time:
                continue

            # Build escalation violations map
            escalation_violations: dict[str, str] = {}
            try:
                esc_rows = conn.execute(
                    "SELECT escalate_bypassed_constraint_id FROM episodes "
                    "WHERE session_id = ? AND mode = 'ESCALATE' "
                    "AND escalate_bypassed_constraint_id IS NOT NULL",
                    [sid],
                ).fetchall()
                for (cid,) in esc_rows:
                    escalation_violations[cid] = sid
            except Exception:
                pass

            # Evaluate constraints
            evaluator = SessionConstraintEvaluator(pipeline_config)
            eval_results = evaluator.evaluate(
                session_id=sid,
                session_scope_paths=session_scope_paths,
                session_start_time=session_start_time,
                events=events,
                constraints=store.constraints,
                escalation_violations=escalation_violations,
            )

            if eval_results:
                write_constraint_evals(conn, eval_results)

            # Detect amnesia events
            detector = AmnesiaDetector()
            amnesia_events = detector.detect(eval_results, store.constraints)
            if amnesia_events:
                write_amnesia_events(conn, amnesia_events)

            honored = sum(1 for r in eval_results if r.eval_state == "HONORED")
            violated = sum(1 for r in eval_results if r.eval_state == "VIOLATED")
            total_amnesia += len(amnesia_events)

            session_result = {
                "session_id": sid,
                "constraints_evaluated": len(eval_results),
                "honored": honored,
                "violated": violated,
                "amnesia_events": [
                    {
                        "amnesia_id": ae.amnesia_id,
                        "constraint_id": ae.constraint_id,
                        "constraint_type": ae.constraint_type,
                        "severity": ae.severity,
                        "evidence": ae.evidence,
                    }
                    for ae in amnesia_events
                ],
            }
            all_results.append(session_result)

            if not output_json:
                click.echo(f"\nSession: {sid}")
                click.echo(f"  Constraints evaluated: {len(eval_results)}")
                click.echo(f"  HONORED: {honored}")
                click.echo(f"  VIOLATED: {violated}")
                if amnesia_events:
                    click.echo(f"  Amnesia events: {len(amnesia_events)}")
                    for ae in amnesia_events:
                        click.echo(f"    - {ae.constraint_id} ({ae.severity})")
                        if ae.evidence:
                            for ev in ae.evidence[:2]:
                                click.echo(
                                    f"      Pattern: {ev.get('matched_pattern', 'N/A')}"
                                )

        conn.close()

        if output_json:
            click.echo(json.dumps(all_results, indent=2))
        else:
            click.echo(f"\nTotal amnesia events: {total_amnesia}")

        if total_amnesia > 0:
            sys.exit(2)
        sys.exit(0)

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@audit_group.command(name="durability")
@click.option(
    "--constraint-id", default=None, help="Specific constraint ID."
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def audit_durability(
    constraint_id: str | None,
    output_json: bool,
    db: str,
) -> None:
    """Show durability scores per constraint.

    Computes durability_score = sessions_honored / sessions_active for
    each constraint. Requires at least 3 sessions for a meaningful score.
    """
    _setup_logging()

    try:
        from src.pipeline.durability.index import DurabilityIndex

        conn = get_connection(db)
        create_schema(conn)

        index = DurabilityIndex(conn)

        if constraint_id:
            scores = [index.compute_score(constraint_id)]
        else:
            scores = index.compute_all_scores()

        conn.close()

        if output_json:
            click.echo(json.dumps(scores, indent=2))
        else:
            if not scores:
                click.echo("No constraint evaluations found.")
                return

            # Table header
            click.echo(
                f"{'constraint_id':<20} {'sessions':<10} {'honored':<10} "
                f"{'violated':<10} {'durability_score':<20}"
            )
            click.echo("-" * 70)

            for s in scores:
                cid = s["constraint_id"][:18] if len(s["constraint_id"]) > 18 else s["constraint_id"]
                if s["insufficient_data"]:
                    score_str = "null (need >= 3 sessions)"
                else:
                    score_str = f"{s['durability_score']:.4f}"
                click.echo(
                    f"{cid:<20} {s['sessions_active']:<10} "
                    f"{s['sessions_honored']:<10} {s['sessions_violated']:<10} "
                    f"{score_str:<20}"
                )

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING", format="{time:HH:mm:ss} | {level:<7} | {message}")
