"""Shared RxPY operator utilities for OPE pipeline.

Provides reusable observable factories and helpers used across
embedder, runner, and stream processor adoptions (Phase 27).

Exports:
    create_work_observable: Factory for wrapping sync work in an observable
"""

from __future__ import annotations

from typing import Any, Callable

import reactivex as rx
from reactivex import Observable
from reactivex.disposable import Disposable


def create_work_observable(
    work_fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> Observable:
    """Create a cold observable that executes a sync function and emits its result.

    The work function runs when subscribed (cold). On success, emits the
    result and completes. On exception, calls on_error.

    Args:
        work_fn: Synchronous callable to execute.
        *args: Positional arguments passed to work_fn.
        **kwargs: Keyword arguments passed to work_fn.

    Returns:
        Observable that emits one item (the result) then completes.
    """

    def subscribe(observer, scheduler=None):
        try:
            result = work_fn(*args, **kwargs)
            observer.on_next(result)
            observer.on_completed()
        except Exception as e:
            observer.on_error(e)
        return Disposable()

    return rx.create(subscribe)
