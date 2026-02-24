"""CLI commands for assessment scenario management (Phase 17).

Provides subcommands under `assess`:
- annotate-scenarios: Interactively annotate project_wisdom entries with DDF target levels
- list-scenarios: Display scenario inventory with annotation status
- run: Full assessment lifecycle (setup -> launch -> observe -> score -> cleanup)
- calibrate: Compute scenario baseline TE via calibration run

The assess group is registered under intelligence_group in intelligence.py,
accessible via: python -m src.pipeline.cli intelligence assess <command>

Exports:
    assess_group: Click group for assessment scenario commands
"""

from __future__ import annotations

import sys
import uuid

import click


@click.group("assess")
def assess_group():
    """Assessment scenario management commands."""
    pass


@assess_group.command(name="annotate-scenarios")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def annotate_scenarios(db: str) -> None:
    """Interactively annotate project_wisdom entries with DDF target levels.

    For each un-annotated wisdom entry, prompts for:
    - DDF target level (1-7)
    - Optional scenario seed text

    Usage:
        python -m src.pipeline.cli intelligence assess annotate-scenarios
        python -m src.pipeline.cli intelligence assess annotate-scenarios --db data/test.db
    """
    import duckdb

    from src.pipeline.assessment.schema import create_assessment_schema

    try:
        conn = duckdb.connect(db)
    except Exception as e:
        click.echo(f"Error connecting to database: {e}", err=True)
        sys.exit(1)

    # Ensure assessment columns exist on project_wisdom
    try:
        create_assessment_schema(conn)
    except Exception:
        pass  # Tables may already exist

    # Query un-annotated entries
    try:
        rows = conn.execute(
            "SELECT wisdom_id, entity_type, title, description "
            "FROM project_wisdom "
            "WHERE ddf_target_level IS NULL "
            "ORDER BY entity_type, title"
        ).fetchall()
    except Exception as e:
        click.echo(f"Error querying project_wisdom: {e}", err=True)
        conn.close()
        sys.exit(1)

    if not rows:
        click.echo("No un-annotated wisdom entries found.")
        conn.close()
        return

    total = len(rows)
    annotated = 0

    for idx, (wisdom_id, entity_type, title, description) in enumerate(rows, 1):
        desc_preview = (description[:200] + "...") if len(description) > 200 else description

        click.echo(f"\n[{idx}/{total}] {entity_type}: {title}")
        click.echo(f"  {desc_preview}")

        prompt_text = "DDF target level (1-7, or 's' to skip, 'q' to quit): "
        choice = click.prompt(prompt_text, default="s", show_default=False)
        choice = choice.strip().lower()

        if choice == "q":
            click.echo("Quit.")
            break

        if choice == "s":
            continue

        # Validate level
        try:
            level = int(choice)
            if not 1 <= level <= 7:
                click.echo(f"  Invalid level: {level}. Skipping.")
                continue
        except ValueError:
            click.echo(f"  Invalid input: {choice!r}. Skipping.")
            continue

        # Prompt for optional scenario seed
        seed_text = click.prompt(
            "Scenario seed text (optional, Enter to skip)",
            default="",
            show_default=False,
        )
        seed_value = seed_text.strip() if seed_text.strip() else None

        # Update project_wisdom
        try:
            conn.execute(
                "UPDATE project_wisdom "
                "SET ddf_target_level = ?, scenario_seed = ? "
                "WHERE wisdom_id = ?",
                [level, seed_value, wisdom_id],
            )
            annotated += 1
            click.echo(f"  Annotated: L{level}" + (f" (with seed)" if seed_value else ""))
        except Exception as e:
            click.echo(f"  Error updating: {e}", err=True)

    # Summary
    remaining = total - annotated
    click.echo(f"\n{annotated} entries annotated, {remaining} remaining.")
    conn.close()


