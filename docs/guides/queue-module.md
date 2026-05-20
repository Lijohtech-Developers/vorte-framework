# Queue Module

Background job processing with priorities, backpressure, dead letter queues, and retry logic.

## Setup

```python
from vorte import QueueModule

app.register(QueueModule())
```

## Configuration

```env
VORTE_QUEUE_DRIVER=redis
VORTE_QUEUE_DEFAULT_RETRIES=3
VORTE_QUEUE_DEFAULT_RETRY_DELAY=60
VORTE_QUEUE_CONCURRENCY=10
```

## Job Priorities

```python
from vorte.modules.queue import JobPriority

# Priority levels (higher = processed first):
# CRITICAL
# HIGH
# DEFAULT
# LOW
```

Jobs with higher priority are always dequeued before lower priority jobs.

## Features

### Priority Queue

Jobs are dequeued in priority order. A HIGH priority job will always be processed before a DEFAULT job, regardless of enqueue order.

### Backpressure & Watermarks

The queue monitors its fill level and transitions through states:

| State | Condition | Behavior |
|-------|-----------|----------|
| NORMAL | Below LWM | Accept all jobs |
| HIGH | Between LWM and HWM | Accept with warnings |
| FULL | At or above HWM | Reject with `QueueFullError` |

### Dead Letter Queue (DLQ)

Jobs that fail permanently (exhausted retries) are moved to the DLQ:

```python
# Failed jobs are automatically moved to DLQ
# Retrieve failed jobs
failed_jobs = queue.dlq.get_all()

# Retry from DLQ
queue.dlq.retry(job_id, reset_attempts=True)
```

### Retry Logic

```python
# Configurable retry with exponential backoff
# default_retries: 3 (configurable)
# default_retry_delay: 60 seconds (configurable)
```

### Worker Processing

```python
# Concurrent job execution with configurable concurrency
# Success/failure callbacks
# Worker statistics tracking
```

## Job Lifecycle

```
Enqueued -> Pending -> Running -> Completed
                      \-> Failed -> Retry -> Pending (up to max_retries)
                                          -> Dead Letter Queue
```

## Backends

- **Redis** (recommended for production) -- `VORTE_QUEUE_DRIVER=redis`
- **Memory** (development) -- `VORTE_QUEUE_DRIVER=memory`
