"""Mission Control bridge -- reads MC's SQLite database via DuckDB.

Exports:
    MCBridgeReader
"""

from src.pipeline.bridge.mc_reader import MCBridgeReader

__all__ = ["MCBridgeReader"]
