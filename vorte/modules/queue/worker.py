"""
Vorte Queue - Worker
=====================
Worker that processes jobs from one or more queues. Supports concurrent
processing, exponential backoff retries, timeout enforcement, and
graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from .job import Job, JobPayload, JobPriority, resolve_job_class

logger = logging.getLogger("vorte.queue.worker")


@dataclass
class WorkerStats:
    """Runtime statistics for a worker."""
    jobs_processed: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    jobs_retried: int = 0
    jobs_timed_out: int = 0
    start_time: float = field(default_factory=time.time)
    last_job_time: Optional[float] = None


class Worker:
    """
    Processes jobs from one or more queues.

    The worker polls the QueueManager for pending jobs, instantiates the
    appropriate Job subclass, and calls ``handle(**kwargs)``. Failed jobs
    are retried with exponential backoff up to the configured max attempts.

    Features:
        - Concurrent processing (configurable concurrency)
        - Exponential backoff on retries
        - Per-job timeout enforcement
        - Graceful shutdown (finish running jobs)
        - Error reporting via callbacks
        - Queue prioritization

    Args:
        queues: List of queue names to consume from.
        concurrency: Number of concurrent job processors.
        poll_interval: Seconds between queue polls when empty.
        on_job_success: Callback fired after a successful job.
        on_job_failure: Callback fired after a failed job (final failure).
        name: Human-readable worker name.

    Usage:
        worker = Worker(queues=["default", "emails"], concurrency=5)
        await worker.start()  # Blocks until shutdown
    """

    def __init__(
        self,
        queues: Optional[List[str]] = None,
        concurrency: int = 10,
        poll_interval: float = 1.0,
        on_job_success: Optional[Callable] = None,
        on_job_failure: Optional[Callable] = None,
        name: str = "worker-1",
    ):
        self._queues = set(queues) if queues else {"default"}
        self._concurrency = concurrency
        self._poll_interval = poll_interval
        self._on_job_success = on_job_success
        self._on_job_failure = on_job_failure
        self._name = name

        self._running = False
        self._stats = WorkerStats()
        self._active_jobs: Set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(concurrency)
        self._queue_manager: Optional[Any] = None  # Set during start()

    @property
    def stats(self) -> WorkerStats:
        """Get current worker statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Whether the worker is actively processing jobs."""
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, queue_manager: Any) -> None:
        """
        Start the worker and begin processing jobs.

        This method blocks until the worker is stopped via ``shutdown()``.

        Args:
            queue_manager: The QueueManager instance to pull jobs from.
        """
        self._queue_manager = queue_manager
        self._running = True
        self._stats = WorkerStats()

        logger.info(
            "Worker '%s' started (queues=%s, concurrency=%d)",
            self._name, self._queues, self._concurrency,
        )

        try:
            while self._running:
                await self._poll_and_process()
        except asyncio.CancelledError:
            logger.info("Worker '%s' cancelled", self._name)
        finally:
            # Wait for active jobs to finish
            if self._active_jobs:
                logger.info("Waiting for %d active jobs to finish...", len(self._active_jobs))
                await asyncio.gather(*self._active_jobs, return_exceptions=True)
            self._running = False
            logger.info("Worker '%s' stopped", self._name)

    async def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """
        Signal the worker to stop.

        Args:
            wait: If True, wait for active jobs to finish (up to timeout).
            timeout: Maximum seconds to wait for active jobs.
        """
        self._running = False
        logger.info("Worker '%s' shutting down...", self._name)

        if wait and self._active_jobs:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_jobs, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Worker '%s' timed out waiting for active jobs", self._name)
                for task in self._active_jobs:
                    task.cancel()

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    async def _poll_and_process(self) -> None:
        """Poll the queue and process available jobs."""
        if self._queue_manager is None:
            return

        try:
            # Try to dequeue a job from any of our queues
            job_payload = await self._queue_manager.dequeue(
                queues=list(self._queues),
            )

            if job_payload is not None:
                await self._semaphore.acquire()
                task = asyncio.create_task(self._process_job(job_payload))
                task.add_done_callback(self._on_task_done)
                self._active_jobs.add(task)
            else:
                # No jobs available — wait before polling again
                await asyncio.sleep(self._poll_interval)

        except Exception as exc:
            logger.error("Worker '%s' poll error: %s", self._name, exc)
            await asyncio.sleep(self._poll_interval)

    async def _process_job(self, payload: JobPayload) -> None:
        """
        Process a single job: resolve the class, call handle(), handle errors.

        Args:
            payload: The job payload to process.
        """
        self._stats.jobs_processed += 1

        # Resolve job class
        job_class = resolve_job_class(payload.class_name)
        if job_class is None:
            logger.error("Unknown job class: %s", payload.class_name)
            payload.status = "failed"
            payload.error = f"Unknown job class: {payload.class_name}"
            payload.failed_at = time.time()
            self._stats.jobs_failed += 1
            return

        # Instantiate
        job = job_class()

        # Update payload
        payload.status = "running"
        payload.started_at = time.time()
        payload.attempts += 1

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                job.handle(**payload.payload),
                timeout=payload.timeout,
            )

            payload.status = "completed"
            payload.completed_at = time.time()
            self._stats.jobs_succeeded += 1
            self._stats.last_job_time = time.time()

            logger.debug(
                "Job %s (%s) completed in %.2fs",
                payload.id, payload.class_name,
                payload.completed_at - payload.started_at,
            )

            if self._on_job_success:
                try:
                    if asyncio.iscoroutinefunction(self._on_job_success):
                        await self._on_job_success(payload, result)
                    else:
                        self._on_job_success(payload, result)
                except Exception:
                    pass

        except asyncio.TimeoutError:
            payload.status = "failed"
            payload.error = f"Job timed out after {payload.timeout}s"
            payload.failed_at = time.time()
            self._stats.jobs_timed_out += 1
            await self._handle_failure(payload)

        except Exception as exc:
            payload.error = f"{type(exc).__name__}: {str(exc)}"
            payload.failed_at = time.time()
            self._stats.jobs_failed += 1
            logger.error(
                "Job %s (%s) failed: %s\n%s",
                payload.id, payload.class_name, exc,
                traceback.format_exc(),
            )
            await self._handle_failure(payload)

    async def _handle_failure(self, payload: JobPayload) -> None:
        """
        Handle a failed job: retry if attempts remain, or mark as permanently failed.

        Uses exponential backoff: delay = retry_delay * 2^(attempts - 1).
        """
        if payload.attempts < payload.max_attempts:
            # Calculate exponential backoff
            backoff = payload.retry_delay * (2 ** (payload.attempts - 1))
            payload.status = "pending"
            payload.run_at = time.time() + backoff
            self._stats.jobs_retried += 1

            logger.info(
                "Retrying job %s in %ds (attempt %d/%d)",
                payload.id, backoff, payload.attempts, payload.max_attempts,
            )

            # Re-enqueue
            if self._queue_manager:
                await self._queue_manager.enqueue_raw(payload)
        else:
            # Permanent failure
            payload.status = "failed"
            logger.error(
                "Job %s (%s) permanently failed after %d attempts: %s",
                payload.id, payload.class_name, payload.attempts, payload.error,
            )

            if self._on_job_failure:
                try:
                    if asyncio.iscoroutinefunction(self._on_job_failure):
                        await self._on_job_failure(payload)
                    else:
                        self._on_job_failure(payload)
                except Exception:
                    pass

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Callback when a processing task completes."""
        self._active_jobs.discard(task)
        self._semaphore.release()
        if task.exception():
            logger.debug("Task exception: %s", task.exception())
