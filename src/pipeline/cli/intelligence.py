"""CLI subcommands for DDF Intelligence Profile display.

Provides subcommands under `intelligence`:
- profile: Display IntelligenceProfile for a human or AI subject
- stagnant: List stagnant constraints (floating abstractions)
- edges: Topology edge management (list, frontier, show)
- bridge: Structural integrity commands (stats, list, floating-cables)
- memory-review: Review pending memory_candidates and accept/reject to MEMORY.md
- assess: Assessment scenario management (annotate-scenarios, list-scenarios)

Exports:
    intelligence_group: Click group for intelligence subcommands
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import click
from loguru import logger

# Default MEMORY.md path for OPE project
_DEFAULT_MEMORY_PATH = os.path.expanduser(
    "~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction"
    "/memory/MEMORY.md"
)


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

        if ip is None:
            conn.close()
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

        # TE breakdown display (Phase 16, Plan 03)
        _display_te_metrics(conn, human_id, show_ai)

        # Structural Integrity display (Phase 18, Plan 04)
        _display_structural_integrity(conn, human_id, show_ai)

        conn.close()

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


@intelligence_group.group(name="bridge")
def bridge_group():
    """Structural integrity commands."""
    pass


@bridge_group.command("stats")
@click.argument("human_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def bridge_stats(human_id: str, db: str) -> None:
    """Show structural integrity stats for a human.

    Displays signal type breakdown (gravity_check, main_cable,
    dependency_sequencing, spiral_reinforcement) with pass/fail
    counts and the computed StructuralIntegrityScore.

    Usage:
        python -m src.pipeline.cli intelligence bridge stats <human_id>
    """
    _setup_logging()

    try:
        import duckdb

        from src.pipeline.ddf.structural.computer import compute_structural_integrity

        conn = duckdb.connect(db, read_only=True)

        # Find sessions for this human_id
        sessions = conn.execute(
            """
            SELECT DISTINCT se.session_id
            FROM structural_events se
            WHERE se.subject = 'human'
              AND se.assessment_session_id IS NULL
              AND se.session_id IN (
                  SELECT DISTINCT session_id
                  FROM flame_events
                  WHERE human_id = ?
                    AND subject = 'human'
                    AND assessment_session_id IS NULL
              )
            """,
            [human_id],
        ).fetchall()

        if not sessions:
            click.echo(f"No structural events found for: {human_id}")
            conn.close()
            sys.exit(0)

        # Aggregate across sessions by signal_type
        rows = conn.execute(
            """
            SELECT se.signal_type,
                   COUNT(*) AS total,
                   SUM(CASE WHEN se.signal_passed THEN 1 ELSE 0 END) AS passed,
                   SUM(CASE WHEN NOT se.signal_passed THEN 1 ELSE 0 END) AS failed
            FROM structural_events se
            WHERE se.subject = 'human'
              AND se.assessment_session_id IS NULL
              AND se.session_id IN (
                  SELECT DISTINCT session_id
                  FROM flame_events
                  WHERE human_id = ?
                    AND subject = 'human'
                    AND assessment_session_id IS NULL
              )
            GROUP BY se.signal_type
            ORDER BY se.signal_type
            """,
            [human_id],
        ).fetchall()

        click.echo(f"Structural Integrity Stats: {human_id}")
        click.echo("=" * 55)
        click.echo(
            f"{'signal_type':<25} {'total':<8} {'passed':<8} "
            f"{'failed':<8} {'rate':<8}"
        )
        click.echo("-" * 55)

        for signal_type, total, passed, failed in rows:
            rate = f"{passed / total:.2f}" if total > 0 else "N/A"
            click.echo(
                f"{signal_type:<25} {total:<8} {passed:<8} "
                f"{failed:<8} {rate:<8}"
            )

        # Compute aggregate integrity score
        from src.pipeline.ddf.intelligence_profile import (
            compute_structural_integrity_for_profile,
        )

        score, event_count = compute_structural_integrity_for_profile(
            conn, subject="human", human_id=human_id,
        )
        click.echo("-" * 55)
        if score is not None:
            click.echo(
                f"Integrity Score: {score:.4f}  "
                f"({event_count} events across {len(sessions)} sessions)"
            )
        else:
            click.echo("Integrity Score: N/A")

        conn.close()

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@bridge_group.command("list")
@click.argument("human_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--signal-type", default=None, help="Filter by signal type.")
@click.option("--failed-only", is_flag=True, default=False, help="Show only failed signals.")
def bridge_list(
    human_id: str,
    db: str,
    signal_type: str | None,
    failed_only: bool,
) -> None:
    """List structural events for a human.

    Usage:
        python -m src.pipeline.cli intelligence bridge list <human_id>
        python -m src.pipeline.cli intelligence bridge list <human_id> --failed-only
        python -m src.pipeline.cli intelligence bridge list <human_id> --signal-type main_cable
    """
    _setup_logging()

    try:
        import duckdb

        conn = duckdb.connect(db, read_only=True)

        # Build query with optional filters
        where_clauses = [
            "se.subject = 'human'",
            "se.assessment_session_id IS NULL",
            """se.session_id IN (
                SELECT DISTINCT session_id
                FROM flame_events
                WHERE human_id = ?
                  AND subject = 'human'
                  AND assessment_session_id IS NULL
            )""",
        ]
        params: list = [human_id]

        if signal_type:
            where_clauses.append("se.signal_type = ?")
            params.append(signal_type)

        if failed_only:
            where_clauses.append("se.signal_passed = false")

        where_sql = " AND ".join(where_clauses)

        rows = conn.execute(
            f"""
            SELECT se.session_id, se.prompt_number, se.signal_type,
                   se.signal_passed, se.evidence
            FROM structural_events se
            WHERE {where_sql}
            ORDER BY se.session_id, se.prompt_number
            """,
            params,
        ).fetchall()

        conn.close()

        if not rows:
            click.echo(f"No structural events found for: {human_id}")
            sys.exit(0)

        click.echo(
            f"{'session_id':<24} {'prompt':<8} {'signal_type':<25} "
            f"{'passed':<8} {'evidence'}"
        )
        click.echo("-" * 90)

        for session_id, prompt, sig_type, passed, evidence in rows:
            sid_display = (
                session_id[:22] + ".."
                if len(session_id) > 24
                else session_id
            )
            ev_display = ""
            if evidence:
                ev_display = (
                    evidence[:40] + "..."
                    if len(evidence) > 40
                    else evidence
                )
            pass_str = "yes" if passed else "NO"
            click.echo(
                f"{sid_display:<24} {prompt:<8} {sig_type:<25} "
                f"{pass_str:<8} {ev_display}"
            )

        click.echo(f"\nTotal: {len(rows)} events")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@bridge_group.command("floating-cables")
@click.argument("human_id")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def bridge_floating_cables(human_id: str, db: str) -> None:
    """Show AI floating cables and their Op-8 correction candidates.

    Lists AI main_cable failures (floating abstractions) and joins
    with memory_candidates to show correction status.

    Usage:
        python -m src.pipeline.cli intelligence bridge floating-cables <human_id>
    """
    _setup_logging()

    try:
        import duckdb

        conn = duckdb.connect(db, read_only=True)

        # Query AI floating cables (main_cable failures)
        rows = conn.execute(
            """
            SELECT se.session_id, se.evidence,
                   se.op8_correction_candidate_id,
                   mc.ccd_axis, mc.status AS mc_status
            FROM structural_events se
            LEFT JOIN memory_candidates mc
                ON se.op8_correction_candidate_id = mc.id
            WHERE se.signal_type = 'main_cable'
              AND se.signal_passed = false
              AND se.subject = 'ai'
              AND se.assessment_session_id IS NULL
            ORDER BY se.session_id
            """,
        ).fetchall()

        conn.close()

        if not rows:
            click.echo("No AI floating cables found.")
            sys.exit(0)

        click.echo("AI Floating Cables (Main Cable Failures)")
        click.echo("=" * 70)
        click.echo(
            f"{'axis':<30} {'session':<24} {'mc_status':<12}"
        )
        click.echo("-" * 70)

        for session_id, evidence, op8_id, ccd_axis, mc_status in rows:
            axis_display = ccd_axis or "(no axis)"
            if len(axis_display) > 28:
                axis_display = axis_display[:26] + ".."
            sid_display = (
                session_id[:22] + ".."
                if len(session_id) > 24
                else session_id
            )
            status_display = mc_status or "not deposited"
            click.echo(
                f"{axis_display:<30} {sid_display:<24} {status_display:<12}"
            )

        click.echo(f"\nTotal floating cables: {len(rows)}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@intelligence_group.command(name="memory-review")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--memory-file", default=None, help="Override MEMORY.md path.")
def memory_review(db: str, memory_file: str | None) -> None:
    """Review pending memory_candidates and accept/reject to MEMORY.md.

    The terminal act of the deposit chain: transforms pending
    memory_candidates into permanent MEMORY.md entries that change
    what the AI retrieves next session.

    Usage:
        python -m src.pipeline.cli intelligence memory-review
        python -m src.pipeline.cli intelligence memory-review --db data/ope.db
    """
    _setup_logging()
    _memory_review_impl(db=db, memory_file=memory_file, input_fn=input)


def _memory_review_impl(
    db: str,
    memory_file: str | None,
    input_fn=input,
) -> None:
    """Implementation of memory-review, with injectable input_fn for testing.

    Args:
        db: DuckDB database path.
        memory_file: Override MEMORY.md path. If None, uses default project path.
        input_fn: Callable for user input (default=input). Injectable for tests.
    """
    import duckdb

    memory_path = memory_file or _DEFAULT_MEMORY_PATH

    conn = duckdb.connect(db)

    # Query pending candidates
    try:
        rows = conn.execute(
            "SELECT id, ccd_axis, scope_rule, flood_example, "
            "confidence, subject, source_flame_event_id, session_id, "
            "detection_count "
            "FROM memory_candidates "
            "WHERE status = 'pending' "
            "ORDER BY confidence DESC NULLS LAST, detection_count DESC"
        ).fetchall()
    except Exception as e:
        click.echo(f"Error querying memory_candidates: {e}", err=True)
        conn.close()
        sys.exit(1)

    if not rows:
        click.echo("No pending memory candidates.")
        conn.close()
        return

    total = len(rows)
    for idx, row in enumerate(rows, 1):
        (
            candidate_id, ccd_axis, scope_rule, flood_example,
            confidence, subject, source_flame_event_id, session_id,
            detection_count,
        ) = row

        # Display candidate
        conf_str = f"{confidence:.2f}" if confidence is not None else "N/A"
        subj_str = subject or "N/A"
        det_str = str(detection_count) if detection_count is not None else "0"
        click.echo(f"\n---")
        click.echo(
            f"CANDIDATE [{idx}/{total}] -- "
            f"Confidence: {conf_str} | Subject: {subj_str} | Detections: {det_str}"
        )
        click.echo(f"---")
        click.echo(f"CCD axis:      {ccd_axis}")
        click.echo(f"Scope rule:    {scope_rule}")
        click.echo(f"Flood example: {flood_example}")
        fe_str = source_flame_event_id or "N/A"
        sess_str = session_id or "N/A"
        click.echo(f"Source:        flame_event {fe_str} | session {sess_str}")
        click.echo(f"---")
        click.echo("[a]ccept  [r]eject  [e]dit  [s]kip  [q]uit")

        choice = input_fn("Choice: ").strip().lower()

        if choice in ("a", "accept"):
            _handle_accept(
                conn, candidate_id, ccd_axis, scope_rule,
                flood_example, memory_path, input_fn,
            )
        elif choice in ("r", "reject"):
            _handle_reject(conn, candidate_id, ccd_axis)
        elif choice in ("e", "edit"):
            edited = _handle_edit(
                ccd_axis, scope_rule, flood_example, input_fn,
            )
            if edited is not None:
                ccd_axis, scope_rule, flood_example = edited
                # Show updated candidate and ask for accept/reject/skip
                click.echo(f"\n--- EDITED ---")
                click.echo(f"CCD axis:      {ccd_axis}")
                click.echo(f"Scope rule:    {scope_rule}")
                click.echo(f"Flood example: {flood_example}")
                click.echo("[a]ccept  [r]eject  [s]kip")
                post_choice = input_fn("Choice: ").strip().lower()
                if post_choice in ("a", "accept"):
                    # Update the candidate with edited values before accepting
                    conn.execute(
                        "UPDATE memory_candidates SET ccd_axis = ?, "
                        "scope_rule = ?, flood_example = ? WHERE id = ?",
                        [ccd_axis, scope_rule, flood_example, candidate_id],
                    )
                    _handle_accept(
                        conn, candidate_id, ccd_axis, scope_rule,
                        flood_example, memory_path, input_fn,
                    )
                elif post_choice in ("r", "reject"):
                    _handle_reject(conn, candidate_id, ccd_axis)
                # else skip
        elif choice in ("q", "quit"):
            click.echo("Quit.")
            break
        # else skip (including 's')

    conn.close()


def _handle_accept(
    conn,
    candidate_id: str,
    ccd_axis: str,
    scope_rule: str,
    flood_example: str,
    memory_path: str,
    input_fn,
) -> None:
    """Accept a candidate: write to MEMORY.md and update status."""
    # Check if MEMORY.md exists
    if not os.path.exists(memory_path):
        click.echo(f"WARNING: MEMORY.md not found at {memory_path}")
        click.echo("Creating new file.")
        os.makedirs(os.path.dirname(memory_path), exist_ok=True)
        memory_content = ""
    else:
        with open(memory_path) as f:
            memory_content = f.read()

    # Dedup check: case-insensitive substring match of ccd_axis
    if ccd_axis.lower() in memory_content.lower():
        click.echo(
            f"WARNING: CCD axis '{ccd_axis}' already appears in MEMORY.md."
        )
        proceed = input_fn("Proceed anyway? [y/N]: ").strip().lower()
        if proceed not in ("y", "yes"):
            click.echo("Skipped (duplicate).")
            return

    # Format entry in CCD format
    entry = (
        f"\n---\n\n"
        f"## {ccd_axis}\n\n"
        f"**CCD axis:** {ccd_axis}\n"
        f"**Scope rule:** {scope_rule}\n"
        f"**Flood example:** {flood_example}\n\n"
    )

    # Atomic write: read full file, append entry, write full file
    new_content = memory_content + entry
    with open(memory_path, "w") as f:
        f.write(new_content)

    # Update status to 'validated'
    conn.execute(
        "UPDATE memory_candidates SET status = 'validated', "
        "reviewed_at = NOW() WHERE id = ?",
        [candidate_id],
    )

    click.echo(f"ACCEPTED: {ccd_axis} -> MEMORY.md")


def _handle_reject(conn, candidate_id: str, ccd_axis: str) -> None:
    """Reject a candidate: update status to 'rejected'."""
    conn.execute(
        "UPDATE memory_candidates SET status = 'rejected', "
        "reviewed_at = NOW() WHERE id = ?",
        [candidate_id],
    )
    click.echo(f"REJECTED: {ccd_axis}")


def _handle_edit(
    ccd_axis: str,
    scope_rule: str,
    flood_example: str,
    input_fn,
) -> tuple[str, str, str] | None:
    """Edit a candidate's CCD fields via $EDITOR.

    Returns:
        Tuple of (ccd_axis, scope_rule, flood_example) if edited,
        or None if editing failed or was cancelled.
    """
    editor = os.environ.get("EDITOR", "vi")

    # Write fields to temp file
    content = (
        f"ccd_axis: {ccd_axis}\n"
        f"scope_rule: {scope_rule}\n"
        f"flood_example: {flood_example}\n"
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="memory_review_"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Open editor
        ret = os.system(f'{editor} "{tmp_path}"')
        if ret != 0:
            click.echo("Editor exited with error. Skipping edit.")
            return None

        # Re-read and parse
        with open(tmp_path) as f:
            edited_content = f.read()

        os.unlink(tmp_path)

        # Parse fields back
        new_axis = ccd_axis
        new_scope = scope_rule
        new_flood = flood_example

        for line in edited_content.split("\n"):
            line = line.strip()
            if line.startswith("ccd_axis:"):
                new_axis = line[len("ccd_axis:"):].strip()
            elif line.startswith("scope_rule:"):
                new_scope = line[len("scope_rule:"):].strip()
            elif line.startswith("flood_example:"):
                new_flood = line[len("flood_example:"):].strip()

        return (new_axis, new_scope, new_flood)

    except Exception as e:
        click.echo(f"Edit failed: {e}")
        return None


def _display_te_metrics(
    conn,
    human_id: str,
    show_ai: bool,
) -> None:
    """Display TransportEfficiency metrics after the IntelligenceProfile display.

    Queries transport_efficiency_sessions for the subject and displays:
    - TE breakdown (4 sub-metrics + composite + fringe drift)
    - TE trend (last 10 sessions with pending/confirmed counts)
    - For AI: te_delta ranking of accepted memory entries

    Gracefully skips if transport_efficiency_sessions table doesn't exist.

    Args:
        conn: Open DuckDB connection (read-only).
        human_id: Human ID or "ai".
        show_ai: Whether to display AI-specific metrics.
    """
    try:
        is_ai = show_ai or human_id == "ai"
        subject_filter = "ai" if is_ai else "human"

        # Query last 10 TE sessions
        if is_ai:
            te_rows = conn.execute(
                "SELECT raven_depth, crow_efficiency, transport_speed, "
                "trunk_quality, composite_te, trunk_quality_status, "
                "fringe_drift_rate "
                "FROM transport_efficiency_sessions "
                "WHERE subject = 'ai' "
                "ORDER BY created_at DESC "
                "LIMIT 10"
            ).fetchall()
        else:
            te_rows = conn.execute(
                "SELECT raven_depth, crow_efficiency, transport_speed, "
                "trunk_quality, composite_te, trunk_quality_status, "
                "fringe_drift_rate "
                "FROM transport_efficiency_sessions "
                "WHERE human_id = ? AND subject = 'human' "
                "ORDER BY created_at DESC "
                "LIMIT 10",
                [human_id],
            ).fetchall()

        if not te_rows:
            click.echo("\nTransportEfficiency: not yet computed")
            return

        # Display latest session's TE breakdown
        latest = te_rows[0]
        raven_d, crow_e, trans_s, trunk_q, comp_te, tq_status, fringe_dr = latest

        click.echo(f"\nTransportEfficiency (last session):")
        click.echo(f"  Raven Depth:      {raven_d:.3f}")
        click.echo(f"  Crow Efficiency:  {crow_e:.3f}")
        click.echo(f"  Transport Speed:  {trans_s:.3f}")
        click.echo(f"  Trunk Quality:    {trunk_q:.3f} ({tq_status})")
        click.echo(f"  Composite TE:     {comp_te:.4f}")

        # Fringe drift: show latest + average of recent
        if fringe_dr is not None:
            fringe_values = [
                r[6] for r in te_rows if r[6] is not None
            ]
            avg_fringe = (
                sum(fringe_values) / len(fringe_values)
                if fringe_values
                else 0.0
            )
            click.echo(
                f"  Fringe Drift:     {fringe_dr:.1f} "
                f"(avg recent: {avg_fringe:.2f})"
            )
        else:
            click.echo(f"  Fringe Drift:     N/A")

        # TE trend (last 10 sessions)
        trend_values = [f"{r[4]:.4f}" for r in te_rows]

        # Pending vs confirmed counts
        pending_count = conn.execute(
            "SELECT COUNT(*) FROM transport_efficiency_sessions "
            "WHERE subject = ? AND trunk_quality_status = 'pending'",
            [subject_filter],
        ).fetchone()[0]
        confirmed_count = conn.execute(
            "SELECT COUNT(*) FROM transport_efficiency_sessions "
            "WHERE subject = ? AND trunk_quality_status = 'confirmed'",
            [subject_filter],
        ).fetchone()[0]

        click.echo(
            f"\nTE Trend (last {len(te_rows)} sessions):"
        )
        click.echo(f"  {' '.join(trend_values)}")
        click.echo(
            f"  ({pending_count} pending, {confirmed_count} confirmed)"
        )

        # AI-specific: te_delta ranking
        if is_ai:
            _display_te_delta_ranking(conn)

    except Exception:
        # Graceful fallback: table may not exist on older DBs
        click.echo("\nTransportEfficiency: not yet computed")


def _display_te_delta_ranking(conn) -> None:
    """Display te_delta ranking for AI profile.

    Shows validated memory_candidates ranked by TE impact,
    plus count of entries pending backfill.

    Args:
        conn: Open DuckDB connection (read-only).
    """
    try:
        # Validated candidates with te_delta
        ranked = conn.execute(
            "SELECT ccd_axis, te_delta, pre_te_avg, post_te_avg "
            "FROM memory_candidates "
            "WHERE status = 'validated' AND te_delta IS NOT NULL "
            "ORDER BY te_delta DESC"
        ).fetchall()

        # Count pending backfill
        pending_backfill_row = conn.execute(
            "SELECT COUNT(*) FROM memory_candidates "
            "WHERE status = 'validated' AND te_delta IS NULL"
        ).fetchone()
        pending_backfill = pending_backfill_row[0] if pending_backfill_row else 0

        if ranked:
            click.echo("\nTop Memory Entries by TE Impact:")
            for i, (axis, delta, pre_avg, post_avg) in enumerate(ranked, 1):
                sign = "+" if delta >= 0 else ""
                click.echo(
                    f"  {i}. {axis} ({sign}{delta:.4f} TE delta)"
                )

        if pending_backfill > 0:
            click.echo(f"  [{pending_backfill} entries pending backfill]")
        elif not ranked:
            click.echo("\nTop Memory Entries by TE Impact: none yet")

    except Exception:
        pass  # memory_candidates may not have te_delta column yet


def _display_structural_integrity(
    conn,
    human_id: str,
    show_ai: bool,
) -> None:
    """Display Structural Integrity metrics after TE in the profile display.

    Shows aggregate integrity score and per-signal-type breakdown.
    Gracefully skips if structural_events table doesn't exist.

    Args:
        conn: Open DuckDB connection (read-only).
        human_id: Human ID or "ai".
        show_ai: Whether to display AI-specific metrics.
    """
    try:
        is_ai = show_ai or human_id == "ai"
        subject_filter = "ai" if is_ai else "human"

        # Get per-signal-type breakdown
        if is_ai:
            rows = conn.execute(
                """
                SELECT signal_type,
                       COUNT(*) AS total,
                       SUM(CASE WHEN signal_passed THEN 1 ELSE 0 END) AS passed
                FROM structural_events
                WHERE subject = 'ai'
                  AND assessment_session_id IS NULL
                GROUP BY signal_type
                ORDER BY signal_type
                """,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT se.signal_type,
                       COUNT(*) AS total,
                       SUM(CASE WHEN se.signal_passed THEN 1 ELSE 0 END) AS passed
                FROM structural_events se
                WHERE se.subject = 'human'
                  AND se.assessment_session_id IS NULL
                  AND se.session_id IN (
                      SELECT DISTINCT session_id
                      FROM flame_events
                      WHERE human_id = ?
                        AND subject = 'human'
                        AND assessment_session_id IS NULL
                  )
                GROUP BY se.signal_type
                ORDER BY se.signal_type
                """,
                [human_id],
            ).fetchall()

        if not rows:
            click.echo("\nStructural Integrity: not yet computed")
            return

        # Build signal type ratios
        signal_ratios: dict[str, float] = {}
        total_events = 0
        for signal_type, total, passed in rows:
            ratio = passed / total if total > 0 else 0.0
            signal_ratios[signal_type] = ratio
            total_events += total

        # Compute overall integrity score from profile function
        from src.pipeline.ddf.intelligence_profile import (
            compute_structural_integrity_for_profile,
        )

        score, event_count = compute_structural_integrity_for_profile(
            conn, subject=subject_filter,
            human_id=None if is_ai else human_id,
        )

        score_display = f"{score:.2f}" if score is not None else "N/A"
        click.echo(
            f"\nStructural Integrity:  {score_display}  ({total_events} events)"
        )

        # Per-signal-type breakdown
        gravity = signal_ratios.get("gravity_check", 0.0)
        main_cable = signal_ratios.get("main_cable", 0.0)
        deps = signal_ratios.get("dependency_sequencing", 0.0)
        spiral = signal_ratios.get("spiral_reinforcement", 0.0)
        click.echo(
            f"  Gravity:  {gravity:.2f}  Main Cable:  {main_cable:.2f}  "
            f"Deps:  {deps:.2f}  Spiral:  {spiral:.2f}"
        )

    except Exception:
        # Graceful fallback: table may not exist on older DBs
        click.echo("\nStructural Integrity: not yet computed")


def _setup_logging() -> None:
    """Configure logging to suppress INFO in CLI output."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING", format="{time:HH:mm:ss} | {level:<7} | {message}")


# Register assess subgroup (Phase 17, Plan 02)
from src.pipeline.cli.assess import assess_group  # noqa: E402

intelligence_group.add_command(assess_group)
