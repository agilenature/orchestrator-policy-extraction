"""Shadow mode testing framework for RAG recommendation validation.

Runs leave-one-out batch evaluation over historical episodes, comparing
RAG recommendations against actual human decisions to compute agreement
metrics and flag dangerous recommendations.

Exports:
    ShadowEvaluator: Compare recommendation against actual human decision
    ShadowModeRunner: Run shadow mode testing in batch over historical episodes
"""

from __future__ import annotations

from src.pipeline.shadow.evaluator import ShadowEvaluator
from src.pipeline.shadow.runner import ShadowModeRunner

__all__ = [
    "ShadowEvaluator",
    "ShadowModeRunner",
]
