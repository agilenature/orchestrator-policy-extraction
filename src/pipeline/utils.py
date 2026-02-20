"""Shared pipeline utilities.

Functions shared across multiple pipeline modules to avoid circular imports.

Exports:
    scopes_overlap: Check if two sets of scope paths overlap
"""

from __future__ import annotations


def scopes_overlap(paths_a: list[str], paths_b: list[str]) -> bool:
    """Check if two sets of scope paths overlap using bidirectional prefix matching.

    An empty paths list means repo-wide scope (matches everything).
    This differs from validation/layers.py _scopes_overlap() which only
    treats the constraint side as repo-wide when empty (episode paths empty
    means no scope info, not repo-wide).

    Args:
        paths_a: First set of scope paths (e.g., constraint paths).
        paths_b: Second set of scope paths (e.g., session paths).

    Returns:
        True if the scopes overlap, False otherwise.
    """
    if not paths_a or not paths_b:
        return True

    for a in paths_a:
        for b in paths_b:
            if a.startswith(b) or b.startswith(a):
                return True

    return False
