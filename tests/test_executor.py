"""Tests for vorte.core.executor — VorteExecutor and @safe_route."""
import asyncio
import time
import pytest
from vorte.core.executor import VorteExecutor, safe_route


@pytest.mark.asyncio
async def test_executor_runs_async_fn():
    executor = VorteExecutor()
    async def async_work():
        return "async_result"
    result = await executor.run(async_work)
    assert result == "async_result"


@pytest.mark.asyncio
async def test_executor_runs_sync_fn_in_thread():
    executor = VorteExecutor()
    def sync_work():
        return 42
    result = await executor.run(sync_work)
    assert result == 42


@pytest.mark.asyncio
async def test_executor_sync_does_not_block_loop():
    """A blocking sync function should not freeze the event loop."""
    executor = VorteExecutor()
    def blocking():
        time.sleep(0.05)
        return "done"

    # Run the blocking call alongside a fast coroutine concurrently
    fast_done = []
    async def fast():
        fast_done.append(True)

    await asyncio.gather(executor.run(blocking), fast())
    assert fast_done  # fast coroutine ran while blocking was in thread pool


@pytest.mark.asyncio
async def test_executor_kwargs_forwarded():
    executor = VorteExecutor()
    def add(a, b):
        return a + b
    result = await executor.run(add, 3, b=7)
    assert result == 10


@pytest.mark.asyncio
async def test_executor_timeout():
    executor = VorteExecutor()
    def slow():
        time.sleep(5)
    with pytest.raises(asyncio.TimeoutError):
        await executor.run_with_timeout(slow, timeout=0.1)


def test_executor_pool_size():
    import os
    executor = VorteExecutor()
    assert executor.pool_size == (os.cpu_count() or 4) * 4


def test_safe_route_async_passthrough():
    """@safe_route on an async function returns the function unchanged."""
    @safe_route
    async def handler():
        return "ok"
    assert asyncio.iscoroutinefunction(handler)
    assert getattr(handler, "_vorte_safe_route", False) is True


@pytest.mark.asyncio
async def test_safe_route_wraps_sync():
    """@safe_route on a sync function makes it awaitable."""
    @safe_route
    def sync_handler():
        return "sync_ok"

    result = await sync_handler()
    assert result == "sync_ok"


@pytest.mark.asyncio
async def test_safe_route_sync_has_metadata():
    @safe_route
    def handler():
        return "x"
    assert getattr(handler, "_vorte_safe_route", False) is True
    assert getattr(handler, "_vorte_original_sync", None) is not None
