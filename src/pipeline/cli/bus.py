"""Bus CLI -- manage OPE Governance Bus lifecycle.

Provides start and status commands for the OPE Governance Bus Unix socket
server. The bus delivers constraint briefings to operator sessions and
records session registrations in DuckDB.
"""

from __future__ import annotations

import click


@click.group(name="bus")
def bus_group():
    """OPE Governance Bus management."""


@bus_group.command()
@click.option("--db", default="data/ope.db", help="DuckDB path")
@click.option(
    "--socket",
    default="/tmp/ope-governance-bus.sock",
    help="Unix socket path",
)
def start(db: str, socket: str):
    """Start the OPE Governance Bus server."""
    import os

    from src.pipeline.live.bus.server import create_app

    if os.path.exists(socket):
        click.echo(
            f"[OPE Bus] Socket already exists at {socket}. "
            "Is the bus already running?"
        )
        click.echo(f"[OPE Bus] Remove {socket} to restart: rm {socket}")
        raise SystemExit(1)

    try:
        import uvicorn
    except ImportError:
        click.echo(
            "[OPE Bus] uvicorn not installed. "
            "Install with: pip install uvicorn"
        )
        raise SystemExit(1)

    app = create_app(db_path=db)
    click.echo(f"[OPE Bus] Starting on {socket} (db: {db})")
    uvicorn.run(app, uds=socket, log_level="warning")


@bus_group.command()
@click.option(
    "--socket",
    default="/tmp/ope-governance-bus.sock",
    help="Unix socket path",
)
def status(socket: str):
    """Check if the OPE Governance Bus is running."""
    import os

    if os.path.exists(socket):
        click.echo(
            f"[OPE Bus] Socket exists at {socket} -- bus may be running"
        )
        click.echo(
            "[OPE Bus] Test with: curl --unix-socket "
            f"{socket} http://localhost/api/check -d '{{}}'"
        )
    else:
        click.echo(
            f"[OPE Bus] No socket at {socket} -- bus is not running"
        )
        click.echo(
            "[OPE Bus] Start with: python -m src.pipeline.cli bus start"
        )
