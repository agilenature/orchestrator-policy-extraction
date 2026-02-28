"""Alert artifact JSON writer for EBC drift alerts.

Persists EBCDriftAlert instances as JSON files to the data/alerts/
directory for later analysis and review.

Exports:
    write_alert: Write an EBCDriftAlert to a JSON file
"""

from __future__ import annotations

from pathlib import Path

from src.pipeline.ebc.models import EBCDriftAlert

ALERTS_DIR = Path("data/alerts")


def write_alert(alert: EBCDriftAlert, alerts_dir: Path | None = None) -> Path:
    """Persist an EBCDriftAlert as a JSON file.

    Creates the alerts directory if it does not exist. Overwrites any
    existing alert for the same session_id.

    Args:
        alert: The drift alert to persist.
        alerts_dir: Override the default alerts directory (for testing).

    Returns:
        Path to the written JSON file.
    """
    target_dir = alerts_dir if alerts_dir is not None else ALERTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{alert.session_id}-ebc-drift.json"
    out_path = target_dir / filename
    out_path.write_text(alert.model_dump_json(indent=2) + "\n", encoding="utf-8")

    return out_path