@assess_group.command(name="list-scenarios")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--level", type=int, default=None, help="Filter by DDF target level.")
def list_scenarios(db: str, level: int | None) -> None:
    """Display scenario inventory with annotation status.

    Usage:
        python -m src.pipeline.cli intelligence assess list-scenarios
        python -m src.pipeline.cli intelligence assess list-scenarios --level 3
    """
    import duckdb

    try:
        conn = duckdb.connect(db, read_only=True)
    except Exception as e:
        click.echo(f"Error connecting to database: {e}", err=True)
        sys.exit(1)

    # Check if assessment columns exist; they may not if schema hasn't been applied
    try:
        rows = conn.execute(
            "SELECT wisdom_id, entity_type, title, ddf_target_level, "
            "scenario_seed IS NOT NULL AS has_seed "
            "FROM project_wisdom "
            "ORDER BY ddf_target_level NULLS LAST, entity_type, title"
        ).fetchall()
    except Exception as e:
        err_msg = str(e)
        if "ddf_target_level" in err_msg or "scenario_seed" in err_msg:
            click.echo(
                "Assessment columns not found on project_wisdom table. "
                "Run 'annotate-scenarios' first to apply the schema.",
                err=True,
            )
        else:
            click.echo(f"Error querying project_wisdom: {e}", err=True)
        conn.close()
        sys.exit(1)

    conn.close()

    # Apply level filter
    if level is not None:
        rows = [r for r in rows if r[3] == level]

    if not rows:
        click.echo("No scenarios found.")
        annotated_count = 0
        unannotated_count = 0
    else:
        # Display table header
        click.echo(
            f"{'ID':<18} {'TYPE':<16} {'LEVEL':<7} {'SEED':<6} {'TITLE'}"
        )
        click.echo("-" * 75)

        annotated_count = 0
        unannotated_count = 0

        for wisdom_id, entity_type, title, ddf_level, has_seed in rows:
            level_str = str(ddf_level) if ddf_level is not None else "-"
            seed_str = "yes" if has_seed else "no"
            title_display = (title[:40] + "...") if len(title) > 40 else title
            wid_display = (wisdom_id[:16] + "..") if len(wisdom_id) > 18 else wisdom_id

            click.echo(
                f"{wid_display:<18} {entity_type:<16} {level_str:<7} "
                f"{seed_str:<6} {title_display}"
            )

            if ddf_level is not None:
                annotated_count += 1
            else:
                unannotated_count += 1

    click.echo(f"\nTotal: {annotated_count} annotated, {unannotated_count} unannotated")


