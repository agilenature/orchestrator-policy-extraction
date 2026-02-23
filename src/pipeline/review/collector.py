"""Interactive verdict collector for identification review.

Collects a binary verdict (accept/reject) and optional opinion from
the human reviewer via stdin. The input function is injectable for
test isolation.

Exports:
    VerdictCollector
"""

from __future__ import annotations

from typing import Callable, Optional

from src.pipeline.review.models import ReviewVerdict


class VerdictCollector:
    """Collects verdict and optional opinion interactively.

    Args:
        input_fn: Callable that prompts for user input. Defaults to
            builtin input(). Injectable for testing.
    """

    def __init__(self, input_fn: Callable[[str], str] = input):
        self._input = input_fn

    def collect(self) -> tuple[ReviewVerdict, Optional[str]]:
        """Prompt for verdict and optional opinion.

        Loops until a valid verdict is entered ('accept'/'a' or 'reject'/'r').
        Then prompts for an optional opinion (Enter to skip).

        Returns:
            Tuple of (verdict, opinion_or_None). Opinion is None if
            the reviewer pressed Enter without typing anything.
        """
        while True:
            raw = self._input("Your verdict [accept/reject]: ").strip().lower()
            if raw in ("accept", "a"):
                verdict = ReviewVerdict.ACCEPT
                break
            elif raw in ("reject", "r"):
                verdict = ReviewVerdict.REJECT
                break
            else:
                print("Please enter 'accept' or 'reject'.")

        opinion = self._input(
            "Your opinion (optional, press Enter to skip): "
        ).strip()
        return verdict, opinion or None
