"""
Vorte Queue - Cron Scheduler
==============================
Cron-based job scheduler that triggers jobs on a schedule.
Supports standard 5-field cron expressions and pre-defined intervals.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Type

from .job import Job, JobPayload, resolve_job_class

logger = logging.getLogger("vorte.queue.scheduler")

# Pre-defined interval names
_INTERVALS = {
    "every_minute": "* * * * *",
    "every_5_minutes": "*/5 * * * *",
    "every_10_minutes": "*/10 * * * *",
    "every_15_minutes": "*/15 * * * *",
    "every_30_minutes": "*/30 * * * *",
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "daily_midnight": "0 0 * * *",
    "weekly": "0 0 * * 0",
    "monthly": "0 0 1 * *",
    "yearly": "0 0 1 1 *",
}


@dataclass
class ScheduledJob:
    """A job registered for cron-based execution."""
    name: str
    job_class_name: str
    cron_expression: str
    payload: Dict[str, Any] = field(default_factory=dict)
    queue: str = "default"
    enabled: bool = True
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    run_count: int = 0
    last_error: Optional[str] = None


def _parse_cron_fields(expression: str) -> List[str]:
    """
    Parse a cron expression into its five fields.

    Supports both standard 5-field expressions and named intervals.
    Also accepts 6-field expressions (with seconds) by dropping the first field.

    Args:
        expression: Cron expression (e.g., ``"*/5 * * * *"``) or named interval.

    Returns:
        List of 5 cron fields: [minute, hour, day, month, weekday].

    Raises:
        ValueError: If the expression is invalid.
    """
    # Check named intervals
    if expression in _INTERVALS:
        return _parse_cron_fields(_INTERVALS[expression])

    fields = expression.strip().split()
    if len(fields) == 6:
        # Drop seconds field
        fields = fields[1:]
    if len(fields) != 5:
        raise ValueError(
            f"Invalid cron expression '{expression}': "
            f"expected 5 fields (min hour day month weekday), got {len(fields)}"
        )
    return fields


def _cron_matches_now(fields: List[str], now: Optional[datetime] = None) -> bool:
    """
    Check if a parsed cron expression matches the current time.

    Args:
        fields: 5-element list of cron field expressions.
        now: The datetime to check against (for testing). Defaults to now.

    Returns:
        True if the cron expression matches the current minute.
    """
    from datetime import datetime as _dt

    now = now or _dt.now()
    checks = [
        ("minute", fields[0], now.minute, 0, 59),
        ("hour", fields[1], now.hour, 0, 23),
        ("day", fields[2], now.day, 1, 31),
        ("month", fields[3], now.month, 1, 12),
        ("weekday", fields[4], now.weekday(), 0, 6),  # Monday=0 in Python
    ]

    for name, pattern, value, min_val, max_val in checks:
        if not _field_matches(pattern, value, min_val, max_val, name):
            return False
    return True


def _field_matches(pattern: str, value: int, min_val: int, max_val: int, field_name: str) -> bool:
    """Check if a single cron field pattern matches a value."""
    if pattern == "*":
        return True

    # Handle comma-separated values
    for part in pattern.split(","):
        part = part.strip()
        if "/" in part:
            # Step: e.g., "*/5" or "0-30/5"
            range_part, step_str = part.split("/", 1)
            step = int(step_str)
            if range_part == "*":
                range_start, range_end = min_val, max_val
            elif "-" in range_part:
                range_start, range_end = map(int, range_part.split("-", 1))
            else:
                range_start, range_end = int(range_part), max_val
            if value >= range_start and value <= range_end:
                return (value - range_start) % step == 0
        elif "-" in part:
            # Range: e.g., "1-5"
            start, end = map(int, part.split("-", 1))
            if start <= value <= end:
                return True
        elif part == str(value):
            return True

    return False


def _next_run_time(fields: List[str], after: Optional[float] = None) -> float:
    """
    Calculate the next run time for a cron expression.

    Args:
        fields: 5-element list of cron field expressions.
        after: Unix timestamp to search from. Defaults to now.

    Returns:
        Unix timestamp of the next matching minute.
    """
    from datetime import datetime as _dt, timedelta

    after_dt = _dt.fromtimestamp(after or time.time())
    # Start checking from the next minute
    candidate = after_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Brute-force search (max 1 year ahead)
    max_iterations = 525600  # minutes in a year
    for _ in range(max_iterations):
        if _cron_matches_now(fields, candidate):
            return candidate.timestamp()
        candidate += timedelta(minutes=1)

    raise ValueError("Could not find next run time within 1 year")


class Scheduler:
    """
    Cron-based job scheduler.

    Manages a collection of scheduled jobs and periodically checks
    if any are due for execution. When a job is due, it is dispatched
    to the queue for processing.

    Features:
        - Standard 5-field cron expressions
        - Named intervals (every_minute, hourly, daily, etc.)
        - Enable/disable individual schedules
        - Next-run calculation
        - Dynamic schedule management at runtime

    Args:
        check_interval: Seconds between schedule checks.
        timezone: Optional timezone string (currently informational).

    Usage:
        scheduler = Scheduler()
        scheduler.add_job("cleanup", "app.jobs.CleanupJob", "*/5 * * * *")
        scheduler.add_job("report", MyReportJob, "daily")
        await scheduler.start(queue_manager)
    """

    def __init__(
        self,
        check_interval: float = 60.0,
        timezone: Optional[str] = None,
    ):
        self._check_interval = check_interval
        self._timezone = timezone
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._queue_manager: Optional[Any] = None

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(
        self,
        name: str,
        job_class: Any,
        cron_expression: str,
        payload: Optional[Dict[str, Any]] = None,
        queue: str = "default",
        enabled: bool = True,
    ) -> ScheduledJob:
        """
        Register a job for scheduled execution.

        Args:
            name: Unique schedule name.
            job_class: A Job subclass or its fully-qualified class name string.
            cron_expression: Cron expression or named interval.
            payload: Default kwargs to pass to the job's ``handle()`` method.
            queue: Queue name for dispatched jobs.
            enabled: Whether the schedule is initially enabled.

        Returns:
            The ScheduledJob instance.
        """
        if isinstance(job_class, type) and issubclass(job_class, Job):
            class_name = job_class.get_class_name()
        else:
            class_name = str(job_class)

        # Parse and validate cron expression
        try:
            fields = _parse_cron_fields(cron_expression)
        except ValueError as exc:
            raise ValueError(f"Invalid cron expression for job '{name}': {exc}") from exc

        scheduled = ScheduledJob(
            name=name,
            job_class_name=class_name,
            cron_expression=cron_expression,
            payload=payload or {},
            queue=queue,
            enabled=enabled,
        )

        # Calculate initial next_run
        try:
            scheduled.next_run = _next_run_time(fields)
        except ValueError:
            pass

        self._jobs[name] = scheduled
        logger.info("Scheduled job '%s' (%s) with cron '%s'", name, class_name, cron_expression)
        return scheduled

    def remove_job(self, name: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            name: Schedule name to remove.

        Returns:
            True if the job was found and removed.
        """
        return self._jobs.pop(name, None) is not None

    def enable_job(self, name: str) -> bool:
        """Enable a scheduled job. Returns True if the job exists."""
        job = self._jobs.get(name)
        if job:
            job.enabled = True
            return True
        return False

    def disable_job(self, name: str) -> bool:
        """Disable a scheduled job. Returns True if the job exists."""
        job = self._jobs.get(name)
        if job:
            job.enabled = False
            return True
        return False

    def get_job(self, name: str) -> Optional[ScheduledJob]:
        """Get a scheduled job by name."""
        return self._jobs.get(name)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all scheduled jobs with their metadata."""
        return [
            {
                "name": job.name,
                "job_class": job.job_class_name,
                "cron": job.cron_expression,
                "enabled": job.enabled,
                "last_run": job.last_run,
                "next_run": job.next_run,
                "run_count": job.run_count,
                "last_error": job.last_error,
            }
            for job in self._jobs.values()
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, queue_manager: Any) -> None:
        """
        Start the scheduler.

        Begins an async loop that checks for due jobs every ``check_interval`` seconds.

        Args:
            queue_manager: The QueueManager to dispatch jobs through.
        """
        self._queue_manager = queue_manager
        self._running = True
        logger.info("Scheduler started with %d jobs", len(self._jobs))

        try:
            while self._running:
                await self._check_schedules()
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _check_schedules(self) -> None:
        """Check all scheduled jobs and dispatch those that are due."""
        now = time.time()

        for job in self._jobs.values():
            if not job.enabled:
                continue
            if job.next_run is None:
                continue

            if now >= job.next_run:
                await self._dispatch_scheduled_job(job)

    async def _dispatch_scheduled_job(self, job: ScheduledJob) -> None:
        """Dispatch a scheduled job to the queue."""
        try:
            if self._queue_manager is None:
                logger.error("Cannot dispatch job '%s': no queue manager", job.name)
                return

            # Build a JobPayload
            payload = JobPayload(
                class_name=job.job_class_name,
                queue=job.queue,
                payload=job.payload,
            )

            await self._queue_manager.enqueue_raw(payload)

            job.last_run = time.time()
            job.run_count += 1

            # Update next_run
            try:
                fields = _parse_cron_fields(job.cron_expression)
                job.next_run = _next_run_time(fields, after=job.last_run)
            except ValueError:
                job.next_run = None

            logger.debug("Scheduled job '%s' dispatched (run #%d)", job.name, job.run_count)

        except Exception as exc:
            job.last_error = str(exc)
            logger.error("Error dispatching scheduled job '%s': %s", job.name, exc)