@assess_group.command(name="run")
@click.argument("scenario_id")
@click.argument("candidate_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--timeout", default=1800, type=int, help="Actor timeout in seconds.")
@click.option("--prompt", default=None, help="Custom assessment prompt.")
def run_assessment(
    scenario_id: str,
    candidate_id: str,
    db: str,
    timeout: int,
    prompt: str | None,
) -> None:
    """Run a full assessment session for SCENARIO_ID with CANDIDATE_ID.

    Full lifecycle: setup dir -> launch Actor -> run Observer ->
    compute TE -> write row -> detect rejections -> update baselines ->
    cleanup -> display summary.

    Usage:
        python -m src.pipeline.cli intelligence assess run <scenario_id> <candidate_id>
        python -m src.pipeline.cli intelligence assess run abc123 david --timeout 900
    """
    import duckdb

    from src.pipeline.assessment.observer import AssessmentObserver
    from src.pipeline.assessment.rejection_detector import RejectionDetector
    from src.pipeline.assessment.schema import create_assessment_schema
    from src.pipeline.assessment.scenario_generator import ScenarioGenerator
    from src.pipeline.assessment.session_runner import AssessmentSessionRunner
    from src.pipeline.assessment.te_assessment import (
        compute_assessment_te,
        update_assessment_baselines,
        write_assessment_te_row,
    )

    try:
        conn = duckdb.connect(db)
    except Exception as e:
        click.echo(f"Error connecting to database: {e}", err=True)
        sys.exit(1)

    # Ensure schema exists
    try:
        create_assessment_schema(conn)
    except Exception:
        pass

    session_id = str(uuid.uuid4())
    click.echo(f"Assessment session: {session_id}")
    click.echo(f"Scenario: {scenario_id}, Candidate: {candidate_id}")

    runner = AssessmentSessionRunner(conn, db_path=db)

    # Generate scenario spec
    try:
        gen = ScenarioGenerator(conn)
        # Look up wisdom_id from scenario metadata
        row = conn.execute(
            "SELECT wisdom_id, ddf_target_level FROM project_wisdom "
            "WHERE wisdom_id = ? OR wisdom_id IN ("
            "  SELECT wisdom_id FROM project_wisdom "
            "  WHERE ddf_target_level IS NOT NULL"
            ") LIMIT 1",
            [scenario_id],
        ).fetchone()

        if row is None:
            click.echo(f"Scenario not found: {scenario_id}", err=True)
            conn.close()
            sys.exit(1)

        wisdom_id = row[0]
        scenario_spec = gen.generate_scenario(wisdom_id)
    except Exception as e:
        click.echo(f"Error generating scenario: {e}", err=True)
        conn.close()
        sys.exit(1)

    # Setup assessment dir
    click.echo("Setting up assessment directory...")
    session = runner.setup_assessment_dir(scenario_spec, session_id)
    from src.pipeline.assessment.models import AssessmentSession

    session = AssessmentSession(
        session_id=session.session_id,
        scenario_id=scenario_spec.scenario_id,
        candidate_id=candidate_id,
        assessment_dir=session.assessment_dir,
        status=session.status,
        handicap_level=scenario_spec.ddf_target_level if scenario_spec.handicap_claude_md else None,
        started_at=session.started_at,
    )

    # Launch Actor
    click.echo("Launching Actor Claude Code...")
    session = runner.launch_actor(session, prompt=prompt, timeout=timeout)
    click.echo(f"Actor status: {session.status}")

    if session.status == "failed":
        click.echo("Actor failed. Cleaning up...", err=True)
        session = runner.cleanup_session(session)
        conn.close()
        sys.exit(1)

    # Run Observer
    click.echo("Running Observer pipeline...")
    try:
        observer = AssessmentObserver(db_path=db)
        stats = observer.run_observation(session)
        click.echo(f"Observer: {stats.get('event_count', 0)} events processed")
    except FileNotFoundError:
        click.echo("JSONL not found -- Actor may not have produced output.", err=True)
        session = runner.cleanup_session(session)
        conn.close()
        sys.exit(1)
    except Exception as e:
        click.echo(f"Observer error: {e}", err=True)

    # Compute assessment TE
    click.echo("Computing assessment TE...")
    te_result = compute_assessment_te(conn, session.session_id)
    candidate_te = te_result["candidate_te"] if te_result else None

    # Get scenario baseline
    baseline_row = conn.execute(
        "SELECT scenario_baseline_te FROM assessment_te_sessions "
        "WHERE scenario_id = ? AND candidate_id = 'calibration' "
        "ORDER BY assessment_date DESC LIMIT 1",
        [scenario_spec.scenario_id],
    ).fetchone()
    scenario_baseline_te = baseline_row[0] if baseline_row else None

    # Write assessment TE row
    if te_result:
        write_assessment_te_row(
            conn,
            session_id=session.session_id,
            scenario_id=scenario_spec.scenario_id,
            candidate_id=candidate_id,
            candidate_te=candidate_te,
            scenario_baseline_te=scenario_baseline_te,
            raven_depth=te_result["raven_depth"],
            crow_efficiency=te_result["crow_efficiency"],
            trunk_quality=te_result["trunk_quality"],
            fringe_drift_rate=None,
            scenario_ddf_level=scenario_spec.ddf_target_level,
        )

    # Detect rejections
    click.echo("Detecting rejections...")
    detector = RejectionDetector(conn)
    rejections = detector.detect_rejections(
        session.session_id,
        scenario_baseline_te or 0.0,
    )
    for rej in rejections:
        click.echo(
            f"  Rejection at prompt {rej['prompt_number']}: "
            f"{rej['rejection_type']} (TE={rej['candidate_te']})"
        )

    # Update baselines
    update_assessment_baselines(conn, scenario_spec.scenario_id)

    # Cleanup
    click.echo("Cleaning up...")
    session = runner.cleanup_session(session)

    # Summary
    click.echo("\n=== Assessment Summary ===")
    click.echo(f"Session:    {session.session_id}")
    click.echo(f"Candidate:  {candidate_id}")
    click.echo(f"Scenario:   {scenario_spec.title} (L{scenario_spec.ddf_target_level})")
    if te_result:
        click.echo(f"Raven Depth:     {te_result['raven_depth']:.4f}")
        click.echo(f"Crow Efficiency: {te_result['crow_efficiency']:.4f}")
        click.echo(f"Trunk Quality:   {te_result['trunk_quality']:.4f}")
        click.echo(f"Candidate TE:    {candidate_te:.4f}")
    else:
        click.echo("Candidate TE:    N/A (no flame events)")
    click.echo(f"Rejections:      {len(rejections)}")
    click.echo(f"Archive:         {session.session_artifact_path}")

    conn.close()


