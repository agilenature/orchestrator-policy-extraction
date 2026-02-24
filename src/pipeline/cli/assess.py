"""CLI commands for assessment scenario management (Phase 17).

Provides subcommands under `assess`:
- annotate-scenarios: Interactively annotate project_wisdom entries with DDF target levels
- list-scenarios: Display scenario inventory with annotation status

The assess group is registered under intelligence_group in intelligence.py,
accessible via: python -m src.pipeline.cli intelligence assess <command>

Exports:
    assess_group: Click group for assessment scenario commands
"""

from __future__ import annotations

import sys

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

    try:
        rows = conn.execute(
            "SELECT wisdom_id, entity_type, title, ddf_target_level, "
            "scenario_seed IS NOT NULL AS has_seed "
            "FROM project_wisdom "
            "ORDER BY ddf_target_level NULLS LAST, entity_type, title"
        ).fetchall()
    except Exception as e:
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
