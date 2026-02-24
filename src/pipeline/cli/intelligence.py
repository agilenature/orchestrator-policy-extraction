"""CLI subcommands for DDF Intelligence Profile display.

Provides subcommands under `intelligence`:
- profile: Display IntelligenceProfile for a human or AI subject
- stagnant: List stagnant constraints (floating abstractions)
- edges: Topology edge management (list, frontier, show)

Exports:
    intelligence_group: Click group for intelligence subcommands
"""

from __future__ import annotations

import json
import sys

import click
from loguru import logger


@click.group("intelligence")
def intelligence_group():
    """DDF Intelligence Profile commands."""
    pass


@intelligence_group.command(name="profile")
@click.argument("human_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--ai", "show_ai", is_flag=True, help="Display AI marker profile instead.")
def profile(human_id: str, db: str, show_ai: bool) -> None:
    """Display IntelligenceProfile for a human or AI subject.

    Usage:
        python -m src.pipeline.cli intelligence profile <human_id>
        python -m src.pipeline.cli intelligence profile ai --ai
    """
    _setup_logging()

    try:
        import duckdb

        from src.pipeline.ddf.intelligence_profile import (
            compute_ai_profile,
            compute_intelligence_profile,
            compute_spiral_depth_for_human,
        )
        from src.pipeline.ddf.schema import create_ddf_schema

        conn = duckdb.connect(db, read_only=True)

        # Ensure tables exist for queries (read_only=True prevents actual DDL
        # on disk, but for in-memory tables created fresh, this is safe)
        try:
            create_ddf_schema(conn)
        except Exception:
            pass  # Read-only mode may block DDL; tables should already exist

        if show_ai or human_id == "ai":
            ip = compute_ai_profile(conn)
        else:
            ip = compute_intelligence_profile(conn, human_id)

        conn.close()

        if ip is None:
            click.echo(f"No flame events found for human_id: {human_id}")
            sys.exit(0)

        # Format display
        subject_label = "AI" if ip.subject == "ai" else human_id
        click.echo(f"Intelligence Profile: {subject_label}")
        click.echo("=" * 40)
        click.echo(f"Sessions:         {ip.session_count}")
        click.echo(f"Flame Frequency:  {ip.flame_frequency}")
        click.echo(f"Avg Marker Level: {ip.avg_marker_level:.1f}")
        click.echo(f"Max Marker Level: {ip.max_marker_level}")
        click.echo(f"Spiral Depth:     {ip.spiral_depth}")
        flood_pct = f"{ip.flood_rate * 100:.0f}" if ip.flood_rate else "0"
        click.echo(f"Flood Rate:       {ip.flood_rate:.2f} ({flood_pct}%)")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@intelligence_group.command(name="stagnant")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def stagnant(db: str) -> None:
    """List stagnant constraints (floating abstractions).

    Stagnant constraints have radius=1 (single scope context) with
    high firing count -- potential floating abstractions that never
    generalized beyond their original context.

    Usage:
        python -m src.pipeline.cli intelligence stagnant
    """
    _setup_logging()

    try:
        import duckdb

        from src.pipeline.ddf.generalization import detect_stagnation
        from src.pipeline.ddf.schema import create_ddf_schema
        from src.pipeline.models.config import load_config

        conn = duckdb.connect(db, read_only=True)

        try:
            create_ddf_schema(conn)
        except Exception:
            pass  # Read-only mode may block DDL; tables should already exist

        try:
            config = load_config("data/config.yaml")
        except Exception:
            config = None

        stagnant_metrics = detect_stagnation(conn, config)
        conn.close()

        if not stagnant_metrics:
            click.echo("No stagnant constraints detected.")
            sys.exit(0)

        # Table header
        click.echo(
            f"{'constraint_id':<20} {'radius':<10} {'firing_count':<15} {'stagnant':<10}"
        )
        click.echo("-" * 55)

        for m in stagnant_metrics:
            cid = m.constraint_id[:18] if len(m.constraint_id) > 18 else m.constraint_id
            click.echo(
                f"{cid:<20} {m.radius:<10} {m.firing_count:<15} {str(m.is_stagnant):<10}"
            )

        click.echo(f"\nTotal stagnant: {len(stagnant_metrics)}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@intelligence_group.group(name="edges")
def edges_group():
    """Topology edge commands (list, frontier, show)."""
    pass


@edges_group.command(name="list")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--axis", default=None, help="Filter to edges involving this axis.")
def edges_list(db: str, axis: str | None) -> None:
    """List active topology edges.

    Usage:
        python -m src.pipeline.cli intelligence edges list
        python -m src.pipeline.cli intelligence edges list --axis deposit-not-detect
    """
    _setup_logging()

    try:
        import duckdb

        conn = duckdb.connect(db, read_only=True)

        if axis:
            rows = conn.execute(
                "SELECT edge_id, axis_a, axis_b, relationship_text, "
                "activation_condition, trunk_quality "
                "FROM axis_edges WHERE status = 'active' "
                "AND (axis_a = ? OR axis_b = ?) "
                "ORDER BY trunk_quality DESC",
                [axis, axis],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT edge_id, axis_a, axis_b, relationship_text, "
                "activation_condition, trunk_quality "
                "FROM axis_edges WHERE status = 'active' "
                "ORDER BY trunk_quality DESC"
            ).fetchall()

        conn.close()

        if not rows:
            click.echo("No active edges found.")
            sys.exit(0)

        for edge_id, axis_a, axis_b, rel_text, ac_json, trunk_q in rows:
            rel_display = rel_text[:80] + "..." if len(rel_text) > 80 else rel_text
            try:
                ac = json.loads(ac_json) if isinstance(ac_json, str) else ac_json
                ac_display = (
                    f"goal={ac.get('goal_type', ['any'])}, "
                    f"scope={ac.get('scope_prefix', '')!r}, "
                    f"min_axes={ac.get('min_axes_simultaneously_active', 2)}"
                )
            except (json.JSONDecodeError, TypeError):
                ac_display = str(ac_json)

            click.echo(f"  {edge_id}  [{axis_a}] <-> [{axis_b}]")
            click.echo(f"    relationship: {rel_display}")
            click.echo(f"    activation:   {ac_display}")
            click.echo(f"    trunk_quality: {trunk_q:.2f}")
            click.echo()

        click.echo(f"Total active edges: {len(rows)}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@edges_group.command(name="frontier")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def edges_frontier(db: str) -> None:
    """Show axis pairs with no active edge (frontier territory).

    Usage:
        python -m src.pipeline.cli intelligence edges frontier
    """
    _setup_logging()

    try:
        import duckdb

        from src.pipeline.ddf.topology.frontier import FrontierChecker

        conn = duckdb.connect(db, read_only=True)

        # Collect known axes from flame_events and memory_candidates
        known_axes: set[str] = set()

        try:
            flame_axes = conn.execute(
                "SELECT DISTINCT axis_identified FROM flame_events "
                "WHERE axis_identified IS NOT NULL"
            ).fetchall()
            for (ax,) in flame_axes:
                known_axes.add(ax)
        except Exception:
            pass

        try:
            mc_axes = conn.execute(
                "SELECT DISTINCT ccd_axis FROM memory_candidates "
                "WHERE ccd_axis IS NOT NULL"
            ).fetchall()
            for (ax,) in mc_axes:
                known_axes.add(ax)
        except Exception:
            pass

        if len(known_axes) < 2:
            click.echo("Fewer than 2 known axes -- no frontier pairs possible.")
            conn.close()
            sys.exit(0)

        checker = FrontierChecker(conn)
        pairs = checker.find_frontier_pairs(sorted(known_axes))
        conn.close()

        if not pairs:
            click.echo(
                "No frontier pairs found -- all axis pairs have active edges."
            )
            sys.exit(0)

        click.echo("Frontier pairs (no active edge):")
        for axis_a, axis_b in pairs:
            click.echo(f"  [{axis_a}] <-> [{axis_b}]")

        click.echo(f"\nTotal frontier pairs: {len(pairs)}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@edges_group.command(name="show")
@click.argument("edge_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def edges_show(edge_id: str, db: str) -> None:
    """Show full edge artifact by EDGE_ID.

    Usage:
        python -m src.pipeline.cli intelligence edges show <edge_id>
    """
    _setup_logging()

    try:
        import duckdb

        conn = duckdb.connect(db, read_only=True)

        row = conn.execute(
            "SELECT edge_id, axis_a, axis_b, relationship_text, "
            "activation_condition, evidence, abstraction_level, "
            "status, trunk_quality, created_session_id, created_at "
            "FROM axis_edges WHERE edge_id = ?",
            [edge_id],
        ).fetchone()

        conn.close()

        if row is None:
            click.echo(f"Edge not found: {edge_id}")
            sys.exit(1)

        (
            eid, axis_a, axis_b, rel_text, ac_json,
            ev_json, abs_level, status, trunk_q,
            session, created_at,
        ) = row

        click.echo(f"Edge: {eid}")
        click.echo("=" * 50)
        click.echo(f"  axis_a:             {axis_a}")
        click.echo(f"  axis_b:             {axis_b}")
        click.echo(f"  status:             {status}")
        click.echo(f"  trunk_quality:      {trunk_q:.2f}")
        click.echo(f"  abstraction_level:  {abs_level}")
        click.echo(f"  session:            {session}")
        click.echo(f"  created_at:         {created_at}")
        click.echo(f"  relationship_text:  {rel_text}")

        # Parse activation_condition
        try:
            ac = json.loads(ac_json) if isinstance(ac_json, str) else ac_json
            click.echo("  activation_condition:")
            click.echo(f"    goal_type:                     {ac.get('goal_type', [])}")
            click.echo(f"    scope_prefix:                  {ac.get('scope_prefix', '')!r}")
            click.echo(
                f"    min_axes_simultaneously_active: "
                f"{ac.get('min_axes_simultaneously_active', 2)}"
            )
        except (json.JSONDecodeError, TypeError):
            click.echo(f"  activation_condition: {ac_json}")

        # Parse evidence
        try:
            ev = json.loads(ev_json) if isinstance(ev_json, str) else ev_json
            click.echo("  evidence:")
            click.echo(f"    session_id:      {ev.get('session_id', '')}")
            click.echo(f"    episode_id:      {ev.get('episode_id', '')}")
            click.echo(f"    flame_event_ids: {ev.get('flame_event_ids', [])}")
        except (json.JSONDecodeError, TypeError):
            click.echo(f"  evidence: {ev_json}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING", format="{time:HH:mm:ss} | {level:<7} | {message}")