@assess_group.command(name="calibrate")
@click.argument("scenario_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--timeout", default=1800, type=int, help="Actor timeout in seconds.")
def calibrate_scenario(scenario_id: str, db: str, timeout: int) -> None:
    """Compute scenario baseline TE via calibration run.

    Runs a full assessment session with candidate_id='calibration' and
    no handicap. The resulting TE becomes the scenario_baseline_te
    used to normalize future candidate scores.

    Usage:
        python -m src.pipeline.cli intelligence assess calibrate <scenario_id>
        python -m src.pipeline.cli intelligence assess calibrate abc123 --timeout 900
    """
    import duckdb

    from src.pipeline.assessment.observer import AssessmentObserver
    from src.pipeline.assessment.schema import create_assessment_schema
    from src.pipeline.assessment.scenario_generator import ScenarioGenerator
    from src.pipeline.assessment.session_runner import AssessmentSessionRunner
    from src.pipeline.assessment.te_assessment import (
        compute_assessment_te,
        write_assessment_te_row,
    )

    try:
        conn = duckdb.connect(db)
    except Exception as e:
        click.echo(f"Error connecting to database: {e}", err=True)
        sys.exit(1)

    try:
        create_assessment_schema(conn)
    except Exception:
        pass

    session_id = str(uuid.uuid4())
    click.echo(f"Calibration session: {session_id}")
    click.echo(f"Scenario: {scenario_id}")

    runner = AssessmentSessionRunner(conn, db_path=db)

    # Generate scenario (no handicap for calibration)
    try:
        gen = ScenarioGenerator(conn)
        scenario_spec = gen.generate_scenario(scenario_id)
        # Override handicap for calibration: create non-handicap version
        from src.pipeline.assessment.models import ScenarioSpec

        calibration_spec = ScenarioSpec(
            scenario_id=scenario_spec.scenario_id,
            wisdom_id=scenario_spec.wisdom_id,
            ddf_target_level=scenario_spec.ddf_target_level,
            entity_type=scenario_spec.entity_type,
            title=scenario_spec.title,
            scenario_context=scenario_spec.scenario_context,
            broken_impl_filename=scenario_spec.broken_impl_filename,
            broken_impl_content=scenario_spec.broken_impl_content,
            handicap_claude_md=None,  # No handicap for calibration
            scenario_seed=scenario_spec.scenario_seed,
        )
    except Exception as e:
        click.echo(f"Error generating scenario: {e}", err=True)
        conn.close()
        sys.exit(1)

    # Setup and launch
    click.echo("Setting up calibration directory...")
    session = runner.setup_assessment_dir(calibration_spec, session_id)
    from src.pipeline.assessment.models import AssessmentSession

    session = AssessmentSession(
        session_id=session.session_id,
        scenario_id=calibration_spec.scenario_id,
        candidate_id="calibration",
        assessment_dir=session.assessment_dir,
        status=session.status,
        started_at=session.started_at,
    )

    click.echo("Launching Actor for calibration...")
    session = runner.launch_actor(session, timeout=timeout)
    click.echo(f"Actor status: {session.status}")

    if session.status == "failed":
        click.echo("Calibration Actor failed.", err=True)
        session = runner.cleanup_session(session)
        conn.close()
        sys.exit(1)

    # Run Observer
    click.echo("Running Observer pipeline...")
    try:
        observer = AssessmentObserver(db_path=db)
        stats = observer.run_observation(session)
        click.echo(f"Observer: {stats.get('event_count', 0)} events processed")
    except Exception as e:
        click.echo(f"Observer error: {e}", err=True)

    # Compute calibration TE
    click.echo("Computing baseline TE...")
    te_result = compute_assessment_te(conn, session.session_id)
    baseline_te = te_result["candidate_te"] if te_result else None

    if te_result:
        write_assessment_te_row(
            conn,
            session_id=session.session_id,
            scenario_id=calibration_spec.scenario_id,
            candidate_id="calibration",
            candidate_te=baseline_te,
            scenario_baseline_te=baseline_te,
            raven_depth=te_result["raven_depth"],
            crow_efficiency=te_result["crow_efficiency"],
            trunk_quality=te_result["trunk_quality"],
            fringe_drift_rate=None,
            scenario_ddf_level=calibration_spec.ddf_target_level,
        )

    # Cleanup
    session = runner.cleanup_session(session)

    # Summary
    click.echo("\n=== Calibration Summary ===")
    click.echo(f"Session:    {session.session_id}")
    click.echo(f"Scenario:   {calibration_spec.title} (L{calibration_spec.ddf_target_level})")
    if baseline_te:
        click.echo(f"Baseline TE: {baseline_te:.4f}")
    else:
        click.echo("Baseline TE: N/A (no flame events)")
    click.echo(f"Archive:     {session.session_artifact_path}")

    conn.close()
