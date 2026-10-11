"""Background execution of ingestion jobs."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any


class JobRunner:
    """Runs jobs on one worker thread, or inline when ``synchronous`` is set (used by tests)."""

    def __init__(self, synchronous: bool = False) -> None:
        self._executor = None if synchronous else ThreadPoolExecutor(max_workers=1)

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        """Run ``fn(*args, **kwargs)`` and return a future for its result.

        In synchronous mode the call completes before ``submit`` returns, and any exception
        propagates to the caller.
        """
        if self._executor is None:
            done: Future[Any] = Future()
            done.set_result(fn(*args, **kwargs))
            return done
        return self._executor.submit(fn, *args, **kwargs)
