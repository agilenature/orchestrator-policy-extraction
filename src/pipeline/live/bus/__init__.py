"""OPE Governance Bus — session registration, signal routing, constraint delivery.

The bus is the coordination layer between Claude Code sessions and the
governing daemon. Sessions call /api/register, /api/deregister, /api/check.
They have no endpoint to write constraints — the constraint store is owned
by the governing daemon only.
"""

from .models import BusSession, CheckRequest, CheckResponse, GovernanceSignal
from .schema import create_bus_schema
from .server import SOCKET_PATH, create_app

__all__ = [
    "BusSession",
    "GovernanceSignal",
    "CheckRequest",
    "CheckResponse",
    "create_bus_schema",
    "create_app",
    "SOCKET_PATH",
]
