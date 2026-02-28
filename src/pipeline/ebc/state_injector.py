"""STATE.md drift alert injection using HTML comment sentinels.

Safely injects or updates an EBC drift alert section in STATE.md
without corrupting existing content. Uses paired HTML comment markers
to delimit the alert section for safe replacement on subsequent runs.

Exports:
    inject_alert_into_state: Inject or update drift alert section in STATE.md
    SENTINEL_START: Opening HTML comment sentinel
    SENTINEL_END: Closing HTML comment sentinel
"""

from __future__ import annotations

import re
from pathlib import Path

SENTINEL_START = "<!-- EBC_DRIFT_ALERTS_START -->"
SENTINEL_END = "<!-- EBC_DRIFT_ALERTS_END -->"


def inject_alert_into_state(state_path: Path, alert_block: str) -> bool:
    """Inject or update the EBC drift alert section in STATE.md.

    Uses HTML comment sentinels for safe replacement:
    - If sentinels already exist, replaces content between them.
    - If no sentinels exist but '## Performance Metrics' is found,
      inserts the alert section before that heading.
    - Otherwise, appends the alert section at the end of the file.

    Args:
        state_path: Path to the STATE.md file.
        alert_block: Formatted alert text to inject between sentinels.

    Returns:
        True if the file was modified, False if the file does not exist.
    """
    if not state_path.exists():
        return False

    content = state_path.read_text(encoding="utf-8")

    new_section = (
        f"{SENTINEL_START}\n"
        f"## EBC Drift Alerts\n"
        f"\n"
        f"{alert_block}\n"
        f"{SENTINEL_END}"
    )

    if SENTINEL_START in content:
        # Replace existing sentinel block
        pattern = re.escape(SENTINEL_START) + r".*?" + re.escape(SENTINEL_END)
        new_content = re.sub(pattern, new_section, content, flags=re.DOTALL)
    elif "## Performance Metrics" in content:
        # Insert before Performance Metrics section
        new_content = content.replace(
            "## Performance Metrics",
            new_section + "\n\n## Performance Metrics",
        )
    else:
        # Append at end of file
        new_content = content.rstrip("\n") + "\n\n" + new_section + "\n"

    state_path.write_text(new_content, encoding="utf-8")
    return True
