# Executor & Concurrency

VorteExecutor provides work-stealing thread pool execution with optional Rust scheduler integration for transparent sync/async dispatch.

## VorteExecutor

```python
from vorte import VorteExecutor

executor = VorteExecutor(max_workers=8)

# Properties
print(executor.pool_size)    # Number of threads (default: cpu_count * 4)
print(executor.active_jobs)  # Current in-flight tasks
```

### Running Functions

```python
# Async functions are awaited directly
result = await executor.run(async_fetch_data, url="...")

# Sync functions run in the thread pool
result = await executor.run(cpu_intensive_compute, data=[...])

# With timeout (raises TimeoutError)
result = await executor.run_with_timeout(slow_function, timeout=30.0)
```

### Background Jobs

```python
# Fire-and-forget execution
executor.submit_background(send_email, to="user@example.com", subject="Welcome")

# With priority
executor.submit_background(cleanup_task, priority="low")
executor.submit_background(urgent_task, priority="critical")
```

Priority levels: `critical`, `high`, `normal` (default), `low`

### Scheduler Stats

When the Rust scheduler is available:

```python
stats = executor.scheduler_stats
# Returns: {"queue_depth": 5, "active_workers": 3, "completed": 100}
```

### Shutdown

```python
executor.shutdown(wait=True)  # Wait for all jobs to complete
```

## safe_route Decorator

Transparently handles sync and async route handlers:

```python
from vorte import safe_route

# Sync function - automatically wrapped for async dispatch
@safe_route
def get_data():
    result = expensive_computation()
    return result

# Async function - passed through unchanged
@safe_route
async def fetch_data():
    result = await api_client.get("/data")
    return result
```

The decorator:
- Detects if the function is async or sync
- Async functions are passed through unchanged
- Sync functions are wrapped to run in the VorteExecutor thread pool
- Marks the function with `_vorte_safe_route = True`
- Stores the original sync function in `_vorte_original_sync`

## Structured Concurrency

VorteTaskGroup provides structured concurrency that bridges Python asyncio with Rust/Tokio cancellation:

```python
from vorte import VorteTaskGroup

async def fetch_all():
    async with VorteTaskGroup() as tg:
        users = tg.create_task(fetch_users())
        orders = tg.create_task(fetch_orders())
        inventory = tg.create_task(fetch_inventory())

    # All tasks completed (or all cancelled if any failed)
    return {
        "users": users.result(),
        "orders": orders.result(),
        "inventory": inventory.result(),
    }
```

### Cancellation Propagation

When any task in a `VorteTaskGroup` fails:
1. All other tasks are cancelled immediately
2. The Rust cancellation token (`PyCancellationToken`) is triggered
3. This propagates to Rust/Tokio workers for cooperative cancellation
4. An `ExceptionGroup` is raised with all exceptions

```python
async with VorteTaskGroup() as tg:
    tg.create_task(risky_operation())   # If this fails...
    tg.create_task(other_work())        # ...this is cancelled
    tg.create_task(more_work())         # ...this too

    # Access the cancellation token
    token = tg.cancel_token  # PyCancellationToken for Rust interop
```

## Rust Executor Integration

When the native engine is available:

- **RustExecutor** -- Work-stealing pool implemented in Rust
- **TaskScheduler** -- Priority-based scheduler with configurable workers
- **PyCancellationToken** -- Cooperative cancellation bridge between Python and Rust

```python
from vorte._vorte_engine import RustExecutor, TaskScheduler, PyCancellationToken

scheduler = TaskScheduler()
scheduler.submit(task, priority="high")
stats = scheduler.stats()
```
