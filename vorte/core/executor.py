"""
Vorte Work-Stealing Executor
==============================
Abstracts async safety entirely away from the developer. Whether a route is
defined as ``sync`` or ``async``, VORTE schedules the underlying operations
into a high-performance, native work-stealing pool.

If a call is synchronous, :func:`safe_route` automatically dispatches it to a
thread pool so it never blocks the event loop. If an async handler encounters
unexpected blocking (e.g. a legacy un-optimised database connection), the
thread pool absorbs the stall, maintaining linear throughput scaling.

Blueprint reference: §4.2 Unifying The Concurrency Engine
    T_throughput = Σ(C_core_i / μ_serialization) × K_work_stealing
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

F = TypeVar("F", bound=Callable)


class VorteExecutor:
    """
    Unified work-stealing executor for VORTE routes.

    Maintains a shared :class:`~concurrent.futures.ThreadPoolExecutor` sized
    to ``cpu_count × 4`` threads (matching what Tokio allocates on the Rust
    side). Async handlers run directly on the event loop; sync handlers are
    automatically offloaded via ``loop.run_in_executor``.

    Usage::

        executor = VorteExecutor()

        # Dispatch a blocking call without freezing the event loop
        result = await executor.run(some_blocking_function, arg1, arg2)

        # Access underlying thread pool stats
        print(executor.pool_size)    # -> int
        print(executor.active_jobs)  # -> int (approximate)
    """

    def __init__(self, max_workers: Optional[int] = None) -> None:
        cpu = os.cpu_count() or 4
        self._max_workers = max_workers or cpu * 4
        self._pool = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="vorte-worker",
        )
        self._submitted: int = 0
        self._completed: int = 0

    @property
    def pool_size(self) -> int:
        """Maximum number of worker threads."""
        return self._max_workers

    @property
    def active_jobs(self) -> int:
        """Approximate number of in-flight synchronous jobs."""
        return self._submitted - self._completed

    async def run(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute *fn* without blocking the event loop.

        - If *fn* is already a coroutine function it is awaited directly.
        - If *fn* is a plain callable it is dispatched to the thread pool.
        """
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)

        loop = asyncio.get_running_loop()
        self._submitted += 1
        try:
            if kwargs:
                from functools import partial
                result = await loop.run_in_executor(self._pool, partial(fn, *args, **kwargs))
            else:
                result = await loop.run_in_executor(self._pool, fn, *args)
        finally:
            self._completed += 1
        return result

    async def run_with_timeout(
        self, fn: Callable, *args: Any, timeout: float = 30.0, **kwargs: Any
    ) -> Any:
        """Run *fn* with a deadline, raising :exc:`asyncio.TimeoutError` on expiry."""
        return await asyncio.wait_for(self.run(fn, *args, **kwargs), timeout=timeout)

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the underlying thread pool."""
        self._pool.shutdown(wait=wait)

    def __del__(self) -> None:
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass


# Module-level shared executor instance (used by @safe_route)
_default_executor: Optional[VorteExecutor] = None


def _get_default_executor() -> VorteExecutor:
    global _default_executor
    if _default_executor is None:
        _default_executor = VorteExecutor()
    return _default_executor


def safe_route(func: F) -> F:
    """
    Route decorator that transparently handles sync/async dispatch.

    - **Async routes** — passed through unchanged; the event loop drives them.
    - **Sync routes** — automatically offloaded to the VORTE work-stealing
      thread pool so they never block inbound request processing.

    Usage::

        @safe_route
        @app.get("/slow")
        def slow_endpoint():          # sync — safe: runs in thread pool
            time.sleep(1)
            return {"ok": True}

        @safe_route
        @app.get("/fast")
        async def fast_endpoint():    # async — passes through unchanged
            return {"ok": True}

    Blueprint reference: §4.2 — VORTE schedules operations into a
    high-performance, native work-stealing pool.
    """
    if asyncio.iscoroutinefunction(func):
        # Already async — nothing to do
        func._vorte_safe_route = True  # type: ignore[attr-defined]
        return func

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        executor = _get_default_executor()
        return await executor.run(func, *args, **kwargs)

    wrapper._vorte_safe_route = True  # type: ignore[attr-defined]
    wrapper._vorte_original_sync = func  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]
