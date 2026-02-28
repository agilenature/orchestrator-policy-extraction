"""FundamentalityChecker for genus declaration validation (Phase 24).

Validates that a genus declaration satisfies the fundamentality criterion:
two citable instances + causal explanation (causal indicator word OR 3+ word name).

Loads causal_indicator_words from data/config.yaml (genus_check section).
Falls back to a hardcoded minimal set if config is unavailable (fail-open).

Exports:
    FundamentalityResult
    FundamentalityChecker
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


# Fallback word set if config is unavailable
_FALLBACK_CAUSAL_WORDS = frozenset({
    "retrieval", "identification", "formation", "derivation", "detection",
    "synchronization", "propagation", "extraction", "resolution", "scoping",
    "isolation", "drift", "failure", "mechanism", "process", "computation",
    "generation", "validation", "discrimination", "differentiation",
    "selection", "projection", "instantiation", "classification",
})

_CONFIG_PATH = Path("data/config.yaml")


def _load_causal_words() -> frozenset[str]:
    """Load causal_indicator_words from config.yaml.

    Returns fallback set if config is missing or malformed.
    """
    try:
        with _CONFIG_PATH.open() as f:
            cfg = yaml.safe_load(f)
        words = cfg.get("genus_check", {}).get("causal_indicator_words", [])
        if words:
            return frozenset(w.lower() for w in words)
    except Exception:
        pass
    return _FALLBACK_CAUSAL_WORDS


@dataclass(frozen=True)
class FundamentalityResult:
    """Result of a fundamentality check on a genus declaration."""
    valid: bool
    reason: str
    genus_name: str
    instance_count: int


class FundamentalityChecker:
    """Validates genus declarations against the fundamentality criterion.

    Criterion: a genus is fundamental if it satisfies ALL of:
      Rule 1: >= 2 citable instances provided
      Rule 2: genus_name is non-empty
      Rule 3: genus_name contains a causal indicator word OR has >= 3 words
    """

    def __init__(self) -> None:
        self._causal_words = _load_causal_words()

    def check(
        self,
        genus_name: str,
        instances: list[str] | None,
    ) -> FundamentalityResult:
        """Check whether a genus declaration satisfies the fundamentality criterion."""
        name = genus_name.strip() if genus_name else ""
        if not name:
            return FundamentalityResult(
                valid=False,
                reason="GENUS name is empty — must provide a non-empty genus name",
                genus_name=name,
                instance_count=0,
            )

        instance_list = instances or []
        instance_count = len(instance_list)
        if instance_count < 2:
            return FundamentalityResult(
                valid=False,
                reason=(
                    f"GENUS '{name}' has {instance_count} instance(s) — "
                    f"fundamentality requires >= 2 citable instances"
                ),
                genus_name=name,
                instance_count=instance_count,
            )

        name_lower = name.lower()
        name_words = name_lower.split()
        has_causal_word = any(w in self._causal_words for w in name_words)
        has_three_words = len(name_words) >= 3

        if not has_causal_word and not has_three_words:
            return FundamentalityResult(
                valid=False,
                reason=(
                    f"GENUS '{name}' lacks causal explanation — "
                    f"add a causal indicator word (e.g. 'retrieval', 'detection', 'formation') "
                    f"or use >= 3 words to imply causal structure"
                ),
                genus_name=name,
                instance_count=instance_count,
            )

        return FundamentalityResult(
            valid=True,
            reason=f"GENUS '{name}' satisfies fundamentality ({instance_count} instances, causal structure present)",
            genus_name=name,
            instance_count=instance_count,
        )

    def reload_config(self) -> None:
        """Reload causal_indicator_words from config. Useful in tests."""
        self._causal_words = _load_causal_words()
